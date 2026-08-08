import pytest
from app.datahub.writeback import DataHubWritebackEngine, WritebackResult


@pytest.mark.asyncio
async def test_writeback_returns_failure_when_gms_unreachable():
    wb = DataHubWritebackEngine(gms_url="http://localhost:59999", token="")
    
    # Must return success=False when DataHub GMS is unreachable
    res = await wb.writeback_investigation(
        investigation_id="test1234",
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        severity="CRITICAL",
        recommendation="BLOCK",
        evidence_completeness=94.0,
        confirmed_consumers=["customer_360"],
        potential_consumers=[],
        summary="Test investigation writeback failure handling"
    )

    assert res.success is False
    assert "failed" in res.message.lower()
    assert res.error_detail is not None
