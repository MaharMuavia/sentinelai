import time
import datetime
import logging
from enum import Enum
from typing import Dict, Any, List, Optional
import httpx
from pydantic import BaseModel, Field
from app.config import settings

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
    query_id: str
    query_text: str
    last_executed: str
    user: str
    provenance: Optional[DataHubProvenance] = None


class DataHubClient:
    """
    Official DataHub MCP / Agent Context Integration Client.
    Provides typed, provenance-backed access to DataHub metadata, entity schemas,
    multi-hop lineage graphs, and historical query executions.
    Strictly distinguishes between LIVE_DATAHUB, DEMO_FIXTURE, and DATAHUB_UNAVAILABLE.
    """

    _connection_cache: Dict[str, Any] = {}

    def __init__(self, gms_url: Optional[str] = None, token: Optional[str] = None):
        self.gms_url = (gms_url or settings.DATAHUB_GMS_URL).rstrip("/")
        self.token = token or settings.DATAHUB_GMS_TOKEN
        self.headers = {"Content-Type": "application/json"}
        if self.token:
            self.headers["Authorization"] = f"Bearer {self.token}"

    async def check_connection(self) -> bool:
        """Check if live DataHub GMS instance is reachable."""
        now = time.time()
        if "connected" in self._connection_cache and (now - self._connection_cache.get("ts", 0) < 5.0):
            return self._connection_cache["connected"]

        connected = False
        try:
            async with httpx.AsyncClient(timeout=1.0) as client:
                res = await client.get(f"{self.gms_url}/health", headers=self.headers)
                connected = (res.status_code == 200)
        except Exception:
            connected = False

        self._connection_cache["connected"] = connected
        self._connection_cache["ts"] = now
        return connected

    async def get_integration_mode(self, allow_fixture_fallback: bool = True) -> IntegrationMode:
        if await self.check_connection():
            return IntegrationMode.LIVE_DATAHUB
        if allow_fixture_fallback:
            return IntegrationMode.DEMO_FIXTURE
        return IntegrationMode.DATAHUB_UNAVAILABLE

    async def get_dataset(
        self, urn: str, allow_fixture_fallback: bool = True
    ) -> Optional[DatasetMetadata]:
        """Fetch dataset metadata including schema, owners, and tags with full provenance."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    res = await client.get(
                        f"{self.gms_url}/entities/v2/dataset/{urn}",
                        headers=self.headers
                    )
                    if res.status_code == 200:
                        data = res.json()
                        return self._parse_live_dataset(urn, data)
            except Exception as e:
                logger.warning(f"Failed to fetch live dataset URN {urn} from DataHub: {e}")
                if not allow_fixture_fallback:
                    return None
                mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_dataset(urn)

        # DATAHUB_UNAVAILABLE: Return None (no silent fake data creation)
        return None

    async def get_downstream_lineage(
        self, urn: str, max_depth: int = 3, allow_fixture_fallback: bool = True
    ) -> List[Dict[str, Any]]:
        """Fetch downstream lineage graph for the dataset."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    query = """
                    query searchAcrossLineage($urn: String!) {
                        searchAcrossLineage(input: { urn: $urn, direction: DOWNSTREAM, types: ["dataset", "dashboard", "mlModel"], start: 0, count: 100 }) {
                            searchResults {
                                entity {
                                    urn
                                    type
                                    ... on Dataset { name platform { name } }
                                    ... on Dashboard { name tool }
                                    ... on MLModel { name platform { name } }
                                }
                                degree
                            }
                        }
                    }
                    """
                    res = await client.post(
                        f"{self.gms_url}/api/graphql",
                        json={"query": query, "variables": {"urn": urn}},
                        headers=self.headers
                    )
                    if res.status_code == 200:
                        data = res.json()
                        results = data.get("data", {}).get("searchAcrossLineage", {}).get("searchResults", [])
                        parsed = []
                        for r in results:
                            entity = r["entity"]
                            e_type = entity.get("type", "")
                            if e_type == "DATASET":
                                platform = entity.get("platform", {}).get("name", "unknown")
                            elif e_type == "DASHBOARD":
                                platform = entity.get("tool", "unknown")
                            elif e_type == "MLMODEL":
                                platform = entity.get("platform", {}).get("name", "unknown")
                            else:
                                platform = "unknown"

                            parsed.append({
                                "entity": entity.get("urn"),
                                "type": e_type,
                                "name": entity.get("name", entity.get("urn")),
                                "platform": platform,
                                "depth": r.get("degree", 1),
                                "source_mode": IntegrationMode.LIVE_DATAHUB.value,
                                "source_tool": "datahub_graphql_searchAcrossLineage"
                            })
                        return parsed
            except Exception as e:
                logger.warning(f"Failed to fetch live lineage for {urn}: {e}")
                if not allow_fixture_fallback:
                    return []
                mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_downstream_lineage(urn)

        return []

    async def get_column_lineage(
        self, source_urn: str, source_field: str, allow_fixture_fallback: bool = True
    ) -> List[ColumnLineageEdge]:
        """Fetch fine-grained column-level lineage with explicit provenance."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    query = """
                    query dataset($urn: String!) {
                        dataset(urn: $urn) {
                            fineGrainedLineages {
                                downstreamType
                                downstreams { urn }
                                upstreams { urn }
                            }
                        }
                    }
                    """
                    res = await client.post(
                        f"{self.gms_url}/api/graphql",
                        json={"query": query, "variables": {"urn": source_urn}},
                        headers=self.headers
                    )
                    if res.status_code == 200:
                        edges = []
                        data = res.json()
                        lineages = data.get("data", {}).get("dataset", {}).get("fineGrainedLineages", []) or []
                        for lin in lineages:
                            upstreams = [u["urn"] for u in lin.get("upstreams", [])]
                            downstreams = [d["urn"] for d in lin.get("downstreams", [])]
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
                                            source_tool="datahub_graphql_fineGrainedLineages",
                                            entity_urn=source_urn,
                                            field_path=source_field
                                        )
                                    ))
                        return edges
            except Exception as e:
                logger.warning(f"Live column lineage failed for {source_urn}: {e}")
                if not allow_fixture_fallback:
                    return []
                mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_column_lineage(source_urn, source_field)

        return []

    async def get_dataset_queries(
        self, urn: str, field_name: Optional[str] = None, allow_fixture_fallback: bool = True
    ) -> List[QueryReference]:
        """Fetch historical query executions referencing dataset and field."""
        mode = await self.get_integration_mode(allow_fixture_fallback)

        if mode == IntegrationMode.LIVE_DATAHUB:
            try:
                async with httpx.AsyncClient(timeout=5.0) as client:
                    query = """
                    query getQueries($urn: String!) {
                        dataset(urn: $urn) {
                            queries(start: 0, count: 10) {
                                elements {
                                    query {
                                        properties {
                                            statement { value }
                                        }
                                    }
                                }
                            }
                        }
                    }
                    """
                    res = await client.post(
                        f"{self.gms_url}/api/graphql",
                        json={"query": query, "variables": {"urn": urn}},
                        headers=self.headers
                    )
                    if res.status_code == 200:
                        parsed = []
                        data = res.json()
                        elements = data.get("data", {}).get("dataset", {}).get("queries", {}).get("elements", [])
                        for i, el in enumerate(elements):
                            stmt = el.get("query", {}).get("properties", {}).get("statement", {}).get("value", "")
                            if not field_name or field_name.lower() in stmt.lower():
                                parsed.append(QueryReference(
                                    query_id=f"q_live_{i}",
                                    query_text=stmt,
                                    last_executed=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                                    user="datahub_query_log",
                                    provenance=DataHubProvenance(
                                        source_mode=IntegrationMode.LIVE_DATAHUB,
                                        source_tool="datahub_graphql_dataset_queries",
                                        entity_urn=urn,
                                        field_path=field_name
                                    )
                                ))
                        return parsed
            except Exception as e:
                logger.warning(f"Live dataset queries failed for {urn}: {e}")
                if not allow_fixture_fallback:
                    return []
                mode = IntegrationMode.DEMO_FIXTURE

        if mode == IntegrationMode.DEMO_FIXTURE:
            return self._get_fixture_queries(urn, field_name)

        return []

    # --- Live DataHub Parsing Helper ---

    def _parse_live_dataset(self, urn: str, data: Dict[str, Any]) -> DatasetMetadata:
        aspects = data.get("aspects", {})

        fields = []
        schema_metadata = aspects.get("schemaMetadata", {})
        if schema_metadata and "value" in schema_metadata:
            for f in schema_metadata["value"].get("fields", []):
                fields.append(SchemaFieldMetadata(
                    field_path=f.get("fieldPath", ""),
                    type=f.get("nativeDataType", "STRING"),
                    nullable=f.get("nullable", True),
                    description=f.get("description", "")
                ))

        owners = []
        ownership = aspects.get("ownership", {})
        if ownership and "value" in ownership:
            for o in ownership["value"].get("owners", []):
                owners.append(EntityOwner(
                    owner_urn=o.get("owner", ""),
                    name=o.get("owner", "").split(":")[-1],
                    email="",
                    type=o.get("type", "TECHNICAL_OWNER")
                ))

        tags = []
        global_tags = aspects.get("globalTags", {})
        if global_tags and "value" in global_tags:
            for t in global_tags["value"].get("tags", []):
                tags.append(t.get("tag", "").replace("urn:li:tag:", ""))

        domain = None
        domains = aspects.get("domains", {})
        if domains and "value" in domains:
            domain_urns = domains["value"].get("domains", [])
            if domain_urns:
                domain = domain_urns[0].replace("urn:li:domain:", "")

        dataset_name = data.get("entityName", urn.split(",")[-2] if "," in urn else urn)

        return DatasetMetadata(
            urn=urn,
            name=dataset_name,
            platform=urn.split(",")[0].split(":")[-1] if "," in urn else "unknown",
            description=aspects.get("datasetProperties", {}).get("value", {}).get("description", "DataHub Catalog Asset"),
            owners=owners,
            tags=tags,
            domain=domain,
            fields=fields,
            is_demo_fixture=False,
            provenance=DataHubProvenance(
                source_mode=IntegrationMode.LIVE_DATAHUB,
                source_tool="datahub_gms_entities_v2",
                entity_urn=urn
            )
        )

    # --- Explicit Demo Fixtures (Isolated & Labeled) ---

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
