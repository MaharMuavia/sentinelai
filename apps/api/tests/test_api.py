import pytest
from fastapi.testclient import TestClient
from app.main import app
from app.db.database import init_db

init_db()
client = TestClient(app)


def test_health_endpoint():
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["app"] == "Sentinel AI"


def test_integrations_status_endpoint():
    res = client.get("/api/integrations/status")
    assert res.status_code == 200
    data = res.json()
    assert "datahub" in data
    assert "llm" in data
    assert "github" in data


def test_analyze_change_endpoint():
    payload = {
        "before_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", "name": "raw_customers"},
            "fields": [
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "email", "type": "STRING", "nullable": True},
                {"name": "country", "type": "STRING", "nullable": True}
            ]
        },
        "after_schema": {
            "dataset": {"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", "name": "raw_customers"},
            "fields": [
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "country", "type": "STRING", "nullable": True}
            ]
        }
    }

    res = client.post("/api/changes/analyze", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert data["severity"] == "CRITICAL"
    assert data["recommendation"] == "BLOCK"
    assert data["evidence_completeness"] >= 90.0
    assert data["confirmed_consumers_count"] > 0
    assert data["remediation"]["validation"]["status"] == "VALIDATED"
