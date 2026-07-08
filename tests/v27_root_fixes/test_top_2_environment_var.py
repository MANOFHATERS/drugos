"""TOP-2: ENVIRONMENT vs DRUGOS_ENVIRONMENT env-var name mismatch.

ROOT-CAUSE BEING VERIFIED:
  Phase 1 read ENVIRONMENT (vocab: dev/staging/prod).
  Phase 2 read DRUGOS_ENVIRONMENT (vocab: development/staging/production).
  Different names + different vocabularies = silent drift.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase1/config/settings.py")


def test_phase1_reads_drugos_environment():
    src = _FILE.read_text()
    # Phase 1 should now read DRUGOS_ENVIRONMENT (with backward-compat
    # fallback to ENVIRONMENT).
    assert "DRUGOS_ENVIRONMENT" in src, (
        "TOP-2 REGRESSION: phase1/config/settings.py does not read "
        "DRUGOS_ENVIRONMENT. Phase 1 / Phase 2 env-var name mismatch persists."
    )


def test_phase1_normalizes_vocabulary():
    """Phase 1 should normalize dev->development, prod->production."""
    src = _FILE.read_text()
    # Look for normalization logic
    assert ("development" in src and "production" in src), (
        "TOP-2 REGRESSION: phase1 does not normalize environment vocabulary "
        "to {development, staging, production}."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
