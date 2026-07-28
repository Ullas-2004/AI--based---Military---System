"""Threat scoring built on the trained XGBoost regressor.

The model is loaded once at import and reused; XGBoost's ``predict`` is
thread-safe for inference, so the Flask worker pool can share this instance.
"""
import json
import logging
import threading

import numpy as np
import xgboost as xgb

from config import config
from middleware.validation import ValidationError
from services.taxonomy import (
    THREAT_CLASSES, WEATHER_CLASSES, TERRAIN_CLASSES, TIME_OF_DAY_CLASSES,
)

logger = logging.getLogger(__name__)

_model = None
_quantile_model = None
_model_card = None
_features = None
_categories = None
_load_lock = threading.Lock()

# Thresholds are shared with the frontend via /api/predict/thresholds so the UI
# never hard-codes a second, drifting copy.
THREAT_BANDS = (
    (80.0, "CRITICAL"),
    (60.0, "HIGH"),
    (40.0, "MEDIUM"),
    (0.0, "LOW"),
)


def _load() -> None:
    global _model, _quantile_model, _model_card, _features, _categories
    if _model is not None:
        return
    with _load_lock:
        if _model is not None:
            return
        try:
            with open(config.ENCODERS_PATH, encoding="utf-8") as fh:
                meta = json.load(fh)
            model = xgb.XGBRegressor()
            model.load_model(config.THREAT_MODEL_PATH)
            _features = meta["features"]
            _categories = meta["categories"]
            _model = model
            logger.info("Threat prediction model loaded (%d features).", len(_features))
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            logger.exception(
                "Failed to load threat model. Run: python api/train_threat_model.py"
            )
            return

        # Uncertainty and model-card metadata are optional: an older model
        # directory still serves scores, just without intervals.
        try:
            quantile = xgb.XGBRegressor()
            quantile.load_model(config.QUANTILE_MODEL_PATH)
            _quantile_model = quantile
            logger.info("Quantile model loaded (prediction intervals enabled).")
        except (OSError, ValueError):
            logger.warning("No quantile model found; intervals disabled.")

        try:
            with open(config.MODEL_CARD_PATH, encoding="utf-8") as fh:
                _model_card = json.load(fh)
        except (OSError, json.JSONDecodeError):
            logger.warning("No model card found.")


def get_model_card() -> dict:
    """Evaluation metrics and documented limitations of the running model."""
    _load()
    return _model_card or {}


def is_ready() -> bool:
    _load()
    return _model is not None


def categorize_score(score: float) -> str:
    for threshold, label in THREAT_BANDS:
        if score >= threshold:
            return label
    return "LOW"


def _encode(field: str, value: str) -> int:
    """Encode a categorical value, refusing unknown labels.

    This is the fix for the silent-fallback bug: previously an unrecognised
    class became index 0 ("Civilian Car"), so a YOLO "Person" detection scored
    as a civilian vehicle. Now the caller gets a 422 naming the valid options.
    """
    classes = _categories[field]
    try:
        return classes.index(value)
    except ValueError:
        raise ValidationError(
            f"Unknown {field} '{value}'. Expected one of: {', '.join(classes)}.",
            field,
        ) from None


# Human-readable labels for the model's internal feature names.
FEATURE_LABELS = {
    "DetectedObject": "Object class",
    "ConfidenceScore": "Detection confidence",
    "Weather": "Weather conditions",
    "Terrain": "Terrain type",
    "TimeOfDay": "Time of day",
    "DistanceToBorder_km": "Distance to border",
}


def _explain(vector, raw_inputs: dict) -> dict:
    """Exact SHAP attribution for a single prediction.

    XGBoost computes true Shapley values via ``pred_contribs`` — this is not an
    approximation and needs no extra dependency. Contributions sum exactly to
    the raw model output, so the explanation is guaranteed faithful rather than
    a plausible-looking story told after the fact.
    """
    try:
        import xgboost as xgb
        matrix = xgb.DMatrix(vector, feature_names=_features)
        contribs = _model.get_booster().predict(matrix, pred_contribs=True)[0]
    except Exception:
        logger.exception("SHAP attribution failed; returning score without explanation.")
        return {}

    baseline = float(contribs[-1])
    factors = []
    for name, contribution in zip(_features, contribs[:-1]):
        raises = contribution > 0
        factors.append({
            "feature": name,
            "label": FEATURE_LABELS.get(name, name),
            "value": raw_inputs[name],
            "contribution": round(float(contribution), 2),
            "direction": "increases" if raises else "decreases",
            "gerund": "raising" if raises else "lowering",
        })

    # Strongest influence first — that's what an analyst reads.
    factors.sort(key=lambda f: abs(f["contribution"]), reverse=True)
    top = factors[0] if factors else None

    return {
        "baseline": round(baseline, 2),
        "factors": factors,
        "summary": (
            f"{top['label']} ({top['value']}) is the dominant factor, "
            f"{top['gerund']} the score by {abs(top['contribution']):.1f} points "
            f"from a baseline of {baseline:.1f}."
        ) if top else "",
        "method": "Exact Shapley values (XGBoost pred_contribs)",
    }


def _interval(vector) -> dict:
    """80% prediction interval from the companion quantile model.

    A point estimate cannot express how sure the model is. A wide band means
    this observation sits in a sparsely-trained region and the analyst should
    weight the score accordingly.
    """
    if _quantile_model is None:
        return {}
    try:
        bounds = _quantile_model.predict(vector)[0]
    except Exception:
        logger.exception("Quantile prediction failed.")
        return {}

    lower, median, upper = (float(b) for b in bounds)
    lower, upper = max(0.0, min(lower, upper)), min(99.0, max(lower, upper))
    width = upper - lower

    # Thresholds chosen against the ~10.7-point mean holdout width.
    if width <= 8:
        level = "high"
    elif width <= 15:
        level = "moderate"
    else:
        level = "low"

    return {
        "lower": round(lower, 2),
        "median": round(median, 2),
        "upper": round(upper, 2),
        "width": round(width, 2),
        "nominal_coverage": 0.8,
        "confidence_level": level,
        "spans_bands": categorize_score(lower) != categorize_score(upper),
    }


# Ordered from least to most disruptive, so the search reports the smallest
# operational change that would alter the assessment.
_COUNTERFACTUAL_SWEEPS = (
    ("distance_km", "Distance to border", [1, 3, 5, 8, 12, 18, 25, 35, 45]),
    ("confidence", "Detection confidence", [50, 60, 70, 80, 90, 99]),
    ("time_of_day", "Time of day", None),
    ("weather", "Weather", None),
    ("terrain", "Terrain", None),
    ("object", "Object class", None),
)


def counterfactuals(detected_object: str, confidence: float, weather: str,
                    terrain: str, time_of_day: str, distance_km: float,
                    max_results: int = 4) -> list:
    """Find the smallest single changes that would move the threat band.

    SHAP explains what drove *this* score. A counterfactual answers the
    question an analyst actually asks next: "what would have to be different
    for this to not be critical?" Each candidate is re-scored through the real
    model, so these are verified outcomes rather than estimates.
    """
    _load()
    if _model is None:
        return []

    baseline = predict_threat_score(detected_object, confidence, weather, terrain,
                                    time_of_day, distance_km, explain=False)
    current_band = baseline["threat_level"]
    current = {
        "object": detected_object, "confidence": confidence, "weather": weather,
        "terrain": terrain, "time_of_day": time_of_day, "distance_km": distance_km,
    }

    found = []
    for field, label, sweep in _COUNTERFACTUAL_SWEEPS:
        options = sweep if sweep is not None else _categories[{
            "object": "DetectedObject", "weather": "Weather",
            "terrain": "Terrain", "time_of_day": "TimeOfDay",
        }[field]]

        best = None
        for candidate in options:
            if candidate == current[field]:
                continue
            probe = dict(current)
            probe[field] = candidate
            try:
                scored = predict_threat_score(
                    probe["object"], probe["confidence"], probe["weather"],
                    probe["terrain"], probe["time_of_day"], probe["distance_km"],
                    explain=False,
                )
            except ValidationError:
                continue
            if scored["threat_level"] == current_band:
                continue

            delta = scored["threat_score"] - baseline["threat_score"]
            # Prefer the smallest score movement that still changes the band.
            if best is None or abs(delta) < abs(best["delta"]):
                best = {
                    "field": field, "label": label,
                    "from": current[field], "to": candidate,
                    "new_score": scored["threat_score"],
                    "new_level": scored["threat_level"],
                    "delta": round(delta, 2),
                }
        if best:
            found.append(best)

    found.sort(key=lambda c: abs(c["delta"]))
    for c in found:
        direction = "drop" if c["delta"] < 0 else "rise"
        c["summary"] = (
            f"If {c['label'].lower()} were {c['to']} instead of {c['from']}, "
            f"the assessment would {direction} to {c['new_level']} ({c['new_score']})."
        )
    return found[:max_results]


def predict_threat_score(detected_object: str, confidence: float, weather: str,
                         terrain: str, time_of_day: str, distance_km: float,
                         explain: bool = True) -> dict:
    """Score a single telemetry observation.

    Raises ValidationError for bad input, RuntimeError if the model is missing.
    Set ``explain=False`` for bulk scoring where attribution is not needed.
    """
    _load()
    if _model is None:
        raise RuntimeError(
            "Threat prediction model is unavailable. "
            "Run 'python api/train_threat_model.py' to generate it."
        )

    row = {
        "DetectedObject": _encode("DetectedObject", detected_object),
        "ConfidenceScore": float(confidence),
        "Weather": _encode("Weather", weather),
        "Terrain": _encode("Terrain", terrain),
        "TimeOfDay": _encode("TimeOfDay", time_of_day),
        "DistanceToBorder_km": float(distance_km),
    }
    # Build the matrix in the exact training column order. Using a plain numpy
    # array avoids a pandas round-trip on every request.
    vector = np.array([[row[name] for name in _features]], dtype=np.float32)

    try:
        raw = float(_model.predict(vector)[0])
    except Exception:
        # Never surface XGBoost internals to the client.
        logger.exception("Threat model inference failed for input %s", row)
        raise RuntimeError("Threat scoring failed. The incident has been logged.") from None

    score = round(min(max(raw, 0.0), 99.0), 2)
    result = {
        "threat_score": score,
        "threat_level": categorize_score(score),
        "model_version": "xgboost-regressor-v3",
    }

    interval = _interval(vector)
    if interval:
        result["interval"] = interval

    if explain:
        # Attribution is computed on the raw output; when the score is clamped
        # to the 0-99 band the contributions still explain the uncapped value,
        # so we say so rather than silently rescaling them.
        readable = {
            "DetectedObject": detected_object, "ConfidenceScore": confidence,
            "Weather": weather, "Terrain": terrain,
            "TimeOfDay": time_of_day, "DistanceToBorder_km": distance_km,
        }
        explanation = _explain(vector, readable)
        if explanation:
            explanation["raw_score"] = round(raw, 2)
            explanation["was_clamped"] = abs(raw - score) > 0.01
            result["explanation"] = explanation

    return result


def valid_categories() -> dict:
    """Expose the accepted enum values so the UI can build inputs from them."""
    return {
        "DetectedObject": list(THREAT_CLASSES),
        "Weather": list(WEATHER_CLASSES),
        "Terrain": list(TERRAIN_CLASSES),
        "TimeOfDay": list(TIME_OF_DAY_CLASSES),
    }
