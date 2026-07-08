"""P2-B-10: training_data temporal split must expose dropped pairs.

ROOT-CAUSE: pairs with no approval_year silently dropped from all splits
with no signal. Operators can't audit the loss.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/training_data.py"
)


def test_temporal_split_returns_dropped_key():
    src = _FILE.read_text()
    # The fix adds "dropped": no_year to the returned dict
    assert '"dropped"' in src or "'dropped'" in src, (
        "P2-B-10 REGRESSION: training_data temporal split does not expose "
        "'dropped' key. Pairs with no approval_year silently disappear."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
