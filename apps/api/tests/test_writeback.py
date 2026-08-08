import pytest
from app.datahub.writeback import DataHubWritebackEngine, WritebackStatus, WritebackResult


@pytest.mark.asyncio
async def test_writeback_returns_disabled_when_mutation_disabled(monkeypatch):
    monkeypatch.setenv("DATAHUB_MUTATION_ENABLED", "false")
    wb = DataHubWritebackEngine(gms_url="http://localhost:59999", token="")
    
    # Must return status=DISABLED and success=False when mutation is disabled
    res = await wb.writeback_investigation(
        investigation_id="test1234",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        severity="CRITICAL",
        recommendation="BLOCK",
        evidence_completeness=94.0,
        evidence_trust="LIVE DATAHUB MCP",
        confirmed_consumers=["customer_360"],
        potential_consumers=[],
        summary="Test investigation writeback failure handling",
        is_approved=True
    )

    assert res.success is False
    assert res.status == WritebackStatus.DISABLED
    assert "disabled" in res.message.lower()


@pytest.mark.asyncio
async def test_writeback_returns_failure_when_gms_unreachable(monkeypatch):
    monkeypatch.setenv("DATAHUB_MUTATION_ENABLED", "true")
    wb = DataHubWritebackEngine(gms_url="http://localhost:59999", token="")
    
    # Must return status=FAILED and success=False when DataHub GMS is unreachable
    res = await wb.writeback_investigation(
        investigation_id="test1234",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        severity="CRITICAL",
        recommendation="BLOCK",
        evidence_completeness=94.0,
        evidence_trust="LIVE DATAHUB MCP",
        confirmed_consumers=["customer_360"],
        potential_consumers=[],
        summary="Test investigation writeback failure handling",
        is_approved=True
    )

    assert res.success is False
    assert res.status == WritebackStatus.FAILED
    assert "failed" in res.message.lower()
