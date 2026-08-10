#!/usr/bin/env python3
"""
Sentinel AI — Extract PR Schema Diff Helper Script for GitHub Actions CI/CD.
Extracts actual git diff between BASE_SHA and HEAD_SHA, maps modified files to DataHub URNs via sentinel_config.json,
and parses before/after schemas deterministically.
Eliminates fake hardcoded fallbacks.
"""

import sys
import os
import json
import argparse
import subprocess
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[1]

# Add apps/api to path for schema engine imports
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.schema_engine.parser import DDLParser, SchemaParseResult
from app.schema_engine.diff import SchemaSnapshot, DatasetIdentifier


def get_git_file_at_commit(commit_sha: str, file_path: str) -> str:
    """Retrieve contents of a file at a specific git commit SHA."""
    try:
        res = subprocess.run(
            ["git", "show", f"{commit_sha}:{file_path}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        return res.stdout
    except Exception as e:
        print(f"[Sentinel AI] Warning: Could not retrieve {file_path} at commit {commit_sha}: {e}")
        return ""


def load_sentinel_config() -> dict:
    """Load dataset URN repository mapping from sentinel_config.json."""
    config_path = REPO_ROOT / "sentinel_config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[Sentinel AI] Error reading sentinel_config.json: {e}")
    return {"datasets": {}}


def extract_git_changed_files(base_sha: str, head_sha: str) -> Optional[list[str]]:
    """Get list of modified files between base_sha and head_sha."""
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", f"{base_sha}...{head_sha}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
        return [f.strip() for f in res.stdout.splitlines() if f.strip()]
    except Exception as e:
        print(f"[Sentinel AI] Warning: Could not run git diff for {base_sha}...{head_sha}: {e}")
        return None


def extract_git_file_statuses(base_sha: str, head_sha: str) -> dict[str, str]:
    """Return Git's status code for each changed path."""
    try:
        res = subprocess.run(
            ["git", "diff", "--name-status", f"{base_sha}...{head_sha}"],
            capture_output=True,
            text=True,
            check=True,
            cwd=REPO_ROOT,
        )
    except Exception as e:
        print(f"[Sentinel AI] Warning: Could not read git change statuses: {e}")
        return {}

    statuses: dict[str, str] = {}
    for line in res.stdout.splitlines():
        status, separator, path = line.partition("\t")
        if separator and path.strip():
            statuses[path.strip()] = status.strip()[:1]
    return statuses


def main():
    parser = argparse.ArgumentParser(description="Extract schema diff from pull request commits")
    parser.add_argument("--base", type=str, default=None, help="Base commit SHA (github.event.pull_request.base.sha)")
    parser.add_argument("--head", type=str, default=None, help="Head commit SHA (github.event.pull_request.head.sha)")
    parser.add_argument("--pr", type=int, default=None, help="Pull Request Number")
    parser.add_argument("--fixture", type=str, default=None, help="Explicit fixture file path for local demo/testing")
    parser.add_argument("--output", type=str, default="sentinel_diff.json", help="Output artifact path")
    args = parser.parse_args()

    out_path = Path(args.output)
    if not out_path.is_absolute():
        out_path = REPO_ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Handle Explicit Local Fixture Mode (Only when explicitly passed via --fixture)
    if args.fixture:
        fixture_path = Path(args.fixture)
        if not fixture_path.is_absolute():
            fixture_path = REPO_ROOT / fixture_path
        if not fixture_path.exists():
            print(f"[Sentinel AI] Error: Specified fixture file '{args.fixture}' does not exist.")
            sys.exit(1)

        print(f"[Sentinel AI] Extracting PR diff from explicit fixture '{args.fixture}'...")
        fixture_data = json.loads(fixture_path.read_text(encoding="utf-8"))
        out_path.write_text(json.dumps(fixture_data, indent=2), encoding="utf-8")
        print(f"[Sentinel AI] Saved diff artifact to '{out_path}'.")
        sys.exit(0)

    base_sha = args.base or os.getenv("BASE_SHA") or os.getenv("GITHUB_BASE_SHA")
    head_sha = args.head or os.getenv("HEAD_SHA") or os.getenv("GITHUB_HEAD_SHA")
    pr_num = args.pr or int(os.getenv("GITHUB_PR_NUMBER", "0"))

    if not base_sha or not head_sha:
        print("[Sentinel AI] Error: Missing BASE_SHA or HEAD_SHA. Cannot extract PR diff without explicit commits.")
        diff_payload = {
            "pr_number": pr_num,
            "status": "ERROR_MISSING_COMMITS",
            "error": "BASE_SHA or HEAD_SHA not provided"
        }
        out_path.write_text(json.dumps(diff_payload, indent=2), encoding="utf-8")
        sys.exit(1)

    print(f"[Sentinel AI] Extracting PR diff between BASE={base_sha[:7]} and HEAD={head_sha[:7]} for PR #{pr_num}...")

    config = load_sentinel_config()
    dataset_mappings = config.get("datasets", {})

    changed_files = extract_git_changed_files(base_sha, head_sha)
    if changed_files is None:
        diff_payload = {
            "pr_number": pr_num,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "status": "ERROR_MISSING_COMMITS",
            "error": "Could not resolve the supplied BASE_SHA/HEAD_SHA git range",
        }
        out_path.write_text(json.dumps(diff_payload, indent=2), encoding="utf-8")
        sys.exit(1)

    file_statuses = extract_git_file_statuses(base_sha, head_sha)
    mapped_file = None
    target_urn = None

    for cf in changed_files:
        if cf in dataset_mappings:
            mapped_file = cf
            target_urn = dataset_mappings[cf]
            break

    if not mapped_file or not target_urn:
        print(f"[Sentinel AI] Warning: None of the changed files ({changed_files}) match mapped datasets in sentinel_config.json.")
        diff_payload = {
            "pr_number": pr_num,
            "base_sha": base_sha,
            "head_sha": head_sha,
            "changed_files": changed_files,
            "status": "UNMAPPED_DATASET",
            "error": f"No mapped dataset for changed files: {changed_files}"
        }
        out_path.write_text(json.dumps(diff_payload, indent=2), encoding="utf-8")
        sys.exit(1)

    # Fetch file content at BASE and HEAD
    base_content = get_git_file_at_commit(base_sha, mapped_file)
    head_content = get_git_file_at_commit(head_sha, mapped_file)

    if not head_content or (not base_content and file_statuses.get(mapped_file) != "A"):
        print(f"[Sentinel AI] Error: Failed to fetch contents of '{mapped_file}' at base ({base_sha[:7]}) or head ({head_sha[:7]}).")
        diff_payload = {
            "pr_number": pr_num,
            "status": "UNSUPPORTED_CHANGE",
            "error": f"Could not read {mapped_file} contents from git commits"
        }
        out_path.write_text(json.dumps(diff_payload, indent=2), encoding="utf-8")
        sys.exit(1)

    # Parse before and after schemas
    dataset_name = target_urn.split(",")[-2] if "," in target_urn else mapped_file.split("/")[-1].replace(".sql", "")
    if file_statuses.get(mapped_file) == "A" and not base_content:
        before_snapshot = SchemaSnapshot(
            dataset=DatasetIdentifier(urn=target_urn, name=dataset_name),
            fields=[],
        )
        before_parse = SchemaParseResult(success=True, snapshot=before_snapshot)
    else:
        before_parse = DDLParser.parse_create_table(base_content, dataset_name=dataset_name, dataset_urn=target_urn)
    after_parse = DDLParser.parse_create_table(head_content, dataset_name=dataset_name, dataset_urn=target_urn)

    if not before_parse.success or not after_parse.success or not before_parse.snapshot or not after_parse.snapshot:
        print(f"[Sentinel AI] Error: DDL parsing failed for '{mapped_file}'.")
        diff_payload = {
            "pr_number": pr_num,
            "status": "UNSUPPORTED_CHANGE",
            "error": f"DDL parse error: {before_parse.error or after_parse.error}"
        }
        out_path.write_text(json.dumps(diff_payload, indent=2), encoding="utf-8")
        sys.exit(1)

    diff_payload = {
        "pr_number": pr_num,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "dataset_urn": target_urn,
        "mapped_file": mapped_file,
        "changed_files": changed_files,
        "before_schema": before_parse.snapshot.model_dump(),
        "after_schema": after_parse.snapshot.model_dump(),
        "status": "EXTRACTED"
    }

    out_path.write_text(json.dumps(diff_payload, indent=2), encoding="utf-8")
    print(f"[Sentinel AI] Successfully extracted schema diff for {target_urn}. Saved artifact to '{out_path}'.")


if __name__ == "__main__":
    main()
