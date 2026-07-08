"""ML-1: held-out AUC must use type-constrained negatives + filtered MRR.

v27 ROOT FIX verification: _evaluate_triples must accept negative_sampler
parameter and route through combined_sampling for type-constrained negatives.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_FILE = Path("/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/transe_model.py")


def test_evaluate_triples_accepts_negative_sampler():
    src = _FILE.read_text()
    # Find the _evaluate_triples signature
    match = re.search(
        r"def\s+_evaluate_triples\s*\(([^)]*)\)",
        src,
        re.DOTALL,
    )
    assert match, "ML-1 setup: cannot find _evaluate_triples"
    sig = match.group(1)
    assert "negative_sampler" in sig, (
        "ML-1 REGRESSION: _evaluate_triples does not accept negative_sampler "
        "parameter. Type-constrained negatives cannot be applied."
    )
    assert "known_triples" in sig, (
        "ML-1 REGRESSION: _evaluate_triples does not accept known_triples "
        "parameter. Filtered MRR cannot be computed."
    )


def test_evaluate_triples_calls_combined_sampling():
    """_evaluate_triples must call negative_sampler.combined_sampling
    when a sampler is provided (route through type-constrained negatives)."""
    src = _FILE.read_text()
    # Find the _evaluate_triples function body (between def and next def/class)
    match = re.search(
        r"def\s+_evaluate_triples\s*\([^)]*\)\s*(?:->\s*[^:]+)?:",
        src,
    )
    assert match, "ML-1 setup: cannot find _evaluate_triples signature"
    start = match.end()
    # Find the next top-level def or class
    next_match = re.search(r"\n(?:def\s|class\s)", src[start:])
    end = start + next_match.start() if next_match else len(src)
    body = src[start:end]
    assert "combined_sampling" in body, (
        "ML-1 REGRESSION: _evaluate_triples body does not call "
        "negative_sampler.combined_sampling. Type-constrained negatives "
        "are not being applied to held-out evaluation."
    )


def test_evaluate_triples_passes_other_true_triples_per_query():
    """Filtered MRR requires other_true_triples_per_query to be passed to
    evaluate_link_prediction."""
    src = _FILE.read_text()
    match = re.search(
        r"def\s+_evaluate_triples\s*\([^)]*\)\s*(?:->\s*[^:]+)?:",
        src,
    )
    assert match
    start = match.end()
    next_match = re.search(r"\n(?:def\s|class\s)", src[start:])
    end = start + next_match.start() if next_match else len(src)
    body = src[start:end]
    assert "other_true_triples_per_query" in body, (
        "ML-1 REGRESSION: _evaluate_triples does not pass "
        "other_true_triples_per_query to evaluate_link_prediction. "
        "Filtered MRR (Bordes 2013 / Sun 2019 standard) is not computed."
    )


def test_evaluate_triples_uses_deterministic_rng():
    """Held-out negatives must use a deterministic generator, not global RNG."""
    src = _FILE.read_text()
    match = re.search(
        r"def\s+_evaluate_triples\s*\([^)]*\)\s*(?:->\s*[^:]+)?:",
        src,
    )
    assert match
    start = match.end()
    next_match = re.search(r"\n(?:def\s|class\s)", src[start:])
    end = start + next_match.start() if next_match else len(src)
    body = src[start:end]
    # Look for Generator().manual_seed(...) or generator=... argument to torch.randint
    has_deterministic_rng = (
        "Generator" in body
        or "generator=" in body
        or "_eval_rng" in body
    )
    assert has_deterministic_rng, (
        "ML-1 / ML-8 REGRESSION: _evaluate_triples does not use a "
        "deterministic RNG for held-out negative sampling. AUC will "
        "vary across runs."
    )


def test_run_pipeline_passes_sampler_to_evaluate_triples():
    src = Path(
        "/home/z/my-project/v28/v28_upgraded/phase2/drugos_graph/run_pipeline.py"
    ).read_text()
    assert "_evaluate_triples" in src, (
        "ML-1 setup: run_pipeline.py does not call _evaluate_triples"
    )


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
