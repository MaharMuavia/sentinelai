import json
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.config import settings
from app.auth import MutationPrincipal, require_mutation_authorization
from app.db.database import get_db, init_db
from app.db.models import InvestigationDB, AuditEventDB
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier, SchemaField
from app.schema_engine.parser import SchemaParserEngine
from app.datahub.client import DataHubClient, IntegrationMode
from app.datahub.writeback import DataHubWritebackEngine, WritebackStatus
from app.github.client import GitHubClient, GitHubActionStatus
from app.workflow.orchestrator import SentinelWorkflowOrchestrator, WorkflowProgressEvent, InvestigationResult


logger = logging.getLogger("sentinel.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize database tables on startup for the selected SQLAlchemy backend.
    init_db()
    yield


app = FastAPI(
    title="Sentinel AI API",
    description="Pre-Merge Data Change Control Agent powered by DataHub context",
    version="1.0.0",
    lifespan=lifespan
)

# Configurable CORS middleware for Next.js frontend
allowed_origins = [origin.strip() for origin in settings.CORS_ALLOWED_ORIGINS.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


class AnalyzeChangeRequest(BaseModel):
    before_schema: SchemaSnapshot
    after_schema: SchemaSnapshot
    pr_url: Optional[str] = Field(None, max_length=2048, description="GitHub Pull Request URL")
    downstream_sql: Optional[str] = Field(
        None,
        max_length=1_000_000,
        description="Downstream model SQL query for remediation verification",
    )


class AnalyzeDDLRequest(BaseModel):
    ddl_statement: str = Field(min_length=1, max_length=100_000)
    dataset_urn: str = Field(min_length=1, max_length=2048)
    pr_url: Optional[str] = Field(None, max_length=2048)


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Sentinel AI", "version": "1.0.0"}


@app.get("/ready")
def readiness_check(db: Session = Depends(get_db)):
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Database is unavailable") from exc
    return {"status": "ready", "database": "connected"}


@app.get("/api/integrations/status")
async def integrations_status():
    dh_client = DataHubClient()
    github_client = GitHubClient()

    dh_connected = await dh_client.check_connection()
    dh_mode = await dh_client.get_integration_mode(allow_fixture_fallback=False)
    tool_discovery = await dh_client.mcp_client.discover_tools()

    llm_connected = bool(settings.OPENAI_API_KEY)
    llm_mode = f"OpenAI ({settings.AGENT_MODEL})" if llm_connected else "DETERMINISTIC_FALLBACK"

    github_configured = github_client.is_configured()
    github_connected = await github_client.check_connection()
    github_mode = (
        "GitHub API (verified)" if github_connected
        else "Configured / connectivity unverified" if github_configured
        else "Disabled / dry-run local mode"
    )

    return {
        "datahub": {
            "name": "DataHub GMS / MCP",
            "url": settings.DATAHUB_GMS_URL,
            "connected": dh_connected,
            "mode": dh_mode.value,
            "discovered_tools": tool_discovery.tools if tool_discovery.connected else [],
        },
        "llm": {
            "name": "AI Reasoning Engine",
            "model": settings.AGENT_MODEL,
            "connected": llm_connected,
            "mode": llm_mode
        },
        "github": {
            "name": "GitHub Actions",
            "repository": settings.GITHUB_REPOSITORY or "Not configured",
            "configured": github_configured,
            "connected": github_connected,
            "mode": github_mode
        }
    }


@app.post("/api/changes/analyze")
async def analyze_change(req: AnalyzeChangeRequest, db: Session = Depends(get_db)):
    orchestrator = SentinelWorkflowOrchestrator(db)
    result = await orchestrator.execute_investigation(
        before_schema=req.before_schema,
        after_schema=req.after_schema,
        pr_url=req.pr_url,
        downstream_sql=req.downstream_sql
    )
    return result


@app.post("/api/changes/analyze/stream")
async def analyze_change_stream(req: AnalyzeChangeRequest, db: Session = Depends(get_db)):
    orchestrator = SentinelWorkflowOrchestrator(db)

    async def event_generator():
        try:
            async for item in orchestrator.execute_investigation_streaming(
                before_schema=req.before_schema,
                after_schema=req.after_schema,
                pr_url=req.pr_url,
                downstream_sql=req.downstream_sql
            ):
                if isinstance(item, WorkflowProgressEvent):
                    yield f"data: {item.model_dump_json()}\n\n"
                elif isinstance(item, InvestigationResult):
                    yield f"data: {json.dumps({'type': 'RESULT', 'data': item.model_dump()})}\n\n"
        except Exception:
            db.rollback()
            logger.exception("Streaming investigation failed")
            yield f"data: {json.dumps({'type': 'ERROR', 'message': 'Investigation failed before completion'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )


@app.post("/api/changes/analyze/ddl")
async def analyze_ddl(req: AnalyzeDDLRequest, db: Session = Depends(get_db)):
    dataset_urn = req.dataset_urn

    # Attempt to load current base schema from DataHub if available
    dh_client = DataHubClient()
    base_meta = await dh_client.get_dataset(dataset_urn, allow_fixture_fallback=False)
    if not base_meta or not base_meta.fields:
        raise HTTPException(status_code=503, detail="Current DataHub schema is unavailable; DDL analysis is fail-closed")

    base_snapshot = None
    if base_meta and base_meta.fields:
        from app.schema_engine.diff import DatasetIdentifier, SchemaField
        base_snapshot = SchemaSnapshot(
            dataset=DatasetIdentifier(urn=dataset_urn, name=base_meta.name),
            fields=[SchemaField(name=f.field_path, type=f.type, nullable=f.nullable) for f in base_meta.fields]
        )

    parse_result = SchemaParserEngine.parse_sql_ddl_alter(
        req.ddl_statement,
        dataset_urn=dataset_urn,
        base_schema=base_snapshot
    )

    if not parse_result.success or not parse_result.before_snapshot or not parse_result.after_snapshot:
        raise HTTPException(
            status_code=400,
            detail=f"DDL Parsing Error: {parse_result.error or 'Invalid SQL syntax'}"
        )

    orchestrator = SentinelWorkflowOrchestrator(db)
    result = await orchestrator.execute_investigation(
        before_schema=parse_result.before_snapshot,
        after_schema=parse_result.after_snapshot,
        pr_url=req.pr_url
    )
    return result


@app.get("/api/investigations")
def list_investigations(db: Session = Depends(get_db)):
    records = db.query(InvestigationDB).order_by(InvestigationDB.created_at.desc()).all()
    out = []
    for r in records:
        out.append({
            "id": r.id,
            "dataset_urn": r.dataset_urn,
            "pr_url": r.pr_url,
            "source": r.source,
            "severity": r.severity,
            "recommendation": r.recommendation,
            "evidence_completeness": r.evidence_completeness,
            "confirmed_consumers_count": r.confirmed_consumers_count,
            "potential_consumers_count": r.potential_consumers_count,
            "datahub_writeback_status": r.datahub_writeback_status,
            "github_action_status": r.github_action_status,
            "approval_status": r.approval_status,
            "integration_mode": r.integration_mode,
            "evidence_trust": r.evidence_trust,
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return out


@app.get("/api/investigations/{investigation_id}")
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")

    return {
        "id": rec.id,
        "dataset_urn": rec.dataset_urn,
        "pr_url": rec.pr_url,
        "severity": rec.severity,
        "recommendation": rec.recommendation,
        "evidence_completeness": rec.evidence_completeness,
        "confirmed_consumers_count": rec.confirmed_consumers_count,
        "potential_consumers_count": rec.potential_consumers_count,
        "datahub_writeback_status": rec.datahub_writeback_status,
        "github_action_status": rec.github_action_status,
        "approval_status": rec.approval_status,
        "approved_at": rec.approved_at.isoformat() if rec.approved_at else None,
        "approved_by": rec.approved_by,
        "integration_mode": rec.integration_mode,
        "evidence_trust": rec.evidence_trust,
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "changes": rec.schema_change_json,
        "evidence_bundle": rec.evidence_graph_json,
        "risk_assessment": rec.risk_assessment_json,
        "ai_explanation": rec.ai_explanation_json,
        "remediation": rec.remediation_json
    }


@app.get("/api/investigations/{investigation_id}/events")
def get_investigation_events(investigation_id: str, db: Session = Depends(get_db)):
    exists = db.query(InvestigationDB.id).filter(InvestigationDB.id == investigation_id).first()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")
    events = db.query(AuditEventDB).filter(AuditEventDB.investigation_id == investigation_id).order_by(AuditEventDB.id.asc()).all()
    return [{
        "id": e.id,
        "stage": e.stage,
        "status": e.status,
        "message": e.message,
        "details": e.details_json,
        "created_at": e.created_at.isoformat() if e.created_at else None
    } for e in events]


@app.post("/api/investigations/{investigation_id}/writeback")
async def trigger_writeback(
    investigation_id: str,
    db: Session = Depends(get_db),
    principal: MutationPrincipal = Depends(require_mutation_authorization)
):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")

    if rec.approval_status != "APPROVED":
        return {
            "status": WritebackStatus.AWAITING_APPROVAL.value,
            "success": False,
            "executed": False,
            "target_urn": rec.dataset_urn,
            "message": "Persisted approval is required before DataHub mutation",
        }
    if rec.datahub_writeback_status == WritebackStatus.SUCCESS.value and rec.writeback_result_json:
        return rec.writeback_result_json
    assets = (rec.evidence_graph_json or {}).get("classified_assets", [])
    wb = DataHubWritebackEngine()
    res = await wb.writeback_investigation(
        investigation_id=rec.id,
        dataset_urn=rec.dataset_urn,
        severity=rec.severity,
        recommendation=rec.recommendation,
        evidence_completeness=rec.evidence_completeness,
        evidence_trust=rec.evidence_trust or "DATAHUB UNAVAILABLE",
        confirmed_consumers=[a.get("name", a.get("asset_urn", "unknown")) for a in assets if a.get("classification") == "CONFIRMED_IMPACT"],
        potential_consumers=[a.get("name", a.get("asset_urn", "unknown")) for a in assets if a.get("classification") == "POTENTIAL_IMPACT"],
        summary=rec.ai_explanation_json.get("executive_summary", "Sentinel pre-merge investigation") if rec.ai_explanation_json else "Sentinel pre-merge investigation",
        remediation_status=rec.remediation_json.get("validation", {}).get("status") if rec.remediation_json else None,
        pr_url=rec.pr_url,
        approval_granted=True,
    )

    rec.datahub_writeback_status = res.status.value
    rec.writeback_result_json = res.model_dump()
    db.add(AuditEventDB(investigation_id=rec.id, stage="WRITEBACK", status=res.status.value, message=res.message, details_json=res.model_dump()))
    db.commit()

    if not res.success and res.status not in (WritebackStatus.DISABLED, WritebackStatus.DRY_RUN):
        raise HTTPException(
            status_code=502,
            detail=f"DataHub writeback failed: {res.message} ({res.error_detail or 'GMS Unreachable'})"
        )

    return res


@app.post("/api/investigations/{investigation_id}/github/comment")
async def trigger_github_comment(
    investigation_id: str,
    db: Session = Depends(get_db),
    principal: MutationPrincipal = Depends(require_mutation_authorization)
):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")

    if not rec.pr_url:
        raise HTTPException(status_code=400, detail="No PR URL associated with this investigation record.")

    if rec.approval_status != "APPROVED":
        return {
            "status": GitHubActionStatus.AWAITING_APPROVAL.value,
            "success": False,
            "action_type": "COMMENT",
            "message": "Persisted approval is required before posting a GitHub comment",
        }

    if rec.github_action_status == GitHubActionStatus.SUCCESS.value and rec.github_result_json:
        return rec.github_result_json

    gh = GitHubClient()
    res = await gh.post_pr_comment(
        pr_url=rec.pr_url,
        severity=rec.severity,
        recommendation=rec.recommendation,
        evidence_completeness=rec.evidence_completeness,
        evidence_trust=rec.evidence_trust or "DATAHUB UNAVAILABLE",
        proposed_change=rec.schema_change_json.get("changes", [{}])[0].get("details", "Schema modification") if rec.schema_change_json else "Schema modification",
        confirmed_consumers_count=rec.confirmed_consumers_count,
        critical_paths=[f"{edge.get('source')} -> {edge.get('target')}" for edge in (rec.evidence_graph_json or {}).get("graph", {}).get("edges", [])],
        recommended_action=rec.ai_explanation_json.get("recommended_action", "Review downstream model impact") if rec.ai_explanation_json else "Review impact",
        remediation_diff=rec.remediation_json.get("unified_diff") if rec.remediation_json else None,
        investigation_id=rec.id,
        approval_granted=True,
    )

    rec.github_action_status = res.status.value
    rec.github_result_json = res.model_dump()
    db.add(AuditEventDB(investigation_id=rec.id, stage="ACTION", status=res.status.value, message=res.message, details_json=res.model_dump()))
    db.commit()

    if not res.success and res.status not in (GitHubActionStatus.DISABLED, GitHubActionStatus.DRY_RUN):
        raise HTTPException(
            status_code=502,
            detail=f"GitHub action failed: {res.message}"
        )

    return res


@app.post("/api/investigations/{investigation_id}/approve")
def approve_investigation(
    investigation_id: str,
    db: Session = Depends(get_db),
    principal: MutationPrincipal = Depends(require_mutation_authorization),
):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")
    if rec.approval_status == "APPROVED":
        return {
            "status": "APPROVED",
            "approved_at": rec.approved_at.isoformat() if rec.approved_at else None,
            "approved_by": rec.approved_by,
        }
    if rec.approval_status not in ("AWAITING_APPROVAL", "NOT_REQUIRED"):
        raise HTTPException(status_code=409, detail=f"Investigation is not approvable from state {rec.approval_status}")
    from datetime import datetime, timezone
    rec.approval_status = "APPROVED"
    rec.approved_at = datetime.now(timezone.utc)
    rec.approved_by = principal.subject
    db.add(AuditEventDB(
        investigation_id=rec.id,
        stage="APPROVAL",
        status="APPROVED",
        message="External action approved by authenticated server request",
        details_json={"approved_by": rec.approved_by, "approved_at": rec.approved_at.isoformat()},
    ))
    db.commit()
    return {"status": rec.approval_status, "approved_at": rec.approved_at.isoformat(), "approved_by": rec.approved_by}
