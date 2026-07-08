"""P1-ER-2: is_valid_inchikey must reject test-fixture prefixes.

ROOT-CAUSE BEING VERIFIED:
  is_valid_inchikey returned True for keys starting with TEST, OUTER,
  INNER, IK. Real InChIKeys NEVER start with these. Test fixtures could
  flow through to DB → KG.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add phase1 to path
sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase1")

from cleaning.normalizer import is_valid_inchikey  # noqa: E402


def test_real_inchikey_accepted():
    """A real InChIKey (Aspirin) must be accepted."""
    assert is_valid_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N") is True


def test_synth_prefix_accepted():
    """SYNTH-prefixed keys are platform-generated synthetic keys, allowed."""
    assert is_valid_inchikey("SYNTHAAAAAAAAAA-UHFFFAOYSA-A") is True


def test_test_prefix_rejected():
    """TEST-prefixed keys are test fixtures, must be REJECTED."""
    assert is_valid_inchikey("TEST-IK-001") is False, (
        "P1-ER-2 REGRESSION: TEST-IK-001 was accepted. Test-fixture "
        "prefixes must never enter production data."
    )


def test_outer_prefix_rejected():
    assert is_valid_inchikey("OUTER-IK-002") is False


def test_inner_prefix_rejected():
    assert is_valid_inchikey("INNER-IK-003") is False


def test_ik_prefix_rejected():
    assert is_valid_inchikey("IK001") is False


def test_lowercase_inchikey_normalized_to_uppercase():
    """Real InChIKeys are uppercase. The validator may normalize lowercase
    input to uppercase (acceptable) — but if so, must consistently accept
    BOTH the lowercase and uppercase forms."""
    lower_valid = is_valid_inchikey("bsynrymutxbxsq-uhfffaoysa-n")
    upper_valid = is_valid_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
    # Either both True (validator normalizes case) or both False (validator
    # requires explicit uppercase). The bug is if they differ.
    assert lower_valid == upper_valid, (
        "P1-ER-2 REGRESSION: validator gives different answers for "
        "lowercase vs uppercase InChIKey of the same molecule. Must "
        "either normalize case or require uppercase consistently."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
