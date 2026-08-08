import os
import time
import datetime
import logging
from enum import Enum
from typing import Dict, Any, List, Optional
import httpx
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
    entity_urn: str
    field_path: Optional[str] = None
    retrieved_at: str = Field(
        default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat()
    )
    source_reference: Optional[str] = None


class EntityOwner(BaseModel):
    owner_urn: str
    name: str
    email: str
    type: str = "TECHNICAL_OWNER"


class SchemaFieldMetadata(BaseModel):
    field_path: str
    type: str
    nullable: bool = True
    description: Optional[str] = None
    tags: List[str] = []


class DatasetMetadata(BaseModel):
    urn: str
    name: str
    platform: str
    description: str
    owners: List[EntityOwner] = []
    tags: List[str] = []
    domain: Optional[str] = None
    fields: List[SchemaFieldMetadata] = []
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
        self.token = token or settings.DATAHUB_GMS_TOKEN
        self.mcp_client = DataHubMCPClient(gms_url=self.gms_url, token=self.token)

    async def check_connection(self) -> bool:
        """Check if live DataHub GMS / MCP server is reachable."""
        now = time.time()
        if "connected" in self._connection_cache and (now - self._connection_cache.get("ts", 0) < 5.0):
            return self._connection_cache["connected"]

        connected = await self.mcp_client.check_connection()
        self._connection_cache["connected"] = connected
        self._connection_cache["ts"] = now
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

        if allow_fixture_fallback:
            return IntegrationMode.DEMO_FIXTURE

        return IntegrationMode.DATAHUB_UNAVAILABLE

    async def get_dataset(
        self, urn: str, allow_fixture_fallback: bool = False
    ) -> Optional[DatasetMetadata]:
        """Fetch dataset metadata including schema, owners, and tags via DataHub MCP."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_entities([urn])
            if res.success and res.content:
                return self._parse_mcp_dataset(urn, res.content)
            fields_res = await self.mcp_client.list_schema_fields(urn)
            if fields_res.success:
                return self._parse_mcp_fields_result(urn, fields_res.content)
            if not allow_fixture_fallback:
                return None
            mode = IntegrationMode.DEMO_FIXTURE

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
            res = await self.mcp_client.get_lineage(urn, direction="DOWNSTREAM", depth=max_depth)
            if res.success and res.content:
                parsed = []
                nodes = res.content.get("nodes", res.content.get("searchResults", []))
                for node in nodes:
                    entity_urn = node.get("urn", node.get("entity", {}).get("urn", ""))
                    e_type = node.get("type", node.get("entity", {}).get("type", "DATASET"))
                    name = node.get("name", entity_urn.split(",")[-2] if "," in entity_urn else entity_urn)
                    parsed.append({
                        "entity": entity_urn,
                        "type": e_type,
                        "name": name,
                        "platform": node.get("platform", "unknown"),
                        "depth": node.get("degree", 1),
                        "source_mode": IntegrationMode.LIVE_DATAHUB.value,
                        "source_tool": "get_lineage"
                    })
                return parsed
            if not allow_fixture_fallback:
                return []
            mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_downstream_lineage(urn)

        return []

    async def get_column_lineage(
        self, source_urn: str, source_field: str, allow_fixture_fallback: bool = False
    ) -> List[ColumnLineageEdge]:
        """Fetch fine-grained column-level lineage via DataHub MCP get_lineage."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_lineage(source_urn, direction="DOWNSTREAM", depth=3)
            if res.success and res.content:
                edges = []
                fine_lineages = res.content.get("fineGrainedLineages", [])
                for lin in fine_lineages:
                    upstreams = lin.get("upstreams", [])
                    downstreams = lin.get("downstreams", [])
                    if any(source_field in u for u in upstreams):
                        for d in downstreams:
                            target_urn = d.split("/schemaField/")[0]
                            target_field = d.split("/schemaField/")[-1] if "/schemaField/" in d else d
                            edges.append(ColumnLineageEdge(
                                source_urn=source_urn,
                                source_field=source_field,
                                target_urn=target_urn,
                                target_field=target_field,
                                provenance=DataHubProvenance(
                                    source_mode=IntegrationMode.LIVE_DATAHUB,
                                    source_tool="get_lineage",
                                    entity_urn=source_urn,
                                    field_path=source_field
                                )
                            ))
                return edges
            if not allow_fixture_fallback:
                return []
            mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_column_lineage(source_urn, source_field)

        return []

    async def get_dataset_queries(
        self, urn: str, field_name: Optional[str] = None, allow_fixture_fallback: bool = False
    ) -> List[QueryReference]:
        """Fetch historical query executions via DataHub MCP get_dataset_queries."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            res = await self.mcp_client.get_dataset_queries(urn)
            if res.success and res.content:
                queries_raw = res.content.get("queries", res.content.get("elements", []))
                parsed = []
                for q in queries_raw:
                    stmt = q.get("query_text", q.get("query", {}).get("properties", {}).get("statement", {}).get("value", ""))
                    if stmt and (not field_name or field_name.lower() in stmt.lower()):
                        # Honest storage: do NOT synthesize fake IDs or user timestamps if absent
                        parsed.append(QueryReference(
                            query_id=q.get("query_id"),
                            query_text=stmt,
                            last_executed=q.get("last_executed"),
                            user=q.get("user"),
                            provenance=DataHubProvenance(
                                source_mode=IntegrationMode.LIVE_DATAHUB,
                                source_tool="get_dataset_queries",
                                entity_urn=urn,
                                field_path=field_name
                            )
                        ))
                return parsed
            if not allow_fixture_fallback:
                return []
            mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_queries(urn, field_name)

        return []

    # --- DataHub MCP Result Parsers ---

    def _parse_mcp_dataset(self, urn: str, content: Dict[str, Any]) -> DatasetMetadata:
        entity = content.get("entity", content)
        fields = []
        for f in entity.get("fields", entity.get("schema", {}).get("fields", [])):
            fields.append(SchemaFieldMetadata(
                field_path=f.get("fieldPath", f.get("name", "")),
                type=f.get("nativeDataType", f.get("type", "STRING")),
                nullable=f.get("nullable", True),
                description=f.get("description", "")
            ))

        owners = []
        for o in entity.get("owners", []):
            owners.append(EntityOwner(
                owner_urn=o.get("owner", ""),
                name=o.get("name", o.get("owner", "").split(":")[-1]),
                email=o.get("email", ""),
                type=o.get("type", "TECHNICAL_OWNER")
            ))

        return DatasetMetadata(
            urn=urn,
            name=entity.get("name", urn.split(",")[-2] if "," in urn else urn),
            platform=entity.get("platform", urn.split(",")[0].split(":")[-1] if "," in urn else "unknown"),
            description=entity.get("description", "DataHub Catalog Asset"),
            owners=owners,
            tags=entity.get("tags", []),
            domain=entity.get("domain"),
            fields=fields,
            is_demo_fixture=False,
            provenance=DataHubProvenance(
                source_mode=IntegrationMode.LIVE_DATAHUB,
                source_tool="get_entities",
                entity_urn=urn
            )
        )

    def _parse_mcp_fields_result(self, urn: str, content: Dict[str, Any]) -> DatasetMetadata:
        raw_fields = content.get("fields", content.get("schemaFields", [])) if isinstance(content, dict) else []
        fields = [
            SchemaFieldMetadata(
                field_path=f.get("fieldPath", f.get("name", "")),
                type=f.get("type", "STRING"),
                nullable=f.get("nullable", True),
                description=f.get("description", "")
            )
            for f in raw_fields
        ]
        return DatasetMetadata(
            urn=urn,
            name=urn.split(",")[-2] if "," in urn else urn,
            platform="snowflake",
            description="DataHub Catalog Asset",
            fields=fields,
            is_demo_fixture=False,
            provenance=DataHubProvenance(
                source_mode=IntegrationMode.LIVE_DATAHUB,
                source_tool="list_schema_fields",
                entity_urn=urn
            )
        )

    # --- Explicit Demo Fixtures (Isolated & Explicitly Labeled) ---

    def _get_fixture_dataset(self, urn: str) -> DatasetMetadata:
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

        dataset_name = urn.split(",")[-2] if "," in urn else urn
        return DatasetMetadata(
            urn=urn,
            name=dataset_name,
            platform="snowflake",
            description=f"[DEMO FIXTURE] Default fixture metadata for {dataset_name}",
            owners=[EntityOwner(owner_urn="urn:li:corpuser:data.admin", name="Data Admin", email="data.admin@company.com")],
            tags=["Demo_Fixture"],
            fields=[],
            is_demo_fixture=True,
            provenance=DataHubProvenance(
                source_mode=IntegrationMode.DEMO_FIXTURE,
                source_tool="sentinel_demo_fixture_default",
                entity_urn=urn
            )
        )

    def _get_fixture_downstream_lineage(self, urn: str) -> List[Dict[str, Any]]:
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
