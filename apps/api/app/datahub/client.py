import os
import time
import datetime
import logging
from enum import Enum
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field
from app.config import settings
from app.datahub.mcp_client import DataHubMCPClient

logger = logging.getLogger("sentinel.datahub")


class IntegrationMode(str, Enum):
    LIVE_DATAHUB = "LIVE_DATAHUB"
    DEMO_FIXTURE = "DEMO_FIXTURE"
    DATAHUB_UNAVAILABLE = "DATAHUB_UNAVAILABLE"


class DataHubProvenance(BaseModel):
    source_mode: IntegrationMode
    source_tool: str
    entity_urn: Optional[str] = None
    field_path: Optional[str] = None
    retrieved_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    source_reference: Optional[str] = None


class EntityOwner(BaseModel):
    owner_urn: str
    name: Optional[str] = None
    email: Optional[str] = None
    type: str = "TECHNICAL_OWNER"


class SchemaFieldMetadata(BaseModel):
    field_path: str
    type: Optional[str] = None
    nullable: bool = True
    description: Optional[str] = None
    tags: List[str] = Field(default_factory=list)


class DatasetMetadata(BaseModel):
    urn: str
    name: str
    platform: Optional[str] = None
    description: Optional[str] = None
    owners: List[EntityOwner] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    domain: Optional[str] = None
    fields: List[SchemaFieldMetadata] = Field(default_factory=list)
    schema_verified: bool = False
    ownership_verified: bool = False
    tags_verified: bool = False
    is_demo_fixture: bool = False
    provenance: Optional[DataHubProvenance] = None


class ColumnLineageEdge(BaseModel):
    source_urn: str
    source_field: str
    target_urn: str
    target_field: str
    provenance: Optional[DataHubProvenance] = None


class QueryReference(BaseModel):
    query_id: Optional[str] = None
    query_text: str
    last_executed: Optional[str] = None
    user: Optional[str] = None
    provenance: Optional[DataHubProvenance] = None


class DataHubClient:
    """
    Official DataHub MCP / Agent Context Integration Client.
    Provides typed, provenance-backed access to DataHub metadata, entity schemas,
    multi-hop lineage graphs, and historical query executions via JSON-RPC 2.0 MCP protocol.
    Strictly distinguishes between LIVE_DATAHUB, DEMO_FIXTURE, and DATAHUB_UNAVAILABLE.
    """

    _connection_cache: Dict[str, Any] = {}

    def __init__(self, gms_url: Optional[str] = None, token: Optional[str] = None):
        self.gms_url = (gms_url or settings.DATAHUB_GMS_URL).rstrip("/")
        self.token = token if token is not None else settings.DATAHUB_GMS_TOKEN
        self.mcp_client = DataHubMCPClient(
            gms_url=self.gms_url,
            token=self.token,
            mcp_endpoint=settings.DATAHUB_MCP_ENDPOINT,
            mcp_command=settings.DATAHUB_MCP_COMMAND,
            mcp_args=settings.DATAHUB_MCP_ARGS,
        )

    async def check_connection(self) -> bool:
        """Check if live DataHub GMS / MCP server is reachable."""
        now = time.time()
        cache_key = self.mcp_client.connection_key
        cached = self._connection_cache.get(cache_key)
        if cached and now - cached.get("ts", 0) < 5.0:
            return bool(cached["connected"])

        connected = await self.mcp_client.check_connection()
        self._connection_cache[cache_key] = {"connected": connected, "ts": now}
        return connected

    async def get_integration_mode(self, allow_fixture_fallback: bool = False) -> IntegrationMode:
        """
        Determines current integration mode based on config and connection.
        If SENTINEL_DATA_MODE == 'fixture', returns DEMO_FIXTURE.
        If SENTINEL_DATA_MODE == 'live', requires live DataHub GMS connection.
        If live connection fails and allow_fixture_fallback is False, returns DATAHUB_UNAVAILABLE.
        """
        configured_mode = os.getenv("SENTINEL_DATA_MODE", getattr(settings, "SENTINEL_DATA_MODE", "live")).lower()
        if configured_mode == "fixture":
            return IntegrationMode.DEMO_FIXTURE

        if await self.check_connection():
            return IntegrationMode.LIVE_DATAHUB

        return IntegrationMode.DATAHUB_UNAVAILABLE

    async def get_dataset(
        self, urn: str, allow_fixture_fallback: bool = False
    ) -> Optional[DatasetMetadata]:
        """Fetch dataset metadata including schema, owners, and tags via DataHub MCP."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_entities([urn])
            if res.success and res.content:
                try:
                    dataset = self._parse_mcp_dataset(urn, res.content, res.provenance.source_reference)
                except ValueError:
                    dataset = None
                if dataset:
                    fields_res = await self.mcp_client.list_schema_fields(urn)
                    if fields_res.success and fields_res.content:
                        try:
                            fields = self._parse_fields(fields_res.content)
                        except ValueError:
                            return None
                        dataset.fields = fields
                        dataset.schema_verified = bool(fields)
                    return dataset
            fields_res = await self.mcp_client.list_schema_fields(urn)
            if fields_res.success and fields_res.content:
                try:
                    return self._parse_mcp_fields_result(urn, fields_res.content, fields_res.provenance.source_reference)
                except ValueError:
                    return None
            return None

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_dataset(urn)

        # DATAHUB_UNAVAILABLE: Return None (no silent fake data creation)
        return None

    async def get_downstream_lineage(
        self, urn: str, max_depth: int = 3, allow_fixture_fallback: bool = False
    ) -> List[Dict[str, Any]]:
        """Fetch downstream lineage graph for the dataset via DataHub MCP get_lineage."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_lineage(urn, upstream=False, max_hops=max_depth)
            if res.success and res.content:
                parsed: List[Dict[str, Any]] = []
                downstreams = res.content.get("downstreams")
                lineage_payload = downstreams if isinstance(downstreams, dict) else res.content
                nodes = self._items(lineage_payload, "results", "searchResults", "nodes", "entities")
                for node in nodes:
                    entity = node.get("entity") if isinstance(node.get("entity"), dict) else node
                    entity_urn = entity.get("urn") or node.get("urn")
                    if not entity_urn:
                        continue
                    e_type = entity.get("type") or node.get("type") or "DATASET"
                    name = entity.get("name") or node.get("name") or self._urn_name(entity_urn)
                    parsed.append({
                        "entity": entity_urn,
                        "type": e_type,
                        "name": name,
                        "platform": entity.get("platform") or node.get("platform"),
                        "depth": node.get("degree", node.get("hops", 1)),
                        "source_mode": IntegrationMode.LIVE_DATAHUB.value,
                        "source_tool": "get_lineage",
                        "source_reference": res.provenance.source_reference,
                    })
                return parsed
            return []

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_downstream_lineage(urn)

        return []

    async def get_column_lineage(
        self, source_urn: str, source_field: str, allow_fixture_fallback: bool = False
    ) -> List[ColumnLineageEdge]:
        """Fetch fine-grained column-level lineage via DataHub MCP get_lineage."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_lineage(source_urn, upstream=False, max_hops=3, column=source_field)
            if res.success and res.content:
                edges = self._parse_column_lineage(source_urn, source_field, res.content, res.provenance.source_reference)
                return edges
            return []

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_column_lineage(source_urn, source_field)

        return []

    async def get_dataset_queries(
        self, urn: str, field_name: Optional[str] = None, allow_fixture_fallback: bool = False
    ) -> List[QueryReference]:
        """Fetch historical query executions via DataHub MCP get_dataset_queries."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_dataset_queries(urn, column=field_name)
            if res.success and res.content:
                queries_raw = self._items(res.content, "queries", "results", "elements")
                parsed = []
                for q in queries_raw:
                    properties = q.get("properties") if isinstance(q.get("properties"), dict) else {}
                    stmt = (
                        q.get("query_text")
                        or q.get("query")
                        or q.get("statement")
                        or properties.get("statement")
                    )
                    if isinstance(stmt, dict):
                        stmt = stmt.get("value") or stmt.get("text") or stmt.get("statement")
                        if isinstance(stmt, dict):
                            stmt = stmt.get("value") or stmt.get("text")
                    if stmt and (not field_name or field_name.lower() in stmt.lower()):
                        # Honest storage: do NOT synthesize fake IDs or user timestamps if absent
                        last_modified = properties.get("lastModified")
                        if not isinstance(last_modified, dict):
                            last_modified = {}
                        parsed.append(QueryReference(
                            query_id=q.get("query_id") or q.get("urn"),
                            query_text=stmt,
                            last_executed=q.get("last_executed") or properties.get("lastExecuted"),
                            user=q.get("user") or last_modified.get("actor"),
                            provenance=DataHubProvenance(
                                source_mode=IntegrationMode.LIVE_DATAHUB,
                                source_tool="get_dataset_queries",
                                entity_urn=urn,
                                field_path=field_name,
                                source_reference=res.provenance.source_reference,
                            )
                        ))
                return parsed
            return []

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_queries(urn, field_name)

        return []

    async def verify_exact_lineage_path(
        self,
        source_urn: str,
        target_urn: str,
        source_field: Optional[str] = None,
        target_field: Optional[str] = None,
    ) -> bool:
        """Return true only when the exact-path MCP operation returns a matching path."""
        return await self.get_exact_lineage_path_provenance(
            source_urn,
            target_urn,
            source_field,
            target_field,
        ) is not None

    async def get_exact_lineage_path_provenance(
        self,
        source_urn: str,
        target_urn: str,
        source_field: Optional[str] = None,
        target_field: Optional[str] = None,
    ) -> Optional[DataHubProvenance]:
        """Return provenance only when the exact-path MCP result actually matches."""
        if await self.get_integration_mode(False) != IntegrationMode.LIVE_DATAHUB:
            return None
        result = await self.mcp_client.get_lineage_paths_between(
            source_urn,
            target_urn,
            source_column=source_field,
            target_column=target_field,
        )
        if not result.success or not result.content:
            return None
        path_values = result.content.get("paths") or result.content.get("results") or result.content.get("lineagePaths") or []
        if isinstance(path_values, dict):
            path_values = [path_values]
        if not isinstance(path_values, list):
            return None
        for path in path_values:
            if self._path_matches(path, source_urn, target_urn, source_field, target_field):
                return DataHubProvenance(
                    source_mode=IntegrationMode.LIVE_DATAHUB,
                    source_tool="get_lineage_paths_between",
                    entity_urn=source_urn,
                    field_path=source_field,
                    source_reference=result.provenance.source_reference,
                )
        return None

    @classmethod
    def _path_matches(
        cls,
        path: Dict[str, Any],
        source_urn: str,
        target_urn: str,
        source_field: Optional[str],
        target_field: Optional[str],
    ) -> bool:
        values: List[Any] = path.get("path", path.get("nodes", [])) if isinstance(path, dict) else []
        if not values and isinstance(path, list):
            values = path
        refs = [cls._schema_field_ref(value) for value in values]
        refs = [ref for ref in refs if ref]
        urns = [ref[0] for ref in refs]
        if source_urn not in urns or target_urn not in urns:
            return False
        if source_field and not any(ref[0] == source_urn and ref[1].lower() == source_field.lower() for ref in refs):
            return False
        if target_field and not any(ref[0] == target_urn and ref[1].lower() == target_field.lower() for ref in refs):
            return False
        return True

    # --- DataHub MCP Result Parsers ---

    @staticmethod
    def _urn_name(urn: str) -> str:
        return urn.split(",")[-2] if "," in urn else urn

    @staticmethod
    def _items(content: Dict[str, Any], *keys: str) -> List[Dict[str, Any]]:
        for key in keys:
            value = content.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
        return []

    @staticmethod
    def _tag_urn(tag: Any) -> Optional[str]:
        if isinstance(tag, str):
            return tag
        if isinstance(tag, dict):
            value = tag.get("tag") or tag.get("urn") or tag.get("tag_urn")
            if isinstance(value, dict):
                return DataHubClient._tag_urn(value)
            return value if isinstance(value, str) else None
        return None

    def _parse_fields(self, content: Dict[str, Any]) -> List[SchemaFieldMetadata]:
        raw_fields = self._items(content, "fields", "schemaFields", "results")
        fields: List[SchemaFieldMetadata] = []
        for field in raw_fields:
            field_path = field.get("fieldPath") or field.get("field_path") or field.get("name")
            if not field_path:
                continue
            fields.append(SchemaFieldMetadata(
                field_path=field_path,
                type=self._field_type(field),
                nullable=field.get("nullable", True),
                description=field.get("description"),
                tags=[tag for tag in (self._tag_urn(t) for t in field.get("tags", [])) if tag],
            ))
        if raw_fields and not fields:
            raise ValueError("Schema response contained no valid field records")
        return fields

    @staticmethod
    def _field_type(field: Dict[str, Any]) -> Optional[str]:
        value = field.get("nativeDataType") or field.get("native_datatype") or field.get("type")
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            nested = value.get("name") or value.get("type") or value.get("nativeDataType")
            return nested if isinstance(nested, str) else None
        return None

    def _parse_mcp_dataset(self, urn: str, content: Dict[str, Any], source_reference: Optional[str] = None) -> DatasetMetadata:
        entities = self._items(content, "entities", "results")
        entity = content.get("entity") if isinstance(content.get("entity"), dict) else (entities[0] if entities else content)
        if not isinstance(entity, dict) or not any(key in entity for key in ("urn", "name", "platform", "fields", "schema", "description", "owners", "tags")):
            raise ValueError("get_entities response did not contain an entity payload")
        properties = entity.get("properties") if isinstance(entity.get("properties"), dict) else {}
        schema = entity.get("schemaMetadata") or entity.get("schema") or {}
        schema = schema if isinstance(schema, dict) else {}
        fields = self._parse_fields({"fields": entity.get("fields") or schema.get("fields", [])})

        owners = []
        ownership = entity.get("ownership") if isinstance(entity.get("ownership"), dict) else {}
        owner_values = entity.get("owners") or ownership.get("owners") or []
        for o in owner_values:
            if not isinstance(o, dict):
                continue
            owner = o.get("owner") if isinstance(o.get("owner"), dict) else {}
            owner_properties = owner.get("properties") or owner.get("editableProperties") or {}
            owner_urn = owner.get("urn") or o.get("owner") or o.get("owner_urn") or o.get("urn")
            if not owner_urn:
                continue
            owners.append(EntityOwner(
                owner_urn=owner_urn,
                name=o.get("name") or owner_properties.get("displayName") or owner_urn.split(":")[-1],
                email=o.get("email") or owner_properties.get("email"),
                type=o.get("type", "TECHNICAL_OWNER")
            ))

        tag_block = entity.get("tags")
        tag_values = tag_block.get("tags", []) if isinstance(tag_block, dict) else (tag_block or [])
        tags = [tag for tag in (self._tag_urn(t) for t in tag_values) if tag]
        platform = entity.get("platform")
        if isinstance(platform, dict):
            platform = platform.get("name") or platform.get("urn")
        domain = entity.get("domain")
        if isinstance(domain, dict):
            nested_domain = domain.get("domain") if isinstance(domain.get("domain"), dict) else {}
            domain = domain.get("urn") or domain.get("name") or nested_domain.get("urn") or nested_domain.get("name")

        return DatasetMetadata(
            urn=urn,
            name=entity.get("name") or properties.get("name") or self._urn_name(urn),
            platform=platform,
            description=entity.get("description") or properties.get("description"),
            owners=owners,
            tags=tags,
            domain=domain,
            fields=fields,
            schema_verified=bool(fields),
            ownership_verified=bool(owners),
            tags_verified="tags" in entity,
            is_demo_fixture=False,
            provenance=DataHubProvenance(
                source_mode=IntegrationMode.LIVE_DATAHUB,
                source_tool="get_entities",
                entity_urn=urn,
                source_reference=source_reference,
            )
        )

    def _parse_mcp_fields_result(self, urn: str, content: Dict[str, Any], source_reference: Optional[str] = None) -> DatasetMetadata:
        fields = self._parse_fields(content)
        if not fields:
            raise ValueError("list_schema_fields response did not contain valid fields")
        return DatasetMetadata(
            urn=urn,
            name=urn.split(",")[-2] if "," in urn else urn,
            platform="snowflake",
            description=None,
            fields=fields,
            schema_verified=bool(fields),
            is_demo_fixture=False,
            provenance=DataHubProvenance(
                source_mode=IntegrationMode.LIVE_DATAHUB,
                source_tool="list_schema_fields",
                entity_urn=urn,
                source_reference=source_reference,
            )
        )

    def _parse_column_lineage(
        self, source_urn: str, source_field: str, content: Dict[str, Any], source_reference: Optional[str]
    ) -> List[ColumnLineageEdge]:
        """Parse DataHub MCP lineage results, whose column paths are lists of schema-field URNs."""
        edges: List[ColumnLineageEdge] = []
        downstreams = content.get("downstreams")
        lineage_payload = downstreams if isinstance(downstreams, dict) else content
        for result in self._items(lineage_payload, "results", "searchResults", "nodes"):
            entity = result.get("entity") if isinstance(result.get("entity"), dict) else {}
            target_urn = entity.get("urn") or result.get("urn")
            lineage_columns = result.get("lineageColumns") or []
            if isinstance(target_urn, str) and isinstance(lineage_columns, list):
                for target_field in lineage_columns:
                    if not isinstance(target_field, str):
                        continue
                    edges.append(ColumnLineageEdge(
                        source_urn=source_urn,
                        source_field=source_field,
                        target_urn=target_urn,
                        target_field=target_field,
                        provenance=DataHubProvenance(
                            source_mode=IntegrationMode.LIVE_DATAHUB,
                            source_tool="get_lineage",
                            entity_urn=source_urn,
                            field_path=source_field,
                            source_reference=source_reference,
                        ),
                    ))
            path_groups = result.get("paths") or result.get("lineagePaths") or []
            for path in path_groups:
                if not isinstance(path, list) or len(path) < 2:
                    continue
                refs = [self._schema_field_ref(value) for value in path]
                refs = [ref for ref in refs if ref]
                for (left_urn, left_field), (right_urn, right_field) in zip(refs, refs[1:]):
                    if left_urn == source_urn and left_field.lower() == source_field.lower():
                        edges.append(ColumnLineageEdge(
                            source_urn=left_urn,
                            source_field=left_field,
                            target_urn=right_urn,
                            target_field=right_field,
                            provenance=DataHubProvenance(
                                source_mode=IntegrationMode.LIVE_DATAHUB,
                                source_tool="get_lineage",
                                entity_urn=source_urn,
                                field_path=source_field,
                                source_reference=source_reference,
                            ),
                        ))
        return edges

    @staticmethod
    def _schema_field_ref(value: Any) -> Optional[tuple[str, str]]:
        if isinstance(value, dict):
            parent = value.get("parent") if isinstance(value.get("parent"), dict) else {}
            dataset_urn = value.get("dataset_urn") or parent.get("urn")
            field_path = value.get("fieldPath") or value.get("field_path") or value.get("column")
            if isinstance(dataset_urn, str) and isinstance(field_path, str):
                return dataset_urn, field_path
            return None
        if not isinstance(value, str):
            return None
        marker = ","
        if value.startswith("urn:li:schemaField:(") and value.endswith(")"):
            inner = value[len("urn:li:schemaField:("):-1]
            split_at = inner.rfind(marker)
            if split_at > 0:
                return inner[:split_at], inner[split_at + 1:]
        if "/schemaField/" in value:
            return tuple(value.split("/schemaField/", 1))
        return None

    # --- Explicit Demo Fixtures (Isolated & Explicitly Labeled) ---

    def _get_fixture_dataset(self, urn: str) -> Optional[DatasetMetadata]:
        mock_db = {
            "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)": DatasetMetadata(
                urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
                name="raw_customers",
                platform="snowflake",
                description="[DEMO FIXTURE] Raw ingested customer identity and contact records from Salesforce",
                owners=[EntityOwner(owner_urn="urn:li:corpuser:sarah.data", name="Sarah Chen", email="sarah.chen@company.com")],
                tags=["PII", "Core_Entity", "Tier_1"],
                domain="Customer_Analytics",
                fields=[
                    SchemaFieldMetadata(field_path="customer_id", type="STRING", nullable=False, description="Primary customer key"),
                    SchemaFieldMetadata(field_path="email", type="STRING", nullable=True, description="Customer primary email address", tags=["PII"]),
                    SchemaFieldMetadata(field_path="country", type="STRING", nullable=True, description="ISO country code"),
                    SchemaFieldMetadata(field_path="created_at", type="TIMESTAMP", nullable=False, description="Record creation timestamp")
                ],
                is_demo_fixture=True,
                provenance=DataHubProvenance(
                    source_mode=IntegrationMode.DEMO_FIXTURE,
                    source_tool="sentinel_demo_fixture_db",
                    entity_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
                    source_reference="demo_fixtures/raw_customers.json"
                )
            ),
            "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)": DatasetMetadata(
                urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                name="customer_360",
                platform="dbt",
                description="[DEMO FIXTURE] Normalized 360 customer analytical view",
                owners=[EntityOwner(owner_urn="urn:li:corpuser:alex.lead", name="Alex Rodriguez", email="alex.rodriguez@company.com")],
                tags=["Tier_1", "Production_Model"],
                domain="Customer_Analytics",
                fields=[
                    SchemaFieldMetadata(field_path="customer_id", type="STRING", nullable=False),
                    SchemaFieldMetadata(field_path="email", type="STRING", nullable=True, tags=["PII"]),
                    SchemaFieldMetadata(field_path="country", type="STRING", nullable=True),
                    SchemaFieldMetadata(field_path="lifetime_value", type="NUMERIC", nullable=True)
                ],
                is_demo_fixture=True,
                provenance=DataHubProvenance(
                    source_mode=IntegrationMode.DEMO_FIXTURE,
                    source_tool="sentinel_demo_fixture_db",
                    entity_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                    source_reference="demo_fixtures/customer_360.json"
                )
            ),
            "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)": DatasetMetadata(
                urn="urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
                name="marketing_dashboard",
                platform="looker",
                description="[DEMO FIXTURE] Exec Marketing Campaign & Attribution Performance Dashboard",
                owners=[EntityOwner(owner_urn="urn:li:corpuser:emily.marketing", name="Emily Watson", email="emily.watson@company.com")],
                tags=["Executive_Tier", "Critical_Dashboard"],
                domain="Marketing",
                fields=[],
                is_demo_fixture=True,
                provenance=DataHubProvenance(
                    source_mode=IntegrationMode.DEMO_FIXTURE,
                    source_tool="sentinel_demo_fixture_db",
                    entity_urn="urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)"
                )
            ),
            "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)": DatasetMetadata(
                urn="urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
                name="churn_features",
                platform="dbt",
                description="[DEMO FIXTURE] Feature store dataset for customer churn prediction model",
                owners=[EntityOwner(owner_urn="urn:li:corpuser:david.ml", name="David Kim", email="david.kim@company.com")],
                tags=["ML_Feature_Store", "Tier_1"],
                domain="Data_Science",
                fields=[
                    SchemaFieldMetadata(field_path="customer_id", type="STRING", nullable=False),
                    SchemaFieldMetadata(field_path="email_domain", type="STRING", nullable=True)
                ],
                is_demo_fixture=True,
                provenance=DataHubProvenance(
                    source_mode=IntegrationMode.DEMO_FIXTURE,
                    source_tool="sentinel_demo_fixture_db",
                    entity_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)"
                )
            ),
            "urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)": DatasetMetadata(
                urn="urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)",
                name="churn_model",
                platform="mlflow",
                description="[DEMO FIXTURE] Production Customer Churn Risk Classification Model v2.4",
                owners=[EntityOwner(owner_urn="urn:li:corpuser:david.ml", name="David Kim", email="david.kim@company.com")],
                tags=["Production_ML", "Critical_Model"],
                domain="Data_Science",
                fields=[],
                is_demo_fixture=True,
                provenance=DataHubProvenance(
                    source_mode=IntegrationMode.DEMO_FIXTURE,
                    source_tool="sentinel_demo_fixture_db",
                    entity_urn="urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)"
                )
            ),
            "urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)": DatasetMetadata(
                urn="urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)",
                name="billing_dashboard",
                platform="looker",
                description="[DEMO FIXTURE] Monthly Finance & Invoicing Metrics Dashboard",
                owners=[EntityOwner(owner_urn="urn:li:corpuser:finance.team", name="Finance Team", email="finance@company.com")],
                tags=["Finance"],
                domain="Finance",
                fields=[],
                is_demo_fixture=True,
                provenance=DataHubProvenance(
                    source_mode=IntegrationMode.DEMO_FIXTURE,
                    source_tool="sentinel_demo_fixture_db",
                    entity_urn="urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)"
                )
            )
        }

        for key, val in mock_db.items():
            if urn.lower() in key.lower() or key.lower() in urn.lower():
                return val

        return None

    def _get_fixture_downstream_lineage(self, urn: str) -> List[Dict[str, Any]]:
        raw_urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
        if urn != raw_urn:
            return []
        return [
            {
                "entity": "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                "type": "DATASET",
                "name": "customer_360",
                "platform": "dbt",
                "depth": 1,
                "parent_urn": urn,
                "source_mode": IntegrationMode.DEMO_FIXTURE.value,
                "source_tool": "sentinel_demo_lineage_graph"
            },
            {
                "entity": "urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
                "type": "DASHBOARD",
                "name": "marketing_dashboard",
                "platform": "looker",
                "depth": 2,
                "parent_urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                "source_mode": IntegrationMode.DEMO_FIXTURE.value,
                "source_tool": "sentinel_demo_lineage_graph"
            },
            {
                "entity": "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
                "type": "DATASET",
                "name": "churn_features",
                "platform": "dbt",
                "depth": 2,
                "parent_urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                "source_mode": IntegrationMode.DEMO_FIXTURE.value,
                "source_tool": "sentinel_demo_lineage_graph"
            },
            {
                "entity": "urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)",
                "type": "ML_MODEL",
                "name": "churn_model",
                "platform": "mlflow",
                "depth": 3,
                "parent_urn": "urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
                "source_mode": IntegrationMode.DEMO_FIXTURE.value,
                "source_tool": "sentinel_demo_lineage_graph"
            },
            {
                "entity": "urn:li:dataset:(urn:li:dataPlatform:looker,billing_dashboard,PROD)",
                "type": "DASHBOARD",
                "name": "billing_dashboard",
                "platform": "looker",
                "depth": 2,
                "parent_urn": urn,
                "source_mode": IntegrationMode.DEMO_FIXTURE.value,
                "source_tool": "sentinel_demo_lineage_graph"
            }
        ]

    def _get_fixture_column_lineage(self, source_urn: str, source_field: str) -> List[ColumnLineageEdge]:
        if "email" in source_field.lower():
            return [
                ColumnLineageEdge(
                    source_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
                    source_field="email",
                    target_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                    target_field="email",
                    provenance=DataHubProvenance(
                        source_mode=IntegrationMode.DEMO_FIXTURE,
                        source_tool="sentinel_demo_column_lineage",
                        entity_urn=source_urn,
                        field_path=source_field
                    )
                ),
                ColumnLineageEdge(
                    source_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                    source_field="email",
                    target_urn="urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
                    target_field="customer_email",
                    provenance=DataHubProvenance(
                        source_mode=IntegrationMode.DEMO_FIXTURE,
                        source_tool="sentinel_demo_column_lineage",
                        entity_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                        field_path="email"
                    )
                ),
                ColumnLineageEdge(
                    source_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                    source_field="email",
                    target_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
                    target_field="email_domain",
                    provenance=DataHubProvenance(
                        source_mode=IntegrationMode.DEMO_FIXTURE,
                        source_tool="sentinel_demo_column_lineage",
                        entity_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,customer_360,PROD)",
                        field_path="email"
                    )
                ),
                ColumnLineageEdge(
                    source_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
                    source_field="email_domain",
                    target_urn="urn:li:dataset:(urn:li:dataPlatform:mlflow,churn_model,PROD)",
                    target_field="feature_email_domain",
                    provenance=DataHubProvenance(
                        source_mode=IntegrationMode.DEMO_FIXTURE,
                        source_tool="sentinel_demo_column_lineage",
                        entity_urn="urn:li:dataset:(urn:li:dataPlatform:dbt,churn_features,PROD)",
                        field_path="email_domain"
                    )
                )
            ]
        return []

    def _get_fixture_queries(self, urn: str, field_name: Optional[str] = None) -> List[QueryReference]:
        if field_name and "email" in field_name.lower():
            return [
                QueryReference(
                    query_id="q_fixture_109283",
                    query_text="SELECT customer_id, email, lifetime_value FROM customer_360 WHERE email IS NOT NULL;",
                    last_executed="2026-08-07T18:30:00Z",
                    user="marketing_etl_service",
                    provenance=DataHubProvenance(
                        source_mode=IntegrationMode.DEMO_FIXTURE,
                        source_tool="sentinel_demo_query_log",
                        entity_urn=urn,
                        field_path=field_name
                    )
                ),
                QueryReference(
                    query_id="q_fixture_109455",
                    query_text="SELECT LOWER(SPLIT_PART(email, '@', 2)) as email_domain FROM customer_360;",
                    last_executed="2026-08-08T06:15:00Z",
                    user="ml_pipeline_worker",
                    provenance=DataHubProvenance(
                        source_mode=IntegrationMode.DEMO_FIXTURE,
                        source_tool="sentinel_demo_query_log",
                        entity_urn=urn,
                        field_path=field_name
                    )
                )
            ]
        return []
