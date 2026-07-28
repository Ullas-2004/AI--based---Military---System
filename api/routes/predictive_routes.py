"""Predictive intelligence endpoints: threat scoring and forecasting."""
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from database.mongodb import get_db
from middleware.auth import token_required, current_user
from middleware.validation import require_json, require_str, require_number
from services.ml_service import (
    predict_threat_score, valid_categories, categorize_score, is_ready,
    counterfactuals, get_model_card,
)
from services import event_bus
from services.taxonomy import (
    THREAT_CLASSES, WEATHER_CLASSES, TERRAIN_CLASSES, TIME_OF_DAY_CLASSES,
)
from utils.serialization import serialize_doc, parse_pagination

logger = logging.getLogger(__name__)
predictive_bp = Blueprint("predict", __name__)

# Physical bounds. Rejecting -99999 km is not pedantry: an out-of-range value
# silently produced a CRITICAL score in the previous implementation.
MIN_DISTANCE_KM, MAX_DISTANCE_KM = 0.0, 500.0
MIN_CONFIDENCE, MAX_CONFIDENCE = 0.0, 100.0


@predictive_bp.route("/categories", methods=["GET"])
def get_categories():
    """Enum values the scorer accepts, so the UI never hard-codes its own copy."""
    return jsonify({"status": "success", "categories": valid_categories()}), 200


@predictive_bp.route("/model-card", methods=["GET"])
def model_card():
    """Held-out evaluation metrics and documented limitations.

    Served from the artefact written at training time, so the figures always
    describe the model actually running rather than a stale README.
    """
    card = get_model_card()
    if not card:
        return jsonify({
            "status": "error",
            "message": "No model card available. Run: python api/train_threat_model.py",
        }), 503
    return jsonify({"status": "success", "model_card": card}), 200


@predictive_bp.route("/counterfactuals", methods=["POST"])
@token_required
def get_counterfactuals():
    """Smallest single changes that would move this assessment to another band."""
    data = require_json(request.get_json(silent=True) or {})

    detected_object = require_str(data, "object", allowed=set(THREAT_CLASSES))
    weather = require_str(data, "weather", allowed=set(WEATHER_CLASSES), default="Clear")
    terrain = require_str(data, "terrain", allowed=set(TERRAIN_CLASSES), default="Urban")
    time_of_day = require_str(data, "time_of_day", allowed=set(TIME_OF_DAY_CLASSES),
                              default="Morning")
    confidence = require_number(data, "confidence", minimum=MIN_CONFIDENCE,
                                maximum=MAX_CONFIDENCE, default=85.0)
    distance_km = require_number(data, "distance_km", minimum=MIN_DISTANCE_KM,
                                 maximum=MAX_DISTANCE_KM, default=10.0)

    results = counterfactuals(detected_object, confidence, weather, terrain,
                              time_of_day, distance_km)

    return jsonify({
        "status": "success",
        "counterfactuals": results,
        # No single change alters the band: the assessment is robust, which is
        # itself worth telling the analyst.
        "is_robust": len(results) == 0,
    }), 200


@predictive_bp.route("/score", methods=["POST"])
@token_required
def calculate_threat_score():
    """Score a telemetry observation. All six inputs are validated."""
    data = require_json(request.get_json(silent=True) or {})

    detected_object = require_str(data, "object", allowed=set(THREAT_CLASSES))
    weather = require_str(data, "weather", allowed=set(WEATHER_CLASSES), default="Clear")
    terrain = require_str(data, "terrain", allowed=set(TERRAIN_CLASSES), default="Urban")
    time_of_day = require_str(data, "time_of_day", allowed=set(TIME_OF_DAY_CLASSES),
                              default="Morning")
    confidence = require_number(data, "confidence", minimum=MIN_CONFIDENCE,
                                maximum=MAX_CONFIDENCE, default=85.0)
    distance_km = require_number(data, "distance_km", minimum=MIN_DISTANCE_KM,
                                 maximum=MAX_DISTANCE_KM, default=10.0)

    result = predict_threat_score(
        detected_object, confidence, weather, terrain, time_of_day, distance_km
    )

    doc = {
        "telemetry": {
            "object": detected_object,
            "confidence": confidence,
            "weather": weather,
            "terrain": terrain,
            "time_of_day": time_of_day,
            "distance_km": distance_km,
        },
        "ml_output": result,
        "scored_by": current_user().get("user_id"),
        "created_at": datetime.now(timezone.utc),
    }

    db = get_db()
    if db is not None:
        doc["_id"] = db.threat_predictions.insert_one(doc).inserted_id

    serialized = serialize_doc(doc)

    # Push high-severity assessments to any live dashboards.
    if result["threat_level"] in ("HIGH", "CRITICAL"):
        event_bus.publish("threat_assessment", {
            "id": serialized.get("id"),
            "object": detected_object,
            "terrain": terrain,
            "distance_km": distance_km,
            "threat_score": result["threat_score"],
            "threat_level": result["threat_level"],
        })

    return jsonify({
        "status": "success",
        "persisted": db is not None,
        "data": serialized,
    }), 200


@predictive_bp.route("/history", methods=["GET"])
@token_required
def prediction_history():
    """Paginated scoring history, newest first."""
    db = get_db()
    if db is None:
        return jsonify({
            "status": "error",
            "message": "Prediction history is unavailable: database not connected.",
        }), 503

    limit, skip = parse_pagination(request.args)
    cursor = db.threat_predictions.find().sort("created_at", -1).skip(skip).limit(limit)
    records = [serialize_doc(r) for r in cursor]

    return jsonify({
        "status": "success",
        "data": records,
        "pagination": {
            "limit": limit,
            "skip": skip,
            "returned": len(records),
            "total": db.threat_predictions.estimated_document_count(),
        },
    }), 200


@predictive_bp.route("/forecast", methods=["GET"])
@token_required
def get_prediction():
    """Aggregate forward-looking risk derived from recorded predictions.

    This is computed from stored data rather than hard-coded. When no history
    exists it says so explicitly instead of inventing percentages.
    """
    db = get_db()
    if db is None or not is_ready():
        return jsonify({
            "status": "success",
            "forecast": {
                "timeframe": "Next 24 Hours",
                "available": False,
                "reason": "Insufficient data: no prediction history recorded yet.",
            },
        }), 200

    recent = list(
        db.threat_predictions.find(
            {}, {"ml_output": 1, "telemetry": 1}
        ).sort("created_at", -1).limit(200)
    )

    if not recent:
        return jsonify({
            "status": "success",
            "forecast": {
                "timeframe": "Next 24 Hours",
                "available": False,
                "reason": "Insufficient data: no prediction history recorded yet.",
            },
        }), 200

    scores = [r.get("ml_output", {}).get("threat_score", 0) for r in recent]
    mean_score = sum(scores) / len(scores)
    aerial = sum(
        1 for r in recent
        if r.get("telemetry", {}).get("object") in ("UAV", "Helicopter")
    )
    ground = sum(
        1 for r in recent
        if r.get("telemetry", {}).get("object") in ("Tank", "Truck")
    )

    return jsonify({
        "status": "success",
        "forecast": {
            "timeframe": "Next 24 Hours",
            "available": True,
            "sample_size": len(recent),
            "mean_threat_score": round(mean_score, 2),
            "border_risk": categorize_score(mean_score),
            "aerial_activity_share": round(100 * aerial / len(recent), 1),
            "ground_activity_share": round(100 * ground / len(recent), 1),
            "peak_threat_score": round(max(scores), 2),
        },
    }), 200
