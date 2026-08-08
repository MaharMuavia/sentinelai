import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_integrations_status():
    response = client.get("/api/integrations/status")
    assert response.status_code == 200
    data = response.json()
    assert "datahub" in data
    assert "llm" in data
    assert "github" in data
    assert data["datahub"]["mode"] in ("LIVE_DATAHUB", "DEMO_FIXTURE", "DATAHUB_UNAVAILABLE")


def test_analyze_change_api():
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
        "pr_url": "https://github.com/acme/data-platform/pull/42"
    }

    response = client.post("/api/changes/analyze", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "investigation_id" in data
    assert "recommendation" in data
    assert "severity" in data
    assert "evidence_completeness" in data
