import pytest
from app.evidence.engine import ImpactEvidenceBundle, EvidenceGraph, ImpactClassification, AssetImpact, EvidenceItem, EvidenceType
from app.risk.engine import RiskEngine, Severity, DecisionVerdict
from app.schema_engine.diff import ChangeSet, SchemaChange, ChangeType
from app.datahub.client import IntegrationMode


def test_assess_risk_breaking_critical_asset():
    changes = ChangeSet(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        changes=[
            SchemaChange(
                field="email",
                change_type=ChangeType.COLUMN_REMOVED,
                is_breaking=True,
                details="Field 'email' removed"
            )
        ]
    )

    bundle = ImpactEvidenceBundle(
        dataset_urn=changes.dataset_urn,
        dataset_name="raw_customers",
        integration_mode=IntegrationMode.LIVE_DATAHUB,
        changes=changes,
        classified_assets=[
            AssetImpact(
                asset_urn="urn:li:dataset:(urn:li:dataPlatform:looker,marketing_dashboard,PROD)",
                name="marketing_dashboard",
                platform="looker",
                asset_type="DASHBOARD",
                classification=ImpactClassification.CONFIRMED_IMPACT,
                tags=["Executive_Tier", "Critical_Dashboard"],
                owners=["sarah.chen@company.com"],
                evidence=[
                    EvidenceItem(id="e1", type=EvidenceType.COLUMN_LINEAGE, description="Verified field lineage")
                ]
            )
        ],
        graph=EvidenceGraph(nodes=[], edges=[]),
        confirmed_consumers_count=1,
        potential_consumers_count=0
    )

    assessment = RiskEngine.assess_risk(bundle)

    assert assessment.severity == Severity.CRITICAL
    assert assessment.verdict == DecisionVerdict.BLOCK
    assert assessment.evidence_completeness > 0.0


def test_assess_risk_datahub_unavailable_verdict():
    changes = ChangeSet(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        changes=[
            SchemaChange(
                field="email",
                change_type=ChangeType.COLUMN_REMOVED,
                is_breaking=True,
                details="Field 'email' removed"
            )
        ]
    )

    bundle = ImpactEvidenceBundle(
        dataset_urn=changes.dataset_urn,
        dataset_name="raw_customers",
        integration_mode=IntegrationMode.DATAHUB_UNAVAILABLE,
        changes=changes,
        classified_assets=[],
        graph=EvidenceGraph(nodes=[], edges=[]),
        confirmed_consumers_count=0,
        potential_consumers_count=0,
        has_sufficient_evidence=False
    )

    assessment = RiskEngine.assess_risk(bundle)

    # Must return INSUFFICIENT_EVIDENCE and completeness 0% when DataHub context is missing for breaking change
    assert assessment.verdict == DecisionVerdict.INSUFFICIENT_EVIDENCE
    assert assessment.evidence_completeness == 0.0
