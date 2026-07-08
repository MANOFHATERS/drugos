"""ML-11: gpu_utils recommend_batch_size must account for num_negatives.

ROOT-CAUSE: formula `feat_dim * 4 * 2` assumed 2 nodes per sample. Actual
is (1 + num_negatives) * 2. Off by 11×.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/gpu_utils.py"
)


def test_recommend_batch_size_accepts_num_negatives():
    src = _FILE.read_text()
    m = re.search(
        r"def\s+recommend_batch_size\s*\(([^)]*)\)",
        src,
    )
    assert m, "ML-11 setup: cannot find recommend_batch_size"
    sig = m.group(1)
    assert "num_negatives" in sig, (
        "ML-11 REGRESSION: recommend_batch_size does not accept num_negatives "
        "parameter. Formula assumes 2 nodes per sample, off by 11× when "
        "num_negatives=10."
    )


def test_recommend_batch_size_formula_uses_num_negatives():
    src = _FILE.read_text()
    # The fix: bytes_per_sample = feat_dim * 4 * 2 * (1 + num_negatives)
    assert re.search(r"\(1\s*\+\s*num_negatives\)", src), (
        "ML-11 REGRESSION: recommend_batch_size formula does not multiply "
        "by (1 + num_negatives)."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
