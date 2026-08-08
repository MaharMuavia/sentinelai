import pytest
from app.datahub.client import DataHubClient, IntegrationMode, DatasetMetadata


@pytest.mark.asyncio
async def test_datahub_client_integration_modes():
    client = DataHubClient()
    
    # Check default mode (when live GMS offline, fallback to DEMO_FIXTURE)
    mode = await client.get_integration_mode(allow_fixture_fallback=True)
    assert mode in (IntegrationMode.LIVE_DATAHUB, IntegrationMode.DEMO_FIXTURE)

    # When fixture fallback is disabled and GMS is offline, mode must be DATAHUB_UNAVAILABLE
    if not await client.check_connection():
        mode_strict = await client.get_integration_mode(allow_fixture_fallback=False)
        assert mode_strict == IntegrationMode.DATAHUB_UNAVAILABLE


@pytest.mark.asyncio
async def test_get_dataset_provenance():
    client = DataHubClient()
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    dataset = await client.get_dataset(urn, allow_fixture_fallback=True)
    
    assert dataset is not None
    assert dataset.urn == urn
    assert dataset.provenance is not None
    assert dataset.provenance.source_mode in (IntegrationMode.LIVE_DATAHUB, IntegrationMode.DEMO_FIXTURE)
    assert dataset.provenance.entity_urn == urn


@pytest.mark.asyncio
async def test_get_dataset_unavailable_returns_none():
    client = DataHubClient()
    # When GMS is offline and fallback disabled, MUST return None (no silent fake data creation)
    if not await client.check_connection():
        dataset = await client.get_dataset("urn:li:dataset:(urn:li:dataPlatform:snowflake,unknown_table,PROD)", allow_fixture_fallback=False)
        assert dataset is None
