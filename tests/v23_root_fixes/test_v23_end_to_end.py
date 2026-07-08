"""v22 ROOT FIX verification — End-to-end runtime test.

This test runs the ACTUAL unified pipeline (python run_unified.py) and
verifies it exits 0 with V1 launch criteria satisfied. The user's
complaint was that previous sessions CLAIMED integration but the actual
runtime failed. This test catches that exact failure mode.

Audit Chain 1: "Default python run_unified.py exits 1 with no model
trained, no AUC computed, and no V1 launch criteria checked."
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent


def test_end_to_end_run_unified_exits_0_with_v1_pass():
    """``python run_unified.py`` MUST exit 0 with V1 launch criteria passed.

    Audit Chain 1: the previous default run exited 1 with no model trained.
    """
    # Ensure dev mode (default).
    env = os.environ.copy()
    env.pop("DRUGOS_ENVIRONMENT", None)
    # Allow stale CSVs (the toy fixture is intentionally small).
    env["DRUGOS_ALLOW_STALE_CSV"] = "1"

    # Clean previous run artifacts so we get a fresh V1 verdict.
    artifacts = [
        PROJECT_ROOT / "phase2/data/processed/pipeline_results.json",
        PROJECT_ROOT / "phase2/data/checkpoints/transe_best.pt",
    ]
    for f in artifacts:
        if f.exists():
            try:
                f.unlink()
            except OSError:
                pass
    for f in (PROJECT_ROOT / "phase2/data/processed").glob("drugos_heterodata__*"):
        try:
            f.unlink()
        except OSError:
            pass

    # Run the actual entry point.
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "run_unified.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )

    # The exit code MUST be 0 (success) — NOT 1 (V1 fail) or 4 (V1 criteria not met).
    assert result.returncode == 0, (
        f"run_unified.py exited with code {result.returncode}, expected 0.\n"
        f"STDOUT (last 2KB):\n{result.stdout[-2000:]}\n"
        f"STDERR (last 2KB):\n{result.stderr[-2000:]}"
    )

    # The output MUST contain "V1 criteria satisfied" or "V1 launch criteria: ... passed".
    combined = result.stdout + result.stderr
    assert (
        "V1 criteria satisfied" in combined
        or "'passed': True" in combined
        or "passed': True" in combined
    ), (
        "run_unified.py exited 0 but did NOT log V1 criteria satisfied. "
        f"Output (last 2KB):\n{combined[-2000:]}"
    )


def test_end_to_end_produces_model_artifact():
    """After a successful run, the TransE model checkpoint MUST exist."""
    env = os.environ.copy()
    env.pop("DRUGOS_ENVIRONMENT", None)
    env["DRUGOS_ALLOW_STALE_CSV"] = "1"

    # Run the pipeline first (in case the previous test cleaned artifacts).
    subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "run_unified.py")],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )

    checkpoint = PROJECT_ROOT / "phase2/data/checkpoints/transe_best.pt"
    assert checkpoint.exists(), (
        f"TransE model checkpoint not found at {checkpoint}. "
        "Step 11 (TransE training) did not save a model — V1 launch criteria "
        "cannot be verified."
    )
    # Checkpoint must be non-empty.
    assert checkpoint.stat().st_size > 0, (
        f"TransE model checkpoint is empty: {checkpoint}"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
