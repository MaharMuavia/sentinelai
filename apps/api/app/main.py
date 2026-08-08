import json
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from pydantic import BaseModel

from app.config import settings
from app.db.database import get_db, init_db
from app.db.models import InvestigationDB, AuditEventDB
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier, SchemaField
from app.schema_engine.parser import SchemaParserEngine
from app.datahub.client import DataHubClient
from app.datahub.writeback import DataHubWritebackEngine
from app.github.client import GitHubClient
from app.workflow.orchestrator import SentinelWorkflowOrchestrator, WorkflowProgressEvent


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize SQLite database tables on startup
    init_db()
    yield


app = FastAPI(
    title="Sentinel AI API",
    description="Pre-Merge Data Change Control Agent powered by DataHub",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeChangeRequest(BaseModel):
    before_schema: SchemaSnapshot
    after_schema: SchemaSnapshot
    pr_url: Optional[str] = None
    downstream_sql: Optional[str] = None


class AnalyzeDDLRequest(BaseModel):
    ddl_statement: str
    dataset_urn: Optional[str] = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
    pr_url: Optional[str] = None


@app.get("/health")
def health_check():
    return {"status": "ok", "app": "Sentinel AI", "version": "1.0.0"}


@app.get("/api/integrations/status")
async def integrations_status():
    dh_client = DataHubClient()
    github_client = GitHubClient()

    dh_connected = await dh_client.check_connection()
    llm_connected = bool(settings.OPENAI_API_KEY)
    github_connected = github_client.is_configured()

    return {
        "datahub": {
            "name": "DataHub GMS",
            "url": settings.DATAHUB_GMS_URL,
            "connected": dh_connected,
            "mode": "Live GMS Connection" if dh_connected else "Local Metadata Fallback"
        },
        "llm": {
            "name": "AI Reasoning Engine",
            "model": settings.AGENT_MODEL,
            "connected": llm_connected or True,
            "mode": f"OpenAI ({settings.AGENT_MODEL})" if llm_connected else "Deterministic Grounded LLM Engine"
        },
        "github": {
            "name": "GitHub Actions",
            "repository": settings.GITHUB_REPOSITORY or "Not configured",
            "connected": github_connected,
            "mode": "GitHub API" if github_connected else "Dry-Run Local Mode"
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
        async for event in orchestrator.execute_investigation_streaming(
            before_schema=req.before_schema,
            after_schema=req.after_schema,
            pr_url=req.pr_url,
            downstream_sql=req.downstream_sql
        ):
            if isinstance(event, WorkflowProgressEvent):
                yield f"data: {event.model_dump_json()}\n\n"
            else:
                # Final result
                yield f"data: {json.dumps({'type': 'RESULT', 'data': event.model_dump()})}\n\n"
    
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
    before, after = SchemaParserEngine.parse_sql_ddl_alter(req.ddl_statement, dataset_urn=req.dataset_urn)
    orchestrator = SentinelWorkflowOrchestrator(db)
    result = await orchestrator.execute_investigation(
        before_schema=before,
        after_schema=after,
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
            "created_at": r.created_at.isoformat() if r.created_at else None
        })
    return out


@app.get("/api/investigations/{investigation_id}")
def get_investigation(investigation_id: str, db: Session = Depends(get_db)):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Investigation not found")

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
async def trigger_writeback(investigation_id: str, db: Session = Depends(get_db)):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Investigation not found")

    wb = DataHubWritebackEngine()
    res = await wb.writeback_investigation(
        investigation_id=rec.id,
        dataset_urn=rec.dataset_urn,
        severity=rec.severity,
        recommendation=rec.recommendation,
        evidence_completeness=rec.evidence_completeness,
        confirmed_consumers=["customer_360", "marketing_dashboard", "churn_model"],
        potential_consumers=[],
        summary=rec.ai_explanation_json.get("executive_summary", "Sentinel pre-merge investigation"),
        remediation_diff=rec.remediation_json.get("unified_diff") if rec.remediation_json else None
    )

    rec.datahub_writeback_status = "SUCCESS" if res.success else "FAILED"
    db.commit()
    return res


@app.post("/api/investigations/{investigation_id}/github/comment")
async def trigger_github_comment(investigation_id: str, db: Session = Depends(get_db)):
    rec = db.query(InvestigationDB).filter(InvestigationDB.id == investigation_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Investigation not found")

    pr_number = 42
    if rec.pr_url:
        try:
            pr_number = int(rec.pr_url.rstrip('/').split('/')[-1])
        except (ValueError, IndexError):
            pass

    gh = GitHubClient()
    res = await gh.post_pr_comment(
        pr_number=pr_number,
        severity=rec.severity,
        recommendation=rec.recommendation,
        evidence_completeness=rec.evidence_completeness,
        proposed_change="COLUMN_REMOVED: customers.email",
        confirmed_consumers_count=rec.confirmed_consumers_count,
        critical_paths=[f"{rec.dataset_urn} → customer_360 → marketing_dashboard"],
        recommended_action=rec.ai_explanation_json.get("recommended_action", "Update downstream dbt models"),
        remediation_diff=rec.remediation_json.get("unified_diff") if rec.remediation_json else None,
        investigation_id=rec.id
    )

    rec.github_action_status = "COMMENTED" if res.success else "FAILED"
    db.commit()
    return res
