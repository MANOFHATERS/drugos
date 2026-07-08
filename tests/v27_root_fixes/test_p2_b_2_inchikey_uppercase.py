"""P2-B-2: bridge must uppercase InChIKey before assigning canonical_id.

ROOT-CAUSE BEING VERIFIED:
  Bridge used raw InChIKey case. kg_builder.ID_PATTERNS requires
  uppercase. Lowercase InChIKeys got dead-lettered.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/phase1_bridge.py")


def test_bridge_uppercases_inchikey_for_canonical_id():
    src = _FILE.read_text()
    # Look for `.upper()` applied to inchikey near canonical_id assignment.
    # Acceptable patterns:
    #   inchikey.upper()
    #   canonical_id = inchikey.upper()
    #   inchikey_canonical = inchikey.upper() if inchikey else ""
    has_upper = bool(re.search(r"inchikey[^.]*\.upper\s*\(\s*\)", src))
    assert has_upper, (
        "P2-B-2 REGRESSION: bridge does not call .upper() on inchikey. "
        "Lowercase InChIKeys will be dead-lettered by "
        "kg_builder.ID_PATTERNS['Compound'] which requires uppercase."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
