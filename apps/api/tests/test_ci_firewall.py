import pytest
import os
import sys
import subprocess
from pathlib import Path


def test_ci_diff_extraction():
    extract_script = Path("scripts/extract_pr_diff.py")
    assert extract_script.exists()

    res = subprocess.run(
        [sys.executable, str(extract_script), "--pr", "42", "--output", "test_diff.json"],
        capture_output=True,
        text=True
    )
    assert res.returncode == 0
    assert Path("test_diff.json").exists()

    # Clean up test artifact
    Path("test_diff.json").unlink(missing_ok=True)
