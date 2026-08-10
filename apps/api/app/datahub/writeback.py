from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field

from app.config import settings
from app.datahub.mcp_client import DataHubMCPClient


class WritebackStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    PARTIAL_FAILURE = "PARTIAL_FAILURE"
    DISABLED = "DISABLED"
    DRY_RUN = "DRY_RUN"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"


class MutationOperationResult(BaseModel):
    status: WritebackStatus
    success: bool
    executed: bool = False
    error_detail: Optional[str] = None


class WritebackResult(BaseModel):
    status: WritebackStatus
    success: bool
    executed: bool = False
    document_urn: Optional[str] = None
    target_urn: str
    message: str
    error_detail: Optional[str] = None
    document_write: Optional[MutationOperationResult] = None
    tag_write: Optional[MutationOperationResult] = None
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class DataHubWritebackEngine:
    def __init__(self, gms_url: Optional[str] = None, token: Optional[str] = None):
        self.mcp_client = DataHubMCPClient(
            gms_url=gms_url or settings.DATAHUB_GMS_URL,
            token=token if token is not None else settings.DATAHUB_GMS_TOKEN,
            mcp_endpoint=settings.DATAHUB_MCP_ENDPOINT,
            mcp_command=settings.DATAHUB_MCP_COMMAND,
            mcp_args=settings.DATAHUB_MCP_ARGS,
        )

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
        evidence_trust: str,
        pr_url: Optional[str] = None,
        remediation_status: Optional[str] = None,
        is_dry_run: bool = False,
        approval_granted: bool = False,
    ) -> WritebackResult:
        mutation_enabled = os.getenv(
            "DATAHUB_MUTATION_ENABLED", str(settings.DATAHUB_MUTATION_ENABLED)
        ).lower() == "true"
        if not approval_granted:
            return WritebackResult(
                status=WritebackStatus.AWAITING_APPROVAL,
                success=False,
                target_urn=dataset_urn,
                message="Writeback requires persisted server-side approval",
            )
        if not mutation_enabled:
            return WritebackResult(
                status=WritebackStatus.DISABLED,
                success=False,
                target_urn=dataset_urn,
                message="Sentinel DataHub mutations are disabled",
            )
        if is_dry_run:
            return WritebackResult(
                status=WritebackStatus.DRY_RUN,
                success=False,
                executed=False,
                target_urn=dataset_urn,
                message="Dry-run requested; no external operation was executed",
            )

        content = json.dumps(
            {
                "sentinel_investigation_id": investigation_id,
                "target_dataset_urn": dataset_urn,
                "pr_url": pr_url,
                "risk_verdict": recommendation,
                "severity": severity,
                "evidence_coverage_percent": evidence_completeness,
                "evidence_trust": evidence_trust,
                "confirmed_consumers": confirmed_consumers,
                "potential_consumers": potential_consumers,
                "remediation_status": remediation_status,
                "investigation_summary": summary,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            },
            indent=2,
        )
        document_result = await self.mcp_client.save_document(
            title=f"Sentinel AI Investigation: {recommendation} ({severity})",
            content=content,
            related_assets=[dataset_urn],
        )
        if not document_result.success or not document_result.content:
            failed = MutationOperationResult(
                status=WritebackStatus.FAILED,
                success=False,
                executed=True,
                error_detail=document_result.error_message or "save_document returned no valid result",
            )
            return WritebackResult(
                status=WritebackStatus.FAILED,
                success=False,
                executed=True,
                target_urn=dataset_urn,
                message="DataHub save_document failed",
                error_detail=failed.error_detail,
                document_write=failed,
            )

        document_urn = self._document_urn(document_result.content)
        if not document_urn:
            failed = MutationOperationResult(
                status=WritebackStatus.FAILED,
                success=False,
                executed=True,
                error_detail="save_document succeeded without returning document identity",
            )
            return WritebackResult(
                status=WritebackStatus.FAILED,
                success=False,
                executed=True,
                target_urn=dataset_urn,
                message="DataHub document identity was not returned; tag write was not attempted",
                error_detail=failed.error_detail,
                document_write=failed,
            )

        saved = MutationOperationResult(status=WritebackStatus.SUCCESS, success=True, executed=True)
        tag_urn = f"urn:li:tag:Sentinel_{recommendation}"
        tag_result = await self.mcp_client.add_tags(tag_urns=[tag_urn], entity_urns=[dataset_urn])
        if not tag_result.success:
            failed = MutationOperationResult(
                status=WritebackStatus.FAILED,
                success=False,
                executed=True,
                error_detail=tag_result.error_message or "add_tags returned an error",
            )
            return WritebackResult(
                status=WritebackStatus.PARTIAL_FAILURE,
                success=False,
                executed=True,
                document_urn=document_urn,
                target_urn=dataset_urn,
                message="Investigation document saved, but Sentinel tag write failed",
                error_detail=failed.error_detail,
                document_write=saved,
                tag_write=failed,
            )

        return WritebackResult(
            status=WritebackStatus.SUCCESS,
            success=True,
            executed=True,
            document_urn=document_urn,
            target_urn=dataset_urn,
            message="Investigation document and Sentinel tag saved to DataHub",
            document_write=saved,
            tag_write=MutationOperationResult(status=WritebackStatus.SUCCESS, success=True, executed=True),
        )

    @staticmethod
    def _document_urn(content: dict) -> Optional[str]:
        for key in ("document_urn", "documentUrn", "urn", "id"):
            value = content.get(key)
            if isinstance(value, str) and value.startswith("urn:li:document:"):
                return value
        document = content.get("document")
        if isinstance(document, dict):
            return DataHubWritebackEngine._document_urn(document)
        return None
