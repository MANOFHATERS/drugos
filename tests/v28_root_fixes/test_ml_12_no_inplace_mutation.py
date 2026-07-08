"""ML-12: evaluation.py must NOT mutate caller's array in-place.

ROOT-CAUSE: np.negative(scores, out=scores) mutates caller's array.
Bootstrap CIs computed downstream use negated scores → wrong CI bounds.

NOTE: The fix may reference the old buggy pattern in COMMENTS explaining
what was removed. That's fine. We only check LIVE code.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/evaluation.py"
)


def test_evaluation_does_not_use_inplace_negative_in_live_code():
    src = _FILE.read_text()
    # Strip comments
    live_lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_src = "\n".join(live_lines)

    # The buggy pattern: np.negative(scores, out=scores)
    assert "np.negative(scores, out=scores)" not in live_src, (
        "ML-12 REGRESSION: evaluation.py uses np.negative(scores, out=scores) "
        "in live code. This mutates caller's array. Bootstrap CIs use "
        "negated scores → wrong CI bounds."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
