"""ML-9: TransE loss must use explicit formula, not fragile MarginRankingLoss.

ROOT-CAUSE: nn.MarginRankingLoss(target=-1) works for TransE but a future
"higher is better" model would silently train backwards.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/transe_model.py"
)


def test_transe_uses_explicit_loss_formula():
    src = _FILE.read_text()
    # The fix replaces margin_ranking_loss with explicit
    # (pos_scores - neg_scores + margin).clamp(min=0).mean()
    # Look for the explicit formula
    has_explicit = bool(
        re.search(r"pos.*neg.*margin.*clamp", src, re.DOTALL)
        or re.search(r"\(pos_scores\s*-\s*neg_scores\s*\+\s*config\.margin\)", src)
    )
    assert has_explicit, (
        "ML-9 REGRESSION: TransE still uses fragile nn.MarginRankingLoss. "
        "A future 'higher is better' model would silently train backwards."
    )


def test_transe_has_score_direction_assertion():
    src = _FILE.read_text()
    # The fix adds `assert config.score_direction == "lower_better"`
    assert "score_direction" in src, (
        "ML-9 REGRESSION: TransEConfig does not have score_direction field."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
