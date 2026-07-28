"""Train the AegisAI threat-scoring model.

Run with:  python api/train_threat_model.py

Honest description of what this is
----------------------------------
Real military telemetry is classified, so the training set is synthetic. The
labels come from a doctrine-inspired scoring function plus Gaussian analyst
noise, which means the model is learning a *noisy, interacting* function rather
than memorising a handful of if-statements.

Every feature carries real signal by construction:

  * DetectedObject      - base threat of the asset class
  * DistanceToBorder_km - non-linear proximity decay
  * ConfidenceScore     - low-confidence detections are discounted multiplicatively
  * Terrain             - modulates concealment/exposure, and interacts with object
  * Weather / TimeOfDay - low-visibility conditions raise suspicion of intent

The model is a gradient-boosted regressor over those six features. It is a
decision-support aid, not an oracle; scores are advisory and every prediction is
persisted with its inputs so an analyst can audit it.
"""
import json
import os
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import mean_absolute_error, r2_score
from sklearn.model_selection import train_test_split

sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import config  # noqa: E402
from services.taxonomy import (  # noqa: E402
    THREAT_CLASSES, WEATHER_CLASSES, TERRAIN_CLASSES, TIME_OF_DAY_CLASSES,
)

RANDOM_SEED = 42
# 10th/50th/90th percentiles -> an 80% prediction interval.
QUANTILES = (0.1, 0.5, 0.9)
NUM_SAMPLES = 12_000
FEATURE_ORDER = [
    "DetectedObject",
    "ConfidenceScore",
    "Weather",
    "Terrain",
    "TimeOfDay",
    "DistanceToBorder_km",
]

# --- Doctrine weights -------------------------------------------------------
OBJECT_BASE = {
    "Tank": 62.0,
    "Helicopter": 58.0,
    "UAV": 52.0,
    "Soldier": 34.0,
    "Truck": 26.0,
    "Civilian Car": 8.0,
}
# Terrain modifies how threatening an asset is: armour in open desert can
# manoeuvre fast, infantry in forest/urban is hard to track and can mass unseen.
TERRAIN_MODIFIER = {
    ("Tank", "Desert"): 9.0, ("Tank", "Urban"): -4.0,
    ("Tank", "Mountain"): -6.0, ("Tank", "Forest"): -2.0,
    ("Soldier", "Forest"): 8.0, ("Soldier", "Urban"): 7.0,
    ("Soldier", "Desert"): -4.0, ("Soldier", "Mountain"): 5.0,
    ("UAV", "Mountain"): 6.0, ("UAV", "Urban"): 4.0,
    ("Helicopter", "Mountain"): 7.0, ("Helicopter", "Desert"): 3.0,
    ("Truck", "Desert"): 4.0, ("Truck", "Urban"): 2.0,
}
TERRAIN_BASE = {"Desert": 3.0, "Urban": 4.0, "Forest": 2.0, "Mountain": 1.0}
WEATHER_MODIFIER = {"Clear": 0.0, "Overcast": 2.5, "Rain": 4.5, "Snow": 6.5, "Fog": 8.5}
TIME_MODIFIER = {"Morning": 0.0, "Afternoon": -1.0, "Evening": 3.0, "Night": 7.5}


def proximity_score(distance_km: np.ndarray) -> np.ndarray:
    """Exponential decay: threat concentrates sharply inside ~10km."""
    return 30.0 * np.exp(-distance_km / 9.0)


def confidence_multiplier(confidence: np.ndarray) -> np.ndarray:
    """Discount uncertain detections. 50% conf -> ~0.72x, 99% -> ~1.0x."""
    return 0.55 + 0.45 * (confidence / 100.0) ** 0.65


def build_dataset(rng: np.random.Generator) -> pd.DataFrame:
    df = pd.DataFrame({
        "DetectedObject": rng.choice(THREAT_CLASSES, NUM_SAMPLES),
        "ConfidenceScore": rng.uniform(40, 99.5, NUM_SAMPLES),
        "Weather": rng.choice(WEATHER_CLASSES, NUM_SAMPLES),
        "Terrain": rng.choice(TERRAIN_CLASSES, NUM_SAMPLES),
        "TimeOfDay": rng.choice(TIME_OF_DAY_CLASSES, NUM_SAMPLES),
        "DistanceToBorder_km": rng.uniform(0.1, 50.0, NUM_SAMPLES),
    })

    base = df["DetectedObject"].map(OBJECT_BASE).to_numpy()
    terrain_base = df["Terrain"].map(TERRAIN_BASE).to_numpy()
    interaction = np.array([
        TERRAIN_MODIFIER.get((o, t), 0.0)
        for o, t in zip(df["DetectedObject"], df["Terrain"])
    ])
    weather = df["Weather"].map(WEATHER_MODIFIER).to_numpy()
    time_of_day = df["TimeOfDay"].map(TIME_MODIFIER).to_numpy()
    proximity = proximity_score(df["DistanceToBorder_km"].to_numpy())

    raw = base + terrain_base + interaction + weather + time_of_day + proximity
    # Confidence scales the whole assessment, not just one additive term.
    raw = raw * confidence_multiplier(df["ConfidenceScore"].to_numpy())
    # Analyst disagreement / sensor jitter: prevents a perfect deterministic fit.
    raw = raw + rng.normal(0.0, 4.0, NUM_SAMPLES)

    df["ThreatScore"] = np.clip(raw, 0.0, 99.0)
    return df


def main() -> int:
    rng = np.random.default_rng(RANDOM_SEED)
    print("Training AegisAI threat-scoring model...")
    df = build_dataset(rng)
    print(f"  Generated {len(df):,} synthetic telemetry records.")

    # Deterministic, explicit encoders — index == position in the class tuple.
    encoders = {
        "DetectedObject": list(THREAT_CLASSES),
        "Weather": list(WEATHER_CLASSES),
        "Terrain": list(TERRAIN_CLASSES),
        "TimeOfDay": list(TIME_OF_DAY_CLASSES),
    }
    encoded = df.copy()
    for column, classes in encoders.items():
        lookup = {name: idx for idx, name in enumerate(classes)}
        encoded[column] = encoded[column].map(lookup).astype(int)

    X = encoded[FEATURE_ORDER]
    y = encoded["ThreatScore"]
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=RANDOM_SEED
    )

    model = xgb.XGBRegressor(
        objective="reg:squarederror",
        n_estimators=400,
        learning_rate=0.05,
        max_depth=5,
        subsample=0.85,
        colsample_bytree=0.85,
        reg_lambda=1.5,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    model.fit(X_train, y_train)

    preds = model.predict(X_test)
    mae = mean_absolute_error(y_test, preds)
    r2 = r2_score(y_test, preds)
    rmse = float(np.sqrt(np.mean((y_test - preds) ** 2)))
    print(f"  Holdout MAE : {mae:.2f} threat points")
    print(f"  Holdout RMSE: {rmse:.2f}")
    print(f"  Holdout R^2 : {r2:.4f}")

    importances = dict(zip(FEATURE_ORDER, (float(v) for v in model.feature_importances_)))
    print("\n  Feature importances:")
    for name, importance in sorted(importances.items(), key=lambda kv: -kv[1]):
        print(f"    {name:22s} {importance:.4f}")

    # --- Uncertainty model ---------------------------------------------
    # A point estimate alone cannot say how confident it is. This companion
    # model predicts the 10th/50th/90th conditional quantiles, giving an 80%
    # prediction interval per assessment. Wide interval => the model is
    # extrapolating and the analyst should weight it accordingly.
    print("\nTraining quantile model for prediction intervals...")
    quantile_model = xgb.XGBRegressor(
        objective="reg:quantileerror",
        quantile_alpha=np.array(QUANTILES),
        n_estimators=250,
        learning_rate=0.06,
        max_depth=4,
        subsample=0.85,
        random_state=RANDOM_SEED,
        n_jobs=-1,
    )
    quantile_model.fit(X_train, y_train)

    bounds = quantile_model.predict(X_test)
    lower, upper = bounds[:, 0], bounds[:, 2]
    # Empirical coverage: what fraction of held-out truths land inside the
    # nominal 80% band. Near 0.80 means the intervals are honest.
    coverage = float(np.mean((y_test >= lower) & (y_test <= upper)))
    mean_width = float(np.mean(upper - lower))
    print(f"  Nominal coverage : {int((QUANTILES[2] - QUANTILES[0]) * 100)}%")
    print(f"  Empirical coverage: {coverage:.1%}")
    print(f"  Mean interval width: {mean_width:.2f} points")

    # --- Band-level classification quality ------------------------------
    def band(values):
        return np.select(
            [values >= 80, values >= 60, values >= 40],
            ["CRITICAL", "HIGH", "MEDIUM"], default="LOW",
        )

    true_bands, pred_bands = band(y_test.to_numpy()), band(preds)
    band_accuracy = float(np.mean(true_bands == pred_bands))
    print(f"\n  Threat-band accuracy: {band_accuracy:.1%}")

    confusion = {}
    for actual in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
        row = {}
        for predicted in ("LOW", "MEDIUM", "HIGH", "CRITICAL"):
            row[predicted] = int(np.sum((true_bands == actual) & (pred_bands == predicted)))
        confusion[actual] = row

    os.makedirs(config.MODEL_DIR, exist_ok=True)
    # Native JSON format: portable across XGBoost versions, no pickle warning,
    # and no scikit-learn needed at inference time.
    model.save_model(config.THREAT_MODEL_PATH)
    quantile_model.save_model(config.QUANTILE_MODEL_PATH)
    with open(config.ENCODERS_PATH, "w", encoding="utf-8") as fh:
        json.dump(
            {"features": FEATURE_ORDER, "categories": encoders},
            fh, indent=2, sort_keys=True,
        )

    # --- Model card ------------------------------------------------------
    # Persisted at training time and served to the UI, so the reported metrics
    # always belong to the model actually running rather than a stale README.
    model_card = {
        "model_version": "xgboost-regressor-v3",
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "algorithm": "XGBoost gradient-boosted trees (squared error)",
        "training_samples": len(X_train),
        "holdout_samples": len(X_test),
        "features": FEATURE_ORDER,
        "metrics": {
            "mae": round(float(mae), 3),
            "rmse": round(rmse, 3),
            "r2": round(float(r2), 4),
            "band_accuracy": round(band_accuracy, 4),
        },
        "uncertainty": {
            "quantiles": list(QUANTILES),
            "nominal_coverage": round(QUANTILES[2] - QUANTILES[0], 2),
            "empirical_coverage": round(coverage, 4),
            "mean_interval_width": round(mean_width, 2),
        },
        "feature_importance": {k: round(v, 4) for k, v in importances.items()},
        "confusion_matrix": confusion,
        "training_data": "synthetic",
        "limitations": [
            "Trained on synthetic telemetry generated from a doctrine-inspired "
            "scoring function with Gaussian analyst noise. Real operational "
            "telemetry is classified and was not used.",
            "Object classes originate from COCO-trained YOLO weights mapped onto "
            "a military taxonomy as a documented proxy.",
            "Scores are advisory decision support and require analyst "
            "confirmation before any action.",
        ],
    }
    with open(config.MODEL_CARD_PATH, "w", encoding="utf-8") as fh:
        json.dump(model_card, fh, indent=2, sort_keys=True)

    print(f"\nSaved model     -> {config.THREAT_MODEL_PATH}")
    print(f"Saved quantiles -> {config.QUANTILE_MODEL_PATH}")
    print(f"Saved encoders  -> {config.ENCODERS_PATH}")
    print(f"Saved model card-> {config.MODEL_CARD_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
