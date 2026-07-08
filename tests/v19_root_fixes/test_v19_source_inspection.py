"""V19 source-inspection tests for fixes that don't require heavy imports.

These tests verify the actual source code contains the V19 root-fix
patterns. They run instantly (no module imports) so they can be
verified even in environments where the full pipeline dependencies
(torch, neo4j, requests, rdkit) are not installed.

For each fix, the corresponding INVOCATION test (which actually executes
the fixed code path) lives in test_v19_root_fixes.py.
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


class TestPS12ValidationNegativesHardFailSource(unittest.TestCase):
    """PS-12 source inspection: 3 distinct raise RuntimeError sites in the
    validation-negatives block of transe_model.py.

    V18 had only 1 raise (the no-sampler path). V19 adds 2 more:
    (b) relation missing from per_relation_neg_pools
    (c) relation_to_types unpopulated on the sampler
    """

    def test_three_raise_sites_present(self):
        transe_path = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "transe_model.py"
        )
        source = transe_path.read_text()

        # Site (a): no sampler — V18 had this.
        self.assertIn("DRUGOS_ALLOW_NO_SAMPLER", source)

        # Site (b): missing-relation — V19 adds this.
        # v20: switched to re.search with re.DOTALL because assertRegex
        # doesn't accept a flags arg — the multi-line comment block between
        # the `if` and `raise` requires DOTALL to match. Pre-existing test bug.
        self.assertIsNotNone(
            re.search(
                r"pool is None or len\(pool\[1\]\) == 0:.*?raise RuntimeError",
                source, re.DOTALL,
            )
        )

        # Site (c): unpopulated relation_to_types — V19 adds this.
        self.assertIsNotNone(
            re.search(
                r"relation_to_types is empty.*?raise RuntimeError",
                source, re.DOTALL,
            )
        )

        # Count raises in the validation-negatives block.
        val_block_match = re.search(
            r"PS-12 / SW-15 ROOT FIX: validation negatives.*?(?=\n                # BUG-C-004)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(val_block_match)
        val_block = val_block_match.group(0)
        raise_count = val_block.count("raise RuntimeError")
        self.assertGreaterEqual(
            raise_count, 3,
            f"V19 PS-12: validation-negatives block must contain at least 3 "
            f"'raise RuntimeError' statements (V18 had 1). Found {raise_count}.",
        )


class TestSF3ChembStrictDefaultSource(unittest.TestCase):
    """SF-3 source inspection: ChEMBL clean_activities defaults to STRICT."""

    def test_strict_is_default(self):
        chembl_path = (
            _PROJECT_ROOT / "phase1" / "pipelines" / "chembl_pipeline.py"
        )
        source = chembl_path.read_text()
        self.assertIn("DRUGOS_ALLOW_PERMISSIVE_DPI", source)
        self.assertIn(
            '_strict = (_os.environ.get("DRUGOS_STRICT", "") == "1") or (not _permissive)',
            source,
        )


class TestSF7StringUniprotFatalSource(unittest.TestCase):
    """SF-7 source inspection: STRING and UniProt ingestion raise RuntimeError."""

    def test_string_ingestion_raises(self):
        run_pipeline_path = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        )
        source = run_pipeline_path.read_text()
        self.assertIn("DRUGOS_ALLOW_PERMISSIVE_KG", source)
        # v20: assertRegex doesn't accept re.DOTALL as 3rd arg (it's the msg).
        # Use re.search with DOTALL explicitly to span the multi-line block.
        self.assertIsNotNone(
            re.search(
                r"STRING ingestion failed.*?raise RuntimeError",
                source, re.DOTALL,
            )
        )

    def test_uniprot_ingestion_raises(self):
        run_pipeline_path = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "run_pipeline.py"
        )
        source = run_pipeline_path.read_text()
        self.assertIsNotNone(
            re.search(
                r"UniProt parsing failed.*?raise RuntimeError",
                source, re.DOTALL,
            )
        )


class TestCD2Migration005IntegerSource(unittest.TestCase):
    """CD-2 source inspection: migration 005 uses INTEGER (not SMALLINT)."""

    def test_integer_for_count_columns(self):
        migration_path = (
            _PROJECT_ROOT
            / "phase1"
            / "database"
            / "migrations"
            / "005_pubchem_compound_properties.sql"
        )
        source = migration_path.read_text()
        for col in [
            "h_bond_donor_count",
            "h_bond_acceptor_count",
            "rotatable_bond_count",
            "heavy_atom_count",
            "formal_charge",
        ]:
            pattern = re.compile(rf"\b{col}\s+(SMALLINT|INTEGER)\b", re.IGNORECASE)
            match = pattern.search(source)
            self.assertIsNotNone(match, f"column {col} not found")
            self.assertEqual(
                match.group(1).upper(), "INTEGER",
                f"V19 CD-2: column {col} must use INTEGER (not SMALLINT).",
            )


class TestCompound7DoctestSource(unittest.TestCase):
    """Compound-7 source inspection: doctest at resolver_utils.py:731-732
    must say 'r-aspirin' (not 'aspirin')."""

    def test_doctest_matches_actual_behavior(self):
        resolver_path = (
            _PROJECT_ROOT
            / "phase1"
            / "entity_resolution"
            / "resolver_utils.py"
        )
        source = resolver_path.read_text()
        match = re.search(
            r'>>> normalize_name\("\(R\)-aspirin"\)\s*\n\s*\'([^\']+)\'',
            source,
        )
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), "r-aspirin")


class TestPS5IndicationTypeTokenMatchSource(unittest.TestCase):
    """PS-5 source inspection: _derive_indication_type uses token match."""

    def test_uses_token_match(self):
        drugbank_path = (
            _PROJECT_ROOT / "phase1" / "pipelines" / "drugbank_pipeline.py"
        )
        source = drugbank_path.read_text()
        match = re.search(
            r'def _derive_indication_type\(dbid: str\) -> str:.*?return "unknown"',
            source, re.DOTALL,
        )
        self.assertIsNotNone(match)
        body = match.group(0)
        self.assertIn('g.replace(";", "|").split("|")', body)
        self.assertIn('if "withdrawn" in tokens:', body)
        self.assertNotIn('if "vet_approved" in g and "approved" not in g:', body)


class TestPS1InchikeyVersionFlagSource(unittest.TestCase):
    """PS-1 source inspection: InChIKey last char is version flag, not
    protonation flag."""

    def test_version_flag_constants_present(self):
        pubchem_path = (
            _PROJECT_ROOT / "phase1" / "pipelines" / "pubchem_pipeline.py"
        )
        source = pubchem_path.read_text()
        self.assertIn("INCHIKEY_VERSION_FLAGS", source)
        self.assertIn("_extract_inchikey_version_flag", source)
        self.assertIn("_extract_protonation_from_inchi", source)
        self.assertIn("_INCHI_PROTON_LAYER_RE", source)
        self.assertIn("_INCHI_CHARGE_LAYER_RE", source)
        # The V18 PROTONATION_VALUES 4-state constant must be GONE.
        self.assertNotIn('PROTONATION_VALUES: frozenset[str] = frozenset({"N", "M", "P", "S"})', source)


class TestRT2ChemblSQLSource(unittest.TestCase):
    """RT-2 source inspection: chembl SQL uses tc.target_id (not tc.tid)."""

    def test_uses_target_id(self):
        chembl_path = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "chembl_loader.py"
        )
        source = chembl_path.read_text()
        self.assertIn("target_components tc ON td.tid = tc.target_id", source)
        self.assertNotIn("target_components tc ON td.tid = tc.tid", source)


class TestPS7SiderColumnNamesSource(unittest.TestCase):
    """PS-7 source inspection: SIDER_COLUMN_NAMES[0]='stitch_id_flat',
    [1]='stitch_id_stereo'."""

    def test_column_order_correct(self):
        sider_path = (
            _PROJECT_ROOT / "phase2" / "drugos_graph" / "sider_loader.py"
        )
        source = sider_path.read_text()
        # Find the SIDER_COLUMN_NAMES tuple — comments inside the tuple
        # contain ')' characters, so we match up to the first ')' that's
        # alone on a line (the tuple's closing paren).
        tuple_match = re.search(
            r"SIDER_COLUMN_NAMES[^=]*=\s*\((.*?)\n\)",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(tuple_match, "SIDER_COLUMN_NAMES tuple not found")
        tuple_body = tuple_match.group(1)
        # Extract all quoted strings from the tuple body.
        quoted = re.findall(r'"([^"]+)"', tuple_body)
        self.assertGreaterEqual(
            len(quoted), 2,
            f"Expected at least 2 quoted strings in SIDER_COLUMN_NAMES, got {quoted}",
        )
        self.assertEqual(
            quoted[0], "stitch_id_flat",
            f"V19 PS-7: SIDER_COLUMN_NAMES[0] must be 'stitch_id_flat' "
            f"(col 1 of meddra_all_se.tsv.gz is FLAT). Got: {quoted[0]!r}",
        )
        self.assertEqual(
            quoted[1], "stitch_id_stereo",
            f"V19 PS-7: SIDER_COLUMN_NAMES[1] must be 'stitch_id_stereo' "
            f"(col 2 is STEREO). Got: {quoted[1]!r}",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
