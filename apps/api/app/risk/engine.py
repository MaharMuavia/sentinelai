from enum import Enum
from typing import List, Dict, Any
from pydantic import BaseModel
from app.evidence.engine import ImpactEvidenceBundle, ImpactClassification
from app.datahub.client import IntegrationMode


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"
    UNKNOWN = "UNKNOWN"


class DecisionVerdict(str, Enum):
    SAFE_TO_MERGE = "SAFE_TO_MERGE"
    MERGE_WITH_CAUTION = "MERGE_WITH_CAUTION"
    BLOCK = "BLOCK"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


class RiskFactor(BaseModel):
    name: str
    impact: str
    description: str


class CompletenessSignal(BaseModel):
    signal_name: str
    is_present: bool
    weight: float
    description: str


class RiskAssessment(BaseModel):
    severity: Severity
    verdict: DecisionVerdict
    evidence_completeness: float  # e.g. 94.0 or 0.0
    risk_factors: List[RiskFactor]
    completeness_breakdown: List[CompletenessSignal]
    policy_triggered: str


class RiskEngine:
    """
    Deterministic Pre-Merge Risk Assessment Engine.
    Computes severity, verdict, and evidence completeness transparently from empirical DataHub evidence.
    Ensures Sentinel NEVER claims 100% verified when evidence is missing or DataHub is unavailable.
    """

    @staticmethod
    def assess_risk(bundle: ImpactEvidenceBundle) -> RiskAssessment:
        breaking_changes = [c for c in bundle.changes.changes if c.is_breaking]
        confirmed_consumers = [
            a for a in bundle.classified_assets if a.classification == ImpactClassification.CONFIRMED_IMPACT
        ]
        potential_consumers = [
            a for a in bundle.classified_assets if a.classification == ImpactClassification.POTENTIAL_IMPACT
        ]

        # 1. Integration & Evidence Availability Check
        if bundle.integration_mode == IntegrationMode.DATAHUB_UNAVAILABLE or not bundle.has_sufficient_evidence:
            signals = [
                CompletenessSignal(
                    signal_name="SCHEMA_VERIFIED",
                    is_present=False,
                    weight=25.0,
                    description="DataHub GMS metadata catalog unavailable or unreachable."
                ),
                CompletenessSignal(
                    signal_name="COLUMN_LINEAGE_AVAILABLE",
                    is_present=False,
                    weight=25.0,
                    description="Column-level lineage could not be retrieved from DataHub."
                ),
                CompletenessSignal(
                    signal_name="QUERY_USAGE_HISTORY",
                    is_present=False,
                    weight=20.0,
                    description="Query execution log history unavailable."
                ),
                CompletenessSignal(
                    signal_name="OWNERSHIP_ASSIGNED",
                    is_present=False,
                    weight=15.0,
                    description="Asset ownership unverified due to catalog connection failure."
                ),
                CompletenessSignal(
                    signal_name="EXACT_LINEAGE_PATH_VERIFIED",
                    is_present=False,
                    weight=15.0,
                    description="Multi-hop lineage tracing unavailable."
                )
            ]

            risk_factors = [
                RiskFactor(
                    name="DATAHUB_CATALOG_UNAVAILABLE",
                    impact="HIGH",
                    description="DataHub metadata service was unreachable during change evaluation."
                )
            ]
            if breaking_changes:
                risk_factors.append(RiskFactor(
                    name="UNVERIFIED_BREAKING_SCHEMA_CHANGE",
                    impact="CRITICAL",
                    description=f"{len(breaking_changes)} breaking change(s) proposed without catalog evidence."
                ))
                verdict = DecisionVerdict.INSUFFICIENT_EVIDENCE
                severity = Severity.HIGH
                policy = "FAIL-CLOSED POLICY: Breaking schema change proposed while DataHub context is unavailable."
            else:
                verdict = DecisionVerdict.INSUFFICIENT_EVIDENCE
                severity = Severity.MEDIUM
                policy = "INSUFFICIENT EVIDENCE: Catalog context missing for proposed change."

            return RiskAssessment(
                severity=severity,
                verdict=verdict,
                evidence_completeness=0.0,
                risk_factors=risk_factors,
                completeness_breakdown=signals,
                policy_triggered=policy
            )

        # 2. Check for critical business assets
        has_critical_assets = any(
            "Executive_Tier" in a.tags
            or "Critical_Dashboard" in a.tags
            or "Critical_Model" in a.tags
            or a.asset_type in ("DASHBOARD", "ML_MODEL")
            for a in confirmed_consumers
        )

        risk_factors: List[RiskFactor] = []
        severity = Severity.LOW
        verdict = DecisionVerdict.SAFE_TO_MERGE
        policy = "LOW: Non-breaking or additive schema change with no confirmed downstream breaks."

        if breaking_changes:
            risk_factors.append(RiskFactor(
                name="BREAKING_SCHEMA_CHANGE",
                impact="HIGH",
                description=f"{len(breaking_changes)} breaking schema modification(s) detected (e.g. {breaking_changes[0].details})"
            ))

            if confirmed_consumers:
                risk_factors.append(RiskFactor(
                    name="CONFIRMED_DOWNSTREAM_CONSUMERS",
                    impact="HIGH",
                    description=f"{len(confirmed_consumers)} downstream asset(s) are confirmed users of modified field(s)."
                ))

                if has_critical_assets:
                    severity = Severity.CRITICAL
                    verdict = DecisionVerdict.BLOCK
                    policy = "CRITICAL BLOCK: Breaking schema change on field with confirmed downstream executive dashboards or ML models."
                    risk_factors.append(RiskFactor(
                        name="CRITICAL_BUSINESS_ASSET_IMPACT",
                        impact="CRITICAL",
                        description="Affected downstream consumers include Executive Dashboards and Production ML Models."
                    ))
                else:
                    severity = Severity.HIGH
                    verdict = DecisionVerdict.BLOCK
                    policy = "HIGH BLOCK: Breaking schema change with confirmed downstream model consumers."
            elif potential_consumers:
                severity = Severity.MEDIUM
                verdict = DecisionVerdict.MERGE_WITH_CAUTION
                policy = "MEDIUM WARNING: Breaking schema change with potential/unverified downstream dataset consumers."
            else:
                severity = Severity.LOW
                verdict = DecisionVerdict.SAFE_TO_MERGE
                policy = "LOW: Breaking schema change with zero downstream consumers found in catalog."
        else:
            risk_factors.append(RiskFactor(
                name="NON_BREAKING_CHANGE",
                impact="LOW",
                description="Proposed change is non-breaking (e.g. additive column addition or nullability relaxation)."
            ))

        # 3. Calculate Evidence Completeness strictly from verified signals
        schema_verified = bool(bundle.dataset_urn and (len(bundle.classified_assets) > 0 or bundle.has_sufficient_evidence))

        column_lineage_present = any(
            len(a.evidence) > 0 and any(e.type == "COLUMN_LINEAGE" for e in a.evidence)
            for a in bundle.classified_assets
        )
        query_usage_present = any(
            len(a.evidence) > 0 and any(e.type == "QUERY_USAGE" for e in a.evidence)
            for a in bundle.classified_assets
        )
        ownership_present = len(bundle.classified_assets) > 0 and all(
            len(a.owners) > 0 for a in bundle.classified_assets
        )
        exact_path_verified = len(bundle.graph.edges) > 0 and all(
            e.lineage_type == "FIELD_LEVEL" for e in bundle.graph.edges if e.source != bundle.dataset_urn
        ) if bundle.graph.edges else False

        signals: List[CompletenessSignal] = [
            CompletenessSignal(
                signal_name="SCHEMA_VERIFIED",
                is_present=schema_verified,
                weight=25.0,
                description=f"Current schema snapshot verified against DataHub ({bundle.integration_mode.value})"
            ),
            CompletenessSignal(
                signal_name="COLUMN_LINEAGE_AVAILABLE",
                is_present=column_lineage_present,
                weight=25.0,
                description="Fine-grained column-level lineage verified across downstream models"
            ),
            CompletenessSignal(
                signal_name="QUERY_USAGE_HISTORY",
                is_present=query_usage_present,
                weight=20.0,
                description="Query execution log history inspected for exact column references"
            ),
            CompletenessSignal(
                signal_name="OWNERSHIP_ASSIGNED",
                is_present=ownership_present,
                weight=15.0,
                description="Technical and business owners identified for all affected assets"
            ),
            CompletenessSignal(
                signal_name="EXACT_LINEAGE_PATH_VERIFIED",
                is_present=exact_path_verified,
                weight=15.0,
                description="Multi-hop lineage paths fully traced from root dataset to end consumers"
            )
        ]

        completeness_score = sum(s.weight for s in signals if s.is_present)

        return RiskAssessment(
            severity=severity,
            verdict=verdict,
            evidence_completeness=round(completeness_score, 1),
            risk_factors=risk_factors,
            completeness_breakdown=signals,
            policy_triggered=policy
        )
