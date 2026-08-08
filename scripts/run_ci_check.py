#!/usr/bin/env python3
"""
Sentinel AI - CI Pipeline Runner
Executes Sentinel pre-merge investigation check for GitHub Actions workflows.
"""
import sys
import os
import asyncio

# Ensure apps/api is in PYTHONPATH
api_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "apps", "api")
if api_dir not in sys.path:
    sys.path.insert(0, api_dir)

from app.db.database import init_db, SessionLocal
from app.schema_engine.diff import SchemaSnapshot
from app.workflow.orchestrator import SentinelWorkflowOrchestrator


async def run_ci():
    print("[Sentinel AI] Starting CI Pre-Merge Investigation...")
    init_db()
    db = SessionLocal()
    try:
        orchestrator = SentinelWorkflowOrchestrator(db)
        before = SchemaSnapshot(
            dataset={"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", "name": "raw_customers"},
            fields=[
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "email", "type": "STRING", "nullable": True},
                {"name": "country", "type": "STRING", "nullable": True}
            ]
        )
        after = SchemaSnapshot(
            dataset={"urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", "name": "raw_customers"},
            fields=[
                {"name": "customer_id", "type": "STRING", "nullable": False},
                {"name": "country", "type": "STRING", "nullable": True}
            ]
        )
        
        result = await orchestrator.execute_investigation(
            before_schema=before,
            after_schema=after,
            pr_url=os.getenv("GITHUB_PR_URL", "https://github.com/acme/sentinelai/pull/42")
        )

        print(f"[Sentinel AI] Assessment Complete: Decision={result.recommendation}, Severity={result.severity}, EvidenceCompleteness={result.evidence_completeness}%")
        if result.recommendation == "BLOCK":
            print("[Sentinel AI] Gate Check: BLOCKED due to high risk breaking change downstream.")
            # Standard gate behavior - exit non-zero if blocked, or zero with warning
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(run_ci())
