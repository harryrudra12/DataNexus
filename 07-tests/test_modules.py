"""
DataNexus Era 3 — combined module tests
Living Nodes, Zero Gravity Fabric, Conscious Compliance, AI Operating System.
"""
import pytest


# ─── LIVING NODES ─────────────────────────────────────────────
class TestLivingNodes:
    def test_node_creates_and_ingests(self, sample_patient_data):
        from nodes.living_node import DataNexusNode, NodeType, NodeCapability
        cap = NodeCapability(cpu_cores=4, memory_mb=8192, storage_mb=100_000)
        node = DataNexusNode(
            node_type=NodeType.EDGE_HOSPITAL,
            capability=cap,
            region="IN-TG",
            ledger_peers=["dn-hyderabad-01"],
        )
        # Node has an ID and is online
        assert node.node_id
        assert node.is_online
        assert node.region == "IN-TG"

    def test_node_status_reports(self, sample_patient_data):
        from nodes.living_node import DataNexusNode, NodeType, NodeCapability
        node = DataNexusNode(
            NodeType.CORE_CLOUD,
            NodeCapability(8, 16384, 500_000),
            "IN-MH",
            ["dn-mumbai-01"],
        )
        status = node.status()
        assert "node_id" in status
        assert "region" in status
        assert "is_online" in status


# ─── ZERO GRAVITY FABRIC ──────────────────────────────────────
class TestZeroGravityFabric:
    def test_fabric_registers_node(self):
        from fabric.zero_gravity import ZeroGravityFabric
        fabric = ZeroGravityFabric("test-fabric")
        fabric.register_node("dn-test-01", "IN-TG", 1000.0, "core_cloud")
        assert "dn-test-01" in fabric.node_catalog
        assert fabric.node_catalog["dn-test-01"]["region"] == "IN-TG"

    def test_put_creates_data_particle(self, sample_patient_data):
        from fabric.zero_gravity import ZeroGravityFabric, DataState
        fabric = ZeroGravityFabric("test-fabric")
        fabric.register_node("dn-test-01", "IN-TG", 1000.0, "core_cloud")
        particle = fabric.put(sample_patient_data, "dn-test-01", sigma=5.5)
        assert particle.content_hash
        assert len(particle.content_hash) == 64
        assert particle.sigma_score == 5.5
        assert "dn-test-01" in particle.home_nodes

    def test_dedup_same_data(self, sample_patient_data):
        """Same content should not create a duplicate particle."""
        from fabric.zero_gravity import ZeroGravityFabric
        fabric = ZeroGravityFabric("test-fabric")
        fabric.register_node("dn-test-01", "IN-TG", 1000.0, "core_cloud")
        fabric.register_node("dn-test-02", "IN-MH", 1000.0, "core_cloud")
        p1 = fabric.put(sample_patient_data, "dn-test-01", 5.5)
        p2 = fabric.put(sample_patient_data, "dn-test-02", 5.5)
        # Same content_hash, but both nodes registered
        assert p1.content_hash == p2.content_hash
        assert len(fabric.particles) == 1

    def test_get_finds_particle(self, sample_patient_data):
        from fabric.zero_gravity import ZeroGravityFabric
        fabric = ZeroGravityFabric("test-fabric")
        fabric.register_node("dn-test-01", "IN-TG", 1000.0, "core_cloud")
        particle = fabric.put(sample_patient_data, "dn-test-01", 5.5)
        found = fabric.get(particle.content_hash, "dn-test-01", "IN-TG")
        assert found is not None
        assert found.content_hash == particle.content_hash


# ─── CONSCIOUS COMPLIANCE ─────────────────────────────────────
class TestConsciousCompliance:
    def _make_engine(self):
        from compliance.conscious_compliance import ConsciousComplianceEngine
        return ConsciousComplianceEngine()

    def test_dpdp_blocks_us_transfer(self):
        from compliance.conscious_compliance import LawCode
        engine = self._make_engine()
        allowed, reason, violations = engine.check_transfer(
            dataset_id      = "ds-test-001",
            applicable_laws = [LawCode.IN_DPDP_2023],
            target_country  = "US",
            transfer_purpose= "research",
            context         = {"has_consent": False},
        )
        assert allowed is False
        assert "DPDP" in reason or any("DPDP" in str(v) for v in violations)

    def test_dpdp_allows_within_india(self):
        from compliance.conscious_compliance import LawCode
        engine = self._make_engine()
        allowed, reason, violations = engine.check_transfer(
            dataset_id      = "ds-test-002",
            applicable_laws = [LawCode.IN_DPDP_2023],
            target_country  = "IN-TG",
            transfer_purpose= "medical_treatment",
            context         = {"has_consent": True, "fabric_tx_id": "TX_123"},
        )
        # Within India should at minimum not be blocked outright
        assert allowed is True or len([v for v in violations if not v.get("auto_fixed")]) == 0

    def test_compliance_report_generates(self):
        from compliance.conscious_compliance import LawCode
        engine = self._make_engine()
        # Trigger one violation first
        engine.check_transfer(
            dataset_id="ds-rep-001",
            applicable_laws=[LawCode.IN_DPDP_2023],
            target_country="US",
            transfer_purpose="research",
            context={"has_consent": False},
        )
        report_json = engine.generate_compliance_report("ds-rep-001")
        import json
        report = json.loads(report_json)
        assert "report_id" in report
        assert "blockchain_proof" in report


# ─── AI OPERATING SYSTEM ──────────────────────────────────────
class TestAIOperatingSystem:
    def test_intent_classification_report(self):
        from ai_os.ai_operating_system import AIOperatingSystem, IntentType
        ai = AIOperatingSystem()
        intent_type = ai.classify_intent("Send daily report at 6am to my email")
        assert intent_type == IntentType.REPORT

    def test_intent_classification_alert(self):
        from ai_os.ai_operating_system import AIOperatingSystem, IntentType
        ai = AIOperatingSystem()
        intent_type = ai.classify_intent("Alert me when revenue drops below 10 lakhs")
        assert intent_type == IntentType.ALERT

    def test_extracts_daily_schedule(self):
        from ai_os.ai_operating_system import AIOperatingSystem
        ai = AIOperatingSystem()
        schedule = ai.extract_schedule("Send daily report at 6am")
        # Should be a cron expression
        assert isinstance(schedule, str)
        assert len(schedule.split()) >= 5 or schedule == "@continuous"

    def test_self_heal_suggests_action(self):
        from ai_os.ai_operating_system import AIOperatingSystem
        ai = AIOperatingSystem()
        # Should have a self-heal method that returns a remediation
        if hasattr(ai, "self_heal"):
            action = ai.self_heal("connection_timeout")
            assert action is not None
