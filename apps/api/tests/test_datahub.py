import pytest
from unittest.mock import AsyncMock
from app.datahub.client import DataHubClient, IntegrationMode, DatasetMetadata
from app.datahub.mcp_client import EvidenceProvenance, MCPToolResult
from app.config import settings


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
async def test_get_dataset_unavailable_returns_none(monkeypatch):
    monkeypatch.delenv("DATAHUB_MCP_COMMAND", raising=False)
    monkeypatch.delenv("DATAHUB_MCP_ARGS", raising=False)
    monkeypatch.setattr(settings, "DATAHUB_MCP_COMMAND", None)
    monkeypatch.setattr(settings, "DATAHUB_MCP_ARGS", [])
    client = DataHubClient()
    # When GMS is offline and fallback disabled, MUST return None (no silent fake data creation)
    if not await client.check_connection():
        dataset = await client.get_dataset("urn:li:dataset:(urn:li:dataPlatform:snowflake,unknown_table,PROD)", allow_fixture_fallback=False)
        assert dataset is None


@pytest.mark.asyncio
async def test_get_dataset_queries_parses_datahub_query_properties(monkeypatch):
    client = DataHubClient()
    raw_urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    result = MCPToolResult(
        tool_name="get_dataset_queries",
        success=True,
        content={
            "queries": [
                {
                    "urn": "urn:li:query:sentinel_demo_customer_email_usage",
                    "properties": {
                        "statement": {"value": "SELECT customer_id, email FROM raw_customers"},
                        "lastModified": {"actor": "urn:li:corpuser:sentinel_demo"},
                    },
                }
            ]
        },
        provenance=EvidenceProvenance(
            source_mode="LIVE_DATAHUB",
            source_tool="get_dataset_queries",
            entity_urn=raw_urn,
            field_path="email",
            verified=True,
        ),
    )
    monkeypatch.setattr(client, "get_integration_mode", AsyncMock(return_value=IntegrationMode.LIVE_DATAHUB))
    client.mcp_client.get_dataset_queries = AsyncMock(return_value=result)

    queries = await client.get_dataset_queries(raw_urn, field_name="email")

    assert len(queries) == 1
    assert queries[0].query_id == "urn:li:query:sentinel_demo_customer_email_usage"
    assert queries[0].query_text == "SELECT customer_id, email FROM raw_customers"
    assert queries[0].user == "urn:li:corpuser:sentinel_demo"


def test_schema_only_live_response_does_not_invent_platform():
    client = DataHubClient()
    dataset = client._parse_mcp_fields_result(
        "urn:li:dataset:(urn:li:dataPlatform:unknown,raw_customers,PROD)",
        {"fields": [{"fieldPath": "email", "nativeDataType": "STRING"}]},
    )

    assert dataset.platform is None
    assert dataset.name == "raw_customers"
