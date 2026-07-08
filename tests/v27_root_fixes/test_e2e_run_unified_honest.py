"""End-to-end smoke test: run_unified.py must exit with code 4 and report
honest held_out_auc < 0.85.

ROOT-CAUSE BEING VERIFIED (the ML-1 fix at runtime):
  Before v27: held_out_auc was 0.90-0.99 (fake, non-type-constrained
  negatives). V1 launch falsely passed.
  After v27: held_out_auc must be HONEST (typically 0.50-0.70 on the
  toy fixture). V1 launch must FAIL with exit code 4.

This test runs the actual run_unified.py (NOT a test script) and
verifies the honest behavior.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path("/home/z/my-project/v28/v28_upgraded")


def test_run_unified_exits_with_code_4():
    """run_unified.py must exit with code 4 (V1 launch criteria not met)."""
    result = subprocess.run(
        [sys.executable, str(_ROOT / "run_unified.py")],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        timeout=180,
        env={**os.environ, "DRUGOS_SKIP_DOWNLOAD": "1", "DRUGOS_SKIP_NEO4J": "1"},
    )
    assert result.returncode == 4, (
        f"ML-1 RUNTIME REGRESSION: run_unified.py exited with code "
        f"{result.returncode}, expected 4. "
        f"stdout tail:\n{result.stdout[-1000:]}\n"
        f"stderr tail:\n{result.stderr[-1000:]}"
    )


def test_run_unified_reports_honest_held_out_auc_below_085():
    """The reported held_out_auc must be HONEST (below 0.85 launch threshold).

    Before v27: fake 0.90-0.99 (non-type-constrained negatives).
    After v27: must be < 0.85 (typically 0.50-0.70 on toy fixture).
    """
    result = subprocess.run(
        [sys.executable, str(_ROOT / "run_unified.py")],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        timeout=180,
        env={**os.environ, "DRUGOS_SKIP_DOWNLOAD": "1", "DRUGOS_SKIP_NEO4J": "1"},
    )
    output = result.stdout + result.stderr
    # Look for held_out_auc in the output
    import re
    match = re.search(r"held_out_auc[\"']?\s*[:=]\s*([0-9.]+)", output)
    assert match, (
        f"ML-1 RUNTIME REGRESSION: cannot find held_out_auc in output. "
        f"Output tail:\n{output[-2000:]}"
    )
    auc = float(match.group(1))
    # Must be below 0.85 (the V1 launch threshold). The honest baseline
    # on the toy fixture is typically 0.50-0.70.
    assert 0.0 <= auc < 0.85, (
        f"ML-1 RUNTIME REGRESSION: held_out_auc={auc} is NOT honest. "
        f"Either it's still fake (>0.85 with non-type-constrained "
        f"negatives) or it's negative (training never ran). "
        f"Expected: 0.50-0.70 range on toy fixture."
    )


def test_run_unified_does_not_report_fake_auc_above_090():
    """Sanity check: held_out_auc must NOT be in the fake 0.90-0.99 range."""
    result = subprocess.run(
        [sys.executable, str(_ROOT / "run_unified.py")],
        capture_output=True,
        text=True,
        cwd=str(_ROOT),
        timeout=180,
        env={**os.environ, "DRUGOS_SKIP_DOWNLOAD": "1", "DRUGOS_SKIP_NEO4J": "1"},
    )
    output = result.stdout + result.stderr
    import re
    match = re.search(r"held_out_auc[\"']?\s*[:=]\s*([0-9.]+)", output)
    if match:
        auc = float(match.group(1))
        assert not (0.90 <= auc <= 0.99), (
            f"ML-1 RUNTIME REGRESSION: held_out_auc={auc} is in the FAKE "
            f"0.90-0.99 range. The non-type-constrained negative sampling "
            f"bug is still present."
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
