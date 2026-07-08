"""P2-B-7: TransE SCORE FUNCTION must use L1 norm (Bordes 2013), not L2.

ROOT-CAUSE: score function used L2 norm. Bordes 2013 paper specifies L1.

NOTE: Bordes 2013 ALSO specifies L2-normalizing entity/relation
embeddings to unit length — that's a separate `p=2` call on
`normalize_entity_embeddings` / `normalize_relation_embeddings` and is
CORRECT. The bug is ONLY in the score function (||h+r-t||).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/transe_model.py"
)


def test_transe_score_function_uses_l1_norm():
    """The SCORE FUNCTION (||h+r-t||) must use L1, not L2.

    Bordes 2013 §3.2: "d(h+l, t) = ||h+l-t||_1" (L1 norm).
    """
    src = _FILE.read_text()
    # Strip comments to avoid matching the v28 fix comment block
    live_lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_src = "\n".join(live_lines)

    # Find the score function: pattern is (h + r - t).norm(p=N, dim=1)
    # or (h+r-t).norm(p=N, ...) — NOT embedding normalization which is
    # entity_embeddings.norm(p=2, dim=1, keepdim=True)
    score_pattern = re.compile(
        r"\(\s*h\s*\+\s*r\s*-\s*t\s*\)\.norm\s*\(\s*p\s*=\s*(\d)"
    )
    m = score_pattern.search(live_src)
    assert m, (
        "P2-B-7 setup: cannot find score function `(h + r - t).norm(p=N)` "
        "in transe_model.py live code"
    )
    p_value = int(m.group(1))
    assert p_value == 1, (
        f"P2-B-7 REGRESSION: TransE score function uses L{p_value} norm. "
        f"Bordes 2013 §3.2 specifies L1 (||h+r-t||_1). Margin calibration "
        f"is wrong with L2."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
