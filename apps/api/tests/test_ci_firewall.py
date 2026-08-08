import pytest
import os
import sys
import subprocess
from pathlib import Path


def test_ci_diff_extraction_with_fixture():
    extract_script = Path("scripts/extract_pr_diff.py")
    fixture_file = Path("examples/critical-schema-removal/input.json")
    assert extract_script.exists()

    if fixture_file.exists():
        res = subprocess.run(
            [sys.executable, str(extract_script), "--fixture", str(fixture_file), "--output", "test_diff.json"],
            capture_output=True,
            text=True
        )
        assert res.returncode == 0
        assert Path("test_diff.json").exists()
        Path("test_diff.json").unlink(missing_ok=True)
