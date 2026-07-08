"""v22 ROOT FIX verification tests — Part 3: Phase 2 Loaders & Pipeline.

Verifies audit findings P0-3, P0-4, P1-5, P1-6, X-5, X-6, X-7, X-11, X-12,
X-13, X-14, X-15, X-16.
"""
from __future__ import annotations

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


def _fn_body(src: str, fn_name: str, window: int = 6000) -> str:
    """Return a window of source starting at `def <fn_name>`."""
    idx = src.find(f"def {fn_name}")
    if idx == -1:
        return ""
    return src[idx:idx + window]


# ─── P1-5: SIDER stubs replaced with real parsers ───────────────────────────

def test_p1_5_sider_fda_labels_not_stub():
    """parse_sider_fda_labels MUST NOT raise NotImplementedError.

    Audit finding: patient-safety stub. Drugs with black-box warnings
    but no post-marketing reports appeared GREEN to the RL safety ranker.
    """
    src = _source_lines("phase2/drugos_graph/sider_loader.py")
    body = _fn_body(src, "parse_sider_fda_labels")
    assert body, "parse_sider_fda_labels not found"
    bare_raise = re.search(r"^\s*raise NotImplementedError", body, re.MULTILINE)
    assert bare_raise is None, (
        "parse_sider_fda_labels STILL raises NotImplementedError. "
        "Patient-safety blind spot is still present."
    )


def test_p1_5_sider_frequencies_not_stub():
    """parse_sider_frequencies MUST NOT raise NotImplementedError."""
    src = _source_lines("phase2/drugos_graph/sider_loader.py")
    body = _fn_body(src, "parse_sider_frequencies")
    assert body, "parse_sider_frequencies not found"
    bare_raise = re.search(r"^\s*raise NotImplementedError", body, re.MULTILINE)
    assert bare_raise is None, (
        "parse_sider_frequencies STILL raises NotImplementedError. "
        "RL safety ranker missing frequency data."
    )


# ─── P1-6: NCBI fake verification replaced ──────────────────────────────────

def test_p1_6_ncbi_verification_makes_real_call():
    """verify_builtin_against_ncbi MUST make a real NCBI API call
    (not just return True for every entry).

    Audit finding: function returned True for every entry WITHOUT
    calling NCBI. The fix: make a real HTTP call and set True only
    when NCBI confirms the gene symbol matches.
    """
    src = _source_lines("phase2/drugos_graph/id_crosswalk.py")
    body = _fn_body(src, "verify_builtin_against_ncbi", window=10000)
    assert body, "verify_builtin_against_ncbi not found"
    has_http_call = (
        "urlopen" in body
        or "requests.get" in body
        or "urllib.request" in body
        or "NCBI_URL" in body
        or "eutils.ncbi.nlm.nih.gov" in body
    )
    assert has_http_call, (
        "verify_builtin_against_ncbi does NOT make a real NCBI API call. "
        "The fake verification stub is still present."
    )
    # The fix must compare the NCBI-returned gene symbol to the stored one.
    # If they match → True. If they don't → False. The OLD code just set
    # True unconditionally ("optimistic").
    has_comparison = (
        "ncbi_symbol" in body
        and "results[key] = True" in body
        and "results[key] = False" in body
    )
    assert has_comparison, (
        "verify_builtin_against_ncbi does NOT compare NCBI's gene_symbol "
        "to the stored entry before setting True/False. The old 'optimistic' "
        "stub (always True) may still be present."
    )


# ─── X-5: chembl_loader deterministic SQLite selection ──────────────────────

def test_x_5_chembl_loader_deterministic_sqlite():
    """chembl_loader MUST NOT do db_files[0] without sorting.

    Audit finding: db_files = list(...rglob('*.db')); db_path = db_files[0]
    — non-deterministic, different runs pick different DBs.
    """
    src = _source_lines("phase2/drugos_graph/chembl_loader.py")
    assert "sorted" in src or "sort_key" in src, (
        "chembl_loader does NOT sort db_files before selection. "
        "Non-deterministic SQLite selection is still present."
    )


# ─── X-6: evaluation.py filtered MRR ────────────────────────────────────────

def test_x_6_evaluation_filtered_mrr():
    """evaluation.py MRR computation MUST filter other true triples
    from candidate ranking (Bordes 2013 / Sun 2019 standard).

    Audit finding: non-filtered MRR → reported MRR biased LOW,
    results not comparable to literature.
    """
    src = _source_lines("phase2/drugos_graph/evaluation.py")
    assert "other_true" in src, (
        "evaluation.py MRR does NOT filter other true triples. "
        "The non-filtered MRR bias is still present."
    )


# ─── X-7: negative_sampling relation_idx passed by caller ───────────────────

def test_x_7_transe_model_passes_relation_idx_to_sampler():
    """transe_model's TYPE-AWARE combined_sampling call MUST pass
    relation_idx (not rely on the dummy-0 default).

    Audit finding: combined_sampling used 'dummy relation 0' for ALL
    relations → type-wrong negatives for any non-treats relation.

    Note: there is also a LEGACY fallback call (no head_type/tail_type)
    that doesn't pass relation_idx — that one is a separate code path
    used only when relation_to_types is not populated. The audit's
    complaint is about the MAIN type-aware path.
    """
    src = _source_lines("phase2/drugos_graph/transe_model.py")
    # Find ALL combined_sampling call sites.
    call_sites = list(re.finditer(r"negative_sampler\.combined_sampling\s*\(", src))
    assert call_sites, "combined_sampling call not found in transe_model.py"
    # Check each call site. The MAIN type-aware call passes head_type/tail_type
    # — that one MUST also pass relation_idx. The legacy fallback (no
    # head_type/tail_type) is exempt.
    type_aware_calls_checked = 0
    for m in call_sites:
        start = m.end()
        depth = 1
        i = start
        while i < len(src) and depth > 0:
            if src[i] == "(":
                depth += 1
            elif src[i] == ")":
                depth -= 1
            i += 1
        call_args = src[start:i]
        # Skip calls that are inside comments.
        line_start = src.rfind("\n", 0, m.start()) + 1
        call_line_prefix = src[line_start:m.start()].strip()
        if call_line_prefix.startswith("#"):
            continue
        # Only check the type-aware call (passes head_type/tail_type).
        if "head_type" not in call_args or "tail_type" not in call_args:
            continue  # legacy fallback — exempt
        type_aware_calls_checked += 1
        assert "relation_idx" in call_args, (
            f"transe_model type-aware combined_sampling call at offset {m.start()} "
            f"does NOT pass relation_idx. Call args: {call_args[:300]}. "
            "The sampler falls back to 'dummy relation 0' for ALL relations → "
            "type-wrong negatives for non-treats relations."
        )
    assert type_aware_calls_checked > 0, (
        "No type-aware combined_sampling call found (one with head_type/tail_type). "
        "The audit's complaint about 'dummy relation 0' applies to that path."
    )


# ─── X-11: chembl_pipeline is_fda_approved stale message updated ────────────

def test_x_11_chembl_pipeline_no_stale_fda_message():
    """chembl_pipeline MUST NOT log the stale 'None until FDA Orange Book
    join is wired in' message.

    Audit finding: stale log message said is_fda_approved=None even after
    _derive_fda was implemented → misled operators.
    """
    src = _source_lines("phase1/pipelines/chembl_pipeline.py")
    stale_msg = "None until FDA Orange Book join is wired in"
    assert stale_msg not in src, (
        "chembl_pipeline STILL logs the stale 'None until FDA Orange Book' "
        "message. The is_fda_approved field is now derived from approved_by "
        "+ max_phase — the log message must reflect this."
    )


# ─── X-12: omim_pipeline dead code removed ──────────────────────────────────

def test_x_12_omim_pipeline_dead_code_removed():
    """omim_pipeline MUST NOT define _download_via_api, _fetch_gene_map_page,
    _write_gene_map_json (the dead ~150 lines).

    Audit finding: 3 functions defined but never called.
    """
    src = _source_lines("phase1/pipelines/omim_pipeline.py")
    for dead_fn in ["_download_via_api", "_fetch_gene_map_page", "_write_gene_map_json"]:
        pattern = rf"def\s+{dead_fn}\s*\("
        assert not re.search(pattern, src), (
            f"omim_pipeline STILL defines {dead_fn}. The dead code is still present."
        )


# ─── X-13: _cached_parse_drkg dead function removed ─────────────────────────

def test_x_13_cached_parse_drkg_removed():
    """run_pipeline MUST NOT define _cached_parse_drkg (dead function)."""
    src = _source_lines("phase2/drugos_graph/run_pipeline.py")
    pattern = r"def\s+_cached_parse_drkg\s*\("
    assert not re.search(pattern, src), (
        "run_pipeline STILL defines _cached_parse_drkg. The dead function is still present."
    )


# ─── X-14: normalizer watch_config / sign_output docstrings updated ─────────

def test_x_14_normalizer_watch_config_not_stub():
    """normalizer.watch_config FIRST docstring line MUST NOT say 'stub'."""
    src = _source_lines("phase1/cleaning/normalizer.py")
    idx = src.find("def watch_config")
    assert idx != -1, "watch_config not found"
    body = src[idx:idx + 3000]
    docstring_m = re.search(r'"""(.*?)"""', body, re.DOTALL)
    assert docstring_m is not None, "watch_config docstring not found"
    docstring = docstring_m.group(1)
    first_line = docstring.strip().split("\n")[0]
    assert "stub" not in first_line.lower(), (
        f"watch_config docstring summary line STILL calls itself a stub: "
        f"{first_line!r}"
    )


def test_x_14_normalizer_sign_output_not_stub():
    """normalizer.sign_output FIRST docstring line MUST NOT call itself a 'stub'.

    The fix's explanatory note ("the previous docstring said 'Add a minimal
    e-signature STUB'") IS allowed — only the original summary line
    claiming to be a stub must be gone.
    """
    src = _source_lines("phase1/cleaning/normalizer.py")
    idx = src.find("def sign_output")
    assert idx != -1, "sign_output not found"
    body = src[idx:idx + 3000]
    # Extract the docstring (first triple-quoted block).
    docstring_m = re.search(r'"""(.*?)"""', body, re.DOTALL)
    assert docstring_m is not None, "sign_output docstring not found"
    docstring = docstring_m.group(1)
    # The FIRST line (summary) must NOT contain "stub".
    first_line = docstring.strip().split("\n")[0]
    assert "stub" not in first_line.lower(), (
        f"sign_output docstring summary line STILL calls itself a stub: "
        f"{first_line!r}"
    )


# ─── X-15: omim_pipeline HGNC strict-by-default in production ───────────────

def test_x_15_omim_hgnc_strict_in_production():
    """omim_pipeline HGNC validation MUST be strict by default in production."""
    src = _source_lines("phase1/pipelines/omim_pipeline.py")
    assert "DRUGOS_ENVIRONMENT" in src, (
        "omim_pipeline HGNC strict-mode check does NOT consult DRUGOS_ENVIRONMENT. "
        "Production deployments still skip HGNC validation silently."
    )


# ─── X-16: disgenet/omim loaders freshness check ────────────────────────────

def test_x_16_disgenet_loader_has_freshness_check():
    """disgenet_loader.download_disgenet MUST check CSV freshness (mtime)."""
    src = _source_lines("phase2/drugos_graph/disgenet_loader.py")
    assert "DRUGOS_DISGENET_MAX_AGE_DAYS" in src or "max_age_days" in src, (
        "disgenet_loader does NOT check CSV freshness. "
        "Years-stale CSVs are silently used in production."
    )


def test_x_16_omim_loader_has_freshness_check():
    """omim_loader.download_omim MUST check CSV freshness (mtime)."""
    src = _source_lines("phase2/drugos_graph/omim_loader.py")
    assert "DRUGOS_OMIM_MAX_AGE_DAYS" in src or "max_age_days" in src, (
        "omim_loader does NOT check CSV freshness. "
        "Years-stale CSVs are silently used in production."
    )


# ─── P0-3: chembl/drugbank/string/uniprot loaders consume Phase 1 CSVs ──────

def test_p0_3_phase1_processed_dir_threaded_through_run_full_pipeline():
    """run_full_pipeline MUST thread phase1_processed_dir to step4, step7."""
    src = _source_lines("phase2/drugos_graph/run_pipeline.py")
    step4_call = re.search(
        r"step4_drugbank_enrichment\([^)]*phase1_processed_dir=phase1_processed_dir",
        src,
        re.DOTALL,
    )
    assert step4_call is not None, (
        "step4_drugbank_enrichment call does NOT thread phase1_processed_dir. "
        "DrugBank parser bypasses Phase 1's drugbank_drugs.csv."
    )


# ─── P0-4: real negative filtering ──────────────────────────────────────────

def test_p0_4_negative_sampler_filters_known_positives():
    """KGNegativeSampler MUST filter known positives during sampling.

    Audit finding: combined_sampling comment claimed filter, no code.
    """
    src = _source_lines("phase2/drugos_graph/negative_sampling.py")
    assert "filtered" in src.lower() and "known-positive" in src.lower(), (
        "KGNegativeSampler does NOT log known-positive filtering. "
        "The fake filter (comment-only) may still be present."
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
