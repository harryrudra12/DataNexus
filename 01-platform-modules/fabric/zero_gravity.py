"""
DataNexus Era 3 — Zero Gravity Data
Data has no fixed home. It flows to where compute needs it.
Content-addressed via IPFS. Location-independent via Iceberg.
Data gravity: data moves to compute, not compute to data.
"""
import hashlib, json, time, uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from enum import Enum

class DataState(Enum):
    FLOATING   = "floating"    # in fabric, no fixed location
    ANCHORED   = "anchored"    # pinned to a specific node
    MIGRATING  = "migrating"   # moving toward compute gravity
    REPLICATED = "replicated"  # copied to multiple nodes

@dataclass
class ComputeGravity:
    """Represents a compute workload pulling data toward it."""
    gravity_id:   str
    node_id:      str
    region:       str
    job_type:     str        # SPARK | PRESTO | FLINK | MLFLOW
    data_needs:   List[str]  # content hashes needed
    pull_strength:float      # 0.0 – 1.0, higher = pull data here
    created_at:   float = field(default_factory=time.time)

@dataclass
class DataParticle:
    """
    A unit of data in the Zero Gravity fabric.
    Identified by WHAT it is (content hash), not WHERE it lives.
    """
    content_hash:  str           # SHA-256 — this IS the address
    ipfs_cid:      str           # IPFS content identifier
    size_bytes:    int
    state:         DataState
    home_nodes:    List[str]     # nodes currently holding this data
    sigma_score:   float
    created_at:    float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count:  int = 0

    def nearest_node(self, requester_region: str) -> Optional[str]:
        """Find the home node nearest to the requester (latency-based)."""
        region_map = {
            "IN-TG": ["IN-TG", "IN-AP", "IN-MH", "IN"],
            "IN-MH": ["IN-MH", "IN-TG", "IN-KA", "IN"],
            "IN-AP": ["IN-AP", "IN-TG", "IN-KA", "IN"],
            "IN-KA": ["IN-KA", "IN-TG", "IN-MH", "IN"],
            "IN":    ["IN", "IN-TG", "IN-MH", "IN-AP"],
        }
        preference = region_map.get(requester_region, [requester_region, "IN"])
        for preferred in preference:
            for node in self.home_nodes:
                if preferred in node:
                    return node
        return self.home_nodes[0] if self.home_nodes else None


class ZeroGravityFabric:
    """
    The Zero Gravity Data Fabric.
    Data lives everywhere and nowhere simultaneously.
    Compute pulls data toward it. Data flows like water — downhill toward need.
    """

    def __init__(self, fabric_id: str = "datanexus-fabric-01"):
        self.fabric_id     = fabric_id
        self.particles:    Dict[str, DataParticle] = {}
        self.gravities:    Dict[str, ComputeGravity] = {}
        self.node_catalog: Dict[str, dict] = {}     # node_id → metadata
        self.movement_log: List[dict] = []
        self.ipfs_registry:Dict[str, str] = {}      # content_hash → ipfs_cid
        print(f"[FABRIC] Zero Gravity Fabric '{fabric_id}' initialized")

    def register_node(self, node_id: str, region: str,
                       capacity_gb: float, node_type: str):
        self.node_catalog[node_id] = {
            "region":      region,
            "capacity_gb": capacity_gb,
            "used_gb":     0.0,
            "node_type":   node_type,
            "online":      True,
        }
        print(f"[FABRIC] Node registered: {node_id} | {region} | {capacity_gb}GB")

    # ── PUT DATA INTO THE FABRIC ──────────────────────────────
    def put(self, raw_data: bytes, source_node: str,
             sigma: float = 5.0) -> DataParticle:
        """
        Add data to the fabric. Returns a DataParticle.
        Data is identified forever by its content hash — not its location.
        """
        content_hash = hashlib.sha256(raw_data).hexdigest()

        if content_hash in self.particles:
            # De-duplicate — same content already in fabric
            existing = self.particles[content_hash]
            if source_node not in existing.home_nodes:
                existing.home_nodes.append(source_node)
            print(f"[FABRIC] De-duplicated: {content_hash[:12]}... already in fabric")
            return existing

        # Generate fake IPFS CID (in production: actual ipfs add)
        ipfs_cid = "Qm" + hashlib.sha256(
            content_hash.encode()).hexdigest()[:44]

        particle = DataParticle(
            content_hash = content_hash,
            ipfs_cid     = ipfs_cid,
            size_bytes   = len(raw_data),
            state        = DataState.FLOATING,
            home_nodes   = [source_node],
            sigma_score  = sigma,
        )
        self.particles[content_hash] = particle
        self.ipfs_registry[content_hash] = ipfs_cid

        print(f"[FABRIC] Data entered fabric: {content_hash[:12]}..."
              f" | {len(raw_data)} bytes | node={source_node} | σ={sigma}")
        return particle

    # ── DATA GRAVITY ─────────────────────────────────────────
    def register_compute(self, node_id: str, region: str,
                          job_type: str, data_needs: List[str],
                          pull_strength: float = 1.0) -> ComputeGravity:
        """
        A compute job declares what data it needs.
        The fabric automatically pulls that data to the nearest available node.
        """
        gravity = ComputeGravity(
            gravity_id   = f"grav-{uuid.uuid4().hex[:8]}",
            node_id      = node_id,
            region       = region,
            job_type     = job_type,
            data_needs   = data_needs,
            pull_strength= pull_strength,
        )
        self.gravities[gravity.gravity_id] = gravity
        print(f"[GRAVITY] Compute registered: {job_type} @ {region}"
              f" needs {len(data_needs)} datasets")

        # Immediately resolve gravity — pull data to compute
        self._resolve_gravity(gravity)
        return gravity

    def _resolve_gravity(self, gravity: ComputeGravity):
        """
        Core data gravity algorithm.
        For each needed dataset, find if a copy is already near compute.
        If not, move/replicate the nearest copy toward compute.
        """
        for content_hash in gravity.data_needs:
            if content_hash not in self.particles:
                print(f"[GRAVITY] Dataset {content_hash[:12]}... not in fabric — skipping")
                continue

            particle = self.particles[content_hash]
            nearest  = particle.nearest_node(gravity.region)

            if nearest and gravity.region in (nearest or ""):
                print(f"[GRAVITY] {content_hash[:12]}... already near {gravity.region} — no move needed")
                particle.last_accessed = time.time()
                particle.access_count += 1
                continue

            # Need to move/replicate data toward compute
            self._pull_data(particle, gravity.node_id, gravity.region)

    def _pull_data(self, particle: DataParticle,
                    target_node: str, target_region: str):
        """Pull (replicate) data to the target node. Like water flowing downhill."""
        source_node = particle.home_nodes[0] if particle.home_nodes else "unknown"

        # Check target node has capacity
        target_meta = self.node_catalog.get(target_node, {})
        size_gb = particle.size_bytes / (1024**3)
        avail   = target_meta.get("capacity_gb", 0) - target_meta.get("used_gb", 0)

        if avail < size_gb:
            print(f"[GRAVITY] {target_node} insufficient capacity — data stays at {source_node}")
            return

        # Move data
        if target_node not in particle.home_nodes:
            particle.home_nodes.append(target_node)
        particle.state = DataState.MIGRATING

        # Update catalog
        if target_node in self.node_catalog:
            self.node_catalog[target_node]["used_gb"] += size_gb

        movement = {
            "move_id":       uuid.uuid4().hex[:8],
            "content_hash":  particle.content_hash,
            "ipfs_cid":      particle.ipfs_cid,
            "from_node":     source_node,
            "to_node":       target_node,
            "to_region":     target_region,
            "size_bytes":    particle.size_bytes,
            "moved_at":      time.time(),
            "reason":        "data_gravity",
        }
        self.movement_log.append(movement)
        particle.state = DataState.REPLICATED

        print(f"[GRAVITY] Pulled {particle.content_hash[:12]}..."
              f" from {source_node} → {target_node} ({target_region})"
              f" | {particle.size_bytes/1024:.1f}KB")

    # ── CONTENT-ADDRESSED GET ─────────────────────────────────
    def get(self, content_hash: str, requester_node: str,
             requester_region: str) -> Optional[DataParticle]:
        """
        Get data by what it IS (content hash), not where it lives.
        The fabric finds the nearest copy automatically.
        """
        particle = self.particles.get(content_hash)
        if not particle:
            return None

        # Log access
        particle.last_accessed = time.time()
        particle.access_count += 1

        nearest = particle.nearest_node(requester_region)
        print(f"[FABRIC] Get {content_hash[:12]}... | requester={requester_region}"
              f" | served from {nearest or 'unknown'}")

        # If no nearby copy, register gravity to pull it
        if nearest is None or requester_region not in (nearest or ""):
            self.register_compute(
                node_id      = requester_node,
                region       = requester_region,
                job_type     = "ON_DEMAND_FETCH",
                data_needs   = [content_hash],
                pull_strength= 0.8,
            )
        return particle

    # ── GARBAGE COLLECTION ────────────────────────────────────
    def gc(self, cold_threshold_days: float = 30.0):
        """
        Remove cold copies from overloaded nodes.
        Keep at least one copy of every dataset in the fabric.
        """
        cutoff = time.time() - (cold_threshold_days * 86400)
        removed_copies = 0
        for particle in self.particles.values():
            if (particle.last_accessed < cutoff
                    and len(particle.home_nodes) > 1
                    and particle.access_count < 3):
                # Remove from all but the first (origin) node
                cold_node = particle.home_nodes.pop()
                if cold_node in self.node_catalog:
                    self.node_catalog[cold_node]["used_gb"] -= (
                        particle.size_bytes / 1024**3)
                removed_copies += 1
                print(f"[GC] Evicted cold copy of {particle.content_hash[:12]}"
                      f"... from {cold_node}")
        print(f"[GC] Garbage collection complete: {removed_copies} cold copies removed")

    def fabric_status(self) -> dict:
        total_bytes  = sum(p.size_bytes for p in self.particles.values())
        total_nodes  = len(self.node_catalog)
        online_nodes = sum(1 for n in self.node_catalog.values() if n["online"])
        avg_sigma    = (sum(p.sigma_score for p in self.particles.values()) /
                        max(len(self.particles), 1))
        return {
            "fabric_id":       self.fabric_id,
            "total_datasets":  len(self.particles),
            "total_size_gb":   round(total_bytes / 1024**3, 4),
            "total_nodes":     total_nodes,
            "online_nodes":    online_nodes,
            "avg_sigma":       round(avg_sigma, 2),
            "total_movements": len(self.movement_log),
            "active_gravities":len(self.gravities),
        }


# ── DEMO ──────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=== DataNexus Era 3 — Zero Gravity Data Fabric Demo ===\n")

    fabric = ZeroGravityFabric("datanexus-india-01")

    # Register nodes across India
    nodes = [
        ("dn-hyderabad-01", "IN-TG", 50000.0, "core_cloud"),
        ("dn-mumbai-01",    "IN-MH", 80000.0, "core_cloud"),
        ("dn-delhi-01",     "IN-DL", 60000.0, "core_cloud"),
        ("dn-hospital-hyd", "IN-TG",   500.0, "edge_hospital"),
        ("dn-factory-ap",   "IN-AP",   128.0, "edge_iot"),
    ]
    print("--- Registering fabric nodes ---")
    for nid, region, cap, ntype in nodes:
        fabric.register_node(nid, region, cap, ntype)

    print("\n--- Adding data to the fabric ---")
    datasets = [
        (b"patient_id,age,bp\nP001,45,120\nP002,62,140",
         "dn-hospital-hyd", 5.9, "Patient vitals"),
        (b"ts,temp,pressure\n1704067200,72.3,1.8\n1704067260,73.1,1.9",
         "dn-factory-ap",   5.2, "Factory sensors"),
        (b"order_id,amount,region\nO001,45000,Hyderabad\nO002,82000,Mumbai",
         "dn-mumbai-01",    5.7, "Sales orders"),
    ]
    particles = []
    for data, node, sigma, label in datasets:
        print(f"\n  Adding: {label}")
        p = fabric.put(data, node, sigma)
        particles.append(p)

    print("\n--- Compute gravity: Spark job in Delhi needs all datasets ---")
    fabric.register_compute(
        node_id      = "dn-delhi-01",
        region       = "IN-DL",
        job_type     = "SPARK_BATCH",
        data_needs   = [p.content_hash for p in particles],
        pull_strength= 1.0,
    )

    print("\n--- Content-addressed retrieval (no paths, no buckets) ---")
    for p in particles:
        result = fabric.get(p.content_hash, "dn-delhi-01", "IN-DL")
        if result:
            print(f"  Found: {result.content_hash[:12]}... | σ={result.sigma_score}"
                  f" | copies={len(result.home_nodes)}")

    print("\n--- Deduplication: adding same patient data again ---")
    fabric.put(b"patient_id,age,bp\nP001,45,120\nP002,62,140",
               "dn-delhi-01", 5.9)

    print("\n--- Fabric status ---")
    s = fabric.fabric_status()
    for k, v in s.items():
        print(f"  {k}: {v}")
