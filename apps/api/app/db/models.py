from sqlalchemy import Column, String, Integer, Float, DateTime, Text, ForeignKey, JSON
from sqlalchemy.sql import func
from app.db.database import Base


class InvestigationDB(Base):
    __tablename__ = "investigations"

    id = Column(String, primary_key=True, index=True)
    dataset_urn = Column(String, index=True, nullable=False)
    pr_url = Column(String, nullable=True)
    source = Column(String, default="manual")
    severity = Column(String, nullable=False)  # LOW, MEDIUM, HIGH, CRITICAL
    recommendation = Column(String, nullable=False)  # SAFE_TO_MERGE, MERGE_WITH_CAUTION, BLOCK, INSUFFICIENT_EVIDENCE
    evidence_completeness = Column(Float, nullable=False)  # e.g., 94.0
    confirmed_consumers_count = Column(Integer, default=0)
    potential_consumers_count = Column(Integer, default=0)
    datahub_writeback_status = Column(String, default="PENDING")  # PENDING, SUCCESS, FAILED, DISABLED
    github_action_status = Column(String, default="NONE")  # NONE, COMMENTED, PR_CREATED, FAILED
    approval_status = Column(String, nullable=False, default="NOT_REQUIRED")
    approved_at = Column(DateTime(timezone=True), nullable=True)
    approved_by = Column(String, nullable=True)
    integration_mode = Column(String, nullable=True)
    evidence_trust = Column(String, nullable=True)
    risk_assessment_json = Column(JSON, nullable=True)
    writeback_result_json = Column(JSON, nullable=True)
    github_result_json = Column(JSON, nullable=True)
    
    # Detailed payloads serialized as JSON
    schema_change_json = Column(JSON, nullable=False)
    evidence_graph_json = Column(JSON, nullable=False)
    ai_explanation_json = Column(JSON, nullable=False)
    remediation_json = Column(JSON, nullable=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AuditEventDB(Base):
    __tablename__ = "audit_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False, index=True)
    stage = Column(String, nullable=False)
    status = Column(String, nullable=False)  # STARTED, COMPLETED, FAILED, AWAITING_APPROVAL
    message = Column(Text, nullable=False)
    details_json = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
