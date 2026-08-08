import pytest
import os
from app.datahub.mcp_client import DataHubMCPClient, IntegrationMode
from app.datahub.client import DataHubClient


@pytest.mark.asyncio
async def test_mcp_client_rpc_payload():
    client = DataHubMCPClient(gms_url="http://localhost:59999")
    
    # Connection check when GMS offline must return False
    assert await client.check_connection() is False

    # Tool call when offline must return success=False and DATAHUB_UNAVAILABLE provenance
    res = await client.get_entities(["urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"])
    assert res.success is False
    assert res.provenance.source_mode == IntegrationMode.DATAHUB_UNAVAILABLE
    assert res.provenance.source_tool == "get_entities"


@pytest.mark.asyncio
async def test_datahub_client_no_silent_fallback_in_live_mode(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "live")
    client = DataHubClient(gms_url="http://localhost:59999")

    # In live mode when GMS offline, MUST return DATAHUB_UNAVAILABLE, NOT DEMO_FIXTURE
    mode = await client.get_integration_mode(allow_fixture_fallback=False)
    assert mode == IntegrationMode.DATAHUB_UNAVAILABLE

    dataset = await client.get_dataset("urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", allow_fixture_fallback=False)
    assert dataset is None


@pytest.mark.asyncio
async def test_datahub_client_explicit_fixture_mode(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "fixture")
    client = DataHubClient()

    mode = await client.get_integration_mode(allow_fixture_fallback=True)
    assert mode == IntegrationMode.DEMO_FIXTURE

    dataset = await client.get_dataset("urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", allow_fixture_fallback=True)
    assert dataset is not None
    assert dataset.is_demo_fixture is True
    assert dataset.provenance.source_mode == IntegrationMode.DEMO_FIXTURE
