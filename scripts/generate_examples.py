#!/usr/bin/env python3
"""
Sentinel AI — Example Artifact Generator
Runs actual Sentinel workflow orchestrator to generate reproducible example artifacts for judging inspection.
"""

import sys
import os
import json
import asyncio
from pathlib import Path

os.environ["SENTINEL_DATA_MODE"] = "fixture"

# Add apps/api to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "api")))

from app.db.database import SessionLocal, init_db
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier, SchemaField
from app.workflow.orchestrator import SentinelWorkflowOrchestrator


async def generate_examples():
    init_db()
    db = SessionLocal()
    orchestrator = SentinelWorkflowOrchestrator(db)

    # --- 1. CRITICAL SCHEMA REMOVAL SCENARIO ---
    critical_before = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False, description="Primary key"),
            SchemaField(name="email", type="STRING", nullable=True, description="Customer email address"),
            SchemaField(name="country", type="STRING", nullable=True, description="Country code"),
            SchemaField(name="created_at", type="TIMESTAMP", nullable=False, description="Created timestamp")
        ]
    )

    critical_after = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False, description="Primary key"),
            SchemaField(name="country", type="STRING", nullable=True, description="Country code"),
            SchemaField(name="created_at", type="TIMESTAMP", nullable=False, description="Created timestamp")
        ]
    )

    res_critical = await orchestrator.execute_investigation(
        before_schema=critical_before,
        after_schema=critical_after,
        pr_url="https://github.com/MaharMuavia/sentinelai/pull/1",
        downstream_sql="SELECT customer_id, email, lifetime_value FROM customer_360 WHERE email IS NOT NULL;"
    )

    crit_dir = Path(__file__).resolve().parents[1] / "examples" / "critical-schema-removal"
    crit_dir.mkdir(parents=True, exist_ok=True)

    input_payload = {
        "status": "EXTRACTED",
        "dataset_urn": critical_before.dataset.urn,
        "before_schema": critical_before.model_dump(),
        "after_schema": critical_after.model_dump()
    }
    (crit_dir / "input.json").write_text(json.dumps(input_payload, indent=2), encoding="utf-8")
    (crit_dir / "evidence.json").write_text(json.dumps(res_critical.evidence_bundle.model_dump(), indent=2), encoding="utf-8")
    (crit_dir / "impact.json").write_text(json.dumps(res_critical.risk_assessment.model_dump(), indent=2), encoding="utf-8")
    (crit_dir / "validation.json").write_text(json.dumps(res_critical.remediation.validation.model_dump() if res_critical.remediation else {}, indent=2), encoding="utf-8")
    (crit_dir / "remediation.patch").write_text(res_critical.remediation.unified_diff if res_critical.remediation else "", encoding="utf-8")

    comment_md = (
        f"## Sentinel AI Change Impact Analysis\n\n"
        f"**Decision:** `{res_critical.recommendation}` | **Severity:** `{res_critical.severity}` | **Evidence Coverage:** `{res_critical.evidence_completeness}%` | **Trust:** `{res_critical.evidence_trust}`\n\n"
        f"### Proposed Change:\n`COLUMN_REMOVED: raw_customers.email`\n\n"
        f"**Confirmed Consumers Affected:** `{res_critical.confirmed_consumers_count}`\n\n"
        f"### Critical Lineage Paths:\n"
        f"- `raw_customers → customer_360 → marketing_dashboard`\n"
        f"- `raw_customers → churn_features → churn_model`\n\n"
        f"### Recommended Action:\n{res_critical.ai_explanation.recommended_action}\n\n"
        f"```diff\n{res_critical.remediation.unified_diff if res_critical.remediation else ''}\n```\n"
    )
    (crit_dir / "github-comment.md").write_text(comment_md, encoding="utf-8")

    inv_md = (
        f"# Sentinel AI Investigation Report ({res_critical.investigation_id})\n\n"
        f"**Dataset:** `{res_critical.dataset_urn}`\n"
        f"**Decision:** `{res_critical.recommendation}`\n"
        f"**Severity:** `{res_critical.severity}`\n"
        f"**Evidence Coverage:** `{res_critical.evidence_completeness}%`\n"
        f"**Evidence Trust:** `{res_critical.evidence_trust}`\n\n"
        f"## Executive Summary\n{res_critical.ai_explanation.executive_summary}\n\n"
        f"## Why It Matters\n{res_critical.ai_explanation.why_it_matters}\n"
    )
    (crit_dir / "investigation.md").write_text(inv_md, encoding="utf-8")

    # --- 2. SAFE ADDITIVE CHANGE SCENARIO ---
    safe_before = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="email", type="STRING", nullable=True)
        ]
    )

    safe_after = SchemaSnapshot(
        dataset=DatasetIdentifier(urn="urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)", name="raw_customers"),
        fields=[
            SchemaField(name="customer_id", type="STRING", nullable=False),
            SchemaField(name="email", type="STRING", nullable=True),
            SchemaField(name="signup_source", type="STRING", nullable=True)
        ]
    )

    res_safe = await orchestrator.execute_investigation(
        before_schema=safe_before,
        after_schema=safe_after,
        pr_url="https://github.com/MaharMuavia/sentinelai/pull/2",
        downstream_sql="SELECT customer_id, email FROM customer_360;"
    )

    safe_dir = Path(__file__).resolve().parents[1] / "examples" / "safe-additive-change"
    safe_dir.mkdir(parents=True, exist_ok=True)

    safe_input_payload = {
        "status": "EXTRACTED",
        "dataset_urn": safe_before.dataset.urn,
        "before_schema": safe_before.model_dump(),
        "after_schema": safe_after.model_dump()
    }
    (safe_dir / "input.json").write_text(json.dumps(safe_input_payload, indent=2), encoding="utf-8")
    (safe_dir / "evidence.json").write_text(json.dumps(res_safe.evidence_bundle.model_dump(), indent=2), encoding="utf-8")
    (safe_dir / "impact.json").write_text(json.dumps(res_safe.risk_assessment.model_dump(), indent=2), encoding="utf-8")
    (safe_dir / "validation.json").write_text(json.dumps(res_safe.remediation.validation.model_dump() if res_safe.remediation else {}, indent=2), encoding="utf-8")
    (safe_dir / "remediation.patch").write_text("", encoding="utf-8")
    (safe_dir / "github-comment.md").write_text(f"## Sentinel AI Analysis: SAFE_TO_MERGE\nSeverity: LOW\nNon-breaking additive column addition.", encoding="utf-8")
    (safe_dir / "investigation.md").write_text(f"# Sentinel AI Investigation Report ({res_safe.investigation_id})\nSafe additive change scenario coverage - not live verified.", encoding="utf-8")

    db.close()
    print("Example artifacts successfully generated!")


if __name__ == "__main__":
    asyncio.run(generate_examples())
