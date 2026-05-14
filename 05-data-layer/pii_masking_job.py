"""
DataNexus Era 3 — Spark PII Masking Job
Production-grade PySpark pipeline that:
  1. Reads raw CSV from HDFS
  2. Runs Great Expectations quality checks (entry gate)
  3. Masks PII columns (Aadhaar, phone, email, name initials)
  4. Writes Parquet to HDFS curated zone
  5. Logs the transformation to Hyperledger Fabric
  6. Quarantines the dataset if sigma drops below 4.5

Run via:
  spark-submit \\
    --master yarn \\
    --deploy-mode cluster \\
    --conf spark.yarn.maxAppAttempts=2 \\
    pii_masking_job.py \\
      --input  hdfs:///datanexus/raw/patient_records/2025-05-07/ \\
      --output hdfs:///datanexus/curated/patient_records/ \\
      --pipeline-id patient_daily_pipeline \\
      --jurisdiction DPDP_2023,HIPAA \\
      --region IN-TG
"""
import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime

from pyspark.sql import SparkSession, DataFrame
from pyspark.sql.functions import (
    col, lit, sha2, concat_ws, when, length, regexp_replace,
    udf, current_timestamp, count as spark_count,
)
from pyspark.sql.types import StringType


# ─── PII MASKING UDFs ─────────────────────────────────────────
def mask_aadhaar(value):
    """Mask Aadhaar: keep last 4 digits, replace rest with X."""
    if value is None or len(str(value)) < 4:
        return None
    s = str(value).replace(" ", "").replace("-", "")
    if len(s) != 12 or not s.isdigit():
        return "INVALID_AADHAAR"
    return "XXXX-XXXX-" + s[-4:]


def mask_phone(value):
    """Mask phone: keep last 4 digits, replace rest with X."""
    if value is None:
        return None
    s = str(value).replace("+", "").replace("-", "").replace(" ", "")
    if len(s) < 8:
        return "INVALID_PHONE"
    return "X" * (len(s) - 4) + s[-4:]


def mask_email(value):
    """Mask email: keep first letter and domain. ravi@apollo.com → r***@apollo.com"""
    if value is None or "@" not in str(value):
        return None
    local, domain = str(value).split("@", 1)
    if len(local) <= 1:
        return "*@" + domain
    return local[0] + "***@" + domain


def mask_name(value):
    """Mask name: keep initials only. 'Ravi Kumar Sharma' → 'R. K. S.'"""
    if value is None:
        return None
    parts = str(value).split()
    return ". ".join(p[0].upper() for p in parts if p) + "."


mask_aadhaar_udf = udf(mask_aadhaar, StringType())
mask_phone_udf   = udf(mask_phone,   StringType())
mask_email_udf   = udf(mask_email,   StringType())
mask_name_udf    = udf(mask_name,    StringType())


# ─── QUALITY CHECKS (Great Expectations subset) ───────────────
class QualityCheck:
    """Lightweight quality check that returns a Six Sigma score."""

    def __init__(self, df: DataFrame, dataset_name: str):
        self.df = df
        self.dataset_name = dataset_name
        self.total_rows = df.count()
        self.results = []

    def check_not_null(self, column: str, threshold_pct: float = 99.0):
        """Expect column to have <1% nulls."""
        null_count = self.df.filter(col(column).isNull()).count()
        null_pct = (null_count / self.total_rows * 100) if self.total_rows else 0
        passed = null_pct <= (100 - threshold_pct)
        self.results.append({
            "check":   f"not_null({column})",
            "passed":  passed,
            "actual":  f"{null_pct:.2f}% nulls",
            "expected":f"<{100-threshold_pct:.1f}%",
        })
        return passed

    def check_unique(self, column: str):
        """Expect column values to be unique."""
        unique_count = self.df.select(column).distinct().count()
        passed = unique_count == self.total_rows
        self.results.append({
            "check":   f"unique({column})",
            "passed":  passed,
            "actual":  f"{unique_count}/{self.total_rows} unique",
            "expected":"100% unique",
        })
        return passed

    def check_pattern(self, column: str, pattern: str, threshold_pct: float = 95.0):
        """Expect column values to match a regex."""
        matching = self.df.filter(col(column).rlike(pattern)).count()
        match_pct = (matching / self.total_rows * 100) if self.total_rows else 0
        passed = match_pct >= threshold_pct
        self.results.append({
            "check":   f"pattern({column},{pattern[:20]})",
            "passed":  passed,
            "actual":  f"{match_pct:.1f}% match",
            "expected":f">={threshold_pct}%",
        })
        return passed

    def check_row_count_min(self, min_rows: int):
        passed = self.total_rows >= min_rows
        self.results.append({
            "check":   f"row_count >= {min_rows}",
            "passed":  passed,
            "actual":  f"{self.total_rows} rows",
            "expected":f">= {min_rows}",
        })
        return passed

    def compute_sigma(self) -> float:
        """Convert pass rate to Six Sigma score."""
        if not self.results:
            return 0.0
        passed = sum(1 for r in self.results if r["passed"])
        pass_rate = passed / len(self.results)
        # DPMO = (1 - pass_rate) * 1_000_000
        # Sigma table approximation
        if pass_rate >= 0.99999966: return 6.0
        if pass_rate >= 0.99999:    return 5.5
        if pass_rate >= 0.99977:    return 5.0
        if pass_rate >= 0.99865:    return 4.5
        if pass_rate >= 0.99379:    return 4.0
        if pass_rate >= 0.97725:    return 3.5
        if pass_rate >= 0.93319:    return 3.0
        return 2.0

    def report(self) -> dict:
        return {
            "dataset":      self.dataset_name,
            "total_rows":   self.total_rows,
            "checks_run":   len(self.results),
            "checks_passed":sum(1 for r in self.results if r["passed"]),
            "sigma_level":  self.compute_sigma(),
            "results":      self.results,
        }


# ─── HYPERLEDGER FABRIC LOGGING ───────────────────────────────
def log_to_fabric(record: dict, fabric_endpoint: str = None) -> str:
    """
    Log transformation to Hyperledger Fabric.
    In production: invokes the lineage chaincode via fabric-sdk-py.
    Here: simulates the call and returns a deterministic tx ID.
    """
    payload = json.dumps(record, sort_keys=True).encode()
    tx_id = "TX_" + hashlib.sha256(payload).hexdigest()[:24]

    if fabric_endpoint:
        # Production: actual fabric-sdk-py call
        try:
            import requests
            requests.post(
                f"{fabric_endpoint}/api/v1/ingest",
                json={
                    "dataset_name":   record["dataset_id"],
                    "data":           record["content_hash"],
                    "data_format":    "parquet",
                    "classification":"PII",
                    "jurisdictions": record["jurisdictions"],
                    "allowed_regions":[record["region"]],
                    "purpose":       "pii_masking_pipeline",
                    "pipeline_id":   record["pipeline_id"],
                },
                timeout=10,
            )
        except Exception as e:
            print(f"[WARN] Fabric logging failed (continuing): {e}", file=sys.stderr)

    print(f"[FABRIC] tx={tx_id} dataset={record['dataset_id']} sigma={record['sigma_level']}")
    return tx_id


# ─── MAIN PIPELINE ────────────────────────────────────────────
def run_pipeline(args):
    spark = (
        SparkSession.builder
        .appName(f"datanexus-pii-mask-{args.pipeline_id}")
        .config("spark.sql.adaptive.enabled", "true")
        .config("spark.sql.adaptive.coalescePartitions.enabled", "true")
        .config("spark.sql.parquet.compression.codec", "snappy")
        .config("spark.dynamicAllocation.enabled", "true")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    print(f"[PIPELINE] Starting {args.pipeline_id} run_id={args.run_id}")
    print(f"[PIPELINE] Input:  {args.input}")
    print(f"[PIPELINE] Output: {args.output}")

    start_time = time.time()

    # ─── Step 1: Read raw data ────────────────────────────
    raw_df = spark.read.option("header", True).csv(args.input)
    print(f"[PIPELINE] Loaded {raw_df.count():,} rows, {len(raw_df.columns)} columns")

    # ─── Step 2: Quality gate (entry) ──────────────────────
    print("[PIPELINE] Running entry quality checks...")
    entry_qc = QualityCheck(raw_df, f"{args.pipeline_id}_raw")
    entry_qc.check_row_count_min(1)

    # Check expected columns exist and are mostly populated
    expected_pii_cols = ["aadhaar", "phone", "email", "name"]
    for c in expected_pii_cols:
        if c in raw_df.columns:
            entry_qc.check_not_null(c, threshold_pct=95.0)

    entry_report = entry_qc.report()
    print(f"[QUALITY] Entry sigma: {entry_report['sigma_level']:.2f}σ "
          f"({entry_report['checks_passed']}/{entry_report['checks_run']} passed)")

    if entry_report["sigma_level"] < args.min_sigma:
        print(f"[QUARANTINE] Entry sigma {entry_report['sigma_level']:.2f}σ "
              f"below threshold {args.min_sigma}σ — quarantining")
        quarantine_path = args.output.rstrip("/") + f"/_quarantine/{args.run_id}/"
        raw_df.write.mode("overwrite").parquet(quarantine_path)
        log_to_fabric({
            "pipeline_id":   args.pipeline_id,
            "dataset_id":    f"{args.pipeline_id}_quarantine_{args.run_id}",
            "content_hash":  hashlib.sha256(args.run_id.encode()).hexdigest(),
            "transformation":"QUARANTINE",
            "sigma_level":   entry_report["sigma_level"],
            "jurisdictions": args.jurisdiction.split(","),
            "region":        args.region,
        }, fabric_endpoint=args.fabric_endpoint)
        spark.stop()
        sys.exit(2)

    # ─── Step 3: Apply PII masking ─────────────────────────
    print("[PIPELINE] Applying PII masking...")
    masked_df = raw_df

    if "aadhaar" in raw_df.columns:
        masked_df = masked_df.withColumn("aadhaar_masked", mask_aadhaar_udf(col("aadhaar"))) \
                              .drop("aadhaar")
    if "phone" in raw_df.columns:
        masked_df = masked_df.withColumn("phone_masked", mask_phone_udf(col("phone"))) \
                              .drop("phone")
    if "email" in raw_df.columns:
        masked_df = masked_df.withColumn("email_masked", mask_email_udf(col("email"))) \
                              .drop("email")
    if "name" in raw_df.columns:
        masked_df = masked_df.withColumn("name_initials", mask_name_udf(col("name"))) \
                              .drop("name")

    # Add lineage columns
    masked_df = masked_df.withColumn("dn_pipeline_id", lit(args.pipeline_id)) \
                         .withColumn("dn_run_id",      lit(args.run_id)) \
                         .withColumn("dn_processed_at", current_timestamp()) \
                         .withColumn("dn_region",      lit(args.region))

    # ─── Step 4: Quality gate (exit) ───────────────────────
    print("[PIPELINE] Running exit quality checks...")
    exit_qc = QualityCheck(masked_df, f"{args.pipeline_id}_masked")
    exit_qc.check_row_count_min(1)

    if "aadhaar_masked" in masked_df.columns:
        exit_qc.check_pattern("aadhaar_masked", r"^XXXX-XXXX-\d{4}$", 99.0)
    if "phone_masked" in masked_df.columns:
        exit_qc.check_pattern("phone_masked", r"^X+\d{4}$", 99.0)
    if "email_masked" in masked_df.columns:
        exit_qc.check_pattern("email_masked", r"^.+@.+\..+$", 95.0)

    exit_report = exit_qc.report()
    print(f"[QUALITY] Exit sigma: {exit_report['sigma_level']:.2f}σ "
          f"({exit_report['checks_passed']}/{exit_report['checks_run']} passed)")

    # ─── Step 5: Write Parquet ─────────────────────────────
    output_path = args.output.rstrip("/") + f"/run_id={args.run_id}/"
    print(f"[PIPELINE] Writing Parquet to {output_path}")
    masked_df.coalesce(args.output_files).write \
        .mode("overwrite") \
        .partitionBy("dn_region") \
        .parquet(output_path)

    output_count = masked_df.count()

    # ─── Step 6: Log to Hyperledger Fabric ─────────────────
    output_hash = hashlib.sha256(
        f"{args.pipeline_id}|{args.run_id}|{output_count}".encode()
    ).hexdigest()
    fabric_record = {
        "pipeline_id":       args.pipeline_id,
        "run_id":            args.run_id,
        "dataset_id":        f"{args.pipeline_id}_curated_{args.run_id}",
        "content_hash":      output_hash,
        "transformation":    "SPARK_PII_MASKING",
        "input_rows":        entry_report["total_rows"],
        "output_rows":       output_count,
        "sigma_level":       exit_report["sigma_level"],
        "entry_sigma":       entry_report["sigma_level"],
        "exit_sigma":        exit_report["sigma_level"],
        "jurisdictions":     args.jurisdiction.split(","),
        "region":            args.region,
        "duration_seconds":  round(time.time() - start_time, 2),
        "output_path":       output_path,
    }
    fabric_tx = log_to_fabric(fabric_record, fabric_endpoint=args.fabric_endpoint)
    fabric_record["fabric_tx_id"] = fabric_tx

    # Write the fabric record as a sidecar file
    sidecar_path = output_path + "_DATANEXUS_LINEAGE.json"
    spark.sparkContext.parallelize([json.dumps(fabric_record, indent=2)], 1) \
                      .saveAsTextFile(sidecar_path)

    # ─── Done ──────────────────────────────────────────────
    duration = time.time() - start_time
    print(f"[PIPELINE] ✓ Complete in {duration:.1f}s")
    print(f"[PIPELINE]   Input rows:    {entry_report['total_rows']:,}")
    print(f"[PIPELINE]   Output rows:   {output_count:,}")
    print(f"[PIPELINE]   Sigma level:   {exit_report['sigma_level']:.2f}σ")
    print(f"[PIPELINE]   Fabric TX:     {fabric_tx}")

    spark.stop()
    return 0


def parse_args():
    p = argparse.ArgumentParser(description="DataNexus PII masking Spark job")
    p.add_argument("--input",       required=True, help="HDFS path to raw CSV")
    p.add_argument("--output",      required=True, help="HDFS path for curated Parquet")
    p.add_argument("--pipeline-id", required=True, help="Pipeline identifier")
    p.add_argument("--run-id",      default=datetime.now().strftime("%Y%m%d_%H%M%S"))
    p.add_argument("--jurisdiction", default="DPDP_2023",
                   help="Comma-separated jurisdiction codes")
    p.add_argument("--region",      default="IN-TG", help="Data residency region")
    p.add_argument("--min-sigma",   type=float, default=4.5,
                   help="Minimum acceptable sigma — below this, dataset is quarantined")
    p.add_argument("--output-files",type=int, default=4,
                   help="Number of output Parquet files (controls partition count)")
    p.add_argument("--fabric-endpoint", default=os.getenv("DATANEXUS_API_URL", ""),
                   help="DataNexus API URL for Fabric logging")
    return p.parse_args()


if __name__ == "__main__":
    args = parse_args()
    sys.exit(run_pipeline(args))
