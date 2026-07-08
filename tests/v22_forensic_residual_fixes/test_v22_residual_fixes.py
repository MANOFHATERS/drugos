"""v22 Forensic Residual Fixes — verification tests.

These tests verify the root-level fixes applied on top of v21 that the
v20 forensic audit demanded but v21 missed or only partially addressed.

Each test names the audit finding it covers (V22-A, V22-B, etc.).

Audit findings addressed:
  V22-A: training_data.py DataFrame attribute access bug
         (``drkg_df._schema_version`` returned a Series when
         ``_schema_version`` was a column, raising
         ``ValueError: The truth value of a Series is ambiguous``).
         This crashed Step 10 on the default Phase 1 path.
  V22-B: STITCH rel_type silent collapse to 'binds'
         (run_pipeline.py:1975,1996,2322). Missing rel_type silently
         became 'binds', losing the 8 STITCH action types.
  V22-C: evaluation.py non-filtered MRR. v21 only flagged the raw
         metric; v22 actually computes the FILTERED MRR / Hits@K when
         the caller passes other_true_triples_per_query.
  V22-D: train_transe ``corrupt_expanded`` UnboundLocalError. The v21
         known-triples filter referenced ``corrupt_expanded`` which
         was only defined in the vectorized ``else:`` branch, not in
         the per-relation-pool or legacy single-pool branches.
  V22-E: step11 inconsistent min_train_triples gate. The v21 fix
         lowered step11's gate to 20 but did not propagate to
         ``config.min_train_triples`` (default 100) — train_transe
         still rejected the toy fixture.
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import pytest

# Ensure phase1 and phase2 are importable.
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PHASE1 = ROOT / "phase1"
PHASE2 = ROOT / "phase2"
for p in (str(PHASE2), str(PHASE1)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Allow dev-mode overrides for the duration of the test session.
os.environ.setdefault("DRUGOS_ALLOW_LAUNCH_FAIL", "1")


# ─────────────────────────────────────────────────────────────────────────
# V22-A: training_data.py DataFrame attribute access
# ─────────────────────────────────────────────────────────────────────────

def test_v22_a_training_data_handles_schema_version_column():
    """V22-A: build_training_data must not crash when the DRKG df has
    a ``_schema_version`` column (which pandas exposes as an
    attribute, returning a Series). The v21 code raised
    ``ValueError: The truth value of a Series is ambiguous``.
    """
    import pandas as pd
    from drugos_graph.training_data import build_training_data

    # Build a tiny DRKG-style df with a _schema_version column (the
    # shape the run_pipeline DRKG-shim produces from bridge edges).
    df = pd.DataFrame([
        {
            "head": "DB00001", "head_id": "DB00001",
            "head_type": "Compound",
            "relation": "treats", "rel_type": "treats",
            "relation_name": "treats",
            "tail": "D00001", "tail_id": "D00001",
            "tail_type": "Disease",
            "edge_props": "{}",
            "_schema_version": "2.0.0",
        },
    ])

    # positive_pairs is List[Dict] per the actual signature.
    pos = [{"drug_id": "DB00001", "disease_id": "D00001"}]
    pair_set = {("DB00001", "D00001")}
    # If the v22 fix is in place, this completes without ValueError.
    # If the v21 bug is still present, this raises
    # "ValueError: The truth value of a Series is ambiguous."
    try:
        result = build_training_data(
            df,
            all_drug_ids=["DB00001"],
            all_disease_ids=["D00001"],
            positive_pairs=pos,
            positive_pair_set=pair_set,
        )
    except ValueError as exc:
        if "truth value of a Series is ambiguous" in str(exc):
            pytest.fail(f"V22-A regression: {exc}")
        raise
    assert result["num_positives"] == 1
    assert "num_negatives" in result


def test_v22_a_training_data_handles_df_attrs_metadata():
    """V22-A: build_training_data must also support the proper pandas
    metadata API (``df.attrs``), not just the column case.
    """
    import pandas as pd
    from drugos_graph.training_data import build_training_data

    df = pd.DataFrame([
        {
            "head": "DB00002", "head_id": "DB00002",
            "head_type": "Compound",
            "relation": "treats", "rel_type": "treats",
            "relation_name": "treats",
            "tail": "D00002", "tail_id": "D00002",
            "tail_type": "Disease",
            "edge_props": "{}",
        },
    ])
    df.attrs["_schema_version"] = "2.0.0"

    pos = [{"drug_id": "DB00002", "disease_id": "D00002"}]
    pair_set = {("DB00002", "D00002")}
    try:
        result = build_training_data(
            df,
            all_drug_ids=["DB00002"],
            all_disease_ids=["D00002"],
            positive_pairs=pos,
            positive_pair_set=pair_set,
        )
    except ValueError as exc:
        if "truth value of a Series is ambiguous" in str(exc):
            pytest.fail(f"V22-A regression: {exc}")
        raise
    assert result["num_positives"] == 1


# ─────────────────────────────────────────────────────────────────────────
# V22-B: STITCH rel_type silent collapse to 'binds'
# ─────────────────────────────────────────────────────────────────────────

def test_v22_b_stitch_rel_type_does_not_collapse_to_binds():
    """V22-B: STITCH edges with missing rel_type must NOT silently
    become 'binds'. The v22 fix uses 'interacts_with' (neutral) as
    the fallback AND logs a warning.
    """
    import drugos_graph.run_pipeline as rp

    src = Path(rp.__file__).read_text()
    # Locate the STITCH section (step5).
    stitch_section_start = src.find("stitch_to_edge_records(df)")
    assert stitch_section_start > 0, "Could not locate STITCH section"
    stitch_section = src[stitch_section_start:stitch_section_start + 4000]

    # The fix introduces an explicit missing-rel_type counter and
    # uses 'interacts_with' as the fallback.
    assert "_stitch_missing_rel_type_count" in stitch_section, (
        "v22 STITCH fix not found — the missing-rel_type counter is absent"
    )
    assert "interacts_with" in stitch_section, (
        "v22 STITCH fix not found — 'interacts_with' fallback is absent"
    )
    # The old silent default must NOT appear as actual CODE (only in
    # comments). Look for the code pattern: rel_type = edge.get("rel_type", "binds")
    # (assignment, not comment).
    code_pattern = re.compile(
        r'^\s*rel_type\s*=\s*edge\.get\(\s*["\']rel_type["\']\s*,\s*["\']binds["\']\s*\)',
        re.MULTILINE,
    )
    matches_in_stitch = code_pattern.findall(stitch_section)
    assert not matches_in_stitch, (
        f"v22 STITCH fix INCOMPLETE — found {len(matches_in_stitch)} "
        f"code-level `rel_type = edge.get('rel_type', 'binds')` "
        f"assignments in the STITCH section"
    )


def test_v22_b_chembl_rel_type_does_not_collapse_to_binds():
    """V22-B (ChEMBL analog): ChEMBL edges with missing rel_type must
    NOT silently become 'binds'. The v22 fix uses 'targets' (matching
    the v21 chembl_loader.standard_type_to_relation fix) as the
    fallback AND logs a warning.
    """
    import drugos_graph.run_pipeline as rp

    src = Path(rp.__file__).read_text()
    # Find the ChEMBL section in step7c.
    chembl_section_start = src.find("chembl_to_edge_records(chembl_df)")
    assert chembl_section_start > 0, "Could not locate ChEMBL section"
    chembl_section = src[chembl_section_start:chembl_section_start + 4000]

    assert "_chembl_missing_rel_type_count" in chembl_section, (
        "v22 ChEMBL fix not found — the missing-rel_type counter is absent"
    )
    assert '"targets"' in chembl_section, (
        "v22 ChEMBL fix not found — 'targets' fallback is absent"
    )


# ─────────────────────────────────────────────────────────────────────────
# V22-C: evaluation.py filtered MRR
# ─────────────────────────────────────────────────────────────────────────

def test_v22_c_evaluation_emits_filtered_mrr_when_other_true_provided():
    """V22-C: when ``other_true_triples_per_query`` is passed to
    ``_compute_all_ranking_metrics``, the FILTERED MRR must be
    computed and the ``mrr`` key must reflect the FILTERED value
    (with ``mrr_is_filtered=True``).

    Setup: the target is at rank 3 in the raw ranking. Ranks 1 and 2
    are OTHER true items (their is_true is False for THIS query
    because they're not the target — they're true tails for the same
    (h, r) pair but not the target). After filtering, the target
    moves to rank 1 → filtered MRR = 1.0; raw MRR = 1/3.
    """
    from drugos_graph.evaluation import _compute_all_ranking_metrics

    # eid, score, is_true
    # Note: is_true=True means "this candidate IS the target true
    # answer for this query". Other-true items have is_true=False
    # (they're true in the graph, but not the target of THIS query).
    ranked_lists = [[
        ("e_other_true_1", 0.9, False),   # rank 1 — other true (filter out)
        ("e_other_true_2", 0.8, False),   # rank 2 — other true (filter out)
        ("e_target", 0.7, True),          # rank 3 — the target true
        ("e_neg_1", 0.6, False),
        ("e_neg_2", 0.5, False),
    ]]
    # Other-true set: the two non-target true tails.
    other_true = [{"e_other_true_1", "e_other_true_2"}]

    metrics_raw = _compute_all_ranking_metrics(
        ranked_lists,
        k_values=(1, 3, 5),
        higher_is_better=True,
    )
    metrics_filtered = _compute_all_ranking_metrics(
        ranked_lists,
        k_values=(1, 3, 5),
        higher_is_better=True,
        other_true_triples_per_query=other_true,
    )

    # RAW MRR: target at rank 3 → 1/3.
    assert metrics_raw["mrr"] == pytest.approx(1.0 / 3.0, abs=1e-6)
    assert metrics_raw["mrr_is_filtered"] is False

    # FILTERED MRR: target moves to rank 1 (others removed) → 1.0.
    assert metrics_filtered["mrr"] == pytest.approx(1.0, abs=1e-6)
    assert metrics_filtered["mrr_is_filtered"] is True
    assert metrics_filtered["mrr_filtered"] == pytest.approx(1.0, abs=1e-6)
    # The raw value must still be preserved under mrr_raw.
    assert metrics_filtered["mrr_raw"] == pytest.approx(1.0 / 3.0, abs=1e-6)


def test_v22_c_evaluation_filtered_mrr_handles_no_other_true():
    """V22-C: when ``other_true_triples_per_query`` is None or empty,
    the filtered metrics are NOT computed and the unqualified ``mrr``
    key keeps the raw value (with ``mrr_is_filtered=False``).
    """
    from drugos_graph.evaluation import _compute_all_ranking_metrics

    ranked_lists = [[
        ("e_target", 0.9, True),
        ("e_neg_1", 0.8, False),
        ("e_neg_2", 0.7, False),
    ]]
    metrics = _compute_all_ranking_metrics(
        ranked_lists,
        k_values=(1, 3),
        higher_is_better=True,
        other_true_triples_per_query=None,
    )
    assert metrics["mrr"] == pytest.approx(1.0, abs=1e-6)
    assert metrics["mrr_is_filtered"] is False
    assert "mrr_filtered" not in metrics


# ─────────────────────────────────────────────────────────────────────────
# V22-D: train_transe corrupt_expanded defined in all sampling branches
# ─────────────────────────────────────────────────────────────────────────

def test_v22_d_train_transe_corrupt_expanded_defined_in_all_branches():
    """V22-D: the v21 known-triples filter references
    ``corrupt_expanded``. The variable must be defined in ALL three
    negative-sampling branches inside train_transe:
      1. per_relation_neg_pools branch (the default for production)
      2. sampler_neg_indices branch (legacy single-pool)
      3. else branch (vectorized random corruption)
    The v21 code only defined it in branch 3 — causing
    ``UnboundLocalError`` when branch 1 or 2 was taken.
    """
    import drugos_graph.transe_model as tm

    src = Path(tm.__file__).read_text()

    # Locate train_transe function body.
    fn_start = src.find("def train_transe(")
    assert fn_start > 0, "Could not locate train_transe"
    # Find the next top-level def or class after train_transe.
    next_def = src.find("\ndef ", fn_start + 1)
    if next_def < 0:
        next_def = src.find("\nclass ", fn_start + 1)
    if next_def < 0:
        next_def = len(src)
    fn_body = src[fn_start:next_def]

    # Count the number of negative-sampling branches.
    # Each branch ends with a definition of neg_t = t_neg.
    branch_end_count = fn_body.count("neg_t = t_neg")
    assert branch_end_count >= 3, (
        f"Expected >=3 sampling branches in train_transe, "
        f"found {branch_end_count} (neg_t = t_neg assignments)"
    )

    # Each branch must define corrupt_expanded (or corrupt_head_mask
    # aliased to corrupt_expanded). The v22 fix added the alias to
    # branches 1 and 2; branch 3 already had it.
    # Count corrupt_expanded assignments (not just references).
    assignments = re.findall(r"^\s*corrupt_expanded\s*=", fn_body, re.MULTILINE)
    assert len(assignments) >= 3, (
        f"Expected >=3 `corrupt_expanded =` assignments in train_transe "
        f"(one per sampling branch), found {len(assignments)}. "
        f"The v21 known-triples filter at the end of the batch loop "
        f"references corrupt_expanded; without an assignment in every "
        f"branch, the filter raises UnboundLocalError when a non-vectorized "
        f"branch is taken."
    )


def test_v22_d_train_transe_end_to_end_with_type_constrained_sampler():
    """V22-D end-to-end: train_transe must complete at least one epoch
    without UnboundLocalError when a type-constrained negative sampler
    is provided (the production default). This exercises the
    per_relation_neg_pools branch where the v21 bug was hidden.
    """
    import torch
    from drugos_graph.transe_model import TransEModel, train_transe
    from drugos_graph.config import TransEConfig
    from drugos_graph.negative_sampling import KGNegativeSampler

    # Tiny synthetic graph.
    # 6 entities: 3 compounds (0, 1, 4), 3 diseases (2, 3, 5)
    # 1 relation: treats (0)
    # Train: 2 triples. Val: 1 different triple (no leakage).
    heads = torch.tensor([0, 1])
    rels = torch.tensor([0, 0])
    tails = torch.tensor([2, 3])
    train_triples = (heads, rels, tails)
    val_triples = (
        torch.tensor([4]),
        torch.tensor([0]),
        torch.tensor([5]),
    )

    # Use env vars to relax thresholds for this tiny synthetic test.
    # v25 ROOT FIX: wrap in try/finally to clean up the env var so it
    # doesn't leak into subsequent tests (was causing
    # test_auc_threshold_unified_to_085 to see target_auc=0.5).
    _orig_target_auc = os.environ.get("DRUGOS_TRANSE_TARGET_AUC")
    os.environ["DRUGOS_TRANSE_TARGET_AUC"] = "0.5"
    try:
        config = TransEConfig(
            embedding_dim=16,
            num_epochs=2,
            batch_size=2,
            min_train_triples=1,
            min_val_triples=1,
        )
        # Force target_auc=0.5 (just above random baseline 0.5) so the
        # tiny synthetic test doesn't fail AUC enforcement. TransEConfig
        # validates target_auc > 0.
        import dataclasses as _dc
        config = _dc.replace(config, target_auc=0.5)
        model = TransEModel(num_entities=6, num_relations=1, embedding_dim=16)

        # Build a type-constrained sampler with the right shape.
        # entity_type_lookup: {entity_idx: "Compound"|"Disease"}
        entity_type_lookup = {
            0: "Compound", 1: "Compound", 4: "Compound",
            2: "Disease", 3: "Disease", 5: "Disease",
        }
        # relation_to_types: {relation_idx (int): (head_type, tail_type)}
        relation_to_types = {
            0: ("Compound", "Disease"),
        }
        known_triples = {(0, 0, 2), (1, 0, 3), (4, 0, 5)}
        sampler = KGNegativeSampler(
            num_entities=6,
            num_relations=1,
            strategy="type_constrained",
            entity_type_lookup=entity_type_lookup,
            relation_to_types=relation_to_types,
            known_triples=known_triples,
            seed=42,
        )

        # If the v22 fix is in place, this completes without
        # UnboundLocalError. If the v21 bug is still present, this raises
        # UnboundLocalError on the first batch.
        try:
            history = train_transe(
                model=model,
                train_triples=train_triples,
                config=config,
                val_triples=val_triples,
                test_triples=val_triples,
                negative_sampler=sampler,
                entity_type_lookup=entity_type_lookup,
                known_triples=known_triples,
            )
        except UnboundLocalError as exc:
            if "corrupt_expanded" in str(exc):
                pytest.fail(f"V22-D regression: {exc}")
            raise
        assert history is not None
        assert len(history.train_loss) >= 1
    finally:
        # v25: clean up env var so it doesn't leak into subsequent tests.
        if _orig_target_auc is None:
            os.environ.pop("DRUGOS_TRANSE_TARGET_AUC", None)
        else:
            os.environ["DRUGOS_TRANSE_TARGET_AUC"] = _orig_target_auc


# ─────────────────────────────────────────────────────────────────────────
# V22-E: step11 dev-mode override of min_train_triples
# ─────────────────────────────────────────────────────────────────────────

def test_v22_e_step11_dev_mode_overrides_min_train_triples():
    """V22-E: when the dataset is below PRODUCTION_MIN_TRIPLES (100)
    but above MIN_TRIPLES_FOR_TRANSE (20), step11 must override
    ``config.min_train_triples`` to MIN_TRIPLES_FOR_TRANSE so that
    train_transe doesn't reject the toy fixture.
    """
    import drugos_graph.run_pipeline as rp

    src = Path(rp.__file__).read_text()
    # The fix uses dataclasses.replace to produce a new config.
    assert "_dc.replace(" in src, (
        "v22 step11 dev-mode override not found — dataclasses.replace "
        "call is absent"
    )
    assert "min_train_triples=MIN_TRIPLES_FOR_TRANSE" in src, (
        "v22 step11 dev-mode override not found — "
        "min_train_triples override is absent"
    )
    assert "min_val_triples=" in src, (
        "v22 step11 dev-mode override incomplete — "
        "min_val_triples override is absent (toy fixture has <30 val triples)"
    )


# ─────────────────────────────────────────────────────────────────────────
# V22 INTEGRATION: end-to-end run_unified.py smoke test
# ─────────────────────────────────────────────────────────────────────────

def test_v22_integration_run_unified_runs_all_steps():
    """V22 integration: ``python run_unified.py`` with
    ``DRUGOS_ALLOW_LAUNCH_FAIL=1`` must complete all 13 steps without
    crashing. The V1 launch criteria will fail (the toy fixture has
    <100 triples and AUC <0.85), but the pipeline must not crash on
    Step 10 (training_data) or Step 11 (train_transe) — the two
    layers where v21 had residual bugs.
    """
    import subprocess
    import sys as _sys

    env = dict(os.environ)
    env["DRUGOS_ALLOW_LAUNCH_FAIL"] = "1"
    result = subprocess.run(
        [_sys.executable, str(ROOT / "run_unified.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        env=env,
        timeout=300,
    )
    combined = result.stdout + result.stderr

    # The pipeline must not crash on Step 10 (training_data).
    assert "ValueError: The truth value of a Series is ambiguous" not in combined, (
        "V22-A regression: training_data still crashes on Series comparison"
    )
    # The pipeline must not crash on Step 11 with UnboundLocalError.
    assert "UnboundLocalError: cannot access local variable 'corrupt_expanded'" not in combined, (
        "V22-D regression: train_transe still raises UnboundLocalError"
    )
    # The pipeline must not crash on Step 11 with min_train_triples.
    assert "minimum is 100" not in combined, (
        "V22-E regression: train_transe still rejects the toy fixture"
    )
    # Step 11 must actually attempt training (the line below appears
    # only when training starts).
    assert "TransE training:" in combined, (
        "Step 11 did not start training — the pipeline stalled before TransE"
    )
    # The pipeline must complete through Step 13.
    assert "STEP 13" in combined or "Data README saved" in combined, (
        "Pipeline did not reach Step 13 (data README generation)"
    )
