from enum import Enum
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from app.schema_engine.diff import ChangeSet, ChangeType
from app.datahub.client import DataHubClient, DatasetMetadata, ColumnLineageEdge, QueryReference, IntegrationMode, DataHubProvenance


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
    platform: str
    asset_type: str  # DATASET, DASHBOARD, ML_MODEL, dbt_MODEL
    classification: ImpactClassification
    owners: List[str] = []
    tags: List[str] = []
    hop_count: int = 1
    evidence: List[EvidenceItem] = []
    provenance: Optional[DataHubProvenance] = None


class EvidenceGraphNode(BaseModel):
    id: str
    label: str
    type: str  # CHANGED_DATASET, CONFIRMED_IMPACT, POTENTIAL_IMPACT, UNAFFECTED, DASHBOARD, ML_MODEL
    platform: str
    classification: ImpactClassification
    owners: List[str] = []
    tags: List[str] = []
    is_demo_fixture: bool = False
    provenance: Optional[DataHubProvenance] = None


class EvidenceGraphEdge(BaseModel):
    source: str
    target: str
    lineage_type: str  # FIELD_LEVEL, TABLE_LEVEL
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
    has_sufficient_evidence: bool = True
    evidence_provenance_summary: List[str] = []


class ImpactEvidenceEngine:
    def __init__(self, datahub_client: DataHubClient):
        self.dh = datahub_client

    async def analyze_impact(
        self, changes: ChangeSet, allow_fixture_fallback: bool = True
    ) -> ImpactEvidenceBundle:
        dataset_urn = changes.dataset_urn
        mode = await self.dh.get_integration_mode(allow_fixture_fallback)

        base_dataset = await self.dh.get_dataset(dataset_urn, allow_fixture_fallback=allow_fixture_fallback)
        dataset_name = base_dataset.name if base_dataset else (dataset_urn.split(",")[-2] if "," in dataset_urn else dataset_urn)

        downstream_nodes = await self.dh.get_downstream_lineage(dataset_urn, allow_fixture_fallback=allow_fixture_fallback)

        classified_assets: List[AssetImpact] = []
        graph_nodes: List[EvidenceGraphNode] = []
        graph_edges: List[EvidenceGraphEdge] = []
        provenance_sources: set = set()

        # Root Node
        root_provenance = base_dataset.provenance if base_dataset else DataHubProvenance(
            source_mode=mode,
            source_tool="sentinel_evidence_engine",
            entity_urn=dataset_urn
        )
        if root_provenance:
            provenance_sources.add(f"{root_provenance.source_mode.value}:{root_provenance.source_tool}")

        graph_nodes.append(EvidenceGraphNode(
            id=dataset_urn,
            label=dataset_name,
            type="CHANGED_DATASET",
            platform=base_dataset.platform if base_dataset else "snowflake",
            classification=ImpactClassification.CONFIRMED_IMPACT,
            owners=[o.name for o in base_dataset.owners] if base_dataset else [],
            tags=base_dataset.tags if base_dataset else [],
            is_demo_fixture=base_dataset.is_demo_fixture if base_dataset else False,
            provenance=root_provenance
        ))

        breaking_changes = [c for c in changes.changes if c.is_breaking]

        # Map to track actual parent URNs for multi-hop graph edge construction
        urn_to_parent: Dict[str, str] = {}
        for node_info in downstream_nodes:
            entity_urn = node_info["entity"]
            parent_urn = node_info.get("parent_urn")
            if not parent_urn:
                # If depth is 1 or unspecified, parent is dataset_urn
                parent_urn = dataset_urn
            urn_to_parent[entity_urn] = parent_urn

        for node_info in downstream_nodes:
            target_urn = node_info["entity"]
            target_name = node_info["name"]
            target_platform = node_info["platform"]
            target_type = node_info["type"]
            hop_depth = node_info.get("depth", 1)
            parent_urn = urn_to_parent.get(target_urn, dataset_urn)

            target_meta = await self.dh.get_dataset(target_urn, allow_fixture_fallback=allow_fixture_fallback)
            owners = [o.name for o in target_meta.owners] if target_meta else []
            tags = target_meta.tags if target_meta else []
            node_prov = target_meta.provenance if target_meta else DataHubProvenance(
                source_mode=mode,
                source_tool="datahub_lineage",
                entity_urn=target_urn
            )
            if node_prov:
                provenance_sources.add(f"{node_prov.source_mode.value}:{node_prov.source_tool}")

            evidence_items: List[EvidenceItem] = []
            is_column_lineage_matched = False
            is_query_matched = False
            field_mappings_found: List[str] = []

            for change in breaking_changes:
                col_name = change.field

                # Fetch column level lineage
                col_edges = await self.dh.get_column_lineage(dataset_urn, col_name, allow_fixture_fallback=allow_fixture_fallback)
                for edge in col_edges:
                    if edge.target_urn.lower() in target_urn.lower() or target_urn.lower() in edge.target_urn.lower():
                        is_column_lineage_matched = True
                        mapping_str = f"{edge.source_field} → {edge.target_field}"
                        field_mappings_found.append(mapping_str)

                        evidence_items.append(EvidenceItem(
                            id=f"ev_col_{len(evidence_items)+1}",
                            type=EvidenceType.COLUMN_LINEAGE,
                            source_field=edge.source_field,
                            target_field=edge.target_field,
                            description=f"Verified field lineage: {dataset_name}.{edge.source_field} → {target_name}.{edge.target_field}",
                            provenance=edge.provenance
                        ))
                        if edge.provenance:
                            provenance_sources.add(f"{edge.provenance.source_mode.value}:{edge.provenance.source_tool}")

                # Fetch historical query usage
                queries = await self.dh.get_dataset_queries(dataset_urn, col_name, allow_fixture_fallback=allow_fixture_fallback)
                for q in queries:
                    if target_name.lower() in q.query_text.lower():
                        is_query_matched = True
                        evidence_items.append(EvidenceItem(
                            id=f"ev_qry_{len(evidence_items)+1}",
                            type=EvidenceType.QUERY_USAGE,
                            query_reference=q.query_id,
                            description=f"Recorded query execution referencing '{col_name}': {q.query_text}",
                            provenance=q.provenance
                        ))
                        if q.provenance:
                            provenance_sources.add(f"{q.provenance.source_mode.value}:{q.provenance.source_tool}")

            # Table-level lineage evidence item
            evidence_items.append(EvidenceItem(
                id=f"ev_tbl_{len(evidence_items)+1}",
                type=EvidenceType.TABLE_LINEAGE,
                description=f"DataHub downstream table lineage path (hop distance: {hop_depth})",
                provenance=node_prov
            ))

            # Classify node based on actual empirical evidence
            if is_column_lineage_matched or is_query_matched:
                classification = ImpactClassification.CONFIRMED_IMPACT
            elif hop_depth <= 1:
                classification = ImpactClassification.POTENTIAL_IMPACT
            else:
                classification = ImpactClassification.UNLIKELY_IMPACT
                evidence_items.append(EvidenceItem(
                    id=f"ev_none_{len(evidence_items)+1}",
                    type=EvidenceType.METADATA_TAG,
                    description="Asset downstream of dataset but no field-level evidence connects the modified column(s).",
                    provenance=node_prov
                ))

            classified_assets.append(AssetImpact(
                asset_urn=target_urn,
                name=target_name,
                platform=target_platform,
                asset_type=target_type,
                classification=classification,
                owners=owners,
                tags=tags,
                hop_count=hop_depth,
                evidence=evidence_items,
                provenance=node_prov
            ))

            # Add node to Evidence Graph
            graph_nodes.append(EvidenceGraphNode(
                id=target_urn,
                label=target_name,
                type="CONFIRMED_IMPACT" if classification == ImpactClassification.CONFIRMED_IMPACT else ("UNAFFECTED" if classification == ImpactClassification.UNLIKELY_IMPACT else "POTENTIAL_IMPACT"),
                platform=target_platform,
                classification=classification,
                owners=owners,
                tags=tags,
                is_demo_fixture=target_meta.is_demo_fixture if target_meta else False,
                provenance=node_prov
            ))

            # Build Graph Edge with true parent URN and true field mapping
            actual_field_mapping = ", ".join(set(field_mappings_found)) if field_mappings_found else None
            graph_edges.append(EvidenceGraphEdge(
                source=parent_urn,
                target=target_urn,
                lineage_type="FIELD_LEVEL" if is_column_lineage_matched else "TABLE_LEVEL",
                field_mapping=actual_field_mapping,
                hop_count=hop_depth,
                evidence_source=f"DataHub Column Lineage ({mode.value})" if is_column_lineage_matched else f"DataHub Table Lineage ({mode.value})",
                provenance=node_prov
            ))

        confirmed_count = sum(1 for a in classified_assets if a.classification == ImpactClassification.CONFIRMED_IMPACT)
        potential_count = sum(1 for a in classified_assets if a.classification == ImpactClassification.POTENTIAL_IMPACT)

        has_sufficient = (mode != IntegrationMode.DATAHUB_UNAVAILABLE) and bool(base_dataset or downstream_nodes)

        return ImpactEvidenceBundle(
            dataset_urn=dataset_urn,
            dataset_name=dataset_name,
            integration_mode=mode,
            changes=changes,
            classified_assets=classified_assets,
            graph=EvidenceGraph(nodes=graph_nodes, edges=graph_edges),
            confirmed_consumers_count=confirmed_count,
            potential_consumers_count=potential_count,
            has_sufficient_evidence=has_sufficient,
            evidence_provenance_summary=sorted(list(provenance_sources))
        )
