"""
DataNexus Era 3 — Configuration
Production configuration using Pydantic Settings.
All values from environment variables with sensible defaults for local dev.
"""
from functools import lru_cache
from typing import List, Optional
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Centralized configuration. Single source of truth for all env vars."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── App metadata ────────────────────────────────────────
    app_name:     str = "DataNexus API"
    app_version:  str = "3.0.0-era3"
    app_env:      str = Field(default="development", description="development|staging|production")
    debug:        bool = False

    # ─── Server ──────────────────────────────────────────────
    host:         str = "0.0.0.0"
    port:         int = 8000
    workers:      int = 4
    log_level:    str = "INFO"

    # ─── Auth ────────────────────────────────────────────────
    jwt_secret_key:        str = Field(
        default="CHANGE-ME-IN-PRODUCTION-USE-OPENSSL-RAND-HEX-32",
        description="HMAC key for JWT — MUST be 32+ bytes in production",
    )
    jwt_algorithm:         str = "HS256"
    jwt_access_ttl_minutes: int = 60
    api_key_header:        str = "X-DataNexus-API-Key"
    require_auth:          bool = True

    # ─── Hyperledger Fabric ──────────────────────────────────
    fabric_mode:           str = Field(
        default="simulation",
        description="simulation | production",
    )
    fabric_network_profile: Optional[str] = None
    fabric_channel_name:   str = "datanexus-channel"
    fabric_org_msp:        str = "Org1MSP"
    fabric_user_id:        str = "datanexus-app"

    # ─── Hadoop / HDFS ───────────────────────────────────────
    hdfs_namenode:         str = "namenode:9000"
    hdfs_default_replication: int = 3

    # ─── Kafka ───────────────────────────────────────────────
    kafka_brokers:         str = "kafka-1:29092,kafka-2:29093"
    kafka_security_protocol: str = "PLAINTEXT"
    kafka_topic_lineage:   str = "datanexus.lineage"
    kafka_topic_quality:   str = "datanexus.quality"
    kafka_topic_compliance: str = "datanexus.compliance"

    # ─── Presto / Trino ──────────────────────────────────────
    presto_host:           str = "presto"
    presto_port:           int = 8080
    presto_user:           str = "datanexus"
    presto_catalog:        str = "hive"
    presto_schema:         str = "datanexus"

    # ─── Atlas ───────────────────────────────────────────────
    atlas_url:             str = "http://atlas:21000"
    atlas_username:        str = "admin"
    atlas_password:        str = Field(default="admin", description="Override in production")

    # ─── IPFS ────────────────────────────────────────────────
    ipfs_api_url:          str = "http://ipfs:5001"
    ipfs_gateway_url:      str = "http://ipfs:8080"

    # ─── MLflow ──────────────────────────────────────────────
    mlflow_tracking_uri:   str = "http://mlflow:5000"

    # ─── Airflow ─────────────────────────────────────────────
    airflow_api_url:       str = "http://airflow-webserver:8080/api/v1"
    airflow_username:      str = "admin"
    airflow_password:      str = "datanexus"

    # ─── PostgreSQL (state, audit) ───────────────────────────
    postgres_dsn:          str = "postgresql+asyncpg://datanexus:datanexus@postgres:5432/datanexus"
    postgres_pool_size:    int = 20
    postgres_max_overflow: int = 10

    # ─── Redis (rate limiting, sessions, caching) ────────────
    redis_url:             str = "redis://redis:6379/0"

    # ─── CORS ────────────────────────────────────────────────
    cors_origins:          List[str] = ["http://localhost:3000", "http://localhost:8080"]

    # ─── Rate limiting ───────────────────────────────────────
    rate_limit_per_minute: int = 100
    rate_limit_burst:      int = 20

    # ─── Observability ───────────────────────────────────────
    metrics_enabled:       bool = True
    tracing_enabled:       bool = True
    sentry_dsn:            Optional[str] = None

    # ─── Six Sigma defaults ──────────────────────────────────
    sla_minimum_sigma:     float = 4.5
    sla_target_sigma:      float = 5.5
    quality_quarantine_threshold: float = 4.0

    # ─── Validators ──────────────────────────────────────────
    @field_validator("app_env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        valid = {"development", "staging", "production", "testing"}
        if v.lower() not in valid:
            raise ValueError(f"app_env must be one of {valid}, got {v}")
        return v.lower()

    @field_validator("fabric_mode")
    @classmethod
    def validate_fabric_mode(cls, v: str) -> str:
        if v.lower() not in {"simulation", "production"}:
            raise ValueError("fabric_mode must be 'simulation' or 'production'")
        return v.lower()

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str, info) -> str:
        # In production, refuse to start with the default key
        if info.data.get("app_env") == "production":
            if "CHANGE-ME" in v or len(v) < 32:
                raise ValueError(
                    "jwt_secret_key MUST be set to a secure 32+ byte value in production. "
                    "Generate with: openssl rand -hex 32"
                )
        return v

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache
def get_settings() -> Settings:
    """Cached settings — call this from anywhere in the app."""
    return Settings()
