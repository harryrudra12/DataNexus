import copy

import pytest

from app.routers import dashboard


@pytest.fixture
def isolated_dashboard_state(monkeypatch):
    pipelines = copy.deepcopy(dashboard.PIPELINES)
    audit_events = copy.deepcopy(dashboard.AUDIT_EVENTS)

    monkeypatch.setattr(dashboard, "PIPELINES", pipelines)
    monkeypatch.setattr(dashboard, "AUDIT_EVENTS", audit_events)
    monkeypatch.setattr(dashboard, "ensure_db", lambda: False)

    return pipelines, audit_events


@pytest.mark.asyncio
async def test_search_question_is_rejected_without_creating_pipeline(
    isolated_dashboard_state,
):
    pipelines, audit_events = isolated_dashboard_state
    pipeline_count = len(pipelines)

    result = await dashboard.dashboard_intent_builder(
        {"question": "show risky pipelines"}
    )

    assert result["status"] == "needs_query"
    assert result["intent"] == "search_or_analysis_query"
    assert result["extracted"] == {}
    assert len(pipelines) == pipeline_count
    assert audit_events[0]["action"] == "INTENT_REJECTED"
    assert audit_events[0]["result"] == "USE_ASK_QUERY"


@pytest.mark.parametrize(
    "question",
    [
        "build a fraud report",
        "show the fraud pipeline status",
    ],
)
@pytest.mark.asyncio
async def test_creation_requires_action_and_pipeline_context(
    question,
    isolated_dashboard_state,
):
    pipelines, _ = isolated_dashboard_state
    pipeline_count = len(pipelines)

    result = await dashboard.dashboard_intent_builder({"question": question})

    assert result["status"] == "needs_query"
    assert len(pipelines) == pipeline_count


@pytest.mark.asyncio
async def test_creation_extracts_metadata_and_avoids_duplicate_name(
    isolated_dashboard_state,
):
    pipelines, audit_events = isolated_dashboard_state
    pipelines.append({"name": "fraud_kafka_pipeline"})
    pipeline_count = len(pipelines)
    audit_count = len(audit_events)

    result = await dashboard.dashboard_intent_builder(
        {
            "question": (
                "create a Kafka fraud pipeline under DPDP in Mumbai"
            )
        }
    )

    assert result["status"] == "created"
    assert result["pipeline_name"] == "fraud_kafka_pipeline_2"
    assert result["extracted"] == {
        "source": "kafka",
        "target": "fabric_node_mumbai",
        "law": "DPDP",
        "region": "IN-MH",
        "domain": "fraud",
    }
    assert len(pipelines) == pipeline_count + 1
    assert pipelines[-1] == result["pipeline"]
    assert len(audit_events) == audit_count + 2
    assert [event["action"] for event in audit_events[:2]] == [
        "INTENT_BUILD_PIPELINE",
        "AI_QUERY",
    ]
