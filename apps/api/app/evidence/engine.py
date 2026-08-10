from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional, Set, Tuple

from pydantic import BaseModel, Field

from app.datahub.client import (
    ColumnLineageEdge,
    DataHubClient,
    DataHubProvenance,
    IntegrationMode,
)
from app.schema_engine.diff import ChangeSet


class ImpactClassification(str, Enum):
    CONFIRMED_IMPACT = "CONFIRMED_IMPACT"
    LIKELY_IMPACT = "LIKELY_IMPACT"
    POTENTIAL_IMPACT = "POTENTIAL_IMPACT"
    UNLIKELY_IMPACT = "UNLIKELY_IMPACT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class EvidenceType(str, Enum):
    COLUMN_LINEAGE = "COLUMN_LINEAGE"
    QUERY_USAGE = "QUERY_USAGE"
    TABLE_LINEAGE = "TABLE_LINEAGE"
    METADATA_TAG = "METADATA_TAG"
    EXACT_LINEAGE_PATH = "EXACT_LINEAGE_PATH"


class EvidenceItem(BaseModel):
    id: str
    type: EvidenceType
    source_field: Optional[str] = None
    target_field: Optional[str] = None
    query_reference: Optional[str] = None
    description: str
    provenance: Optional[DataHubProvenance] = None


class AssetImpact(BaseModel):
    asset_urn: str
    name: str
    platform: Optional[str] = None
    asset_type: str
    classification: ImpactClassification
    owners: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    hop_count: int = 1
    evidence: List[EvidenceItem] = Field(default_factory=list)
    provenance: Optional[DataHubProvenance] = None


class EvidenceGraphNode(BaseModel):
    id: str
    label: str
    type: str
    platform: Optional[str] = None
    classification: ImpactClassification
    owners: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    is_demo_fixture: bool = False
    provenance: Optional[DataHubProvenance] = None


class EvidenceGraphEdge(BaseModel):
    source: str
    target: str
    lineage_type: str
    field_mapping: Optional[str] = None
    hop_count: int = 1
    evidence_source: str
    provenance: Optional[DataHubProvenance] = None


class EvidenceGraph(BaseModel):
    nodes: List[EvidenceGraphNode]
    edges: List[EvidenceGraphEdge]


class ImpactEvidenceBundle(BaseModel):
    dataset_urn: str
    dataset_name: str
    integration_mode: IntegrationMode
    changes: ChangeSet
    classified_assets: List[AssetImpact]
    graph: EvidenceGraph
    confirmed_consumers_count: int
    potential_consumers_count: int
    has_sufficient_evidence: Optional[bool] = None
    schema_verified: Optional[bool] = None
    column_lineage_available: Optional[bool] = None
    query_usage_available: Optional[bool] = None
    ownership_assigned: Optional[bool] = None
    exact_lineage_path_verified: Optional[bool] = None
    evidence_provenance_summary: List[str] = Field(default_factory=list)


class ImpactEvidenceEngine:
    def __init__(self, datahub_client: DataHubClient):
        self.dh = datahub_client

    async def analyze_impact(self, changes: ChangeSet, allow_fixture_fallback: bool = False) -> ImpactEvidenceBundle:
        dataset_urn = changes.dataset_urn
        mode = await self.dh.get_integration_mode(False)
        base_dataset = await self.dh.get_dataset(dataset_urn, allow_fixture_fallback=False)
        dataset_name = base_dataset.name if base_dataset else self._urn_name(dataset_urn)
        downstream_nodes = await self.dh.get_downstream_lineage(dataset_urn, max_depth=3, allow_fixture_fallback=False)

        graph_nodes: List[EvidenceGraphNode] = [EvidenceGraphNode(
            id=dataset_urn,
            label=dataset_name,
            type="CHANGED_DATASET",
            platform=base_dataset.platform if base_dataset else None,
            classification=ImpactClassification.CONFIRMED_IMPACT,
            owners=[o.name for o in base_dataset.owners if o.name] if base_dataset else [],
            tags=base_dataset.tags if base_dataset else [],
            is_demo_fixture=bool(base_dataset and base_dataset.is_demo_fixture),
            provenance=base_dataset.provenance if base_dataset else None,
        )]
        graph_edges: List[EvidenceGraphEdge] = []
        classified_assets: List[AssetImpact] = []
        provenance_sources: Set[str] = set()
        for provenance in [base_dataset.provenance if base_dataset else None]:
            if provenance:
                provenance_sources.add(f"{provenance.source_mode.value}:{provenance.source_tool}")

        parent_by_urn = {
            node["entity"]: node.get("parent_urn", dataset_urn)
            for node in downstream_nodes
            if node.get("entity")
        }
        breaking_fields = [change.field for change in changes.changes if change.is_breaking]
        lineage_cache: Dict[str, List[ColumnLineageEdge]] = {}
        query_cache: Dict[str, list] = {}
        exact_cache: Dict[Tuple[str, str, Optional[str], Optional[str]], Optional[DataHubProvenance]] = {}
        column_available = False
        query_available = False
        exact_available = False

        for node_info in downstream_nodes:
            target_urn = node_info.get("entity")
            if not target_urn:
                continue
            target_name = node_info.get("name") or self._urn_name(target_urn)
            target_meta = await self.dh.get_dataset(target_urn, allow_fixture_fallback=False)
            target_prov = target_meta.provenance if target_meta else None
            lineage_prov = self._lineage_provenance(node_info, target_urn, mode)
            node_prov = target_prov or lineage_prov
            if node_prov:
                provenance_sources.add(f"{node_prov.source_mode.value}:{node_prov.source_tool}")

            evidence_items: List[EvidenceItem] = []
            field_mappings: List[str] = []
            column_match = False
            query_match = False
            exact_match = False
            for source_field in breaking_fields:
                if source_field not in lineage_cache:
                    lineage_cache[source_field] = await self.dh.get_column_lineage(dataset_urn, source_field, False)
                col_edges = lineage_cache[source_field]
                column_available = column_available or bool(col_edges)
                matching_edges = [edge for edge in col_edges if edge.target_urn == target_urn]
                for edge in matching_edges:
                    column_match = True
                    field_mappings.append(f"{edge.source_field} -> {edge.target_field}")
                    evidence_items.append(EvidenceItem(
                        id=f"ev_col_{len(evidence_items) + 1}",
                        type=EvidenceType.COLUMN_LINEAGE,
                        source_field=edge.source_field,
                        target_field=edge.target_field,
                        description=f"Verified field lineage: {dataset_name}.{edge.source_field} -> {target_name}.{edge.target_field}",
                        provenance=edge.provenance,
                    ))
                    if edge.provenance:
                        provenance_sources.add(f"{edge.provenance.source_mode.value}:{edge.provenance.source_tool}")
                    key = (dataset_urn, target_urn, edge.source_field, edge.target_field)
                    if key not in exact_cache:
                        exact_cache[key] = await self.dh.get_exact_lineage_path_provenance(*key)
                    exact_provenance = exact_cache[key]
                    if exact_provenance:
                        exact_match = True
                        exact_available = True
                        provenance_sources.add(
                            f"{exact_provenance.source_mode.value}:{exact_provenance.source_tool}"
                        )
                        evidence_items.append(EvidenceItem(
                            id=f"ev_path_{len(evidence_items) + 1}",
                            type=EvidenceType.EXACT_LINEAGE_PATH,
                            source_field=edge.source_field,
                            target_field=edge.target_field,
                            description=f"Exact MCP lineage path returned for {edge.source_field} -> {edge.target_field}",
                            provenance=exact_provenance,
                        ))

                if source_field not in query_cache:
                    query_cache[source_field] = await self.dh.get_dataset_queries(dataset_urn, source_field, False)
                queries = query_cache[source_field]
                query_match = query_match or any(target_name.lower() in query.query_text.lower() for query in queries)
                query_available = query_available or bool(queries)
                for query in queries:
                    if target_name.lower() in query.query_text.lower():
                        evidence_items.append(EvidenceItem(
                            id=f"ev_query_{len(evidence_items) + 1}",
                            type=EvidenceType.QUERY_USAGE,
                            query_reference=query.query_id,
                            description=f"Recorded query execution references '{source_field}'",
                            provenance=query.provenance,
                        ))

            classification = (
                ImpactClassification.CONFIRMED_IMPACT if column_match or query_match
                else ImpactClassification.POTENTIAL_IMPACT if node_info.get("depth", 1) <= 1
                else ImpactClassification.UNLIKELY_IMPACT
            )
            if not column_match and not query_match:
                evidence_items.append(EvidenceItem(
                    id=f"ev_table_{len(evidence_items) + 1}",
                    type=EvidenceType.TABLE_LINEAGE,
                    description=f"Downstream table lineage returned at hop {node_info.get('depth', 1)}; field use was not verified",
                    provenance=lineage_prov,
                ))
            classified_assets.append(AssetImpact(
                asset_urn=target_urn,
                name=target_name,
                platform=(target_meta.platform if target_meta else node_info.get("platform")),
                asset_type=node_info.get("type", "DATASET"),
                classification=classification,
                owners=[o.name for o in target_meta.owners if o.name] if target_meta else [],
                tags=target_meta.tags if target_meta else [],
                hop_count=int(node_info.get("depth", 1)),
                evidence=evidence_items,
                provenance=target_prov,
            ))
            graph_nodes.append(EvidenceGraphNode(
                id=target_urn,
                label=target_name,
                type="CONFIRMED_IMPACT" if classification == ImpactClassification.CONFIRMED_IMPACT else "POTENTIAL_IMPACT",
                platform=target_meta.platform if target_meta else node_info.get("platform"),
                classification=classification,
                owners=[o.name for o in target_meta.owners if o.name] if target_meta else [],
                tags=target_meta.tags if target_meta else [],
                is_demo_fixture=bool(target_meta and target_meta.is_demo_fixture),
                provenance=target_prov,
            ))
            graph_edges.append(EvidenceGraphEdge(
                source=parent_by_urn.get(target_urn, dataset_urn),
                target=target_urn,
                lineage_type="FIELD_LEVEL" if column_match else "TABLE_LEVEL",
                field_mapping=", ".join(sorted(set(field_mappings))) or None,
                hop_count=int(node_info.get("depth", 1)),
                evidence_source="get_lineage",
                provenance=lineage_prov,
            ))

        confirmed_count = sum(a.classification == ImpactClassification.CONFIRMED_IMPACT for a in classified_assets)
        potential_count = sum(a.classification == ImpactClassification.POTENTIAL_IMPACT for a in classified_assets)
        schema_verified = bool(base_dataset and base_dataset.fields)
        ownership_assigned = bool(base_dataset and base_dataset.owners) and all(bool(asset.owners) for asset in classified_assets) if classified_assets else bool(base_dataset and base_dataset.owners)
        sufficient = mode != IntegrationMode.DATAHUB_UNAVAILABLE and schema_verified and bool(base_dataset)
        return ImpactEvidenceBundle(
            dataset_urn=dataset_urn,
            dataset_name=dataset_name,
            integration_mode=mode,
            changes=changes,
            classified_assets=classified_assets,
            graph=EvidenceGraph(nodes=graph_nodes, edges=graph_edges),
            confirmed_consumers_count=confirmed_count,
            potential_consumers_count=potential_count,
            has_sufficient_evidence=sufficient,
            schema_verified=schema_verified,
            column_lineage_available=column_available,
            query_usage_available=query_available,
            ownership_assigned=ownership_assigned,
            exact_lineage_path_verified=exact_available,
            evidence_provenance_summary=sorted(provenance_sources),
        )

    @staticmethod
    def _urn_name(urn: str) -> str:
        return urn.split(",")[-2] if "," in urn else urn

    @staticmethod
    def _lineage_provenance(node_info: Dict[str, object], entity_urn: str, mode: IntegrationMode) -> Optional[DataHubProvenance]:
        if mode == IntegrationMode.DATAHUB_UNAVAILABLE:
            return None
        return DataHubProvenance(
            source_mode=mode,
            source_tool=str(node_info.get("source_tool", "get_lineage")),
            entity_urn=entity_urn,
            source_reference=node_info.get("source_reference") if isinstance(node_info.get("source_reference"), str) else None,
        )
