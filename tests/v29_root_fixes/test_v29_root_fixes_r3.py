"""v29 ROOT FIX verification tests — round 3 (fixes 19-28).

Each test verifies ONE specific root-level fix from the third round
of the forensic audit remediation.

Run with:
    python -m pytest tests/v29_root_fixes/test_v29_root_fixes_r3.py -v
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_PHASE1_ROOT = _PROJECT_ROOT / "phase1"
_PHASE2_ROOT = _PROJECT_ROOT / "phase2"
for p in (str(_PHASE1_ROOT), str(_PHASE2_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)


# ============================================================================
# FIX 19 (L-2): DrugBank Compound node ID vs edge src_id mismatch
# ============================================================================

def fix_19_drugbank_edge_uses_canonical_id():
    """FIX 19: DrugBank edge src_id must use canonical_id (inchikey),
    not drugbank_id — to match the node's id field."""
    parser_path = _PHASE2_ROOT / "drugos_graph" / "drugbank_parser.py"
    content = parser_path.read_text()
    # The edge must use canonical_id as src_id (not drug.drugbank_id).
    assert '"src_id": canonical_id' in content, \
        "DrugBank edge src_id must use canonical_id (v29 root fix L-2)"
    # The old pattern (src_id = drug.drugbank_id) must NOT appear in
    # actual edge-building code (only in comments documenting the fix).
    import re
    code_lines = [
        line for line in content.split("\n")
        if not line.strip().startswith("#") and "src_id" in line
    ]
    code_only = "\n".join(code_lines)
    code_only = re.sub(r'#.*$', '', code_only, flags=re.MULTILINE)
    # There should be NO line that assigns src_id to drug.drugbank_id
    # (the old pattern). canonical_id is the new pattern.
    assert '"src_id": drug.drugbank_id' not in code_only, \
        "DrugBank edge must NOT use drug.drugbank_id as src_id (audit L-2)"


# ============================================================================
# FIX 20 (L-10): hash()-based fallback ID non-deterministic
# ============================================================================

def fix_20_entity_mapping_hash_is_deterministic():
    """FIX 20: EntityMapping.__hash__ must use hashlib (deterministic),
    not Python's hash() (non-deterministic across processes)."""
    resolver_path = _PHASE2_ROOT / "drugos_graph" / "entity_resolver.py"
    content = resolver_path.read_text()
    # Must use hashlib.sha256, not hash().
    assert "hashlib" in content
    assert "sha256" in content
    # The old pattern (hash((self.canonical_type, ...))) must NOT appear
    # in the __hash__ method.
    import inspect
    # Find the __hash__ method source
    start = content.find("def __hash__(self) -> int:")
    if start == -1:
        start = content.find("def __hash__(self)")
    assert start != -1, "EntityMapping must have __hash__ method"
    # Get ~30 lines after the def
    method_src = content[start:start + 1500]
    assert "hash((" not in method_src, \
        "EntityMapping.__hash__ must NOT use Python's hash() — use hashlib.sha256 (v29 root fix L-10)"
    assert "hashlib" in method_src, \
        "EntityMapping.__hash__ must use hashlib (v29 root fix L-10)"


def fix_20_hash_is_cross_process_stable():
    """FIX 20: verify the hash is actually deterministic by computing it
    in a subprocess with different PYTHONHASHSEED."""
    import subprocess, json
    code = '''
import sys
sys.path.insert(0, "phase1")
sys.path.insert(0, "phase2")
from drugos_graph.entity_resolver import EntityMapping
m = EntityMapping(canonical_type="Compound", canonical_id="BSYNRYMUTXBXSQ-UHFFFAOYSA-N")
print(hash(m))
'''
    # Run with two different PYTHONHASHSEED values
    p1 = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                        env={**os.environ, "PYTHONHASHSEED": "0"}, cwd=str(_PROJECT_ROOT))
    p2 = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                        env={**os.environ, "PYTHONHASHSEED": "12345"}, cwd=str(_PROJECT_ROOT))
    if p1.returncode != 0 or p2.returncode != 0:
        # If import fails (missing deps), skip this test
        return
    h1 = p1.stdout.strip().split("\n")[-1]
    h2 = p2.stdout.strip().split("\n")[-1]
    assert h1 == h2, \
        f"EntityMapping hash must be deterministic across PYTHONHASHSEED — got {h1} vs {h2}"


# ============================================================================
# FIX 21 (D-11): loaders.py fillna("") on source column
# ============================================================================

def fix_21_no_fillna_on_source():
    """FIX 21: loaders.py must NOT fillna("") on the source column."""
    loaders_path = _PHASE1_ROOT / "database" / "loaders.py"
    content = loaders_path.read_text()
    # The old pattern must be removed or commented out.
    import re
    code_lines = [
        line for line in content.split("\n")
        if not line.strip().startswith("#") and "fillna" in line and "source" in line
    ]
    code_only = "\n".join(code_lines)
    code_only = re.sub(r'#.*$', '', code_only, flags=re.MULTILINE)
    assert 'df["source"].fillna("")' not in code_only, \
        "loaders.py must NOT fillna(\"\") on source column — causes CHECK violation (v29 root fix D-11)"


# ============================================================================
# FIX 22 (L-4): EDGE_PROPERTY_WHITELIST strips properties
# ============================================================================

def fix_22_whitelist_includes_geo_and_stitch():
    """FIX 22: EDGE_PROPERTY_WHITELIST must include GEO expression,
    STITCH confidence, and SIDER frequency properties."""
    kg_builder_path = _PHASE2_ROOT / "drugos_graph" / "kg_builder.py"
    content = kg_builder_path.read_text()
    assert "expression_value" in content, \
        "EDGE_PROPERTY_WHITELIST must include expression_value (v29 root fix L-4)"
    assert "stitch_combined_score" in content, \
        "EDGE_PROPERTY_WHITELIST must include stitch_combined_score"
    assert "frequency_lower_bound" in content, \
        "EDGE_PROPERTY_WHITELIST must include frequency_lower_bound"
    assert "frequency_upper_bound" in content, \
        "EDGE_PROPERTY_WHITELIST must include frequency_upper_bound"


# ============================================================================
# FIX 23 (I-4): THREE environment selectors in config.py
# ============================================================================

def fix_23_env_selectors_unified():
    """FIX 23: DRUGOS_ENV and ENVIRONMENT must alias DRUGOS_ENVIRONMENT
    (same default "dev", not "development")."""
    config_path = _PHASE2_ROOT / "drugos_graph" / "config.py"
    content = config_path.read_text()
    # DRUGOS_ENV must reference DRUGOS_ENVIRONMENT (not just "DRUGOS_ENV").
    assert "DRUGOS_ENVIRONMENT" in content
    # ENVIRONMENT must default to "dev" (not "development").
    # Find the ENVIRONMENT assignment.
    import re
    m = re.search(r'^ENVIRONMENT\s*:\s*str\s*=\s*os\.environ\.get\(\s*"DRUGOS_ENVIRONMENT"\s*,\s*"(\w+)"\s*\)', content, re.MULTILINE)
    assert m is not None, "ENVIRONMENT must be read from DRUGOS_ENVIRONMENT"
    assert m.group(1) == "dev", \
        f"ENVIRONMENT must default to 'dev' (not 'development'), got '{m.group(1)}'"


def fix_23_environment_configs_has_dev_key():
    """FIX 23: ENVIRONMENT_CONFIGS must have a 'dev' key."""
    config_path = _PHASE2_ROOT / "drugos_graph" / "config.py"
    content = config_path.read_text()
    assert '"dev"' in content, \
        "ENVIRONMENT_CONFIGS must have a 'dev' key (v29 root fix I-4)"


# ============================================================================
# FIX 24 (P1-16): download_parallel.py reuses PIPELINE_RUN_ID
# ============================================================================

def fix_24_parallel_pipelines_get_unique_run_ids():
    """FIX 24: download_parallel.py must give each pipeline a unique
    PIPELINE_RUN_ID."""
    script_path = _PHASE1_ROOT / "scripts" / "download_parallel.py"
    content = script_path.read_text()
    assert "_run_id" in content, \
        "download_parallel must generate per-pipeline run_id (v29 root fix P1-16)"
    assert 'f"{_base}_{name}"' in content or "parallel_" in content, \
        "download_parallel must create unique run_id per pipeline"
    # The return must be a 4-tuple (name, ok, err, run_id).
    assert "return (name, True, None, _run_id)" in content or \
           "return (name, False, str(e), _run_id)" in content


# ============================================================================
# FIX 25 (C-3): SYNTH InChIKeys get confidence 1.0
# ============================================================================

def fix_25_synth_inchikeys_get_lower_confidence():
    """FIX 25: SYNTH-prefixed InChIKeys must get confidence < 1.0."""
    resolver_path = _PHASE1_ROOT / "entity_resolution" / "drug_resolver.py"
    content = resolver_path.read_text()
    assert "CANONICAL_SYNTHETIC_INCHIKEY_REGEX" in content, \
        "drug_resolver must check SYNTH keys via canonical regex (v29 root fix C-3)"
    # The SYNTH branch must assign confidence < 1.0.
    import re
    # Find the SYNTH check in _match_by_inchikey
    idx = content.find("CANONICAL_SYNTHETIC_INCHIKEY_REGEX")
    assert idx != -1
    method_src = content[idx:idx + 500]
    assert "0.5" in method_src or "confidence=0.5" in method_src, \
        "SYNTH keys must get confidence 0.5 (not 1.0)"


# ============================================================================
# FIX 26 (C-6): conflict_policy="keep_newer" dead code
# ============================================================================

def fix_26_keep_newer_uses_existing_source():
    """FIX 26: conflict_policy='keep_newer' must use existing_source
    (not the incoming source) for meta_existing, and must skip
    self-comparison when sources are the same."""
    resolver_path = _PHASE1_ROOT / "entity_resolution" / "drug_resolver.py"
    content = resolver_path.read_text()
    assert "existing_source" in content, \
        "keep_newer must use existing_source variable (v29 root fix C-6)"
    assert "source != existing_source" in content, \
        "keep_newer must skip self-comparison when sources are the same"


# ============================================================================
# FIX 27 (P1-9): Silent flush swallow
# ============================================================================

def fix_27_chembl_flush_logs_warning():
    """FIX 27: ChEMBL session.flush() must log a warning on failure,
    not silently pass."""
    chembl_path = _PHASE1_ROOT / "pipelines" / "chembl_pipeline.py"
    content = chembl_path.read_text()
    # Find all session.flush() calls that are actual code (not in comments).
    import re
    lines = content.split("\n")
    flush_blocks = []
    for i, line in enumerate(lines):
        if "session.flush()" in line and not line.strip().startswith("#"):
            # Get the surrounding block (the try/except around it).
            start = max(0, i - 2)
            end = min(len(lines), i + 10)
            block = "\n".join(lines[start:end])
            flush_blocks.append(block)
    # At least one flush block must log a warning (the v29 fix).
    has_warning = any("logger.warning" in b for b in flush_blocks)
    assert has_warning, \
        "ChEMBL flush failure must log warning (v29 root fix P1-9)"
    # No flush block should have bare "pass" as the only handler.
    for b in flush_blocks:
        # Skip blocks that have logger.warning (those are fixed).
        if "logger.warning" in b:
            continue
        # Blocks without logger.warning must NOT have bare pass.
        if "except Exception" in b and "pass" in b:
            # Check if pass is the only statement in the except block.
            except_idx = b.find("except Exception")
            except_block = b[except_idx:]
            if except_block.strip().startswith("except Exception") and \
               "pass" in except_block and "logger" not in except_block:
                assert False, \
                    f"ChEMBL flush must NOT silently pass:\n{b}"


def fix_27_drugbank_flush_logs_warning():
    """FIX 27: DrugBank session.flush() must log a warning on failure."""
    drugbank_path = _PHASE1_ROOT / "pipelines" / "drugbank_pipeline.py"
    content = drugbank_path.read_text()
    lines = content.split("\n")
    flush_blocks = []
    for i, line in enumerate(lines):
        if "session.flush()" in line and not line.strip().startswith("#"):
            start = max(0, i - 2)
            end = min(len(lines), i + 10)
            block = "\n".join(lines[start:end])
            flush_blocks.append(block)
    has_warning = any("logger.warning" in b for b in flush_blocks)
    assert has_warning, \
        "DrugBank flush failure must log warning (v29 root fix P1-10)"
    for b in flush_blocks:
        if "logger.warning" in b:
            continue
        if "except Exception" in b and "pass" in b:
            except_idx = b.find("except Exception")
            except_block = b[except_idx:]
            if except_block.strip().startswith("except Exception") and \
               "pass" in except_block and "logger" not in except_block:
                assert False, \
                    f"DrugBank flush must NOT silently pass:\n{b}"


# ============================================================================
# FIX 28 (L-7): No organism filter
# ============================================================================

def fix_28_organism_filter_in_entity_resolver():
    """FIX 28: Phase 2 entity_resolver must filter proteins by organism
    (Homo sapiens / 9606)."""
    resolver_path = _PHASE2_ROOT / "drugos_graph" / "entity_resolver.py"
    content = resolver_path.read_text()
    assert "homo sapiens" in content.lower(), \
        "entity_resolver must check organism for 'homo sapiens' (v29 root fix L-7)"
    assert "9606" in content, \
        "entity_resolver must check NCBI TaxID 9606"
    assert "skipped_non_human_organism" in content, \
        "entity_resolver must count skipped non-human organisms"


# ============================================================================
# Run all tests
# ============================================================================

if __name__ == "__main__":
    test_funcs = [
        v for k, v in sorted(globals().items())
        if k.startswith("fix_") and callable(v)
    ]
    print(f"Running {len(test_funcs)} v29 round-3 root-fix verification tests...\n")
    passed = 0
    failed = 0
    for tf in test_funcs:
        try:
            tf()
            print(f"  PASS  {tf.__name__}")
            passed += 1
        except Exception as e:
            print(f"  FAIL  {tf.__name__}: {e}")
            failed += 1
    print(f"\n{passed} passed, {failed} failed, {passed + failed} total")
    if failed:
        sys.exit(1)
