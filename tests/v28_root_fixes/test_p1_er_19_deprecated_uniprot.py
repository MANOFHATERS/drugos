"""P1-ER-19: _DEPRECATED_UNIPROT_MAP must be expanded + crosswalk loader.

ROOT-CAUSE: ~30 hardcoded entries. UniProt has thousands of deprecations.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/protein_resolver.py"
)


def test_deprecated_uniprot_map_expanded():
    src = _FILE.read_text()
    # Find the _DEPRECATED_UNIPROT_MAP dict
    m = re.search(
        r"_DEPRECATED_UNIPROT_MAP\s*:\s*Dict\[str,\s*str\]\s*=\s*\{([^}]+)\}",
        src,
        re.DOTALL,
    )
    assert m, "P1-ER-19 setup: cannot find _DEPRECATED_UNIPROT_MAP"
    body = m.group(1)
    # Count entries (lines with "X": "Y",)
    entries = re.findall(r'"[OPQ][0-9][A-Z0-9]{3}[0-9]"\s*:', body)
    # Must have at least 50 entries (was ~30)
    assert len(entries) >= 50, (
        f"P1-ER-19 REGRESSION: _DEPRECATED_UNIPROT_MAP has only "
        f"{len(entries)} entries (was ~30, must be 50+)."
    )


def test_load_uniprot_deprecation_crosswalk_exists():
    src = _FILE.read_text()
    assert "load_uniprot_deprecation_crosswalk" in src, (
        "P1-ER-19 REGRESSION: load_uniprot_deprecation_crosswalk function "
        "not found. Cannot load full UniProt deprecation list at runtime."
    )


def test_uniprot_deprecation_crosswalk_env_var():
    src = _FILE.read_text()
    assert "UNIPROT_DEPRECATION_CROSSWALK_PATH" in src, (
        "P1-ER-19 REGRESSION: UNIPROT_DEPRECATION_CROSSWALK_PATH env var "
        "not referenced. Cannot auto-load crosswalk."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
