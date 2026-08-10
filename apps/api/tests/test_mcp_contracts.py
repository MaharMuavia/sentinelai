import sys

import httpx
import pytest

from app.datahub.mcp_client import DataHubMCPClient, IntegrationMode, MCPToolResult, EvidenceProvenance
from app.datahub.client import DataHubClient


class _TextContent:
    def __init__(self, text: str):
        self.text = text


class _CallResult:
    def __init__(self, *, structured=None, text=None, is_error=False):
        self.structuredContent = structured
        self.content = [_TextContent(text)] if text is not None else []
        self.isError = is_error


def test_normalization_accepts_structured_content_and_json_text():
    assert DataHubMCPClient._normalize_call_result(_CallResult(structured={"entities": []})) == {"entities": []}
    assert DataHubMCPClient._normalize_call_result(_CallResult(text='{"fields": []}')) == {"fields": []}
    assert DataHubMCPClient._normalize_call_result(_CallResult(structured={"result": [{"urn": "u"}]})) == {
        "results": [{"urn": "u"}]
    }


def test_normalization_rejects_tool_error_and_malformed_text():
    with pytest.raises(Exception):
        DataHubMCPClient._normalize_call_result(_CallResult(is_error=True))
    with pytest.raises(Exception):
        DataHubMCPClient._normalize_call_result(_CallResult(text="not json"))


@pytest.mark.asyncio
async def test_adapter_contracts_use_current_argument_names(monkeypatch):
    client = DataHubMCPClient(mcp_endpoint="http://example.test/mcp")
    calls = []

    async def fake_call(tool_name, arguments, entity_urn=None, field_path=None):
        calls.append((tool_name, arguments))
        return type("Result", (), {"success": True, "content": {"ok": True}, "provenance": type("P", (), {"source_reference": "r"})()})()

    monkeypatch.setattr(client, "call_tool", fake_call)
    await client.list_schema_fields("urn:dataset", query="email", max_results=20, offset=5)
    await client.get_lineage("urn:dataset", upstream=False, max_hops=3, max_results=20, offset=5, column="email")
    await client.get_lineage_paths_between("urn:source", "urn:target", source_column="email", target_column="customer_email")
    await client.save_document(title="title", content="body", related_assets=["urn:dataset"])
    await client.add_tags(tag_urns=["urn:li:tag:Sentinel_BLOCK"], entity_urns=["urn:dataset"])

    assert calls == [
        ("list_schema_fields", {"urn": "urn:dataset", "limit": 20, "offset": 5, "keywords": ["email"]}),
        ("get_lineage", {"urn": "urn:dataset", "upstream": False, "max_hops": 3, "max_results": 20, "offset": 5, "column": "email"}),
        ("get_lineage_paths_between", {"source_urn": "urn:source", "target_urn": "urn:target", "source_column": "email", "target_column": "customer_email"}),
        ("save_document", {"document_type": "Analysis", "title": "title", "content": "body", "related_assets": ["urn:dataset"]}),
        ("add_tags", {"tag_urns": ["urn:li:tag:Sentinel_BLOCK"], "entity_urns": ["urn:dataset"]}),
    ]


@pytest.mark.asyncio
async def test_official_streamable_http_transport_round_trip():
    from mcp.server.fastmcp import FastMCP

    server = FastMCP("contract", json_response=True)

    @server.tool()
    def get_entities(urns: list[str]) -> dict:
        return {"entities": [{"urn": urns[0], "name": "raw_customers"}]}

    app = server.streamable_http_app()
    transport = httpx.ASGITransport(app=app)
    client = DataHubMCPClient(mcp_endpoint="http://localhost:8000/mcp", transport=transport)
    async with server.session_manager.run():
        result = await client.get_entities(["urn:dataset"])

    assert result.success is True
    assert result.content == {"entities": [{"urn": "urn:dataset", "name": "raw_customers"}]}
    assert result.provenance.source_mode == IntegrationMode.LIVE_DATAHUB


@pytest.mark.asyncio
async def test_official_stdio_transport_round_trip():
    server_code = """
from mcp.server.fastmcp import FastMCP

server = FastMCP("stdio-contract", json_response=True)

@server.tool()
def get_entities(urns: list[str]) -> dict:
    return {"entities": [{"urn": urns[0], "name": "raw_customers"}]}

server.run(transport="stdio")
"""
    client = DataHubMCPClient(mcp_command=sys.executable, mcp_args=["-c", server_code])
    result = await client.get_entities(["urn:dataset"])

    assert result.success is True
    assert result.content == {"entities": [{"urn": "urn:dataset", "name": "raw_customers"}]}
    assert result.provenance.source_mode == IntegrationMode.LIVE_DATAHUB


def test_stdio_args_must_be_json_string_array():
    with pytest.raises(ValueError, match="JSON array of strings"):
        DataHubMCPClient(mcp_command="uvx", mcp_args='{"bad": true}')


@pytest.mark.asyncio
async def test_exact_path_requires_matching_returned_path(monkeypatch):
    client = DataHubClient()
    source = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    target = "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)"
    provenance = EvidenceProvenance(source_mode=IntegrationMode.LIVE_DATAHUB, source_tool="get_lineage_paths_between", verified=True)
    monkeypatch.setattr(client, "get_integration_mode", lambda *args, **kwargs: _live_mode())

    async def _live_mode():
        return IntegrationMode.LIVE_DATAHUB

    async def paths(*args, **kwargs):
        return MCPToolResult(
            tool_name="get_lineage_paths_between",
            success=True,
            content={"paths": [[f"urn:li:schemaField:({source},email)", f"urn:li:schemaField:({target},email)"]]},
            provenance=provenance,
        )

    monkeypatch.setattr(client.mcp_client, "get_lineage_paths_between", paths)
    assert await client.verify_exact_lineage_path(source, target, "email", "email") is True
    exact_provenance = await client.get_exact_lineage_path_provenance(source, target, "email", "email")
    assert exact_provenance is not None
    assert exact_provenance.source_tool == "get_lineage_paths_between"


def test_live_datahub_entity_shape_parses_nested_metadata():
    client = DataHubClient()
    urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    dataset = client._parse_mcp_dataset(
        urn,
        {
            "results": [
                {
                    "urn": urn,
                    "name": "raw_customers",
                    "platform": {"urn": "urn:li:dataPlatform:snowflake", "name": "snowflake"},
                    "properties": {"description": "Raw customers"},
                    "ownership": {
                        "owners": [
                            {
                                "owner": {"urn": "urn:li:corpuser:sarah"},
                                "type": "TECHNICAL_OWNER",
                            }
                        ]
                    },
                    "tags": {"tags": [{"tag": {"urn": "urn:li:tag:PII"}}]},
                    "schemaMetadata": {
                        "fields": [
                            {"fieldPath": "email", "nativeDataType": "STRING", "nullable": True}
                        ]
                    },
                }
            ]
        },
    )

    assert dataset.description == "Raw customers"
    assert dataset.platform == "snowflake"
    assert [owner.owner_urn for owner in dataset.owners] == ["urn:li:corpuser:sarah"]
    assert dataset.tags == ["urn:li:tag:PII"]
    assert [field.field_path for field in dataset.fields] == ["email"]


def test_live_datahub_lineage_shapes_parse_nested_downstreams():
    client = DataHubClient()
    source = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    target = "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)"
    content = {
        "downstreams": {
            "searchResults": [
                {
                    "entity": {"urn": target, "name": "customer_360", "type": "DATASET"},
                    "degree": 1,
                    "lineageColumns": ["email"],
                }
            ]
        }
    }

    edges = client._parse_column_lineage(source, "email", content, "ref")

    assert [(edge.target_urn, edge.target_field) for edge in edges] == [(target, "email")]
    assert DataHubClient._schema_field_ref(
        {"fieldPath": "email", "parent": {"urn": source, "type": "DATASET"}}
    ) == (source, "email")


def test_mutation_payload_failure_is_not_reported_as_success():
    result = MCPToolResult(
        tool_name="save_document",
        success=True,
        content={"success": False, "message": "denied"},
        provenance=EvidenceProvenance(
            source_mode=IntegrationMode.LIVE_DATAHUB,
            source_tool="save_document",
            verified=True,
        ),
    )

    validated = DataHubMCPClient._validate_mutation_result(result)

    assert validated.success is False
    assert validated.is_error is True
    assert validated.error_message == "denied"
