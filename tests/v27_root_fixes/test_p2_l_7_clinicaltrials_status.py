"""P2-L-7: ClinicalTrials default allowed_statuses must be ("Completed",) only.

ROOT-CAUSE BEING VERIFIED:
  Default included "Recruiting", "Not yet recruiting", "Enrolling by
  invitation", "Active, not recruiting" — trials with zero results,
  zero enrollment. Counted as evidence of efficacy → patient safety risk.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase2")

from drugos_graph.config import CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES  # noqa: E402


def test_default_allowed_statuses_only_completed():
    assert CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES == ("Completed",), (
        f"P2-L-7 REGRESSION: CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES = "
        f"{CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES}. Must be "
        f"('Completed',) only. Trials with zero results data must NOT "
        f"be counted as efficacy evidence."
    )


def test_recruiting_not_in_default():
    assert "Recruiting" not in CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES
    assert "Not yet recruiting" not in CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES
    assert "Enrolling by invitation" not in CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES
    assert "Active, not recruiting" not in CLINICALTRIALS_DEFAULT_ALLOWED_STATUSES


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
