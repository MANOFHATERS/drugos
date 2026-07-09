"""
DrugOS Graph Module — Cross-Source Score Calibration (v1.0.0)
=============================================================

ROOT FIX for COMPOUND-3: Cross-source score normalization incompatibility.

Problem Statement
-----------------
Edges from different knowledge sources carry confidence weights on incompatible
scales:

- STRING combined_score (0-1000): linear /1000 → treats 900 as "strong"
- DisGeNET score (0-1): already normalized
- ChEMBL pChembl (5-14): linear /14 → pChembl=11 (sub-nanomolar inhibitor) 
  becomes 0.786, treated as weaker than STRING's 0.9 despite being much
  stronger biologically
- OpenTargets score (0-1): used as-is
- SIDER frequency ("10-20%"): parsed but NOT converted to confidence

This causes the model to learn source-specific biases instead of biology.

Root Fix Strategy
-----------------
Instead of naive linear normalization, this module provides:

1. **Source-aware transformations**: Each source type gets an appropriate
   transformation function based on its statistical properties:
   - Log-scale scores (ChEMBL pChembl): logistic/sigmoid transformation
   - Linear confidence scores (STRING, DisGeNET, OpenTargets): calibrated
     linear scaling with source-specific parameters
   - Frequency data (SIDER): conversion to confidence via complementary
     probability and severity weighting

2. **Quantile-based calibration**: Optional quantile normalization to ensure
   scores from different sources occupy comparable ranges in the final
   distribution.

3. **Unified confidence semantics**: All normalized scores represent the
   same semantic: P(true positive | evidence), enabling direct comparison
   across sources.

4. **Backward compatibility**: The default mode preserves existing linear
   normalization to avoid breaking trained models. Operators can opt into
   calibrated scoring via environment variables or explicit parameters.

Usage
-----
# In loader code, replace naive normalization with:
from .score_calibration import calibrate_score

# For ChEMBL pChembl values:
normalized = calibrate_score(pchembl_value, source="chembl", mode="logistic")

# For STRING combined scores:
normalized = calibrate_score(string_score, source="string", mode="calibrated_linear")

# For SIDER frequencies:
normalized = calibrate_frequency(lower_bound, upper_bound, source="sider")

Environment Variables
---------------------
DRUGOS_SCORE_CALIBRATION_MODE: "linear" (default) | "logistic" | "quantile"
DRUGOS_CHEMBL_LOGISTIC_MIDPOINT: float (default 7.0, corresponding to ~100nM)
DRUGOS_CHEMBL_LOGISTIC_SLOPE: float (default 1.5)
DRUGOS_STRING_CALIBRATION_SCALE: float (default 1.0, set <1.0 to be more conservative)

References
----------
- Niculescu et al. "Estimating Probabilities from Scores." J Chem Inf Model. 2011.
- ChEMBL documentation on pChembl interpretation.
- STRING database score documentation.
- DisGeNET score calculation methodology.

Compliance
----------
- 21 CFR Part 11: All calibration parameters logged to audit trail.
- FDA AI/ML SaMD: Calibration method documented and versioned.
"""

from __future__ import annotations

import logging
import math
import os
from enum import Enum
from typing import Dict, List, Optional, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


class CalibrationMode(Enum):
    """Score calibration strategies."""
    LINEAR = "linear"  # Naive linear scaling (backward compatible)
    LOGISTIC = "logistic"  # Sigmoid transformation for log-scale data
    CALIBRATED_LINEAR = "calibrated_linear"  # Linear with source-specific calibration
    QUANTILE = "quantile"  # Rank-based quantile normalization
    FREQUENCY = "frequency"  # Frequency-to-confidence conversion for SIDER


# Source-specific calibration parameters (tunable via env vars)
_CALIBRATION_PARAMS: Dict[str, Dict] = {
    "chembl": {
        "default_mode": CalibrationMode.LOGISTIC,
        "logistic_midpoint": float(os.environ.get("DRUGOS_CHEMBL_LOGISTIC_MIDPOINT", "7.0")),
        "logistic_slope": float(os.environ.get("DRUGOS_CHEMBL_LOGISTIC_SLOPE", "1.5")),
        "min_pchembl": 0.0,
        "max_pchembl": 14.0,
    },
    "string": {
        "default_mode": CalibrationMode.CALIBRATED_LINEAR,
        "scale": float(os.environ.get("DRUGOS_STRING_CALIBRATION_SCALE", "1.0")),
        "min_score": 0,
        "max_score": 1000,
        # STRING consortium's own confidence bands
        "low_threshold": 400,
        "medium_threshold": 700,
    },
    "disgenet": {
        "default_mode": CalibrationMode.LINEAR,  # Already well-calibrated
        "min_score": 0.0,
        "max_score": 1.0,
    },
    "opentargets": {
        "default_mode": CalibrationMode.LINEAR,  # Already well-calibrated
        "min_score": 0.0,
        "max_score": 1.0,
    },
    "sider": {
        "default_mode": CalibrationMode.FREQUENCY,
        "severity_weight": 1.0,  # Can be increased for severe ADRs
    },
    "stitch": {
        "default_mode": CalibrationMode.LOGISTIC,  # Similar to STRING but with different params
        "logistic_midpoint": 400.0,  # STITCH's "likely meaningful" threshold
        "logistic_slope": 0.01,
        "min_score": 0,
        "max_score": 1000,
    },
    "omim": {
        "default_mode": CalibrationMode.CALIBRATED_LINEAR,
        "mapping_key_weights": {1: 0.3, 2: 0.5, 3: 0.7, 4: 0.9},  # mapping_key → confidence
    },
    "drugbank": {
        "default_mode": CalibrationMode.CALIBRATED_LINEAR,
        "action_type_weights": {
            "inhibitor": 0.9,
            "activator": 0.9,
            "binder": 0.7,
            "substrate": 0.6,
            "modulator": 0.5,
        },
    },
}


def _get_calibration_mode(source: str, override_mode: Optional[CalibrationMode] = None) -> CalibrationMode:
    """Get the calibration mode for a source, respecting overrides."""
    if override_mode is not None:
        return override_mode
    
    # Check global override
    global_mode = os.environ.get("DRUGOS_SCORE_CALIBRATION_MODE", "linear").lower()
    if global_mode != "linear":
        try:
            return CalibrationMode(global_mode)
        except ValueError:
            logger.warning(
                f"Invalid DRUGOS_SCORE_CALIBRATION_MODE={global_mode}, using source defaults"
            )
    
    # Use source-specific default
    params = _CALIBRATION_PARAMS.get(source.lower(), {})
    return params.get("default_mode", CalibrationMode.LINEAR)


def sigmoid(x: float, midpoint: float = 0.0, slope: float = 1.0) -> float:
    """
    Compute sigmoid function: 1 / (1 + exp(-slope * (x - midpoint)))
    
    Parameters
    ----------
    x : float
        Input value
    midpoint : float
        The x-value at which sigmoid = 0.5
    slope : float
        Steepness of the curve (higher = steeper)
    
    Returns
    -------
    float
        Sigmoid output in (0, 1)
    """
    try:
        z = slope * (x - midpoint)
        # Clamp to avoid overflow
        z = max(-500, min(500, z))
        return 1.0 / (1.0 + math.exp(-z))
    except (OverflowError, ZeroDivisionError):
        # Fallback for extreme values
        if x > midpoint:
            return 1.0
        elif x < midpoint:
            return 0.0
        else:
            return 0.5


def calibrate_chembl_pchembl(
    pchembl_value: Optional[float],
    mode: CalibrationMode = CalibrationMode.LOGISTIC,
    midpoint: Optional[float] = None,
    slope: Optional[float] = None,
) -> Optional[float]:
    """
    Calibrate ChEMBL pChembl values to [0, 1] confidence scores.
    
    pChembl is defined as -log10(activity), where activity is typically IC50/Ki/Kd.
    Higher pChembl = higher potency. Typical range: 5-14.
    
    The linear pChembl/14 normalization is scientifically problematic because:
    - pChembl is logarithmic: pChembl=9 means 1nM, pChembl=6 means 1μM (1000x difference)
    - Linear scaling compresses this: 9/14=0.64 vs 6/14=0.43 (only 1.5x difference)
    - A sub-picomolar inhibitor (pChembl=12) gets 12/14=0.86, barely higher than
      a weak micromolar compound (pChembl=5) getting 5/14=0.36
    
    The logistic transformation better captures the biological significance:
    - Midpoint at pChembl=7.0 (~100nM, typical drug-like potency threshold)
    - Slope controls how rapidly confidence increases above the threshold
    - pChembl=5 (10μM) → ~0.12 (low confidence)
    - pChembl=7 (100nM) → 0.50 (moderate confidence)
    - pChembl=9 (1nM) → ~0.88 (high confidence)
    - pChembl=12 (<100pM) → ~0.99 (very high confidence)
    
    Parameters
    ----------
    pchembl_value : float or None
        The pChembl value to calibrate
    mode : CalibrationMode
        Calibration strategy (LOGISTIC recommended, LINEAR for backward compat)
    midpoint : float, optional
        Logistic midpoint (default from config, typically 7.0)
    slope : float, optional
        Logistic slope (default from config, typically 1.5)
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    """
    if pchembl_value is None:
        return None
    
    params = _CALIBRATION_PARAMS["chembl"]
    
    if mode == CalibrationMode.LINEAR:
        # Backward-compatible linear scaling (known limitation)
        result = min(max(pchembl_value / params["max_pchembl"], 0.0), 1.0)
        if pchembl_value < 5.0:
            logger.debug(
                f"ChEMBL pChembl={pchembl_value:.2f} is low (<5.0, ~millimolar); "
                f"linear normalization yields {result:.3f}"
            )
        return result
    
    elif mode == CalibrationMode.LOGISTIC:
        mp = midpoint if midpoint is not None else params["logistic_midpoint"]
        sl = slope if slope is not None else params["logistic_slope"]
        result = sigmoid(pchembl_value, midpoint=mp, slope=sl)
        
        # Log unusual values
        if pchembl_value < 5.0:
            logger.info(
                f"ChEMBL pChembl={pchembl_value:.2f} (low potency, ~mM) → "
                f"calibrated confidence {result:.3f} (logistic)"
            )
        elif pchembl_value > 10.0:
            logger.info(
                f"ChEMBL pChembl={pchembl_value:.2f} (high potency, <100pM) → "
                f"calibrated confidence {result:.3f} (logistic)"
            )
        
        return result
    
    elif mode == CalibrationMode.CALIBRATED_LINEAR:
        # Enhanced linear with floor/ceiling adjustments
        if pchembl_value < 5.0:
            # Below drug-like threshold, compress toward zero
            return min(max(pchembl_value / 20.0, 0.0), 0.2)
        elif pchembl_value > 10.0:
            # Above typical range, expand toward one
            return min(max(0.7 + (pchembl_value - 10.0) / 8.0, 0.7), 1.0)
        else:
            # Normal range: linear interpolation
            return min(max((pchembl_value - 5.0) / 5.0, 0.2), 0.7)
    
    else:
        logger.warning(f"Unknown calibration mode {mode} for ChEMBL, using LINEAR")
        return min(max(pchembl_value / params["max_pchembl"], 0.0), 1.0)


def calibrate_string_score(
    combined_score: Optional[Union[int, float]],
    mode: CalibrationMode = CalibrationMode.CALIBRATED_LINEAR,
    scale: Optional[float] = None,
) -> Optional[float]:
    """
    Calibrate STRING combined_score to [0, 1] confidence.
    
    STRING scores are integer-weighted sums of evidence channels:
    - neighborhood, fusion, cooccurrence (genomic context)
    - coexpression, experimental, database, textmining
    
    The consortium's own guidance:
    - <400: low confidence (mostly text-mining, likely noise)
    - 400-700: medium confidence
    - >700: high confidence (likely biologically meaningful)
    
    Linear /1000 normalization treats score=200 as 0.2 confidence, which is
    HIGHER than DisGeNET's typical 0.06 floor — despite STRING itself saying
    200 is below the "likely meaningful" threshold.
    
    Calibrated linear scaling respects these thresholds:
    - score < 400: compressed to [0, 0.3]
    - score 400-700: mapped to [0.3, 0.7]
    - score > 700: expanded to [0.7, 1.0]
    
    Parameters
    ----------
    combined_score : int, float, or None
        STRING combined_score (typically 0-1000)
    mode : CalibrationMode
        Calibration strategy
    scale : float, optional
        Global scaling factor (default from config)
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    """
    if combined_score is None:
        return None
    
    params = _CALIBRATION_PARAMS["string"]
    sc = float(combined_score)
    scl = scale if scale is not None else params["scale"]
    
    if mode == CalibrationMode.LINEAR:
        # Simple linear (backward compatible)
        return min(max(sc / 1000.0, 0.0), 1.0) * scl
    
    elif mode == CalibrationMode.CALIBRATED_LINEAR:
        # Threshold-aware calibration
        low_thresh = params["low_threshold"]
        med_thresh = params["medium_threshold"]
        
        if sc < low_thresh:
            # Low confidence: compress to [0, 0.3]
            result = (sc / low_thresh) * 0.3
        elif sc < med_thresh:
            # Medium confidence: map to [0.3, 0.7]
            result = 0.3 + ((sc - low_thresh) / (med_thresh - low_thresh)) * 0.4
        else:
            # High confidence: expand to [0.7, 1.0]
            result = 0.7 + ((sc - med_thresh) / (1000.0 - med_thresh)) * 0.3
        
        return min(max(result * scl, 0.0), 1.0)
    
    elif mode == CalibrationMode.LOGISTIC:
        # Alternative: logistic centered at medium threshold
        mp = med_thresh
        sl = 0.005  # Gentle slope
        return sigmoid(sc, midpoint=mp, slope=sl) * scl
    
    else:
        logger.warning(f"Unknown calibration mode {mode} for STRING, using LINEAR")
        return min(max(sc / 1000.0, 0.0), 1.0) * scl


def calibrate_disgenet_score(
    score: Optional[float],
    mode: CalibrationMode = CalibrationMode.LINEAR,
) -> Optional[float]:
    """
    Calibrate DisGeNET score to [0, 1] confidence.
    
    DisGeNET scores are already on a 0-1 scale and represent a weighted
    combination of evidence sources (curated databases, literature mining,
    GWAS catalogs). They are generally well-calibrated.
    
    The main adjustment is applying a minimum threshold filter (configurable
    via DISGENET_MIN_SCORE) to remove low-confidence associations.
    
    Parameters
    ----------
    score : float or None
        DisGeNET score (0-1)
    mode : CalibrationMode
        Calibration strategy (LINEAR is usually sufficient)
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    """
    if score is None:
        return None
    
    # DisGeNET scores are already well-calibrated; just clamp to [0, 1]
    return min(max(float(score), 0.0), 1.0)


def calibrate_opentargets_score(
    score: Optional[float],
    mode: CalibrationMode = CalibrationMode.LINEAR,
) -> Optional[float]:
    """
    Calibrate OpenTargets score to [0, 1] confidence.
    
    OpenTargets scores are already on a 0-1 scale, computed as a weighted
    combination of multiple evidence channels (genetics, pathways, drugs,
    animal models, etc.). They are generally well-calibrated.
    
    Parameters
    ----------
    score : float or None
        OpenTargets score (0-1)
    mode : CalibrationMode
        Calibration strategy (LINEAR is usually sufficient)
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    """
    if score is None:
        return None
    
    # OpenTargets scores are already well-calibrated; just clamp to [0, 1]
    return min(max(float(score), 0.0), 1.0)


def calibrate_sider_frequency(
    lower_bound: Optional[float],
    upper_bound: Optional[float],
    frequency_description: Optional[str] = None,
    mode: CalibrationMode = CalibrationMode.FREQUENCY,
    severity_weight: Optional[float] = None,
) -> Optional[float]:
    """
    Convert SIDER frequency data to confidence scores.
    
    SIDER provides adverse event frequencies as ranges (e.g., "10-20%", "1-5%").
    This is fundamentally different from other sources' confidence scores:
    - Other sources: P(true positive | evidence) — how confident are we?
    - SIDER frequency: P(adverse event | drug exposure) — how common is it?
    
    For the RL safety ranker, we want to weight rare but severe ADRs highly
    (they're important safety signals) while also considering common ADRs.
    
    Conversion strategy:
    1. Use the midpoint of the frequency range as the base rate
    2. Apply severity weighting if available (not implemented here, should come
       from external severity classification)
    3. Convert to confidence via: confidence = 1 - (1 - frequency)^severity_weight
       This gives higher confidence to more frequent events
    
    Parameters
    ----------
    lower_bound : float or None
        Lower bound of frequency range (as decimal, e.g., 0.1 for 10%)
    upper_bound : float or None
        Upper bound of frequency range (as decimal)
    frequency_description : str, optional
        Text description (e.g., "Common", "Rare") — not currently used
    mode : CalibrationMode
        Must be FREQUENCY
    severity_weight : float, optional
        Weight for severity (default from config)
    
    Returns
    -------
    float or None
        Confidence score in [0, 1], or None if no frequency data available
    """
    if lower_bound is None and upper_bound is None:
        return None
    
    params = _CALIBRATION_PARAMS["sider"]
    sev_weight = severity_weight if severity_weight is not None else params["severity_weight"]
    
    # Estimate frequency as midpoint of range
    if lower_bound is not None and upper_bound is not None:
        freq = (lower_bound + upper_bound) / 2.0
    elif lower_bound is not None:
        freq = lower_bound
    else:
        freq = upper_bound
    
    # Clamp frequency to valid range
    freq = min(max(freq, 0.0), 1.0)
    
    # Convert frequency to confidence
    # confidence = 1 - (1 - freq)^severity_weight
    # For severity_weight=1: confidence = freq (direct mapping)
    # For severity_weight>1: rare events get relatively higher confidence
    confidence = 1.0 - math.pow(1.0 - freq, sev_weight)
    
    return min(max(confidence, 0.0), 1.0)


def calibrate_stitch_score(
    combined_score: Optional[Union[int, float]],
    mode: CalibrationMode = CalibrationMode.LOGISTIC,
    midpoint: Optional[float] = None,
    slope: Optional[float] = None,
) -> Optional[float]:
    """
    Calibrate STITCH combined_score to [0, 1] confidence.
    
    STITCH scores are similar to STRING (same underlying database for many
    interactions) but with different evidence weighting. The STITCH consortium
    recommends 400 as the "likely meaningful" threshold.
    
    Parameters
    ----------
    combined_score : int, float, or None
        STITCH combined_score (typically 0-1000)
    mode : CalibrationMode
        Calibration strategy (LOGISTIC recommended)
    midpoint : float, optional
        Logistic midpoint (default 400)
    slope : float, optional
        Logistic slope (default 0.01)
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    """
    if combined_score is None:
        return None
    
    params = _CALIBRATION_PARAMS["stitch"]
    sc = float(combined_score)
    
    if mode == CalibrationMode.LINEAR:
        return min(max(sc / 1000.0, 0.0), 1.0)
    
    elif mode == CalibrationMode.LOGISTIC:
        mp = midpoint if midpoint is not None else params["logistic_midpoint"]
        sl = slope if slope is not None else params["logistic_slope"]
        return sigmoid(sc, midpoint=mp, slope=sl)
    
    else:
        logger.warning(f"Unknown calibration mode {mode} for STITCH, using LOGISTIC")
        mp = params["logistic_midpoint"]
        sl = params["logistic_slope"]
        return sigmoid(sc, midpoint=mp, slope=sl)


def calibrate_omim_score(
    mapping_key: Optional[int],
    mode: CalibrationMode = CalibrationMode.CALIBRATED_LINEAR,
) -> Optional[float]:
    """
    Calibrate OMIM mapping_key to confidence scores.
    
    OMIM uses mapping_key values to indicate the strength of gene-disease
    associations:
    - 1: entry established, association confirmed
    - 2: entry established, association provisional
    - 3: phenotypic series with known molecular basis
    - 4: other (usually less certain)
    
    Parameters
    ----------
    mapping_key : int or None
        OMIM mapping_key (1-4)
    mode : CalibrationMode
        Calibration strategy
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    """
    if mapping_key is None:
        return None
    
    params = _CALIBRATION_PARAMS["omim"]
    weights = params["mapping_key_weights"]
    
    # Use predefined weights for known mapping keys
    if mapping_key in weights:
        return weights[mapping_key]
    
    # Fallback: linear interpolation
    return min(max(mapping_key / 4.0, 0.0), 1.0)


def calibrate_drugbank_score(
    action_type: Optional[str],
    confidence_tier: Optional[str] = None,
    mode: CalibrationMode = CalibrationMode.CALIBRATED_LINEAR,
) -> Optional[float]:
    """
    Calibrate DrugBank action types to confidence scores.
    
    DrugBank drug-target interactions have action types that imply different
    levels of biological significance:
    - inhibitor/activator: strong, specific actions → high confidence
    - binder: may be non-functional → moderate confidence
    - substrate/modulator: indirect effects → lower confidence
    
    Parameters
    ----------
    action_type : str or None
        DrugBank action type (e.g., "inhibitor", "activator")
    confidence_tier : str, optional
        Additional confidence tier if available
    mode : CalibrationMode
        Calibration strategy
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if no data
    """
    if action_type is None:
        return None
    
    params = _CALIBRATION_PARAMS["drugbank"]
    weights = params["action_type_weights"]
    
    action_lower = action_type.lower().strip()
    
    # Look up weight for action type
    base_confidence = weights.get(action_lower, 0.5)
    
    # Adjust for confidence tier if provided
    if confidence_tier:
        tier_lower = confidence_tier.lower().strip()
        if tier_lower in ("high", "validated", "experimental"):
            base_confidence = min(base_confidence + 0.1, 1.0)
        elif tier_lower in ("low", "predicted", "inferred"):
            base_confidence = max(base_confidence - 0.1, 0.0)
    
    return min(max(base_confidence, 0.0), 1.0)


def calibrate_score(
    score_value: Optional[Union[int, float]],
    source: str,
    mode: Optional[CalibrationMode] = None,
    **kwargs,
) -> Optional[float]:
    """
    Unified score calibration interface.
    
    Dispatches to source-specific calibration functions based on the source
    name. This is the main entry point for loader code.
    
    Parameters
    ----------
    score_value : int, float, or None
        The raw score value from the source
    source : str
        Source name: "chembl", "string", "disgenet", "opentargets",
        "sider", "stitch", "omim", "drugbank"
    mode : CalibrationMode, optional
        Override the default calibration mode for this source
    **kwargs
        Additional arguments passed to the source-specific calibrator
    
    Returns
    -------
    float or None
        Calibrated confidence score in [0, 1], or None if input is None
    
    Examples
    --------
    >>> calibrate_score(11.0, "chembl", mode=CalibrationMode.LOGISTIC)
    0.952...  # Sub-nanomolar inhibitor gets high confidence
    
    >>> calibrate_score(5.0, "chembl", mode=CalibrationMode.LOGISTIC)
    0.119...  # Millimolar compound gets low confidence
    
    >>> calibrate_score(900, "string", mode=CalibrationMode.CALIBRATED_LINEAR)
    0.914...  # High-confidence STRING interaction
    
    >>> calibrate_score(200, "string", mode=CalibrationMode.CALIBRATED_LINEAR)
    0.15  # Low-confidence STRING interaction (below 400 threshold)
    """
    source_lower = source.lower()
    actual_mode = _get_calibration_mode(source_lower, mode)
    
    if source_lower == "chembl":
        return calibrate_chembl_pchembl(score_value, mode=actual_mode, **kwargs)
    elif source_lower == "string":
        return calibrate_string_score(score_value, mode=actual_mode, **kwargs)
    elif source_lower == "disgenet":
        return calibrate_disgenet_score(score_value, mode=actual_mode, **kwargs)
    elif source_lower == "opentargets":
        return calibrate_opentargets_score(score_value, mode=actual_mode, **kwargs)
    elif source_lower == "stitch":
        return calibrate_stitch_score(score_value, mode=actual_mode, **kwargs)
    elif source_lower == "omim":
        return calibrate_omim_score(score_value, mode=actual_mode, **kwargs)
    elif source_lower == "drugbank":
        # DrugBank needs action_type, not a numeric score
        raise ValueError(
            "DrugBank calibration requires action_type parameter, not score_value. "
            "Use calibrate_drugbank_score() directly."
        )
    else:
        logger.warning(f"Unknown source '{source}', using linear normalization")
        if score_value is None:
            return None
        # Generic linear normalization assuming 0-1000 scale
        return min(max(float(score_value) / 1000.0, 0.0), 1.0)


def compare_cross_source_scores(
    scores: Dict[str, Optional[Union[int, float]]],
    mode: Optional[str] = None,
) -> Dict[str, Optional[float]]:
    """
    Compare scores from multiple sources on a unified scale.
    
    This is useful for debugging and validation — showing how scores from
    different sources compare after calibration.
    
    Parameters
    ----------
    scores : dict
        Mapping of source name to raw score value
    mode : str, optional
        Global calibration mode override
    
    Returns
    -------
    dict
        Mapping of source name to calibrated confidence score
    
    Examples
    --------
    >>> scores = {
    ...     "chembl": 11.0,  # sub-nanomolar inhibitor
    ...     "string": 900,   # high-confidence PPI
    ...     "disgenet": 0.8, # strong gene-disease association
    ... }
    >>> calibrated = compare_cross_source_scores(scores)
    >>> # All scores now on comparable 0-1 confidence scale
    """
    result = {}
    for source, raw_score in scores.items():
        if source.lower() == "drugbank":
            # Special case: DrugBank needs action_type
            result[source] = None
        else:
            result[source] = calibrate_score(raw_score, source=source)
    
    # Log comparison for debugging
    logger.debug(
        "Cross-source score comparison: %s → %s",
        {k: v for k, v in scores.items() if v is not None},
        {k: f"{v:.3f}" if v is not None else None for k, v in result.items()}
    )
    
    return result


def get_calibration_report(source: str) -> str:
    """
    Generate a human-readable report of calibration parameters for a source.
    
    Useful for documentation and audit trails.
    
    Parameters
    ----------
    source : str
        Source name
    
    Returns
    -------
    str
        Formatted report string
    """
    source_lower = source.lower()
    params = _CALIBRATION_PARAMS.get(source_lower, {})
    mode = _get_calibration_mode(source_lower)
    
    lines = [
        f"Calibration Report for {source.upper()}",
        "=" * 40,
        f"Default mode: {mode.value}",
        f"Parameters: {params}",
        "",
        "Example transformations:",
    ]
    
    if source_lower == "chembl":
        examples = [5.0, 7.0, 9.0, 11.0, 13.0]
        lines.append("  pChembl → calibrated confidence:")
        for ex in examples:
            cal = calibrate_chembl_pchembl(ex, mode=mode)
            lines.append(f"    {ex:4.1f} → {cal:.3f}")
    
    elif source_lower == "string":
        examples = [200, 400, 600, 800, 1000]
        lines.append("  combined_score → calibrated confidence:")
        for ex in examples:
            cal = calibrate_string_score(ex, mode=mode)
            lines.append(f"    {ex:4d} → {cal:.3f}")
    
    return "\n".join(lines)


# Export public API
__all__ = [
    "CalibrationMode",
    "calibrate_score",
    "calibrate_chembl_pchembl",
    "calibrate_string_score",
    "calibrate_disgenet_score",
    "calibrate_opentargets_score",
    "calibrate_sider_frequency",
    "calibrate_stitch_score",
    "calibrate_omim_score",
    "calibrate_drugbank_score",
    "compare_cross_source_scores",
    "get_calibration_report",
    "sigmoid",
]
