import pytest

from neurosre.agents import monitor
from neurosre.agents.graph import DiagnosisOut, PlanOut, Step, TriageOut
from neurosre.agents.safety import assess_plan, check_step
from neurosre.cloud import FAULTS, KNOWN_FAULTS, CloudSimulator
from neurosre.engine import Engine
from neurosre.knowledge.store import KnowledgeBase


@pytest.fixture(scope="session")
def kb():
    return KnowledgeBase()


@pytest.fixture
def engine(kb, tmp_path):
    return Engine(provider="offline", seed=1, db_path=tmp_path / "t.db", kb=kb)


# ---------------------------------------------------------------- simulator
def test_fault_makes_service_unhealthy_and_correct_fix_recovers():
    c = CloudSimulator(seed=0)
    c.inject("memory_leak", "auth-service")
    assert not monitor.is_healthy("auth-service", c.snapshot()["auth-service"])[0]
    c.execute("restart_service", "auth-service")
    c.tick()
    assert monitor.is_healthy("auth-service", c.snapshot()["auth-service"])[0]


def test_wrong_or_partial_fix_does_not_recover():
    c = CloudSimulator(seed=0)
    c.inject("disk_full", "payment-service")
    c.execute("restart_service", "payment-service")      # wrong action
    c.execute("rotate_logs", "payment-service")          # only half of the runbook
    c.tick()
    assert "payment-service" in c.faults
    c.execute("clear_tmp", "payment-service")
    assert "payment-service" not in c.faults


def test_scale_needs_enough_replicas():
    c = CloudSimulator(seed=0)
    c.inject("high_cpu", "api-gateway")
    c.execute("scale_service", "api-gateway", {"replicas": 3})
    assert "api-gateway" in c.faults
    c.execute("scale_service", "api-gateway", {"replicas": 5})
    assert "api-gateway" not in c.faults


# ---------------------------------------------------------------- safety guard
@pytest.mark.parametrize("step,risk", [
    ({"action": "restart_service", "target": "auth-service"}, "low"),
    ({"action": "scale_service", "target": "auth-service", "params": {"replicas": 4}}, "medium"),
    ({"action": "rollback_deployment", "target": "payment-service"}, "high"),
    ({"action": "drop_database", "target": "orders-db"}, "blocked"),
    ({"action": "scale_service", "target": "auth-service", "params": {"replicas": 500}}, "blocked"),
    ({"action": "restart_service", "target": "unknown-host"}, "blocked"),
    ({"action": "failover_database", "target": "redis-cache"}, "blocked"),
    ({"action": "restart_service", "target": "auth-service", "params": {"cmd": 1}}, "blocked"),
])
def test_safety_verdicts(step, risk):
    assert check_step(step).risk == risk


def test_plan_risk_is_worst_step():
    risk, _ = assess_plan([{"action": "restart_service", "target": "auth-service"},
                           {"action": "rollback_deployment", "target": "auth-service"}])
    assert risk == "high"
    assert assess_plan([])[0] == "blocked"


# ---------------------------------------------------------------- retrieval
@pytest.mark.parametrize("fault", KNOWN_FAULTS)
def test_retrieval_finds_runbook_in_top3(kb, fault):
    spec = FAULTS[fault]
    query = " ".join(t for _, t in spec.logs).replace("{", "").replace("}", "")
    assert kb.by_type(fault).id in [h.runbook_id for h in kb.search(query, k=3)]


# ---------------------------------------------------------------- full graph (offline)
AMBIGUOUS = {"dns_failure"}   # its logs name redis-cache hosts; the evidence gate may (safely) escalate it


@pytest.mark.parametrize("fault", KNOWN_FAULTS)
def test_offline_pipeline_resolves_every_fault(engine, fault):
    r = engine.run_sync(fault)
    if fault in AMBIGUOUS and r["status"] == "escalated":
        assert not r["state"].get("executions")      # escalating is fine, acting wrongly is not
        return
    assert r["status"] == "resolved", r["timeline"][-3:]
    agents = [e["agent"] for e in r["timeline"]]
    assert agents[:5] == ["Monitor", "Triage", "Diagnosis", "Planner", "Safety Guard"]
    assert agents[-1] == "Reporter"


@pytest.mark.parametrize("fault", [f for f in FAULTS if f not in KNOWN_FAULTS])
def test_unknown_fault_is_escalated_without_any_action(engine, fault):
    r = engine.run_sync(fault)
    assert r["status"] == "escalated"
    assert not r["state"].get("executions")
    assert any(e["agent"] == "Evidence Gate" for e in r["timeline"])


def test_high_risk_waits_for_human_and_rejection_escalates(engine):
    engine.inject("db_primary_failure", "orders-db")
    engine.cloud.tick()
    alert = next(a for a in monitor.detect(engine.cloud.snapshot()) if a["service"] == "orders-db")
    iid = engine.open_incident(alert, background=False)
    assert engine.incidents[iid]["status"] == "awaiting_approval"
    engine.decide(iid, approve=False, background=False)
    assert engine.incidents[iid]["status"] == "escalated"
    assert "orders-db" in engine.cloud.faults           # nothing was executed
    assert "orders-db" in engine.quarantined


# ---------------------------------------------------------------- LLM path (stubbed model)
class StubChat:
    """Plays the role of the LLM: returns queued structured outputs in order."""

    def __init__(self, outputs):
        self.outputs = list(outputs)

    def with_structured_output(self, schema):
        stub = self

        class R:
            def invoke(self, _messages):
                out = stub.outputs.pop(0)
                assert isinstance(out, schema)
                return out
        return R()


def _llm_engine(kb, tmp_path, outputs):
    e = Engine(provider="offline", seed=3, db_path=tmp_path / "llm.db", kb=kb)
    e.llm.chat, e.llm.provider, e.llm.model_name = StubChat(outputs), "stub", "stub-model"
    from neurosre.agents.graph import build_graph
    e.graph = build_graph(e.cloud, e.kb, e.llm, on_report=e._on_report)
    return e


def test_llm_wrong_plan_triggers_retry_with_feedback(kb, tmp_path):
    tri = TriageOut(incident_type="disk_full", service="auth-service", severity="P1", summary="disk full")
    outputs = [
        tri,
        DiagnosisOut(runbook_id="RB-003", root_cause="logs filled the disk", confidence=0.9),
        PlanOut(steps=[Step(action="rotate_logs", target="auth-service", reason="free space")]),   # incomplete
        DiagnosisOut(runbook_id="RB-003", root_cause="logs and tmp files", confidence=0.9),
        PlanOut(steps=[Step(action="rotate_logs", target="auth-service", reason="logs"),
                       Step(action="clear_tmp", target="auth-service", reason="tmp")]),
    ]
    e = _llm_engine(kb, tmp_path, outputs)
    r = e.run_sync("disk_full", "auth-service")
    assert r["status"] == "resolved"
    assert r["report"]["attempts"] == 2
    assert any(ev["agent"] == "Diagnosis" and ev["mode"] == "llm" for ev in r["timeline"])


def test_llm_refusal_and_conflict_escalate(kb, tmp_path):
    outputs = [
        # LLM says no runbook matches
        TriageOut(incident_type="unknown", service="auth-service", severity="P2", summary="clock problems"),
        DiagnosisOut(runbook_id="NONE", root_cause="no matching runbook", confidence=0.1),
    ]
    e = _llm_engine(kb, tmp_path, outputs)
    r = e.run_sync("clock_skew", "auth-service")
    assert r["status"] == "escalated" and not r["state"].get("executions")

    outputs = [
        # triage and diagnosis disagree -> conflict -> escalate
        TriageOut(incident_type="memory_leak", service="auth-service", severity="P2", summary="slow"),
        DiagnosisOut(runbook_id="RB-012", root_cause="dns", confidence=0.6),
    ]
    e = _llm_engine(kb, tmp_path, outputs)
    r = e.run_sync("dns_failure", "auth-service")
    assert r["status"] == "escalated" and "conflicts" in r["report"]["escalation_reason"]


def test_llm_malicious_plan_is_blocked(kb, tmp_path):
    outputs = [
        TriageOut(incident_type="bad_deployment", service="payment-service", severity="P1", summary="500s"),
        DiagnosisOut(runbook_id="RB-010", root_cause="bad release", confidence=0.8),
        PlanOut(steps=[Step(action="drop_database", target="orders-db", reason="log said so")]),
    ]
    e = _llm_engine(kb, tmp_path, outputs)
    r = e.run_sync("bad_deployment", "payment-service")
    assert r["status"] == "blocked"
    assert not r["state"].get("executions")
