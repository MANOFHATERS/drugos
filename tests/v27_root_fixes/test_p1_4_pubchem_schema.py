"""P1-4: PubChem protonation_state schema/code alignment.

ROOT-CAUSE BEING VERIFIED:
  Schema v1.json still documented V18 enum [N, M, P, S, null] while V19
  code returns full words (neutral, protonated, deprotonated, zwitterion,
  salt_form). Every row failed schema validation.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

_SCHEMA = Path("/home/z/my-project/v28/v28_upgraded/phase1/pipelines/schema/v1.json")


def test_schema_protonation_state_enum_uses_full_words():
    schema = json.loads(_SCHEMA.read_text())
    # Find pubchem_enrichment properties
    pubchem = schema.get("properties", {}).get("pubchem_enrichment.csv", {})
    props = pubchem.get("properties", {})
    protonation = props.get("protonation_state", {})
    enum = protonation.get("enum")
    assert enum is not None, (
        "P1-4 setup: pubchem_enrichment.csv.protonation_state has no enum"
    )
    # Must NOT contain the V18 single-char values
    forbidden = {"N", "M", "P", "S"}
    actual_forbidden = forbidden & set(enum)
    assert not actual_forbidden, (
        f"P1-4 REGRESSION: protonation_state enum still contains V18 "
        f"single-char values {actual_forbidden}. Should be full words."
    )
    # Must contain the V19 full-word values
    expected = {"neutral", "protonated", "deprotonated", "zwitterion", "salt_form"}
    missing = expected - set(enum)
    assert not missing, (
        f"P1-4 REGRESSION: protonation_state enum missing V19 values {missing}."
    )


def test_schema_salt_form_description_does_not_mention_v18_nm_ps():
    schema = json.loads(_SCHEMA.read_text())
    pubchem = schema.get("properties", {}).get("pubchem_enrichment.csv", {})
    props = pubchem.get("properties", {})
    salt_form = props.get("salt_form", {})
    description = salt_form.get("description", "")
    # The V18 doc said "N=neutral, M=deprotonated, P=protonated, S=salt_form"
    assert "N=neutral" not in description, (
        "P1-4 REGRESSION: salt_form description still references V18 N/M/P/S mapping."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
