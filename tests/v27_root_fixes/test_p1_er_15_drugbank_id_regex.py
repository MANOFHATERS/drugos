"""P1-ER-15: DrugBank ID regex must align between Phase 1 and Phase 2.

ROOT-CAUSE BEING VERIFIED:
  Phase 1 resolver_utils used `^DB\d{5,7}$` (allowed 7 digits).
  Phase 2 kg_builder used `DB\d{5,6}` (allowed only 6 digits).
  Divergent — Phase 1 would accept IDs Phase 2 would reject.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/resolver_utils.py")


def test_drugbank_id_regex_allows_5_to_6_digits():
    src = _FILE.read_text()
    match = re.search(
        r"_DRUGBANK_ID_RE\s*(?::\s*[^=]+)?\s*=\s*re\.compile\(\s*r[\"']([^\"']+)[\"']\s*\)",
        src,
    )
    assert match, "P1-ER-15 setup: cannot find _DRUGBANK_ID_RE"
    pattern = re.compile(match.group(1))

    # 5-digit IDs (DB00001) — current DrugBank 5.1.x range
    assert pattern.match("DB00001"), "5-digit DrugBank ID rejected"
    # 6-digit IDs (DB123456) — allowed for future expansion
    assert pattern.match("DB123456"), "6-digit DrugBank ID rejected"
    # 7-digit IDs (DB1234567) — must be REJECTED (aligns with Phase 2 kg_builder)
    assert not pattern.match("DB1234567"), (
        "P1-ER-15 REGRESSION: 7-digit DrugBank ID accepted by Phase 1 "
        "but rejected by Phase 2 kg_builder.ID_PATTERNS['Compound']. "
        "Align on `^DB\\d{5,6}$`."
    )
    # 4-digit IDs — must be rejected
    assert not pattern.match("DB1234")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
