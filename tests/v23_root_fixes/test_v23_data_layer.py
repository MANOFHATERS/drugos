"""v22 ROOT FIX verification tests — Part 2: Data Layer.

Verifies audit findings P1-7 (InChIKey), P1-8 (UniProt/gene-symbol),
P2-10 (migration rollback), P2-11 (dead-letter lock), P2-12 (no duplicate defs),
X-8 (gene_symbol quarantine), X-9 (chunk filtering asymmetry), X-10 (type contract).
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent.parent
PHASE1_ROOT = PROJECT_ROOT / "phase1"
PHASE2_ROOT = PROJECT_ROOT / "phase2"

for p in (str(PROJECT_ROOT), str(PHASE1_ROOT), str(PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


def _read(rel: str) -> str:
    return (PROJECT_ROOT / rel).read_text(encoding="utf-8")


def _source_lines(module_path: str) -> str:
    return _read(module_path)


def _fn_body(src: str, fn_name: str, window: int = 5000) -> str:
    """Return a window of source starting at `def <fn_name>`."""
    idx = src.find(f"def {fn_name}")
    if idx == -1:
        return ""
    return src[idx:idx + window]


# ─── P1-7: InChIKey validators unified ──────────────────────────────────────

def test_p1_7_inchikey_validators_unified():
    """normalizer.is_valid_inchikey and models._validate_inchikey MUST
    accept the SAME set of keys (delegation or replication).

    Audit Chain 3: IK001 passed DB validation but failed resolver →
    duplicate drug in canonical mapping.
    """
    normalizer_src = _source_lines("phase1/cleaning/normalizer.py")
    models_src = _source_lines("phase1/database/models.py")

    # normalizer.is_valid_inchikey must accept IK prefix.
    n_body = _fn_body(normalizer_src, "is_valid_inchikey")
    assert n_body, "normalizer.is_valid_inchikey not found"
    assert "IK" in n_body and "TEST" in n_body, (
        "normalizer.is_valid_inchikey does NOT accept IK/TEST/OUTER/INNER. "
        "The canonical validator is still divergent from models._validate_inchikey."
    )

    # models._validate_inchikey must delegate OR replicate canonical.
    m_body = _fn_body(models_src, "_validate_inchikey")
    assert m_body, "models._validate_inchikey not found"
    assert (
        "from cleaning.normalizer import is_valid_inchikey" in m_body
        or "_canonical_is_valid_inchikey" in m_body
    ), (
        "models._validate_inchikey does NOT delegate to normalizer.is_valid_inchikey. "
        "The two validators may diverge again."
    )


# ─── P1-8: UniProt regexes unified ──────────────────────────────────────────

def test_p1_8_uniprot_regex_unified():
    """models._UNIPROT_RE MUST match resolver_utils._UNIPROT_ACCESSION_RE.

    Audit finding: models used loose pattern [A-Z0-9]{3}[0-9] for 10-char
    IDs; resolver used strict [A-Z][A-Z0-9]{2}[0-9]. DB accepted IDs the
    resolver rejected.
    """
    models_src = _source_lines("phase1/database/models.py")
    has_import = "from entity_resolution.resolver_utils import _UNIPROT_ACCESSION_RE" in models_src
    has_strict_pattern = "[A-Z][A-Z0-9]{2}[0-9]" in models_src
    assert has_import or has_strict_pattern, (
        "models._UNIPROT_RE does NOT import from resolver_utils and does NOT "
        "use the official strict pattern. The divergent loose regex is still present."
    )


def test_p1_8_gene_symbol_regex_unified():
    """models._GENE_SYMBOL_RE and protein_resolver MUST use the same length cap.

    Audit finding: models used {0,49} (50 chars); protein_resolver used
    {0,39} (40 chars). 41-50 char symbols accepted by models were rejected
    by protein_resolver → silent data loss.
    """
    models_src = _source_lines("phase1/database/models.py")
    resolver_src = _source_lines("phase1/entity_resolution/protein_resolver.py")

    assert re.search(r"\[A-Za-z\]\[A-Za-z0-9\\-\]\{0,49\}", models_src), (
        "models._GENE_SYMBOL_RE does NOT use {0,49} (50-char cap)."
    )
    # protein_resolver MUST also use {0,49} (not {0,39}).
    resolver_caps = re.findall(r"\[A-Za-z\]\[A-Za-z0-9-\]\{0,(\d+)\}", resolver_src)
    assert resolver_caps, "protein_resolver gene-symbol regex not found"
    bad_caps = [c for c in resolver_caps if c != "49"]
    assert not bad_caps, (
        f"protein_resolver uses caps={bad_caps} (should all be 49). "
        "The divergent length cap is still present."
    )


# ─── P2-10: migration rollback sidecars exist ───────────────────────────────

def test_p2_10_migration_rollback_sidecars_exist():
    """All 6 migration files MUST have a corresponding _rollback.sql sidecar.

    Audit finding: rollback_migration raised NotImplementedError for every
    migration because no sidecars existed.
    """
    migrations_dir = PROJECT_ROOT / "phase1/database/migrations"
    migration_files = sorted(migrations_dir.glob("00*.sql"))
    forward_migrations = [f for f in migration_files if "_rollback" not in f.name]
    assert len(forward_migrations) >= 6, (
        f"Expected >=6 forward migrations, got {len(forward_migrations)}"
    )
    missing_sidecars = []
    for f in forward_migrations:
        stem = f.stem
        rollback = migrations_dir / f"{stem}_rollback.sql"
        if not rollback.exists():
            missing_sidecars.append(rollback.name)
    assert not missing_sidecars, (
        f"Missing rollback sidecars: {missing_sidecars}. "
        f"rollback_migration will raise NotImplementedError for these migrations."
    )


# ─── P2-11: dead-letter queue RLock ─────────────────────────────────────────

def test_p2_11_dead_letter_queue_has_lock():
    """loaders._dead_letter_queue MUST be protected by a Lock/RLock.

    Audit Chain 10: 7 concurrent pipelines race on copy() + clear().
    """
    src = _source_lines("phase1/database/loaders.py")
    assert "RLock" in src or "threading.Lock" in src, (
        "loaders._dead_letter_queue is NOT protected by a Lock/RLock. "
        "The 7-concurrent-pipeline race condition is still present."
    )


# ─── P2-12: no within-class duplicate method definitions ────────────────────

def test_p2_12_no_within_class_duplicate_methods_in_models():
    """models.py MUST NOT have within-class duplicate method definitions."""
    src = _source_lines("phase1/database/models.py")
    tree = ast.parse(src)
    duplicates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_names = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_names.append(item.name)
            seen = set()
            for name in method_names:
                if name in seen:
                    duplicates.append(f"{node.name}.{name}")
                seen.add(name)
    assert not duplicates, (
        f"Within-class duplicate method definitions in models.py: {duplicates[:10]}. "
        "Python keeps only the LAST definition — earlier defs are silently dead."
    )


def test_p2_12_no_within_class_duplicate_methods_in_loaders():
    """loaders.py MUST NOT have within-class duplicate method definitions."""
    src = _source_lines("phase1/database/loaders.py")
    tree = ast.parse(src)
    duplicates = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            method_names = []
            for item in node.body:
                if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    method_names.append(item.name)
            seen = set()
            for name in method_names:
                if name in seen:
                    duplicates.append(f"{node.name}.{name}")
                seen.add(name)
    assert not duplicates, (
        f"Within-class duplicate method definitions in loaders.py: {duplicates[:10]}"
    )


# ─── X-8: gene_symbol quarantine (not silent drop) ──────────────────────────

def test_x_8_loaders_quarantines_invalid_gene_symbol():
    """loaders._pre_validate_proteins MUST quarantine (not silently drop)
    invalid gene symbols.

    Audit Chain 2: mouse protein 'Tp53' entered via resolver, failed
    models validator, loader caught and set gene_symbol=None silently →
    protein-disease edges silently missing.
    """
    src = _source_lines("phase1/database/loaders.py")
    body = _fn_body(src, "_pre_validate_proteins")
    assert body, "_pre_validate_proteins not found"
    # The old buggy pattern: except ValueError: record["gene_symbol"] = None
    bad_pattern = re.search(
        r"except\s+ValueError[^:]*:\s*\n\s*record\[.gene_symbol.\]\s*=\s*None",
        body,
    )
    assert bad_pattern is None, (
        "_pre_validate_proteins STILL silently sets gene_symbol=None on "
        "ValueError. Mouse proteins (Tp53, Brca1) silently lose gene identity."
    )
    assert "_quarantine_invalid_record" in body, (
        "_pre_validate_proteins does NOT call _quarantine_invalid_record. "
        "Invalid gene symbols are not quarantined."
    )


# ─── X-9: protein loader chunk filtering (asymmetry fixed) ──────────────────

def test_x_9_protein_loader_filters_columns():
    """bulk_upsert_proteins MUST filter records to Protein.__table__.columns.keys()
    before insert (same pattern as bulk_upsert_drugs).

    Audit finding: drug loader filtered, protein loader did NOT →
    CompileError on extra lineage columns → 100% chunk dead-letter.
    """
    src = _source_lines("phase1/database/loaders.py")
    body = _fn_body(src, "bulk_upsert_proteins", window=8000)
    assert body, "bulk_upsert_proteins not found"
    assert "Protein.__table__.columns.keys()" in body, (
        "bulk_upsert_proteins does NOT filter records to "
        "Protein.__table__.columns.keys(). The chunk-filtering asymmetry "
        "(drug loader filters, protein loader doesn't) is still present."
    )


# ─── X-10: run_migrations type contract ─────────────────────────────────────

def test_x_10_run_migrations_errors_is_list_of_dicts():
    """MigrationResult.errors MUST be annotated as list[dict[str, str]]
    (not list[str]) to match the dicts that are actually appended.

    Audit finding: list[str] declared but dicts appended at lines 3344, 3375.
    """
    src = _source_lines("phase1/database/migrations/run_migrations.py")
    m = re.search(r"errors:\s*list\[([^\]]+)\]", src)
    assert m is not None, "errors field annotation not found"
    inner = m.group(1)
    assert "dict" in inner, (
        f"errors field is annotated as list[{inner}] — should be list[dict[str, str]] "
        "because dicts are appended at runtime."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
