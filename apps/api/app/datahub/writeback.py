import os
import json
import logging
from enum import Enum
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from app.config import settings
from app.datahub.mcp_client import DataHubMCPClient, IntegrationMode

logger = logging.getLogger("sentinel.datahub.writeback")


class WritebackStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    DISABLED = "DISABLED"
    DRY_RUN = "DRY_RUN"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class WritebackResult(BaseModel):
    status: WritebackStatus
    success: bool
    document_urn: Optional[str] = None
    target_urn: str
    message: str
    error_detail: Optional[str] = None
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DataHubWritebackEngine:
    """
    Official DataHub Writeback Engine powered by Model Context Protocol (MCP).
    Persists investigation memory and additive tags into DataHub via MCP tool calls:
    - save_document
    - add_tags
    Never returns fake success when mutation is disabled or failed.
    """

    def __init__(self, gms_url: Optional[str] = None, token: Optional[str] = None):
        self.gms_url = (gms_url or settings.DATAHUB_GMS_URL).rstrip("/")
        self.token = token or settings.DATAHUB_GMS_TOKEN
        self.mcp_client = DataHubMCPClient(gms_url=self.gms_url, token=self.token)

    async def writeback_investigation(
        self,
        investigation_id: str,
        dataset_urn: str,
        severity: str,
        recommendation: str,
        evidence_completeness: float,
        confirmed_consumers: List[str],
        potential_consumers: List[str],
        summary: str,
        evidence_trust: str = "LIVE DATAHUB MCP",
        pr_url: Optional[str] = None,
        remediation_status: Optional[str] = None,
        is_dry_run: bool = False,
        is_approved: bool = True
    ) -> WritebackResult:
        """
        Persist Sentinel investigation outcome into DataHub as a persistent MCP Document.
        Respects DATAHUB_MUTATION_ENABLED and human approval gating.
        """
        mutation_enabled = os.getenv("DATAHUB_MUTATION_ENABLED", str(settings.DATAHUB_MUTATION_ENABLED)).lower() == "true"

        if not is_approved:
            logger.info(f"Writeback skipped for investigation {investigation_id}: Awaiting human approval")
            return WritebackResult(
                status=WritebackStatus.AWAITING_APPROVAL,
                success=False,
                target_urn=dataset_urn,
                message="Writeback paused: Awaiting human approval before mutating DataHub"
            )

        if not mutation_enabled:
            logger.info(f"Writeback skipped for investigation {investigation_id}: DATAHUB_MUTATION_ENABLED is False")
            return WritebackResult(
                status=WritebackStatus.DISABLED,
                success=False,
                target_urn=dataset_urn,
                message="DataHub mutation disabled (DATAHUB_MUTATION_ENABLED=false). Investigation not written to GMS."
            )

        if is_dry_run:
            logger.info(f"Writeback dry-run for investigation {investigation_id}")
            return WritebackResult(
                status=WritebackStatus.DRY_RUN,
                success=True,
                target_urn=dataset_urn,
                message="Dry-run writeback simulation complete."
            )

        # Build investigation document content
        doc_content = {
            "sentinel_investigation_id": investigation_id,
            "target_dataset_urn": dataset_urn,
            "pr_url": pr_url or "N/A",
            "risk_verdict": recommendation,
            "severity": severity,
            "evidence_coverage_percent": evidence_completeness,
            "evidence_trust": evidence_trust,
            "confirmed_consumers_count": len(confirmed_consumers),
            "confirmed_consumers": confirmed_consumers,
            "potential_consumers": potential_consumers,
            "remediation_status": remediation_status or "NOT_GENERATED",
            "investigation_summary": summary,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }

        doc_title = f"Sentinel AI Investigation: {recommendation} ({severity})"
        doc_text = json.dumps(doc_content, indent=2)

        # 1. Save document via DataHub MCP tool 'save_document'
        res = await self.mcp_client.save_document(
            urn=dataset_urn,
            title=doc_title,
            content=doc_text,
            doc_type="SENTINEL_INVESTIGATION"
        )

        if res.success:
            returned_urn = res.content.get("document_urn", res.content.get("urn", f"urn:li:document:{investigation_id}")) if isinstance(res.content, dict) else f"urn:li:document:{investigation_id}"

            # 2. Add additive Sentinel tag via MCP tool 'add_tags'
            tag_name = f"Sentinel_{recommendation}"
            await self.mcp_client.add_tags(urn=dataset_urn, tags=[tag_name])

            logger.info(f"Successfully persisted investigation {investigation_id} to DataHub via MCP document {returned_urn}")
            return WritebackResult(
                status=WritebackStatus.SUCCESS,
                success=True,
                document_urn=returned_urn,
                target_urn=dataset_urn,
                message=f"Investigation document successfully saved to DataHub ({returned_urn})"
            )
        else:
            logger.error(f"DataHub MCP writeback failed for {investigation_id}: {res.error_message}")
            return WritebackResult(
                status=WritebackStatus.FAILED,
                success=False,
                target_urn=dataset_urn,
                message="DataHub MCP writeback failed",
                error_detail=res.error_message or "MCP save_document tool execution error"
            )
