import pytest
import os
import sys
import json
import subprocess
from pathlib import Path


def test_ci_missing_artifact_exits_nonzero():
    """Verify run_ci_check.py exits non-zero (1) when sentinel_diff.json is missing."""
    ci_script = Path("scripts/run_ci_check.py")
    assert ci_script.exists()

    res = subprocess.run(
        [sys.executable, str(ci_script), "--diff-file", "non_existent_diff.json"],
        capture_output=True,
        text=True
    )
    assert res.returncode == 1
    assert "FAIL-CLOSED" in res.stdout or "ERROR" in res.stdout


def test_ci_fixture_block_exits_nonzero():
    """Verify run_ci_check.py exits non-zero (1) for BLOCK verdict scenario."""
    ci_script = Path("scripts/run_ci_check.py")
    fixture_file = Path("examples/critical-schema-removal/input.json")
    
    if fixture_file.exists():
        env = {**os.environ, "SENTINEL_DATA_MODE": "fixture"}
        res = subprocess.run(
            [sys.executable, str(ci_script), "--fixture", str(fixture_file)],
            capture_output=True,
            text=True,
            env=env
        )
        assert res.returncode == 1
        assert "PR BLOCKED" in res.stdout or "BLOCK" in res.stdout


def test_ci_fixture_safe_exits_zero():
    """Verify run_ci_check.py exits zero (0) for SAFE_TO_MERGE scenario in fixture mode."""
    ci_script = Path("scripts/run_ci_check.py")
    fixture_file = Path("examples/safe-additive-change/input.json")
    
    if fixture_file.exists():
        env = {**os.environ, "SENTINEL_DATA_MODE": "fixture"}
        res = subprocess.run(
            [sys.executable, str(ci_script), "--fixture", str(fixture_file)],
            capture_output=True,
            text=True,
            env=env
        )
        assert res.returncode == 0
        assert "SUCCESS" in res.stdout or "SAFE_TO_MERGE" in res.stdout
