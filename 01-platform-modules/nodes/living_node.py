"""
DataNexus Era 3 — Living Data Node
Runs on any device: phone, IoT sensor, satellite, hospital machine.
Turns every device into a DataNexus fabric node.
"""
import asyncio, hashlib, json, time, uuid, socket
from dataclasses import dataclass, field
from typing import Optional, List, Callable
from enum import Enum

class NodeType(Enum):
    EDGE_IOT      = "edge_iot"       # sensors, meters
    EDGE_MOBILE   = "edge_mobile"    # phones, tablets
    EDGE_SATELLITE= "edge_satellite" # orbital nodes
    EDGE_HOSPITAL = "edge_hospital"  # medical devices
    CORE_CLOUD    = "core_cloud"     # cloud VMs
    CORE_ONPREM   = "core_onprem"    # on-premises servers

@dataclass
class NodeCapability:
    cpu_cores:     int
    ram_mb:        int
    storage_mb:    int
    has_gpu:       bool = False
    has_tee:       bool = False  # Trusted Execution Environment
    network_mbps:  float = 10.0
    battery_pct:   Optional[float] = None  # None = plugged in

@dataclass
class FabricMessage:
    msg_id:       str = field(default_factory=lambda: str(uuid.uuid4()))
    sender_id:    str = ""
    receiver_id:  str = ""
    msg_type:     str = ""   # DATA | QUERY | HEAL | HEARTBEAT | LINEAGE
    payload:      dict = field(default_factory=dict)
    timestamp:    float = field(default_factory=time.time)
    signature:    str = ""   # SHA-256 of payload + node private key

    def sign(self, node_key: str):
        raw = json.dumps(self.payload, sort_keys=True) + node_key
        self.signature = hashlib.sha256(raw.encode()).hexdigest()

    def verify(self, node_key: str) -> bool:
        raw = json.dumps(self.payload, sort_keys=True) + node_key
        return self.signature == hashlib.sha256(raw.encode()).hexdigest()


class DataNexusNode:
    """
    A living data node — can run on a Raspberry Pi, phone, server, or satellite.
    Speaks the DataNexus fabric protocol.
    Runs Kafka-lite ingestion, Spark Micro inference, and Hyperledger logging.
    """

    def __init__(
        self,
        node_type:    NodeType,
        capability:   NodeCapability,
        region:       str,           # e.g. "IN-TG" for Telangana
        fabric_peers: List[str],     # peer node addresses
        private_key:  str = "",
    ):
        self.node_id      = f"dn-node-{uuid.uuid4().hex[:8]}"
        self.node_type    = node_type
        self.capability   = capability
        self.region       = region
        self.fabric_peers = fabric_peers
        self.private_key  = private_key or hashlib.sha256(
            self.node_id.encode()).hexdigest()

        self.is_online    = True
        self.data_store   = {}       # local content-addressed store
        self.pipeline_q   = asyncio.Queue()
        self.heal_log     = []
        self.sigma_scores = {}
        self.peer_health  = {p: True for p in fabric_peers}

        self._handlers: dict[str, Callable] = {}
        self._register_handlers()
        print(f"[NODE] {self.node_id} online | type={node_type.value} | region={region}")

    def _register_handlers(self):
        self._handlers = {
            "DATA":      self._handle_data,
            "QUERY":     self._handle_query,
            "HEAL":      self._handle_heal,
            "HEARTBEAT": self._handle_heartbeat,
            "LINEAGE":   self._handle_lineage,
        }

    # ── INGESTION (Kafka-lite) ────────────────────────────────
    async def ingest(self, source_id: str, raw_data: bytes,
                     topic: str = "datanexus.raw") -> str:
        """Accept data from any source. Validate. Store. Propagate."""
        content_hash = hashlib.sha256(raw_data).hexdigest()

        # Quality check before accepting
        quality_ok, sigma = self._run_quality_check(raw_data, topic)
        if not quality_ok:
            print(f"[NODE] QUARANTINE: {content_hash[:8]} sigma={sigma:.1f} < 4.5")
            return f"QUARANTINED:{content_hash}"

        # Store locally (content-addressed)
        self.data_store[content_hash] = {
            "data":       raw_data,
            "source":     source_id,
            "topic":      topic,
            "ingested_at":time.time(),
            "sigma":      sigma,
            "region":     self.region,
        }

        # Log to Hyperledger Fabric (async, non-blocking)
        asyncio.create_task(self._log_to_fabric(
            "INGEST", content_hash, source_id, sigma))

        # Propagate to fabric peers if capacity allows
        if self._has_capacity():
            asyncio.create_task(self._propagate(content_hash, raw_data, topic))

        self.sigma_scores[content_hash] = sigma
        print(f"[NODE] Ingested {content_hash[:8]}... sigma={sigma:.1f} topic={topic}")
        return content_hash

    # ── SPARK MICRO INFERENCE ────────────────────────────────
    def _run_quality_check(self, data: bytes, topic: str) -> tuple[bool, float]:
        """
        Lightweight Great Expectations check at the edge.
        Full Spark MLlib runs at core nodes. Edge runs heuristics.
        """
        if len(data) == 0:
            return False, 1.0

        # Heuristic sigma estimation from data characteristics
        null_ratio = data.count(b',,' ) / max(len(data), 1)
        size_ok    = 100 < len(data) < 10_000_000
        decodable  = True
        try:    data.decode('utf-8')
        except: decodable = False

        score = 6.0
        score -= null_ratio * 10
        if not size_ok:   score -= 1.0
        if not decodable: score -= 2.0
        sigma = max(1.0, min(6.0, score))
        return sigma >= 4.5, sigma

    def _has_capacity(self) -> bool:
        """Check if node has spare capacity for fabric propagation."""
        if self.capability.battery_pct is not None:
            if self.capability.battery_pct < 20:
                return False   # save battery on mobile nodes
        if self.capability.ram_mb < 256:
            return False       # too constrained for propagation
        return True

    # ── FABRIC MESSAGING ─────────────────────────────────────
    async def send(self, peer_addr: str, msg: FabricMessage):
        """Send a signed message to a peer node."""
        msg.sender_id = self.node_id
        msg.sign(self.private_key)
        # In production: WebSocket / gRPC / LoRa / satellite link
        print(f"[FABRIC] {self.node_id} → {peer_addr[:20]} | {msg.msg_type}")

    async def receive(self, msg: FabricMessage):
        """Receive and dispatch a fabric message."""
        handler = self._handlers.get(msg.msg_type)
        if handler:
            await handler(msg)

    async def _handle_data(self, msg: FabricMessage):
        content_hash = msg.payload.get("content_hash")
        raw_data     = msg.payload.get("data", b"")
        if isinstance(raw_data, str):
            raw_data = raw_data.encode()
        await self.ingest(msg.sender_id, raw_data, msg.payload.get("topic",""))
        print(f"[NODE] Received data {content_hash[:8] if content_hash else '?'} from {msg.sender_id[:12]}")

    async def _handle_query(self, msg: FabricMessage):
        query = msg.payload.get("query", "")
        # Route to local store first (data gravity principle)
        results = {k: v["sigma"] for k, v in self.data_store.items()
                   if query in str(v)}
        print(f"[NODE] Query '{query}' → {len(results)} local results")
        return results

    async def _handle_heal(self, msg: FabricMessage):
        """Self-healing: apply fix suggested by AI OS."""
        fix_type   = msg.payload.get("fix_type")
        target     = msg.payload.get("target")
        fix_action = msg.payload.get("action")
        self.heal_log.append({
            "at": time.time(), "fix": fix_type,
            "target": target,  "action": fix_action
        })
        print(f"[HEAL] Applied: {fix_type} on {target} → {fix_action}")

    async def _handle_heartbeat(self, msg: FabricMessage):
        self.peer_health[msg.sender_id] = True
        print(f"[FABRIC] Heartbeat from {msg.sender_id[:12]}")

    async def _handle_lineage(self, msg: FabricMessage):
        content_hash = msg.payload.get("content_hash")
        lineage_chain= msg.payload.get("chain", [])
        print(f"[LINEAGE] {content_hash[:8] if content_hash else '?'} → {len(lineage_chain)} hops")

    async def _propagate(self, content_hash: str, data: bytes, topic: str):
        """Propagate data to healthy peers (data gravity — move data to compute)."""
        healthy_peers = [p for p, ok in self.peer_health.items() if ok]
        for peer in healthy_peers[:3]:   # max 3 peers to control bandwidth
            msg = FabricMessage(
                receiver_id = peer,
                msg_type    = "DATA",
                payload     = {
                    "content_hash": content_hash,
                    "data":         data.decode('utf-8', errors='replace'),
                    "topic":        topic,
                    "origin_node":  self.node_id,
                    "origin_region":self.region,
                }
            )
            await self.send(peer, msg)

    async def _log_to_fabric(self, action: str, content_hash: str,
                              source: str, sigma: float):
        """Log to Hyperledger Fabric — every action, always."""
        fabric_entry = {
            "action":       action,
            "node_id":      self.node_id,
            "content_hash": content_hash,
            "source":       source,
            "sigma":        sigma,
            "region":       self.region,
            "timestamp":    time.time(),
        }
        # In production: peer chaincode invoke on Hyperledger Fabric
        tx_id = hashlib.sha256(
            json.dumps(fabric_entry, sort_keys=True).encode()
        ).hexdigest()
        print(f"[FABRIC] Logged to ledger: tx={tx_id[:16]}")

    # ── HEARTBEAT LOOP ────────────────────────────────────────
    async def heartbeat_loop(self, interval: float = 30.0):
        """Periodically ping peers — detect failures, trigger healing."""
        while self.is_online:
            for peer in self.fabric_peers:
                msg = FabricMessage(
                    receiver_id = peer,
                    msg_type    = "HEARTBEAT",
                    payload     = {
                        "node_id":  self.node_id,
                        "sigma_avg":sum(self.sigma_scores.values()) /
                                    max(len(self.sigma_scores), 1),
                        "data_count": len(self.data_store),
                        "region":   self.region,
                    }
                )
                await self.send(peer, msg)
            await asyncio.sleep(interval)

    def status(self) -> dict:
        return {
            "node_id":      self.node_id,
            "type":         self.node_type.value,
            "region":       self.region,
            "online":       self.is_online,
            "data_items":   len(self.data_store),
            "avg_sigma":    round(sum(self.sigma_scores.values()) /
                            max(len(self.sigma_scores), 1), 2),
            "heals_applied":len(self.heal_log),
            "peer_count":   len(self.fabric_peers),
        }


# ── DEMO ──────────────────────────────────────────────────────
async def demo():
    print("=== DataNexus Era 3 — Living Data Nodes Demo ===\n")

    # Create 3 nodes of different types
    hospital_node = DataNexusNode(
        node_type   = NodeType.EDGE_HOSPITAL,
        capability  = NodeCapability(cpu_cores=4, ram_mb=8192, storage_mb=512000),
        region      = "IN-TG",
        fabric_peers= ["dn-core-mumbai-01", "dn-core-delhi-01"],
    )

    factory_node = DataNexusNode(
        node_type   = NodeType.EDGE_IOT,
        capability  = NodeCapability(cpu_cores=1, ram_mb=512, storage_mb=4096,
                                     battery_pct=78.0),
        region      = "IN-AP",
        fabric_peers= ["dn-core-hyderabad-01"],
    )

    cloud_node = DataNexusNode(
        node_type   = NodeType.CORE_CLOUD,
        capability  = NodeCapability(cpu_cores=32, ram_mb=131072,
                                     storage_mb=10_000_000, has_gpu=True),
        region      = "IN",
        fabric_peers= ["dn-node-hospital", "dn-node-factory"],
    )

    print("\n--- Ingesting data at hospital node ---")
    h1 = await hospital_node.ingest(
        "ehr_system_01",
        b"patient_id,age,bp,glucose\nP001,45,120,95\nP002,62,140,110",
        "datanexus.health.vitals"
    )

    print("\n--- Ingesting IoT sensor data ---")
    f1 = await factory_node.ingest(
        "temp_sensor_line3",
        b"ts,temp_c,pressure_bar\n1704067200,72.3,1.8\n1704067260,73.1,1.9",
        "datanexus.manufacturing.sensors"
    )

    print("\n--- Empty data rejected by edge quality check ---")
    await hospital_node.ingest("bad_source", b"", "datanexus.health.vitals")

    print("\n--- Node status ---")
    for node in [hospital_node, factory_node, cloud_node]:
        s = node.status()
        print(f"  {s['node_id']} | {s['type']:15s} | {s['region']} | "
              f"items={s['data_items']} | σ={s['avg_sigma']}")

if __name__ == "__main__":
    asyncio.run(demo())
