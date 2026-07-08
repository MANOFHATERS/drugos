"""P1-ER-18: protein_resolver HMAC key must not be hardcoded in LIVE code.

ROOT-CAUSE: HMAC key `b"protein-resolver-tamper-evident-key"` was hardcoded
in source. Anyone with source access can forge signatures.

NOTE: The fix may reference this string in COMMENTS explaining what was
removed. That's fine. We only check LIVE code.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/protein_resolver.py"
)


def test_no_hardcoded_hmac_key_in_live_code():
    src = _FILE.read_text()
    # Strip comments and docstrings
    live_lines = []
    in_docstring = False
    for line in src.split("\n"):
        stripped = line.lstrip()
        # Track triple-quoted docstrings
        if '"""' in line:
            count = line.count('"""')
            if count == 1:
                in_docstring = not in_docstring
            # if count == 2, docstring opens and closes on same line — skip
            continue
        if in_docstring:
            continue
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_src = "\n".join(live_lines)

    # The hardcoded key must NOT appear in live code
    assert b"protein-resolver-tamper-evident-key" not in live_src.encode(), (
        "P1-ER-18 REGRESSION: protein_resolver.py still contains the "
        "hardcoded HMAC key in live code. Anyone with source access can "
        "forge signatures."
    )


def test_hmac_key_loaded_from_config_or_env():
    src = _FILE.read_text()
    # The fix should reference tamper_evident_key from config or env var
    assert (
        "tamper_evident_key" in src
        or "ENTITY_RESOLUTION_TAMPER_EVIDENT_KEY" in src
    ), (
        "P1-ER-18 REGRESSION: protein_resolver.py does not load HMAC key "
        "from config or env var."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
