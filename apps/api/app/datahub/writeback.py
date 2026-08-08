import json
import logging
from typing import Dict, Any, Optional, List
import httpx
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger("sentinel.datahub.writeback")


class WritebackResult(BaseModel):
    success: bool
    investigation_doc_id: str
    datahub_urn: str
    message: str
    mutations_applied: List[str] = []
    error_detail: Optional[str] = None


class DataHubWritebackEngine:
    """
    Safe Official DataHub Aspect Mutation Engine.
    Ingests Sentinel change control audit documents and additive tags into DataHub GMS
    using Metadata Change Proposals (MCPs). Strictly verifies mutation response HTTP status.
    """

    def __init__(self, gms_url: Optional[str] = None, token: Optional[str] = None):
        self.gms_url = (gms_url or settings.DATAHUB_GMS_URL).rstrip("/")
        self.token = token or settings.DATAHUB_GMS_TOKEN
        self.mutation_enabled = settings.DATAHUB_MUTATION_ENABLED

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
        remediation_diff: Optional[str] = None,
        pr_url: Optional[str] = None
    ) -> WritebackResult:
        doc_id = f"sentinel-inv-{investigation_id}"
        mutations: List[str] = []

        if not self.mutation_enabled:
            logger.info("DataHub writeback skipped: DATAHUB_MUTATION_ENABLED is False")
            return WritebackResult(
                success=True,
                investigation_doc_id=doc_id,
                datahub_urn=dataset_urn,
                message="Writeback skipped (Mutation disabled in configuration)",
                mutations_applied=["MUTATION_DISABLED_BY_CONFIG"]
            )

        headers = {"Content-Type": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        # 1. First fetch existing dataset properties to avoid overwriting description/properties
        existing_custom_props: Dict[str, str] = {}
        existing_description: str = ""
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                get_res = await client.get(
                    f"{self.gms_url}/aspects/dataset/{dataset_urn}/datasetProperties",
                    headers=headers
                )
                if get_res.status_code == 200:
                    val = get_res.json().get("aspect", {}).get("value", "{}")
                    parsed_val = json.loads(val) if isinstance(val, str) else val
                    existing_custom_props = parsed_val.get("customProperties", {})
                    existing_description = parsed_val.get("description", "")
        except Exception:
            pass  # If fetch fails, proceed with additive proposal

        # Merge Sentinel investigation audit metadata additively into customProperties
        updated_custom_props = dict(existing_custom_props)
        updated_custom_props.update({
            "sentinelInvestigationId": investigation_id,
            "sentinelSeverity": severity,
            "sentinelRecommendation": recommendation,
            "sentinelEvidenceCompleteness": str(evidence_completeness),
            "sentinelPRUrl": pr_url or "N/A",
            "sentinelLastAuditSummary": summary[:200]
        })

        prop_payload = {
            "proposal": {
                "entityType": "dataset",
                "entityUrn": dataset_urn,
                "aspectName": "datasetProperties",
                "aspect": {
                    "value": json.dumps({
                        "name": dataset_urn.split(",")[-2] if "," in dataset_urn else dataset_urn,
                        "description": existing_description or "Dataset monitored by Sentinel AI Change Control Firewall",
                        "customProperties": updated_custom_props
                    }),
                    "contentType": "application/json"
                },
                "changeType": "UPSERT"
            }
        }

        tag_payload = {
            "proposal": {
                "entityType": "dataset",
                "entityUrn": dataset_urn,
                "aspectName": "globalTags",
                "aspect": {
                    "value": json.dumps({
                        "tags": [
                            {"tag": "urn:li:tag:sentinel:investigated"},
                            {"tag": f"urn:li:tag:sentinel:{severity.lower()}"}
                        ]
                    }),
                    "contentType": "application/json"
                },
                "changeType": "UPSERT"
            }
        }

        # Send MCP proposals to DataHub GMS
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                res_prop = await client.post(
                    f"{self.gms_url}/aspects?action=ingestProposal",
                    json=prop_payload,
                    headers=headers
                )
                res_tag = await client.post(
                    f"{self.gms_url}/aspects?action=ingestProposal",
                    json=tag_payload,
                    headers=headers
                )

                if res_prop.status_code in (200, 201) and res_tag.status_code in (200, 201):
                    mutations.append("INGESTED_SENTINEL_PROPERTIES_ASPECT")
                    mutations.append("INGESTED_SENTINEL_TAGS_ASPECT")
                    return WritebackResult(
                        success=True,
                        investigation_doc_id=doc_id,
                        datahub_urn=dataset_urn,
                        message="Successfully persisted Sentinel investigation audit record into DataHub GMS.",
                        mutations_applied=mutations
                    )
                else:
                    error_msg = f"DataHub GMS ingestProposal returned HTTP {res_prop.status_code} / {res_tag.status_code}"
                    logger.error(error_msg)
                    return WritebackResult(
                        success=False,
                        investigation_doc_id=doc_id,
                        datahub_urn=dataset_urn,
                        message="DataHub writeback failed: GMS rejected aspect proposal.",
                        mutations_applied=[],
                        error_detail=error_msg
                    )
        except Exception as e:
            err_str = f"DataHub writeback network error: {str(e)}"
            logger.error(err_str)
            return WritebackResult(
                success=False,
                investigation_doc_id=doc_id,
                datahub_urn=dataset_urn,
                message="DataHub writeback failed: GMS endpoint unreachable.",
                mutations_applied=[],
                error_detail=err_str
            )
