"""P1-ER-5: protein_resolver must register string_provisional/chembl_provisional/string_derived methods.

ROOT-CAUSE BEING VERIFIED:
  These methods were called via compute_match_confidence but NOT registered
  in METHOD_CONFIDENCE — they fell back to default 0.5 implicitly.
"""
from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase1")

# Import to trigger the module-level register_match_method calls
from entity_resolution import protein_resolver  # noqa: E402
from entity_resolution.resolver_utils import (  # noqa: E402
    METHOD_CONFIDENCE,
    compute_match_confidence,
)


def test_string_provisional_registered():
    assert "string_provisional" in METHOD_CONFIDENCE, (
        "P1-ER-5 REGRESSION: 'string_provisional' method not registered in "
        "METHOD_CONFIDENCE. Confidence falls back to implicit 0.5 default."
    )
    assert METHOD_CONFIDENCE["string_provisional"] == 0.5


def test_chembl_provisional_registered():
    assert "chembl_provisional" in METHOD_CONFIDENCE
    assert METHOD_CONFIDENCE["chembl_provisional"] == 0.5


def test_string_derived_registered():
    assert "string_derived" in METHOD_CONFIDENCE
    assert METHOD_CONFIDENCE["string_derived"] == 0.5


def test_compute_match_confidence_returns_pinned_value():
    """compute_match_confidence must return the pinned value, not the default."""
    assert compute_match_confidence("string_provisional") == 0.5
    assert compute_match_confidence("chembl_provisional") == 0.5
    assert compute_match_confidence("string_derived") == 0.5


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
