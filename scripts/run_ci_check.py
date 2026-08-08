#!/usr/bin/env python3
"""
Sentinel AI - CI Pipeline Runner
Executes Sentinel pre-merge investigation check for GitHub Actions workflows.
Enforces deterministic non-zero exit code (exit 1) on BLOCK and INSUFFICIENT_EVIDENCE verdicts.
"""
import sys
import os
import json
import asyncio
from pathlib import Path

# Ensure apps/api is in PYTHONPATH
api_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "api")
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from app.db.database import init_db, SessionLocal
from app.schema_engine.diff import SchemaSnapshot
from app.workflow.orchestrator import SentinelWorkflowOrchestrator


async def run_ci():
    print("[Sentinel AI] Starting CI Pre-Merge Investigation...")

    diff_path = Path("sentinel_diff.json")
    if diff_path.exists():
        data = json.loads(diff_path.read_text(encoding="utf-8"))
        before = SchemaSnapshot.model_validate(data["before_schema"])
        after = SchemaSnapshot.model_validate(data["after_schema"])
        pr_url = os.getenv("GITHUB_PR_URL", f"https://github.com/acme/sentinelai/pull/{data.get('pr_number', 42)}")
    else:
        # Fallback default breaking scenario
        dataset_urn = "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)"
        before = SchemaSnapshot(
            dataset={"urn": dataset_urn, "name": "raw_customers"},
            fields=[
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "email", "type": "STRING", "nullable": True},
                {"name": "country", "type": "STRING", "nullable": True}
            ]
        )
        after = SchemaSnapshot(
            dataset={"urn": dataset_urn, "name": "raw_customers"},
            fields=[
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "country", "type": "STRING", "nullable": True}
            ]
        )
        pr_url = os.getenv("GITHUB_PR_URL", "https://github.com/acme/sentinelai/pull/42")

    init_db()
    db = SessionLocal()
    try:
        orchestrator = SentinelWorkflowOrchestrator(db)
        result = await orchestrator.execute_investigation(
            before_schema=before,
            after_schema=after,
            pr_url=pr_url
        )

        print("----------------------------------------------------------------------")
        print(f"[Sentinel AI] Investigation ID: {result.investigation_id}")
        print(f"[Sentinel AI] Decision: {result.recommendation}")
        print(f"[Sentinel AI] Severity: {result.severity}")
        print(f"[Sentinel AI] Evidence Completeness: {result.evidence_completeness}%")
        print(f"[Sentinel AI] DataHub Writeback: {result.datahub_writeback_status}")
        print(f"[Sentinel AI] GitHub Action: {result.github_action_status}")
        print("----------------------------------------------------------------------")

        # Deterministic exit policy:
        # BLOCK or INSUFFICIENT_EVIDENCE -> Exit 1
        # SAFE_TO_MERGE or MERGE_WITH_CAUTION -> Exit 0
        if result.recommendation in ("BLOCK", "INSUFFICIENT_EVIDENCE"):
            print(f"[Sentinel AI] CI GATE FAILED: Decision is '{result.recommendation}'. Policy mandates non-zero exit.")
            sys.exit(1)

        print(f"[Sentinel AI] CI GATE PASSED: Decision is '{result.recommendation}'. PR merge allowed.")
        sys.exit(0)
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_ci())
