"""P2-L-12: DRKG must emit numeric source_confidence, not just string label.

ROOT-CAUSE: DRKG emitted string label "verified"/"curated" as
source_confidence. Downstream ORDER BY confidence DESC returned
alphabetical ordering, meaningless.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/drkg_loader.py"
)


def test_drkg_emits_source_confidence_label():
    src = _FILE.read_text()
    assert "source_confidence_label" in src, (
        "P2-L-12 REGRESSION: drkg_loader does not emit source_confidence_label. "
        "Original string label is lost."
    )


def test_drkg_emits_numeric_source_confidence():
    src = _FILE.read_text()
    # The fix maps labels to numeric: verified=1.0, curated=0.8, etc.
    assert re.search(r'verified["\']?\s*[:=]\s*1\.0|verified.*1\.0', src), (
        "P2-L-12 REGRESSION: drkg_loader does not map 'verified' -> 1.0 "
        "for numeric source_confidence."
    )
    assert re.search(r'curated["\']?\s*[:=]\s*0\.8|curated.*0\.8', src), (
        "P2-L-12 REGRESSION: drkg_loader does not map 'curated' -> 0.8."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
