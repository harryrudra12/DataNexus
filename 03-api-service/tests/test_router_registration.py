"""Regression tests for critical pipeline route registration."""

from __future__ import annotations

import warnings

from app.main import app


def test_pipeline_execution_routes_are_registered_once() -> None:
    app.openapi_schema = None

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        schema = app.openapi()

    duplicate_operation_warnings = [
        warning
        for warning in caught
        if "Duplicate Operation ID" in str(warning.message)
    ]
    assert duplicate_operation_warnings == []

    expected_operations = {
        "/api/v1/dashboard/pipelines/{pipeline_id}/execute-real": "post",
        "/api/v1/dashboard/pipeline-runs/recent": "get",
        "/api/v1/dashboard/pipelines/{pipeline_id}/execute-kafka": "post",
    }
    for path, method in expected_operations.items():
        assert method in schema["paths"][path]

    operation_ids = [
        operation["operationId"]
        for path_item in schema["paths"].values()
        for operation in path_item.values()
        if "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))
