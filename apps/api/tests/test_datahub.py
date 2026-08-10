import pytest
from app.datahub.client import DataHubClient, IntegrationMode, DatasetMetadata


@pytest.mark.asyncio
async def test_datahub_client_integration_modes(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "fixture")
    client = DataHubClient()
    mode = await client.get_integration_mode(allow_fixture_fallback=False)
    assert mode == IntegrationMode.DEMO_FIXTURE

    assert await client.get_integration_mode(allow_fixture_fallback=False) == IntegrationMode.DEMO_FIXTURE


@pytest.mark.asyncio
async def test_get_dataset_provenance(monkeypatch):
    monkeypatch.setenv("SENTINEL_DATA_MODE", "fixture")
    client = DataHubClient()
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    dataset = await client.get_dataset(urn, allow_fixture_fallback=True)
    
    assert dataset is not None
    assert dataset.urn == urn
    assert dataset.provenance is not None
    assert dataset.provenance.source_mode == IntegrationMode.DEMO_FIXTURE
    assert dataset.provenance.entity_urn == urn


@pytest.mark.asyncio
async def test_get_dataset_unavailable_returns_none():
    client = DataHubClient()
    # When GMS is offline and fallback disabled, MUST return None (no silent fake data creation)
    if not await client.check_connection():
        dataset = await client.get_dataset("urn:li:dataset:(urn:li:dataPlatform:snowflake,unknown_table,PROD)", allow_fixture_fallback=False)
        assert dataset is None
