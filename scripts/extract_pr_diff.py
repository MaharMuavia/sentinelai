#!/usr/bin/env python3
"""
Sentinel AI - Extract PR Schema Diff Helper Script for GitHub Actions CI/CD
"""
import sys
import json
import argparse


def main():
    parser = argparse.ArgumentParser(description="Extract schema diff from pull request")
    parser.add_argument("--pr", type=int, help="Pull Request Number")
    args = parser.parse_args()

    print(f"[Sentinel AI] Extracting PR diff for PR #{args.pr or 42}...")
    
    # Example payload output for CI workflow run
    mock_diff = {
        "pr_number": args.pr or 42,
        "dataset_urn": "urn:li:dataset:(urn:li:dataPlatform:snowflake,raw_customers,PROD)",
        "status": "EXTRACTED"
    }
    
    print(json.dumps(mock_diff, indent=2))
    print("[Sentinel AI] Schema diff extraction complete.")


if __name__ == "__main__":
    main()
