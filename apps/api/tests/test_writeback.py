import pytest
from app.datahub.writeback import DataHubWritebackEngine, WritebackStatus, WritebackResult
from app.datahub.mcp_client import MCPToolResult, EvidenceProvenance, IntegrationMode


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
        approval_granted=True
    )

    assert res.success is False
    assert res.status == WritebackStatus.DISABLED
    assert "disabled" in res.message.lower()


@pytest.mark.asyncio
async def test_writeback_awaiting_and_dry_run_are_not_success(monkeypatch):
    monkeypatch.setenv("DATAHUB_MUTATION_ENABLED", "true")
    wb = DataHubWritebackEngine(gms_url="http://localhost:59999", token="")
    kwargs = dict(
        investigation_id="test",
        dataset_urn="urn:li:dataset:raw",
        severity="LOW",
        recommendation="SAFE_TO_MERGE",
        evidence_completeness=40,
        evidence_trust="DEMO FIXTURE - NOT LIVE VERIFIED",
        confirmed_consumers=[],
        potential_consumers=[],
        summary="fixture",
    )
    awaiting = await wb.writeback_investigation(**kwargs)
    assert awaiting.status == WritebackStatus.AWAITING_APPROVAL
    assert awaiting.success is False
    dry_run = await wb.writeback_investigation(**kwargs, approval_granted=True, is_dry_run=True)
    assert dry_run.status == WritebackStatus.DRY_RUN
    assert dry_run.success is False
    assert dry_run.executed is False


@pytest.mark.asyncio
async def test_writeback_returns_failure_when_gms_unreachable(monkeypatch):
    monkeypatch.setenv("DATAHUB_MUTATION_ENABLED", "true")
    wb = DataHubWritebackEngine(gms_url="http://localhost:59999", token="")

    async def unavailable_save_document(**kwargs):
        return MCPToolResult(
            tool_name="save_document",
            success=False,
            error_message="MCP endpoint unavailable",
            provenance=EvidenceProvenance(
                source_mode=IntegrationMode.DATAHUB_UNAVAILABLE,
                source_tool="save_document",
                verified=False,
            ),
        )

    monkeypatch.setattr(wb.mcp_client, "save_document", unavailable_save_document)
    
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
        approval_granted=True
    )

    assert res.success is False
    assert res.status == WritebackStatus.FAILED
    assert "failed" in res.message.lower()


@pytest.mark.asyncio
async def test_writeback_represents_tag_partial_failure(monkeypatch):
    monkeypatch.setenv("DATAHUB_MUTATION_ENABLED", "true")
    wb = DataHubWritebackEngine(gms_url="http://localhost:59999", token="")
    provenance = EvidenceProvenance(source_mode=IntegrationMode.LIVE_DATAHUB, source_tool="test", verified=True)

    async def save_document(**kwargs):
        return MCPToolResult(tool_name="save_document", success=True, content={"document_urn": "urn:li:document:real"}, provenance=provenance)

    async def add_tags(**kwargs):
        return MCPToolResult(tool_name="add_tags", success=False, error_message="tag denied", provenance=provenance)

    monkeypatch.setattr(wb.mcp_client, "save_document", save_document)
    monkeypatch.setattr(wb.mcp_client, "add_tags", add_tags)
    result = await wb.writeback_investigation(
        investigation_id="i",
        dataset_urn="urn:li:dataset:raw",
        severity="HIGH",
        recommendation="BLOCK",
        evidence_completeness=50,
        confirmed_consumers=[],
        potential_consumers=[],
        summary="summary",
        evidence_trust="LIVE DATAHUB MCP",
        approval_granted=True,
    )

    assert result.status == WritebackStatus.PARTIAL_FAILURE
    assert result.success is False
    assert result.document_urn == "urn:li:document:real"
    assert result.document_write.success is True
    assert result.tag_write.success is False
