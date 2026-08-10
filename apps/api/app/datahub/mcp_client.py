"""Typed client boundary for the official DataHub MCP server.

The MCP SDK owns protocol negotiation and Streamable HTTP/SSE transport. This
module owns only Sentinel-specific authentication, response normalization, and
tool argument contracts.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Union

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class IntegrationMode(str, Enum):
    LIVE_DATAHUB = "LIVE_DATAHUB"
    DEMO_FIXTURE = "DEMO_FIXTURE"
    DATAHUB_UNAVAILABLE = "DATAHUB_UNAVAILABLE"


class EvidenceProvenance(BaseModel):
    source_mode: IntegrationMode
    source_tool: str
    entity_urn: Optional[str] = None
    field_path: Optional[str] = None
    source_reference: Optional[str] = None
    verified: bool = False
    retrieved_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class MCPToolResult(BaseModel):
    tool_name: str
    success: bool
    content: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    is_error: bool = False
    provenance: EvidenceProvenance


class MCPConnectionResult(BaseModel):
    connected: bool
    tools: List[str] = []
    protocol_version: Optional[str] = None
    error_message: Optional[str] = None


class MCPResponseError(RuntimeError):
    """Raised when a successful transport response is not a valid MCP payload."""


class DataHubMCPClient:
    REQUIRED_READ_TOOLS = frozenset(
        {
            "get_entities",
            "list_schema_fields",
            "get_lineage",
            "get_lineage_paths_between",
            "get_dataset_queries",
        }
    )
    REQUIRED_MUTATION_TOOLS = frozenset({"save_document", "add_tags"})

    def __init__(
        self,
        gms_url: Optional[str] = None,
        token: Optional[str] = None,
        mcp_endpoint: Optional[str] = None,
        mcp_command: Optional[str] = None,
        mcp_args: Optional[Union[str, Iterable[str]]] = None,
        timeout: float = 10.0,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.gms_url = (gms_url or os.getenv("DATAHUB_GMS_URL", "http://localhost:8080")).rstrip("/")
        self.token = token if token is not None else os.getenv("DATAHUB_GMS_TOKEN", "")
        self.mcp_endpoint = mcp_endpoint or os.getenv("DATAHUB_MCP_ENDPOINT", "")
        if not self.mcp_endpoint:
            self.mcp_endpoint = f"{self.gms_url}/mcp"
        self.mcp_command = (mcp_command or os.getenv("DATAHUB_MCP_COMMAND", "")).strip()
        self.mcp_args = self._parse_command_args(
            mcp_args if mcp_args is not None else os.getenv("DATAHUB_MCP_ARGS", "[]")
        )
        self.timeout = timeout
        self.transport = transport

    @staticmethod
    def _parse_command_args(value: Union[str, Iterable[str]]) -> List[str]:
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError as exc:
                raise ValueError("DATAHUB_MCP_ARGS must be a JSON array of strings") from exc
        else:
            parsed = list(value)
        if not isinstance(parsed, list) or not all(isinstance(item, str) for item in parsed):
            raise ValueError("DATAHUB_MCP_ARGS must be a JSON array of strings")
        return parsed

    @property
    def connection_key(self) -> str:
        if self.mcp_command:
            return json.dumps([self.mcp_command, *self.mcp_args])
        return self.mcp_endpoint

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json, text/event-stream"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    @staticmethod
    def _text_payload(text: str) -> Dict[str, Any]:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MCPResponseError("MCP text content was not serialized JSON") from exc
        if not isinstance(payload, dict):
            raise MCPResponseError("MCP structured payload must be a JSON object")
        return payload

    @classmethod
    def _normalize_call_result(cls, result: Any) -> Dict[str, Any]:
        if getattr(result, "isError", False):
            raise MCPResponseError("MCP tool returned isError=true")

        structured = getattr(result, "structuredContent", None)
        if isinstance(structured, dict) and structured:
            return cls._unwrap_result_envelope(structured)

        content_blocks = getattr(result, "content", None) or []
        text_blocks = [getattr(block, "text", None) for block in content_blocks]
        text_blocks = [value for value in text_blocks if isinstance(value, str) and value.strip()]
        if not text_blocks:
            raise MCPResponseError("MCP tool returned neither structuredContent nor text JSON")
        if len(text_blocks) != 1:
            raise MCPResponseError("MCP tool returned multiple text blocks; payload is ambiguous")
        return cls._unwrap_result_envelope(cls._text_payload(text_blocks[0]))

    @staticmethod
    def _unwrap_result_envelope(payload: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize FastMCP's wrapper for tools whose return type can be a list.

        DataHub's ``get_entities`` returns ``{"result": [...]}`` when called with
        multiple URNs, while dict-returning tools expose their payload directly.
        Sentinel keeps a mapping-shaped boundary and represents that list as
        ``{"results": [...]}``.
        """
        if set(payload) != {"result"}:
            return payload
        value = payload["result"]
        if isinstance(value, dict):
            return value
        if isinstance(value, list):
            return {"results": value}
        return payload

    async def _session_call(self, tool_name: Optional[str], arguments: Optional[Dict[str, Any]] = None) -> Any:
        """Run one fully negotiated SDK session.

        A fresh session is intentional: this client is used by short-lived API
        calls and must not reuse stale session IDs across investigations.
        """
        try:
            from mcp import ClientSession, StdioServerParameters
            from mcp.client.stdio import stdio_client
            from mcp.client.streamable_http import streamable_http_client
        except ImportError as exc:  # pragma: no cover - packaging failure
            raise RuntimeError("The official 'mcp' Python package is required") from exc

        if self.mcp_command:
            child_env = {
                "DATAHUB_GMS_URL": self.gms_url,
                "DATAHUB_GMS_TOKEN": self.token or "",
                "TOOLS_IS_MUTATION_ENABLED": os.getenv("TOOLS_IS_MUTATION_ENABLED", "false"),
                "TOOLS_IS_USER_ENABLED": os.getenv("TOOLS_IS_USER_ENABLED", "false"),
                "SAVE_DOCUMENT_TOOL_ENABLED": os.getenv("SAVE_DOCUMENT_TOOL_ENABLED", "true"),
                "DATAHUB_MCP_DOCUMENT_TOOLS_DISABLED": os.getenv(
                    "DATAHUB_MCP_DOCUMENT_TOOLS_DISABLED", "false"
                ),
            }
            server = StdioServerParameters(command=self.mcp_command, args=self.mcp_args, env=child_env)
            async with stdio_client(server) as (read, write):
                async with ClientSession(read, write) as session:
                    initialize_result = await session.initialize()
                    if tool_name is None:
                        tools_result = await session.list_tools()
                        return initialize_result, tools_result
                    return await session.call_tool(tool_name, arguments=arguments or {})

        timeout = httpx.Timeout(self.timeout, connect=min(self.timeout, 5.0))
        async with httpx.AsyncClient(
            headers=self._headers(),
            timeout=timeout,
            follow_redirects=True,
            transport=self.transport,
        ) as client:
            async with streamable_http_client(self.mcp_endpoint, http_client=client) as (read, write, _):
                async with ClientSession(read, write) as session:
                    initialize_result = await session.initialize()
                    if tool_name is None:
                        tools_result = await session.list_tools()
                        return initialize_result, tools_result
                    return await session.call_tool(tool_name, arguments=arguments or {})

    async def discover_tools(self) -> MCPConnectionResult:
        try:
            initialize_result, tools_result = await self._session_call(None)
            tool_names = [tool.name for tool in getattr(tools_result, "tools", [])]
            protocol_version = getattr(initialize_result, "protocolVersion", None)
            return MCPConnectionResult(
                connected=True,
                tools=tool_names,
                protocol_version=protocol_version,
            )
        except Exception as exc:
            logger.debug("DataHub MCP discovery failed: %s", exc)
            return MCPConnectionResult(connected=False, error_message=str(exc))

    async def check_connection(self, require_tools: bool = True) -> bool:
        result = await self.discover_tools()
        if not result.connected:
            return False
        return not require_tools or self.REQUIRED_READ_TOOLS.issubset(result.tools)

    def _provenance(
        self,
        tool_name: str,
        entity_urn: Optional[str],
        field_path: Optional[str],
        *,
        live: bool,
        reference: Optional[str] = None,
    ) -> EvidenceProvenance:
        return EvidenceProvenance(
            source_mode=IntegrationMode.LIVE_DATAHUB if live else IntegrationMode.DATAHUB_UNAVAILABLE,
            source_tool=tool_name,
            entity_urn=entity_urn,
            field_path=field_path,
            source_reference=reference,
            verified=live,
        )

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        entity_urn: Optional[str] = None,
        field_path: Optional[str] = None,
    ) -> MCPToolResult:
        try:
            result = await self._session_call(tool_name, arguments)
            payload = self._normalize_call_result(result)
            return MCPToolResult(
                tool_name=tool_name,
                success=True,
                content=payload,
                provenance=self._provenance(tool_name, entity_urn, field_path, live=True),
            )
        except MCPResponseError as exc:
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                error_message=str(exc),
                is_error=True,
                provenance=self._provenance(tool_name, entity_urn, field_path, live=True),
            )
        except Exception as exc:
            logger.debug("DataHub MCP call %s failed: %s", tool_name, exc)
            return MCPToolResult(
                tool_name=tool_name,
                success=False,
                error_message=str(exc),
                provenance=self._provenance(tool_name, entity_urn, field_path, live=False),
            )

    async def get_entities(self, urns: List[str]) -> MCPToolResult:
        return await self.call_tool("get_entities", {"urns": urns}, entity_urn=urns[0] if urns else None)

    async def list_schema_fields(
        self, dataset_urn: str, *, query: Optional[str] = None, max_results: int = 100, offset: int = 0
    ) -> MCPToolResult:
        args: Dict[str, Any] = {"urn": dataset_urn, "limit": max_results, "offset": offset}
        if query:
            args["keywords"] = [query]
        return await self.call_tool("list_schema_fields", args, entity_urn=dataset_urn)

    async def get_lineage(
        self,
        dataset_urn: str,
        *,
        upstream: bool = False,
        max_hops: int = 3,
        max_results: int = 100,
        offset: int = 0,
        column: Optional[str] = None,
    ) -> MCPToolResult:
        args: Dict[str, Any] = {
            "urn": dataset_urn,
            "upstream": upstream,
            "max_hops": max_hops,
            "max_results": max_results,
            "offset": offset,
        }
        if column:
            args["column"] = column
        return await self.call_tool("get_lineage", args, entity_urn=dataset_urn, field_path=column)

    async def get_lineage_paths_between(
        self,
        source_urn: str,
        target_urn: str,
        *,
        source_column: Optional[str] = None,
        target_column: Optional[str] = None,
    ) -> MCPToolResult:
        args: Dict[str, Any] = {"source_urn": source_urn, "target_urn": target_urn}
        if source_column:
            args["source_column"] = source_column
        if target_column:
            args["target_column"] = target_column
        return await self.call_tool("get_lineage_paths_between", args, entity_urn=source_urn, field_path=source_column)

    async def get_dataset_queries(self, dataset_urn: str, *, column: Optional[str] = None) -> MCPToolResult:
        args: Dict[str, Any] = {"urn": dataset_urn}
        if column:
            args["column"] = column
        return await self.call_tool("get_dataset_queries", args, entity_urn=dataset_urn, field_path=column)

    async def save_document(
        self,
        *,
        document_type: str = "Analysis",
        title: str,
        content: str,
        related_assets: Optional[List[str]] = None,
        document_urn: Optional[str] = None,
    ) -> MCPToolResult:
        args: Dict[str, Any] = {
            "document_type": document_type,
            "title": title,
            "content": content,
        }
        if related_assets:
            args["related_assets"] = related_assets
        if document_urn:
            args["urn"] = document_urn
        result = await self.call_tool("save_document", args, entity_urn=document_urn)
        return self._validate_mutation_result(result)

    async def add_tags(
        self,
        *,
        tag_urns: List[str],
        entity_urns: List[str],
        column_paths: Optional[List[str]] = None,
    ) -> MCPToolResult:
        args: Dict[str, Any] = {"tag_urns": tag_urns, "entity_urns": entity_urns}
        if column_paths:
            args["column_paths"] = column_paths
        result = await self.call_tool("add_tags", args, entity_urn=entity_urns[0] if entity_urns else None)
        return self._validate_mutation_result(result)

    @staticmethod
    def _validate_mutation_result(result: MCPToolResult) -> MCPToolResult:
        """Treat an operation-level ``success: false`` as a failed mutation."""
        if result.success and result.content and result.content.get("success") is False:
            message = result.content.get("message")
            return result.model_copy(
                update={
                    "success": False,
                    "is_error": True,
                    "error_message": message if isinstance(message, str) else "DataHub mutation reported failure",
                }
            )
        return result
