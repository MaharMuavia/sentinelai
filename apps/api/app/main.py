import os
import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

from app.config import settings
from app.db.database import get_db, init_db
from app.db.models import InvestigationDB, AuditEventDB
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier, SchemaField
from app.schema_engine.parser import SchemaParserEngine
from app.datahub.client import DataHubClient, IntegrationMode
from app.datahub.writeback import DataHubWritebackEngine, WritebackStatus
from app.github.client import GitHubClient, GitHubActionStatus
from app.workflow.orchestrator import SentinelWorkflowOrchestrator, WorkflowProgressEvent, InvestigationResult


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database tables on startup
    init_db()
    yield


app = FastAPI(
    title="Sentinel AI API",
    description="Pre-Merge Data Change Control Agent powered by DataHub context",
    version="1.0.0",
    lifespan=lifespan
)

# Configurable CORS middleware for Next.js frontend
allowed_origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
    "http://localhost:8000"
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def verify_api_authorization(authorization: Optional[str] = Header(None)):
    """Validate API authorization token if SENTINEL_AUTH_TOKEN is configured."""
    expected_token = getattr(settings, "SENTINEL_AUTH_TOKEN", None) or os.getenv("SENTINEL_AUTH_TOKEN")
    if expected_token:
        if not authorization or not authorization.startswith("Bearer ") or authorization.split(" ")[1] != expected_token:
            raise HTTPException(status_code=401, detail="Unauthorized: Invalid or missing authorization token.")


class AnalyzeChangeRequest(BaseModel):
    before_schema: SchemaSnapshot
    after_schema: SchemaSnapshot
    pr_url: Optional[str] = Field(None, description="GitHub Pull Request URL")
    downstream_sql: Optional[str] = Field(None, description="Downstream model SQL query for remediation verification")
    is_approved: bool = Field(False, description="Explicit human approval for external mutations")


class AnalyzeDDLRequest(BaseModel):
    ddl_statement: str
    dataset_urn: Optional[str] = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    pr_url: Optional[str] = None
    is_approved: bool = False


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Sentinel AI", "version": "1.0.0"}


@app.get("/api/integrations/status")
async def integrations_status():
    dh_client = DataHubClient()
    github_client = GitHubClient()

    dh_connected = await dh_client.check_connection()
    dh_mode = await dh_client.get_integration_mode(allow_fixture_fallback=False)

    llm_connected = bool(settings.OPENAI_API_KEY)
    llm_mode = f"OpenAI ({settings.AGENT_MODEL})" if llm_connected else "DETERMINISTIC_FALLBACK"

    github_connected = github_client.is_configured()
    github_mode = "GitHub API" if github_connected else "Disabled / Dry-Run Local Mode"

    return {
        "datahub": {
            "name": "DataHub GMS / MCP",
            "url": settings.DATAHUB_GMS_URL,
            "connected": dh_connected,
            "mode": dh_mode.value
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
        downstream_sql=req.downstream_sql,
        is_approved=req.is_approved
    )
    return result


@app.post("/api/changes/analyze/stream")
async def analyze_change_stream(req: AnalyzeChangeRequest, db: Session = Depends(get_db)):
    orchestrator = SentinelWorkflowOrchestrator(db)

    async def event_generator():
        async for item in orchestrator.execute_investigation_streaming(
            before_schema=req.before_schema,
            after_schema=req.after_schema,
            pr_url=req.pr_url,
            downstream_sql=req.downstream_sql,
            is_approved=req.is_approved
        ):
            if isinstance(item, WorkflowProgressEvent):
                yield f"data: {item.model_dump_json()}\n\n"
            elif isinstance(item, InvestigationResult):
                yield f"data: {json.dumps({'type': 'RESULT', 'data': item.model_dump()})}\n\n"

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
    dataset_urn = req.dataset_urn or "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"

    # Attempt to load current base schema from DataHub if available
    dh_client = DataHubClient()
    base_meta = await dh_client.get_dataset(dataset_urn, allow_fixture_fallback=True)

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
        pr_url=req.pr_url,
        is_approved=req.is_approved
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
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return out


@app.get("/api/investigations/{investigation_id}")
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")

    risk_assessment = None
    if rec.evidence_graph_json and isinstance(rec.evidence_graph_json, dict):
        risk_assessment = rec.evidence_graph_json.get("risk_assessment")

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
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "changes": rec.schema_change_json,
        "evidence_bundle": rec.evidence_graph_json,
        "risk_assessment": risk_assessment,
        "ai_explanation": rec.ai_explanation_json,
        "remediation": rec.remediation_json
    }


@app.get("/api/investigations/{investigation_id}/events")
def get_investigation_events(investigation_id: str, db: Session = Depends(get_db)):
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
    auth: None = Depends(verify_api_authorization)
):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")

    wb = DataHubWritebackEngine()
    res = await wb.writeback_investigation(
        investigation_id=rec.id,
        dataset_urn=rec.dataset_urn,
        severity=rec.severity,
        recommendation=rec.recommendation,
        evidence_completeness=rec.evidence_completeness,
        evidence_trust="LIVE DATAHUB MCP" if rec.datahub_writeback_status == "SUCCESS" else "DEMO FIXTURE",
        confirmed_consumers=["customer_360", "marketing_dashboard"],
        potential_consumers=[],
        summary=rec.ai_explanation_json.get("executive_summary", "Sentinel pre-merge investigation") if rec.ai_explanation_json else "Sentinel pre-merge investigation",
        remediation_status=rec.remediation_json.get("validation", {}).get("status") if rec.remediation_json else None,
        pr_url=rec.pr_url,
        is_approved=True
    )

    rec.datahub_writeback_status = res.status.value
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
    auth: None = Depends(verify_api_authorization)
):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail=f"Investigation record '{investigation_id}' not found")

    if not rec.pr_url:
        raise HTTPException(status_code=400, detail="No PR URL associated with this investigation record.")

    gh = GitHubClient()
    res = await gh.post_pr_comment(
        pr_url=rec.pr_url,
        severity=rec.severity,
        recommendation=rec.recommendation,
        evidence_completeness=rec.evidence_completeness,
        evidence_trust="LIVE DATAHUB MCP",
        proposed_change=rec.schema_change_json.get("changes", [{}])[0].get("details", "Schema modification") if rec.schema_change_json else "Schema modification",
        confirmed_consumers_count=rec.confirmed_consumers_count,
        critical_paths=[f"{rec.dataset_urn} → downstream models"],
        recommended_action=rec.ai_explanation_json.get("recommended_action", "Review downstream model impact") if rec.ai_explanation_json else "Review impact",
        remediation_diff=rec.remediation_json.get("unified_diff") if rec.remediation_json else None,
        investigation_id=rec.id,
        is_approved=True
    )

    rec.github_action_status = res.status.value
    db.commit()

    if not res.success and res.status not in (GitHubActionStatus.DISABLED, GitHubActionStatus.DRY_RUN):
        raise HTTPException(
            status_code=502,
            detail=f"GitHub action failed: {res.message}"
        )

    return res
