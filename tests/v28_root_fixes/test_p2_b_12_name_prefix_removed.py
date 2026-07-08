"""P2-B-12: kg_builder ID_PATTERNS["Compound"] must NOT accept NAME: prefix.

ROOT-CAUSE: `NAME:[A-Za-z0-9 _.-]{1,64}` accepted literally any string
as Compound ID. Defeats validation purpose.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/kg_builder.py"
)


def test_compound_id_pattern_does_not_accept_name_prefix():
    src = _FILE.read_text()
    # Find ID_PATTERNS["Compound"]
    m = re.search(r'"Compound"\s*:\s*r["\']([^"\']+)["\']', src)
    assert m, "P2-B-12 setup: cannot find ID_PATTERNS['Compound']"
    pattern = m.group(1)
    # Must NOT accept NAME: prefix
    assert "NAME:" not in pattern, (
        "P2-B-12 REGRESSION: ID_PATTERNS['Compound'] still accepts NAME: "
        "prefix. Literally any string can be a Compound ID, defeating "
        "validation purpose."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
