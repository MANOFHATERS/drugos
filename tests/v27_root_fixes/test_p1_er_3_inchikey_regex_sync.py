"""P1-ER-3: InChIKey regex must be synchronized across normalizer / base / models.

ROOT-CAUSE BEING VERIFIED:
  normalizer._INCHIKEY_PATTERN accepted 30-char (with protonation suffix),
  base.INCHIKEY_PATTERN and models._STANDARD_INCHIKEY_RE rejected it.
  Same key accepted at one layer, rejected at another.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, "/home/z/my-project/v28/v28_upgraded/phase1")

from cleaning.normalizer import _INCHIKEY_PATTERN  # noqa: E402
from entity_resolution.base import (  # noqa: E402
    INCHIKEY_PATTERN,
    _STRICT_INCHIKEY_PATTERN,
    is_strict_inchikey,
)


def test_all_three_patterns_accept_standard_27_char_inchikey():
    """Standard 27-char InChIKey (Aspirin) must be accepted everywhere."""
    aspirin = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N"
    assert _INCHIKEY_PATTERN.match(aspirin)
    assert INCHIKEY_PATTERN.match(aspirin)


def test_all_three_patterns_accept_suffixed_inchikey():
    """InChIKey with protonation suffix (PubChem tautomeric) must be accepted."""
    suffixed = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N-a"
    assert _INCHIKEY_PATTERN.match(suffixed), (
        "P1-ER-3 REGRESSION: normalizer._INCHIKEY_PATTERN rejects suffixed key"
    )
    assert INCHIKEY_PATTERN.match(suffixed), (
        "P1-ER-3 REGRESSION: base.INCHIKEY_PATTERN rejects suffixed key "
        "but normalizer accepts it. Same key accepted at one layer, "
        "rejected at another — the original divergent-validators bug."
    )


def test_strict_inchikey_rejects_suffixed():
    """is_strict_inchikey must REJECT suffixed keys (that's its purpose)."""
    suffixed = "BSYNRYMUTXBXSQ-UHFFFAOYSA-N-a"
    assert is_strict_inchikey(suffixed) is False, (
        "P1-ER-3 REGRESSION: is_strict_inchikey accepts suffixed key. "
        "Strict validator exists to reject these."
    )


def test_strict_inchikey_accepts_standard():
    """is_strict_inchikey must ACCEPT standard 27-char keys."""
    assert is_strict_inchikey("BSYNRYMUTXBXSQ-UHFFFAOYSA-N") is True


def test_models_regex_matches_normalizer():
    """models._STANDARD_INCHIKEY_RE must use the same pattern as normalizer."""
    models_src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase1/database/models.py"
    ).read_text()
    # Find the _STANDARD_INCHIKEY_RE definition (allow type annotation
    # like `_STANDARD_INCHIKEY_RE: re.Pattern[str] = re.compile(...)`)
    match = re.search(
        r"_STANDARD_INCHIKEY_RE\s*(?::\s*[^=]+)?\s*=\s*re\.compile\(\s*(r[\"']([^\"']+)[\"'])\s*\)",
        models_src,
    )
    assert match, "P1-ER-3 setup: cannot find _STANDARD_INCHIKEY_RE in models.py"
    pattern_str = match.group(2)
    # Must accept the suffixed form (synchronized with normalizer)
    pattern = re.compile(pattern_str)
    assert pattern.match("BSYNRYMUTXBXSQ-UHFFFAOYSA-N"), (
        "P1-ER-3 REGRESSION: models._STANDARD_INCHIKEY_RE rejects standard InChIKey"
    )
    assert pattern.match("BSYNRYMUTXBXSQ-UHFFFAOYSA-N-a"), (
        "P1-ER-3 REGRESSION: models._STANDARD_INCHIKEY_RE rejects suffixed "
        "InChIKey but normalizer accepts it. Divergent validators."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
