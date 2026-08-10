from app.datahub.client import IntegrationMode
from app.evidence.engine import EvidenceGraph, ImpactEvidenceBundle
from app.llm.reasoning import LLMReasoningEngine
from app.risk.engine import DecisionVerdict, RiskAssessment, Severity
from app.schema_engine.diff import ChangeSet, ChangeType, SchemaChange


def test_additive_explanation_does_not_claim_breaking_or_confirmed_impact():
    changes = ChangeSet(
        dataset_urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        changes=[
            SchemaChange(
                field="signup_source",
                change_type=ChangeType.COLUMN_ADDED,
                is_breaking=False,
                details="New field 'signup_source' added",
            )
        ],
    )
    bundle = ImpactEvidenceBundle(
        dataset_urn=changes.dataset_urn,
        dataset_name="raw_customers",
        integration_mode=IntegrationMode.LIVE_DATAHUB,
        changes=changes,
        classified_assets=[],
        graph=EvidenceGraph(nodes=[], edges=[]),
        confirmed_consumers_count=0,
        potential_consumers_count=0,
    )
    risk = RiskAssessment(
        severity=Severity.LOW,
        verdict=DecisionVerdict.SAFE_TO_MERGE,
        evidence_completeness=25,
        evidence_trust="LIVE DATAHUB MCP",
        risk_factors=[],
        completeness_breakdown=[],
        policy_triggered="LOW",
    )

    output = LLMReasoningEngine._generate_deterministic_explanation(bundle, risk)

    assert "without a breaking schema change" in output.executive_summary
    assert "Executive Dashboards" not in output.why_it_matters
    assert "ML Feature Stores" not in output.why_it_matters
    assert output.affected_systems == ["No confirmed downstream consumers detected."]
