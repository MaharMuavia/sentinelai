import os
import json
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger(__name__)


class IntegrationMode(str, Enum):
    LIVE_DATAHUB = "LIVE_DATAHUB"
    DEMO_FIXTURE = "DEMO_FIXTURE"
    DATAHUB_UNAVAILABLE = "DATAHUB_UNAVAILABLE"


class EvidenceProvenance(BaseModel):
    source_mode: IntegrationMode
    source_tool: str
    entity_urn: str
    field_path: Optional[str] = None
    source_reference: Optional[str] = None
    retrieved_at: datetime = Field(default_factory=datetime.utcnow)


class MCPToolResult(BaseModel):
    tool_name: str
    success: bool
    content: Any
    error_message: Optional[str] = None
    provenance: EvidenceProvenance


class DataHubMCPClient:
    """
    Official DataHub Model Context Protocol (MCP) Client.
    Communicates with DataHub MCP Server over JSON-RPC 2.0 transport.
    Invokes official DataHub Agent Context tools:
    - get_entities
    - list_schema_fields
    - get_lineage
    - get_lineage_paths_between
    - get_dataset_queries
    - save_document
    - add_tags
    """

    def __init__(self, gms_url: Optional[str] = None, token: Optional[str] = None, mcp_endpoint: Optional[str] = None):
        self.gms_url = (gms_url or os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")).rstrip("/")
        self.token = token or os.getenv("DATAHUB_GMS_TOKEN", "")
        self.mcp_endpoint = mcp_endpoint or os.getenv("DATAHUB_MCP_ENDPOINT", f"{self.gms_url}/mcp")
        self._request_id = 0

    def _next_request_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _get_headers(self) -> Dict[str, str]:
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    async def check_connection(self) -> bool:
        """Check if DataHub GMS / MCP server is reachable."""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                res = await client.get(f"{self.gms_url}/health", headers=self._get_headers())
                if res.status_code == 200:
                    return True
                # Check MCP endpoint
                mcp_res = await client.post(
                    self.mcp_endpoint,
                    json={"jsonrpc": "2.0", "id": self._next_request_id(), "method": "initialize", "params": {}},
                    headers=self._get_headers()
                )
                return mcp_res.status_code in (200, 204)
        except Exception as e:
            logger.debug(f"DataHub MCP connection check failed: {e}")
            return False

    async def call_tool(self, tool_name: str, arguments: Dict[str, Any], entity_urn: str = "", field_path: Optional[str] = None) -> MCPToolResult:
        """
        Execute a JSON-RPC 2.0 tool call against the DataHub MCP Server.
        Returns a structured MCPToolResult carrying explicit EvidenceProvenance.
        """
        req_id = self._next_request_id()
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "method": "tools/call",
            "params": {
                "name": tool_name,
                "arguments": arguments
            }
        }

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res = await client.post(self.mcp_endpoint, json=payload, headers=self._get_headers())
                if res.status_code == 200:
                    data = res.json()
                    if "error" in data:
                        err_msg = data["error"].get("message", "MCP Tool Execution Error")
                        return MCPToolResult(
                            tool_name=tool_name,
                            success=False,
                            content=None,
                            error_message=err_msg,
                            provenance=EvidenceProvenance(
                                source_mode=IntegrationMode.LIVE_DATAHUB,
                                source_tool=tool_name,
                                entity_urn=entity_urn,
                                field_path=field_path,
                                source_reference=f"mcp_rpc_id_{req_id}"
                            )
                        )
                    result_content = data.get("result", {})
                    return MCPToolResult(
                        tool_name=tool_name,
                        success=True,
                        content=result_content,
                        provenance=EvidenceProvenance(
                            source_mode=IntegrationMode.LIVE_DATAHUB,
                            source_tool=tool_name,
                            entity_urn=entity_urn,
                            field_path=field_path,
                            source_reference=f"mcp_rpc_id_{req_id}"
                        )
                    )
                else:
                    return MCPToolResult(
                        tool_name=tool_name,
                        success=False,
                        content=None,
                        error_message=f"HTTP {res.status_code}: {res.text}",
                        provenance=EvidenceProvenance(
                            source_mode=IntegrationMode.DATAHUB_UNAVAILABLE,
                            source_tool=tool_name,
                            entity_urn=entity_urn,
                            field_path=field_path
                        )
                    )
        except Exception as e:
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                content=None,
                error_message=str(e),
                provenance=EvidenceProvenance(
                    source_mode=IntegrationMode.DATAHUB_UNAVAILABLE,
                    source_tool=tool_name,
                    entity_urn=entity_urn,
                    field_path=field_path
                )
            )

    async def get_entities(self, urns: List[str]) -> MCPToolResult:
        """Invoke MCP tool 'get_entities' to retrieve entity metadata."""
        return await self.call_tool("get_entities", {"urns": urns}, entity_urn=urns[0] if urns else "")

    async def list_schema_fields(self, dataset_urn: str) -> MCPToolResult:
        """Invoke MCP tool 'list_schema_fields' to retrieve schema fields for a dataset."""
        return await self.call_tool("list_schema_fields", {"urn": dataset_urn}, entity_urn=dataset_urn)

    async def get_lineage(self, dataset_urn: str, direction: str = "DOWNSTREAM", depth: int = 3) -> MCPToolResult:
        """Invoke MCP tool 'get_lineage' for multi-hop dependency graph traversal."""
        return await self.call_tool("get_lineage", {"urn": dataset_urn, "direction": direction, "depth": depth}, entity_urn=dataset_urn)

    async def get_lineage_paths_between(self, source_urn: str, target_urn: str) -> MCPToolResult:
        """Invoke MCP tool 'get_lineage_paths_between' for exact path validation."""
        return await self.call_tool(
            "get_lineage_paths_between",
            {"source_urn": source_urn, "target_urn": target_urn},
            entity_urn=source_urn
        )

    async def get_dataset_queries(self, dataset_urn: str) -> MCPToolResult:
        """Invoke MCP tool 'get_dataset_queries' to inspect query log execution references."""
        return await self.call_tool("get_dataset_queries", {"urn": dataset_urn}, entity_urn=dataset_urn)

    async def save_document(self, urn: str, title: str, content: str, doc_type: str = "SENTINEL_INVESTIGATION") -> MCPToolResult:
        """Invoke MCP tool 'save_document' to persist investigation memory in DataHub."""
        return await self.call_tool(
            "save_document",
            {"urn": urn, "title": title, "content": content, "doc_type": doc_type},
            entity_urn=urn
        )

    async def add_tags(self, urn: str, tags: List[str]) -> MCPToolResult:
        """Invoke MCP tool 'add_tags' to add additive metadata tags to a dataset."""
        return await self.call_tool("add_tags", {"urn": urn, "tags": tags}, entity_urn=urn)
