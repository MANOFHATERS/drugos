"""P1-ER-4: protein_resolver must use SHA-256, not SHA-1.

ROOT-CAUSE BEING VERIFIED:
  protein_resolver used SHA-1 (cryptographically broken since 2017) for
  input/canonical/batch checksums while drug_resolver used SHA-256.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path(
    "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/protein_resolver.py"
)


def test_no_sha1_in_protein_resolver_live_code():
    """Live code (not comments) must not call hashlib.sha1()."""
    src = _FILE.read_text()
    # Strip comments
    live_lines = []
    for line in src.split("\n"):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        if "#" in line:
            line = line[: line.index("#")]
        live_lines.append(line)
    live_src = "\n".join(live_lines)

    matches = re.findall(r"hashlib\.sha1\s*\(", live_src)
    assert not matches, (
        f"P1-ER-4 REGRESSION: protein_resolver.py still contains "
        f"{len(matches)} hashlib.sha1() call(s) in live code. SHA-1 is "
        f"cryptographically broken since 2017. Replace with hashlib.sha256()."
    )


def test_sha256_used_in_protein_resolver():
    src = _FILE.read_text()
    assert "hashlib.sha256(" in src, (
        "P1-ER-4 setup: protein_resolver.py does not use hashlib.sha256()."
    )


def test_drug_resolver_uses_sha256():
    """drug_resolver.py should also use SHA-256 (control check)."""
    drug_src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase1/entity_resolution/drug_resolver.py"
    ).read_text()
    assert "hashlib.sha256(" in drug_src


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
