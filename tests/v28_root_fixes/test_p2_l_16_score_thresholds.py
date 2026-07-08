"""P2-L-16: DisGeNET/OMIM loaders must apply score thresholds.

ROOT-CAUSE: NO score threshold applied. score=0.01 noise loaded with
same weight as score=0.95 strong evidence.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase2")

from drugos_graph.config import DISGENET_MIN_SCORE, OMIM_MIN_SCORE  # noqa: E402


def test_disgenet_min_score_defined():
    assert DISGENET_MIN_SCORE > 0, (
        "P2-L-16 REGRESSION: DISGENET_MIN_SCORE not defined or zero. "
        "Noise edges (score=0.01) loaded with same weight as strong evidence."
    )


def test_omim_min_score_defined():
    assert OMIM_MIN_SCORE > 0, (
        "P2-L-16 REGRESSION: OMIM_MIN_SCORE not defined or zero."
    )


def test_disgenet_min_score_at_least_0_3():
    """DisGeNET's own recommendation: score >= 0.3 for curated."""
    assert DISGENET_MIN_SCORE >= 0.3, (
        f"P2-L-16 REGRESSION: DISGENET_MIN_SCORE={DISGENET_MIN_SCORE} is "
        f"below DisGeNET's recommended 0.3 cutoff."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
