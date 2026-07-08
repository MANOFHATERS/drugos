"""ML-10: pyg_builder must have node_disjoint_split for GNN training.

ROOT-CAUSE: RandomLinkSplit is edge-level, not node-disjoint. Fine for
TransE, catastrophic leakage for Phase 3 GNN.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/pyg_builder.py"
)


def test_node_disjoint_split_method_exists():
    src = _FILE.read_text()
    assert "node_disjoint_split" in src, (
        "ML-10 REGRESSION: pyg_builder does not have node_disjoint_split "
        "method. Phase 3 GNN training will use edge-level split, causing "
        "catastrophic leakage."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
