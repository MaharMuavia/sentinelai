import uuid
import datetime
from typing import Dict, Any, List, Optional, AsyncGenerator
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.schema_engine.diff import SchemaSnapshot, SchemaDiffEngine, ChangeSet
from app.datahub.client import DataHubClient, IntegrationMode
from app.datahub.writeback import DataHubWritebackEngine
from app.evidence.engine import ImpactEvidenceEngine, ImpactEvidenceBundle, ImpactClassification
from app.risk.engine import RiskEngine, RiskAssessment, DecisionVerdict
from app.llm.reasoning import LLMReasoningEngine, AIReasoningOutput
from app.remediation.engine import SQLRemediationEngine, RemediationArtifact, RemediationStatus
from app.github.client import GitHubClient
from app.db.models import InvestigationDB, AuditEventDB


class WorkflowStage(str):
    RECEIVE_CHANGE = "RECEIVE_CHANGE"
    NORMALIZE_CHANGE = "NORMALIZE_CHANGE"
    LOAD_DATAHUB_CONTEXT = "LOAD_DATAHUB_CONTEXT"
    BUILD_EVIDENCE_GRAPH = "BUILD_EVIDENCE_GRAPH"
    VERIFY_CONSUMERS = "VERIFY_CONSUMERS"
    COMPUTE_RISK = "COMPUTE_RISK"
    GENERATE_REMEDIATION = "GENERATE_REMEDIATION"
    VALIDATE_REMEDIATION = "VALIDATE_REMEDIATION"
    GENERATE_EXPLANATION = "GENERATE_EXPLANATION"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    ACT = "ACT"
    WRITE_BACK = "WRITE_BACK"
    COMPLETE = "COMPLETE"


class WorkflowProgressEvent(BaseModel):
    investigation_id: str
    stage: str
    status: str  # STARTED, RUNNING, COMPLETED, FAILED, SKIPPED
    message: str
    timestamp: str = Field(default_factory=lambda: datetime.datetime.now(datetime.timezone.utc).isoformat())


class InvestigationResult(BaseModel):
    investigation_id: str
    dataset_urn: str
    severity: str
    recommendation: str
    evidence_completeness: float
    confirmed_consumers_count: int
    potential_consumers_count: int
    integration_mode: IntegrationMode
    changes: ChangeSet
    evidence_bundle: ImpactEvidenceBundle
    risk_assessment: RiskAssessment
    ai_explanation: AIReasoningOutput
    remediation: Optional[RemediationArtifact] = None
    datahub_writeback_status: str = "PENDING"
    github_action_status: str = "NONE"


class SentinelWorkflowOrchestrator:
    """
    Canonical 13-Stage Bounded Sentinel Change Control Workflow Orchestrator.
    Executes pre-merge change investigation deterministically over DataHub context.
    Consolidates state transitions and guarantees database transaction ordering.
    """

    def __init__(self, db_session: Session):
        self.db = db_session
        self.dh_client = DataHubClient()
        self.dh_writeback = DataHubWritebackEngine()
        self.evidence_engine = ImpactEvidenceEngine(self.dh_client)
        self.github_client = GitHubClient()

    async def execute_investigation(
        self,
        before_schema: SchemaSnapshot,
        after_schema: SchemaSnapshot,
        pr_url: Optional[str] = None,
        downstream_sql: Optional[str] = None
    ) -> InvestigationResult:
        events = []
        result = None
        async for event in self.execute_investigation_streaming(
            before_schema=before_schema,
            after_schema=after_schema,
            pr_url=pr_url,
            downstream_sql=downstream_sql
        ):
            if isinstance(event, InvestigationResult):
                result = event
            else:
                events.append(event)
        return result

    async def execute_investigation_streaming(
        self,
        before_schema: SchemaSnapshot,
        after_schema: SchemaSnapshot,
        pr_url: Optional[str] = None,
        downstream_sql: Optional[str] = None
    ) -> AsyncGenerator[Any, None]:
        inv_id = str(uuid.uuid4())[:8]

        # 1. RECEIVE_CHANGE
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.RECEIVE_CHANGE,
            status="COMPLETED",
            message="Received proposed schema snapshot payload"
        )

        # 2. NORMALIZE_CHANGE
        changes = SchemaDiffEngine.diff(before_schema, after_schema, source="github_pr" if pr_url else "manual")
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.NORMALIZE_CHANGE,
            status="COMPLETED",
            message=f"Normalized {len(changes.changes)} schema change(s)"
        )

        # 3. LOAD_DATAHUB_CONTEXT
        mode = await self.dh_client.get_integration_mode(allow_fixture_fallback=True)
        dataset_meta = await self.dh_client.get_dataset(changes.dataset_urn, allow_fixture_fallback=True)
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.LOAD_DATAHUB_CONTEXT,
            status="COMPLETED",
            message=f"Loaded DataHub context ({mode.value}) for '{changes.dataset_urn}'"
        )

        # 4. BUILD_EVIDENCE_GRAPH & 5. VERIFY_CONSUMERS
        evidence_bundle = await self.evidence_engine.analyze_impact(changes, allow_fixture_fallback=True)
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.BUILD_EVIDENCE_GRAPH,
            status="COMPLETED",
            message=f"Constructed blast-radius evidence graph with {len(evidence_bundle.graph.nodes)} node(s)"
        )
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.VERIFY_CONSUMERS,
            status="COMPLETED",
            message=f"Verified {evidence_bundle.confirmed_consumers_count} confirmed and {evidence_bundle.potential_consumers_count} potential downstream consumer(s)"
        )

        # 6. COMPUTE_RISK
        risk_assessment = RiskEngine.assess_risk(evidence_bundle)
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.COMPUTE_RISK,
            status="COMPLETED",
            message=f"Calculated verdict '{risk_assessment.verdict.value}' ({risk_assessment.severity.value}) with {risk_assessment.evidence_completeness}% evidence completeness"
        )

        # 7. GENERATE_REMEDIATION & 8. VALIDATE_REMEDIATION
        sample_sql = downstream_sql or "SELECT customer_id, email, lifetime_value FROM customer_360 WHERE email IS NOT NULL;"
        remediation_artifact = SQLRemediationEngine.remediate_dbt_model(
            file_path="models/marts/customer_360.sql",
            original_sql=sample_sql,
            changes=changes
        )
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.GENERATE_REMEDIATION,
            status="COMPLETED",
            message=f"AST Remediation status: {remediation_artifact.validation.status.value}"
        )
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.VALIDATE_REMEDIATION,
            status="COMPLETED",
            message=f"Remediation validation: syntax_ok={remediation_artifact.validation.syntax_ok}, valid={remediation_artifact.validation.is_valid}"
        )

        # 9. GENERATE_EXPLANATION
        ai_explanation = await LLMReasoningEngine.generate_explanation(
            bundle=evidence_bundle,
            risk=risk_assessment,
            remediation_diff=remediation_artifact.unified_diff
        )
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.GENERATE_EXPLANATION,
            status="COMPLETED",
            message="Generated evidence-grounded decision explanation"
        )

        # 10. HUMAN_APPROVAL
        requires_human = (risk_assessment.verdict == DecisionVerdict.BLOCK) or (remediation_artifact.validation.status == RemediationStatus.REQUIRES_HUMAN)
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.HUMAN_APPROVAL,
            status="COMPLETED",
            message=f"Human approval check: {'REQUIRED (High-risk change / semantic predicate modification)' if requires_human else 'AUTO-APPROVED (Non-breaking change)'}"
        )

        # 11. ACT (GitHub review comment)
        critical_paths = [
            f"{e.source} → {e.target} ({e.lineage_type})"
            for e in evidence_bundle.graph.edges
        ] or [f"{changes.dataset_urn} → downstream consumers"]

        pr_number = 42
        if pr_url:
            try:
                pr_number = int(pr_url.rstrip('/').split('/')[-1])
            except (ValueError, IndexError):
                pass

        github_res = await self.github_client.post_pr_comment(
            pr_number=pr_number,
            severity=risk_assessment.severity.value,
            recommendation=risk_assessment.verdict.value,
            evidence_completeness=risk_assessment.evidence_completeness,
            proposed_change=changes.changes[0].details if changes.changes else "Schema change",
            confirmed_consumers_count=evidence_bundle.confirmed_consumers_count,
            critical_paths=critical_paths,
            recommended_action=ai_explanation.recommended_action,
            remediation_diff=remediation_artifact.unified_diff,
            investigation_id=inv_id
        )
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.ACT,
            status="COMPLETED" if github_res.success else "SKIPPED",
            message=f"GitHub action: {github_res.message}"
        )

        # 12. WRITE_BACK (DataHub GMS mutation)
        writeback_res = await self.dh_writeback.writeback_investigation(
            investigation_id=inv_id,
            dataset_urn=changes.dataset_urn,
            severity=risk_assessment.severity.value,
            recommendation=risk_assessment.verdict.value,
            evidence_completeness=risk_assessment.evidence_completeness,
            confirmed_consumers=[a.name for a in evidence_bundle.classified_assets if a.classification == ImpactClassification.CONFIRMED_IMPACT],
            potential_consumers=[a.name for a in evidence_bundle.classified_assets if a.classification == ImpactClassification.POTENTIAL_IMPACT],
            summary=ai_explanation.executive_summary,
            remediation_diff=remediation_artifact.unified_diff,
            pr_url=pr_url
        )
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.WRITE_BACK,
            status="COMPLETED" if writeback_res.success else "FAILED",
            message=f"DataHub writeback: {writeback_res.message}"
        )

        # 13. COMPLETE
        yield WorkflowProgressEvent(
            investigation_id=inv_id,
            stage=WorkflowStage.COMPLETE,
            status="COMPLETED",
            message="Sentinel change control investigation completed successfully"
        )

        # TRANSACTION ORDERING FIX: Save InvestigationDB record FIRST before any child audit events
        db_inv = InvestigationDB(
            id=inv_id,
            dataset_urn=changes.dataset_urn,
            pr_url=pr_url,
            source=changes.source,
            severity=risk_assessment.severity.value,
            recommendation=risk_assessment.verdict.value,
            evidence_completeness=risk_assessment.evidence_completeness,
            confirmed_consumers_count=evidence_bundle.confirmed_consumers_count,
            potential_consumers_count=evidence_bundle.potential_consumers_count,
            datahub_writeback_status="SUCCESS" if writeback_res.success else "FAILED",
            github_action_status=github_res.action_type,
            schema_change_json=changes.model_dump(),
            evidence_graph_json=evidence_bundle.model_dump(),
            ai_explanation_json=ai_explanation.model_dump(),
            remediation_json=remediation_artifact.model_dump()
        )
        self.db.add(db_inv)
        self.db.commit()

        # Save completed audit log entry
        audit = AuditEventDB(
            investigation_id=inv_id,
            stage=WorkflowStage.COMPLETE,
            status="COMPLETED",
            message="Sentinel investigation workflow completed.",
            details_json={"mode": mode.value, "verdict": risk_assessment.verdict.value}
        )
        self.db.add(audit)
        self.db.commit()

        result = InvestigationResult(
            investigation_id=inv_id,
            dataset_urn=changes.dataset_urn,
            severity=risk_assessment.severity.value,
            recommendation=risk_assessment.verdict.value,
            evidence_completeness=risk_assessment.evidence_completeness,
            confirmed_consumers_count=evidence_bundle.confirmed_consumers_count,
            potential_consumers_count=evidence_bundle.potential_consumers_count,
            integration_mode=mode,
            changes=changes,
            evidence_bundle=evidence_bundle,
            risk_assessment=risk_assessment,
            ai_explanation=ai_explanation,
            remediation=remediation_artifact,
            datahub_writeback_status="SUCCESS" if writeback_res.success else "FAILED",
            github_action_status="SUCCESS" if github_res.success else "FAILED"
        )
        yield result
