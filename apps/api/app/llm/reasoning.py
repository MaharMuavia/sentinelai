import json
import httpx
from typing import List, Optional
from pydantic import BaseModel
from app.config import settings
from app.evidence.engine import ImpactEvidenceBundle, ImpactClassification
from app.risk.engine import RiskAssessment, Severity, DecisionVerdict


class EvidenceReference(BaseModel):
    evidence_id: str
    fact: str


class AIReasoningOutput(BaseModel):
    executive_summary: str
    proposed_change_summary: str
    why_it_matters: str
    affected_systems: List[str]
    recommended_action: str
    merge_recommendation: str  # BLOCK, MERGE_WITH_CAUTION, SAFE_TO_MERGE, INSUFFICIENT_EVIDENCE
    remediation_strategy: str
    evidence_ledger: List[EvidenceReference] = []


class LLMReasoningEngine:
    """
    Evidence-Grounded AI Explanation Engine.
    Generates natural language summaries and remediation strategies over verified DataHub evidence.
    CRITICAL RULE: The LLM NEVER determines the underlying risk verdict.
    The merge recommendation is ALWAYS dictated by the deterministic RiskEngine.
    """

    @staticmethod
    async def generate_explanation(
        bundle: ImpactEvidenceBundle,
        risk: RiskAssessment,
        remediation_diff: Optional[str] = None
    ) -> AIReasoningOutput:
        if settings.OPENAI_API_KEY:
            try:
                output = await LLMReasoningEngine._call_openai_llm(bundle, risk, remediation_diff)
                if output:
                    # Enforce deterministic risk verdict over LLM output
                    output.merge_recommendation = risk.verdict.value
                    return output
            except Exception:
                pass

        return LLMReasoningEngine._generate_deterministic_explanation(bundle, risk, remediation_diff)

    @staticmethod
    def _generate_deterministic_explanation(
        bundle: ImpactEvidenceBundle,
        risk: RiskAssessment,
        remediation_diff: Optional[str] = None
    ) -> AIReasoningOutput:
        breaking = [c for c in bundle.changes.changes if c.is_breaking]
        confirmed = [a for a in bundle.classified_assets if a.classification == ImpactClassification.CONFIRMED_IMPACT]

        field_names = ", ".join([f"'{c.field}'" for c in breaking]) or "schema fields"
        dataset_name = bundle.dataset_name
        evidence_word = "verified" if bundle.integration_mode.value == "LIVE_DATAHUB" else "observed in the explicit demo scenario"

        if risk.verdict == DecisionVerdict.INSUFFICIENT_EVIDENCE:
            exec_summary = (
                f"Proposed change to dataset '{dataset_name}' cannot be fully verified. "
                f"DataHub catalog metadata context is incomplete or unavailable."
            )
            why_matters = (
                f"Proceeding with unverified schema changes to {field_names} creates high risk of silent pipeline failure."
            )
            rec_action = "Verify DataHub connectivity or supply missing lineage metadata before merging PR."
            remediation_strat = "Require manual engineering review and verify downstream models manually."
        elif not breaking:
            exec_summary = (
                f"Proposed change to dataset '{dataset_name}' modifies {len(bundle.changes.changes)} field(s) "
                f"without a breaking schema change. Sentinel {evidence_word} {bundle.confirmed_consumers_count} "
                f"confirmed downstream consumer(s) across the DataHub lineage graph ({bundle.integration_mode.value})."
            )
            why_matters = (
                "The change is additive or relaxes an existing constraint. No confirmed downstream break was found "
                "in the available evidence; the displayed evidence coverage still states how much metadata was verified."
            )
            rec_action = "Merge according to the deterministic policy and monitor the normal validation pipeline."
            remediation_strat = "No downstream SQL remediation is required for this non-breaking schema change."
        else:
            exec_summary = (
                f"Proposed change to dataset '{dataset_name}' modifies {len(bundle.changes.changes)} field(s), "
                f"including breaking change(s) to {field_names}. Sentinel {evidence_word} {bundle.confirmed_consumers_count} "
                f"confirmed downstream consumer(s) across DataHub lineage graph ({bundle.integration_mode.value})."
            )
            if confirmed:
                confirmed_names = ", ".join(a.name for a in confirmed)
                why_matters = f"Altering column(s) {field_names} risks breaking confirmed downstream consumers: {confirmed_names}."
            else:
                why_matters = (
                    f"Altering column(s) {field_names} is breaking, but the available evidence did not confirm a downstream consumer."
                )
            rec_action = (
                f"Review affected downstream dbt models and dashboard field references before merging PR. "
                f"Apply generated candidate remediation patch where semantic safety is validated."
            )
            remediation_strat = (
                "1. Review unified diff generated by SQLGlot AST engine.\n"
                "2. Apply candidate patch to feature branch.\n"
                "3. Re-run Sentinel change analysis to confirm 0 downstream breaks.\n"
                "4. Obtain human engineer approval and merge PR."
            )

        affected_systems = [f"{a.name} ({a.platform} {a.asset_type})" for a in confirmed]
        if not affected_systems:
            affected_systems = ["No confirmed downstream consumers detected."]

        ledger: List[EvidenceReference] = []
        for asset in confirmed:
            for ev in asset.evidence:
                ledger.append(EvidenceReference(
                    evidence_id=ev.id,
                    fact=f"{asset.name}: {ev.description}"
                ))

        return AIReasoningOutput(
            executive_summary=exec_summary,
            proposed_change_summary=(
                f"{bundle.changes.source.upper()}: Schema modification on '{dataset_name}' "
                f"({field_names if breaking else ', '.join(c.field for c in bundle.changes.changes) or 'no field changes'})"
            ),
            why_it_matters=why_matters,
            affected_systems=affected_systems,
            recommended_action=rec_action,
            merge_recommendation=risk.verdict.value,
            remediation_strategy=remediation_strat,
            evidence_ledger=ledger
        )

    @staticmethod
    async def _call_openai_llm(
        bundle: ImpactEvidenceBundle,
        risk: RiskAssessment,
        remediation_diff: Optional[str]
    ) -> Optional[AIReasoningOutput]:
        prompt = {
            "dataset": bundle.dataset_name,
            "verdict": risk.verdict.value,
            "severity": risk.severity.value,
            "evidence_completeness": risk.evidence_completeness,
            "integration_mode": bundle.integration_mode.value,
            "confirmed_consumers": [a.name for a in bundle.classified_assets if a.classification == ImpactClassification.CONFIRMED_IMPACT],
            "risk_factors": [r.description for r in risk.risk_factors]
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            headers = {
                "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                "Content-Type": "application/json"
            }
            body = {
                "model": settings.AGENT_MODEL,
                "messages": [
                    {
                        "role": "system",
                        "content": "You are Sentinel AI Data Reliability Engineer. Reason ONLY over provided evidence. Do NOT invent assets."
                    },
                    {"role": "user", "content": json.dumps(prompt)}
                ],
                "response_format": {"type": "json_object"}
            }
            res = await client.post("https://api.openai.com/v1/chat/completions", headers=headers, json=body)
            if res.status_code == 200:
                data = res.json()["choices"][0]["message"]["content"]
                parsed = AIReasoningOutput.model_validate_json(data)
                parsed.merge_recommendation = risk.verdict.value
                return parsed
        return None
