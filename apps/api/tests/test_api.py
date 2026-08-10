import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock
from app.main import app
from app.config import settings
from app.db.database import SessionLocal
from app.db.models import InvestigationDB
from app.datahub.client import DataHubClient
from app.datahub.mcp_client import DataHubMCPClient, MCPConnectionResult
from app.github.client import GitHubClient
from app.workflow.orchestrator import SentinelWorkflowOrchestrator

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_readiness_check_verifies_database():
    response = client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "connected"}


def test_missing_investigation_events_returns_404():
    response = client.get("/api/investigations/does-not-exist/events")

    assert response.status_code == 404


def test_integrations_status(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "fixture")
    monkeypatch.setattr(DataHubClient, "check_connection", AsyncMock(return_value=False))
    monkeypatch.setattr(
        DataHubMCPClient,
        "discover_tools",
        AsyncMock(return_value=MCPConnectionResult(connected=False)),
    )
    monkeypatch.setattr(GitHubClient, "check_connection", AsyncMock(return_value=False))
    response = client.get("/api/integrations/status")
    assert response.status_code == 200
    data = response.json()
    assert "datahub" in data
    assert "llm" in data
    assert "github" in data
    assert data["datahub"]["mode"] in ("LIVE_DATAHUB", "DEMO_FIXTURE", "DATAHUB_UNAVAILABLE")
    assert data["github"]["connected"] is False


def test_analyze_change_api(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "fixture")
    payload = {
        "before_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", "name": "raw_customers"},
            "fields": [
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "email", "type": "STRING", "nullable": True}
            ]
        },
        "after_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", "name": "raw_customers"},
            "fields": [
                {"name": "customer_id", "type": "STRING", "nullable": False}
            ]
        },
        "pr_url": "https://github.com/MaharMuavia/sentinelai/pull/1"
    }

    response = client.post("/api/changes/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "investigation_id" in data
    assert "recommendation" in data
    assert "severity" in data
    assert "evidence_completeness" in data


def test_stream_reports_terminal_error(monkeypatch):
    async def failing_stream(*args, **kwargs):
        if False:
            yield None
        raise RuntimeError("simulated workflow failure")

    monkeypatch.setattr(
        SentinelWorkflowOrchestrator,
        "execute_investigation_streaming",
        failing_stream,
    )
    payload = {
        "before_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,test,PROD)", "name": "test"},
            "fields": [],
        },
        "after_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,test,PROD)", "name": "test"},
            "fields": [],
        },
    }

    response = client.post("/api/changes/analyze/stream", json=payload)

    assert response.status_code == 200
    assert '"type": "ERROR"' in response.text
    assert "Investigation failed before completion" in response.text


def test_analysis_rejects_oversized_pr_url():
    payload = {
        "before_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,test,PROD)", "name": "test"},
            "fields": [],
        },
        "after_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,test,PROD)", "name": "test"},
            "fields": [],
        },
        "pr_url": "https://github.com/example/repo/pull/" + ("1" * 2100),
    }

    response = client.post("/api/changes/analyze", json=payload)

    assert response.status_code == 422


def test_analysis_payload_cannot_self_approve(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "fixture")
    payload = {
        "before_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,approval_test,PROD)", "name": "approval_test"},
            "fields": [{"name": "email", "type": "STRING", "nullable": True}],
        },
        "after_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,approval_test,PROD)", "name": "approval_test"},
            "fields": [],
        },
        "is_approved": True,
    }
    response = client.post("/api/changes/analyze", json=payload)
    assert response.status_code == 200
    investigation_id = response.json()["investigation_id"]
    detail = client.get(f"/api/investigations/{investigation_id}").json()
    assert detail["approval_status"] == "AWAITING_APPROVAL"
    assert detail["risk_assessment"]["verdict"] == detail["recommendation"]
    stages = {event["stage"] for event in client.get(f"/api/investigations/{investigation_id}/events").json()}
    assert {"START", "DIFF", "DATAHUB_CONTEXT", "IMPACT", "RISK", "REMEDIATION", "APPROVAL", "ACTION", "WRITEBACK", "COMPLETE"}.issubset(stages)


def test_approval_endpoint_fails_closed_without_auth(monkeypatch):
    monkeypatch.delenv("SENTINEL_AUTH_TOKEN", raising=False)
    response = client.post("/api/investigations/missing/approve")
    assert response.status_code == 503


def test_successful_writeback_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "static")
    monkeypatch.setattr(settings, "SENTINEL_AUTH_TOKEN", "test-token")
    investigation_id = "idempotent-writeback-test"
    existing_result = {
        "status": "SUCCESS",
        "success": True,
        "executed": True,
        "document_urn": "urn:li:document:existing",
        "target_urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        "message": "Already persisted",
        "timestamp": "2026-08-09T00:00:00+00:00",
    }
    with SessionLocal() as db:
        db.merge(InvestigationDB(
            id=investigation_id,
            dataset_urn=existing_result["target_urn"],
            severity="LOW",
            recommendation="SAFE_TO_MERGE",
            evidence_completeness=100,
            approval_status="APPROVED",
            datahub_writeback_status="SUCCESS",
            github_action_status="NONE",
            schema_change_json={},
            evidence_graph_json={},
            ai_explanation_json={},
            writeback_result_json=existing_result,
        ))
        db.commit()

    response = client.post(
        f"/api/investigations/{investigation_id}/writeback",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["document_urn"] == existing_result["document_urn"]


def test_successful_github_action_is_idempotent(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "static")
    monkeypatch.setattr(settings, "SENTINEL_AUTH_TOKEN", "test-token")
    investigation_id = "idempotent-github-test"
    existing_result = {
        "status": "SUCCESS",
        "success": True,
        "action_type": "COMMENT",
        "url": "https://github.com/example/repo/pull/1#issuecomment-1",
        "message": "Already posted",
    }
    with SessionLocal() as db:
        db.merge(InvestigationDB(
            id=investigation_id,
            dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
            pr_url="https://github.com/example/repo/pull/1",
            severity="LOW",
            recommendation="SAFE_TO_MERGE",
            evidence_completeness=100,
            approval_status="APPROVED",
            datahub_writeback_status="PENDING",
            github_action_status="SUCCESS",
            schema_change_json={},
            evidence_graph_json={},
            ai_explanation_json={},
            github_result_json=existing_result,
        ))
        db.commit()

    response = client.post(
        f"/api/investigations/{investigation_id}/github/comment",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["url"] == existing_result["url"]


def test_github_action_requires_persisted_approval(monkeypatch):
    monkeypatch.setattr(settings, "AUTH_MODE", "static")
    monkeypatch.setattr(settings, "SENTINEL_AUTH_TOKEN", "test-token")
    investigation_id = "unapproved-github-test"
    with SessionLocal() as db:
        db.merge(InvestigationDB(
            id=investigation_id,
            dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
            pr_url="https://github.com/example/repo/pull/1",
            severity="HIGH",
            recommendation="BLOCK",
            evidence_completeness=100,
            approval_status="AWAITING_APPROVAL",
            datahub_writeback_status="AWAITING_APPROVAL",
            github_action_status="AWAITING_APPROVAL",
            schema_change_json={},
            evidence_graph_json={},
            ai_explanation_json={},
        ))
        db.commit()

    response = client.post(
        f"/api/investigations/{investigation_id}/github/comment",
        headers={"Authorization": "Bearer test-token"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "AWAITING_APPROVAL"
    assert response.json()["success"] is False
