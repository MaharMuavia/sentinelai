from enum import Enum
from typing import List, Dict, Any, Optional
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
    evidence_trust: str  # "LIVE DATAHUB MCP", "DEMO FIXTURE — NOT LIVE VERIFIED", "DATAHUB UNAVAILABLE"
    risk_factors: List[RiskFactor]
    completeness_breakdown: List[CompletenessSignal]
    policy_triggered: str


class RiskEngine:
    """
    Deterministic Pre-Merge Risk Assessment Engine.
    Computes severity, verdict, evidence completeness, and evidence trust.
    Ensures Sentinel never claims complete verification when evidence is missing or DataHub is unavailable.
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

        if bundle.integration_mode == IntegrationMode.LIVE_DATAHUB:
            trust_label = "LIVE DATAHUB MCP"
        elif bundle.integration_mode == IntegrationMode.DEMO_FIXTURE:
            trust_label = "DEMO FIXTURE — NOT LIVE VERIFIED"
        else:
            trust_label = "DATAHUB UNAVAILABLE"

        # 1. Integration & Evidence Availability Check
        if bundle.integration_mode == IntegrationMode.DATAHUB_UNAVAILABLE or bundle.has_sufficient_evidence is False:
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
                evidence_trust=trust_label,
                risk_factors=risk_factors,
                completeness_breakdown=signals,
                policy_triggered=policy
            )

        # 2. Check for critical business assets
        critical_tags = {"Executive_Tier", "Critical_Dashboard", "Critical_Model"}
        has_critical_assets = any(
            any(tag.rsplit(":", 1)[-1] in critical_tags for tag in a.tags)
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
        schema_verified = bundle.schema_verified if bundle.schema_verified is not None else False
        column_lineage_present = bundle.column_lineage_available if bundle.column_lineage_available is not None else any(
            any(e.type == "COLUMN_LINEAGE" for e in asset.evidence) for asset in bundle.classified_assets
        )
        query_usage_present = bundle.query_usage_available if bundle.query_usage_available is not None else any(
            any(e.type == "QUERY_USAGE" for e in asset.evidence) for asset in bundle.classified_assets
        )
        ownership_present = bundle.ownership_assigned if bundle.ownership_assigned is not None else bool(bundle.classified_assets) and all(bool(a.owners) for a in bundle.classified_assets)
        exact_path_verified = bundle.exact_lineage_path_verified if bundle.exact_lineage_path_verified is not None else False

        signals: List[CompletenessSignal] = [
            CompletenessSignal(
                signal_name="SCHEMA_VERIFIED",
                is_present=schema_verified,
                weight=25.0,
                description="Schema metadata was retrieved and parsed successfully"
            ),
            CompletenessSignal(
                signal_name="COLUMN_LINEAGE_AVAILABLE",
                is_present=column_lineage_present,
                weight=25.0,
                description="A valid column lineage result was returned"
            ),
            CompletenessSignal(
                signal_name="QUERY_USAGE_HISTORY",
                is_present=query_usage_present,
                weight=20.0,
                description="Query usage records were retrieved; absent records remain unknown"
            ),
            CompletenessSignal(
                signal_name="OWNERSHIP_ASSIGNED",
                is_present=ownership_present,
                weight=15.0,
                description="Ownership metadata was retrieved for the affected assets"
            ),
            CompletenessSignal(
                signal_name="EXACT_LINEAGE_PATH_VERIFIED",
                is_present=exact_path_verified,
                weight=15.0,
                description="get_lineage_paths_between returned a matching path"
            )
        ]

        completeness_score = sum(s.weight for s in signals if s.is_present)

        return RiskAssessment(
            severity=severity,
            verdict=verdict,
            evidence_completeness=round(completeness_score, 1),
            evidence_trust=trust_label,
            risk_factors=risk_factors,
            completeness_breakdown=signals,
            policy_triggered=policy
        )
