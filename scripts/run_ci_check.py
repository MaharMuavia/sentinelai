#!/usr/bin/env python3
"""
Sentinel AI — GitHub Actions CI/CD Policy Firewall Script
Evaluates Sentinel investigation output for a PR diff and enforces deterministic process exit codes.
Exits 0 ONLY for SAFE_TO_MERGE. Exits non-zero (1) for BLOCK, INSUFFICIENT_EVIDENCE, UNMAPPED_DATASET, or missing artifacts.
"""

import sys
import os
import json
import argparse
import asyncio
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

# Add apps/api to path for orchestrator
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.db.database import SessionLocal, init_db
from app.schema_engine.diff import SchemaSnapshot
from app.workflow.orchestrator import SentinelWorkflowOrchestrator
from app.risk.engine import DecisionVerdict


async def run_ci_check(diff_file: str, pr_url: str):
    diff_path = Path(diff_file)
    if not diff_path.is_absolute():
        diff_path = REPO_ROOT / diff_path
    if not diff_path.exists():
        print(f"[Sentinel CI Firewall] ERROR: Sentinel change artifact '{diff_file}' missing!")
        print("[Sentinel CI Firewall] Policy Enforcement: FAIL-CLOSED -> Exit Code 1")
        sys.exit(1)

    try:
        diff_data = json.loads(diff_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[Sentinel CI Firewall] ERROR: Failed to parse artifact '{diff_file}': {e}")
        sys.exit(1)

    status = diff_data.get("status")
    if status == "UNMAPPED_DATASET":
        print(f"[Sentinel CI Firewall] POLICY REJECTION: {diff_data.get('error', 'Unmapped dataset')}")
        print("[Sentinel CI Firewall] Policy Enforcement: UNMAPPED DATASET -> Exit Code 1")
        sys.exit(1)

    if status in ("UNSUPPORTED_CHANGE", "ERROR_MISSING_COMMITS"):
        print(f"[Sentinel CI Firewall] ERROR: Change extraction failed with status '{status}'")
        sys.exit(1)

    if "before_schema" not in diff_data or "after_schema" not in diff_data:
        print("[Sentinel CI Firewall] ERROR: Malformed schema diff payload.")
        sys.exit(1)

    try:
        before_schema = SchemaSnapshot.model_validate(diff_data["before_schema"])
        after_schema = SchemaSnapshot.model_validate(diff_data["after_schema"])
    except Exception as e:
        print(f"[Sentinel CI Firewall] ERROR: SchemaSnapshot validation error: {e}")
        sys.exit(1)

    print("[Sentinel CI Firewall] Running Sentinel Workflow Orchestrator analysis...")

    init_db()
    db = SessionLocal()
    try:
        orchestrator = SentinelWorkflowOrchestrator(db)
        investigation = await orchestrator.execute_investigation(
            before_schema=before_schema,
            after_schema=after_schema,
            pr_url=pr_url
        )

        print("\n==================================================")
        print(" SENTINEL AI PRE-MERGE FIREWALL ASSESSMENT")
        print("==================================================")
        print(f" Investigation ID:     {investigation.investigation_id}")
        print(f" Target Dataset:        {investigation.dataset_urn}")
        print(f" Risk Verdict:         {investigation.recommendation}")
        print(f" Severity:             {investigation.severity}")
        print(f" Evidence Coverage:    {investigation.evidence_completeness}%")
        print(f" Evidence Trust:       {investigation.evidence_trust}")
        print(f" Policy Triggered:     {investigation.risk_assessment.policy_triggered}")
        print("==================================================\n")

        verdict = investigation.recommendation

        if verdict == DecisionVerdict.SAFE_TO_MERGE:
            if investigation.evidence_trust.startswith("DEMO FIXTURE"):
                print("[Sentinel CI Firewall] SUCCESS: Explicit demo scenario policy is SAFE_TO_MERGE (not live verified).")
            else:
                print("[Sentinel CI Firewall] SUCCESS: PR schema modifications are safe to merge.")
            print("[Sentinel CI Firewall] Policy Enforcement -> Exit Code 0")
            sys.exit(0)

        elif verdict == DecisionVerdict.BLOCK:
            print(f"[Sentinel CI Firewall] PR BLOCKED: Critical or breaking downstream impacts detected.")
            print("[Sentinel CI Firewall] Policy Enforcement -> Exit Code 1")
            sys.exit(1)

        elif verdict == DecisionVerdict.INSUFFICIENT_EVIDENCE:
            print(f"[Sentinel CI Firewall] PR BLOCKED: Fail-closed policy triggered due to missing DataHub catalog evidence.")
            print("[Sentinel CI Firewall] Policy Enforcement -> Exit Code 1")
            sys.exit(1)

        elif verdict == DecisionVerdict.MERGE_WITH_CAUTION:
            # Configurable caution policy (default exit 1 for strict CI safety)
            strict_caution = os.getenv("SENTINEL_STRICT_CAUTION", "true").lower() == "true"
            if strict_caution:
                print("[Sentinel CI Firewall] PR WARNED: Merge with caution required (Strict policy -> Exit Code 1).")
                sys.exit(1)
            else:
                print("[Sentinel CI Firewall] PR WARNED: Merge with caution (Permissive policy -> Exit Code 0).")
                sys.exit(0)

        else:
            print(f"[Sentinel CI Firewall] ERROR: Unknown verdict status '{verdict}'")
            sys.exit(1)

    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Run Sentinel CI Firewall check on PR diff artifact")
    parser.add_argument("--diff-file", type=str, default="sentinel_diff.json", help="Path to schema diff artifact")
    parser.add_argument("--fixture", type=str, default=None, help="Explicit fixture file path")
    parser.add_argument("--pr-url", type=str, default=None, help="GitHub Pull Request URL")
    args = parser.parse_args()

    diff_file = args.fixture if args.fixture else args.diff_file
    pr_url = args.pr_url or os.getenv("GITHUB_PR_URL") or ""

    asyncio.run(run_ci_check(diff_file, pr_url))


if __name__ == "__main__":
    main()
