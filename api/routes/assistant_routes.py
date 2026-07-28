"""Generative AI assistant endpoints."""
import logging
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request

from database.mongodb import get_db
from middleware.auth import token_required, current_user, log_audit_event
from middleware.validation import require_json, require_str
from services.llm_service import (
    query_intelligence_assistant, generate_tactical_report, is_online,
)
from utils.serialization import serialize_doc

logger = logging.getLogger(__name__)
assistant_bp = Blueprint("assistant", __name__)

CONTEXT_RECORD_LIMIT = 5


def get_latest_telemetry() -> str:
    """Build the retrieval context from recent detections and predictions."""
    db = get_db()
    if db is None:
        return "No telemetry available: database not connected."

    lines = []
    try:
        for pred in db.threat_predictions.find().sort("created_at", -1).limit(CONTEXT_RECORD_LIMIT):
            tel = pred.get("telemetry", {})
            ml = pred.get("ml_output", {})
            lines.append(
                f"- PREDICTION: {tel.get('object', 'unknown')} in {tel.get('terrain', 'unknown')} "
                f"terrain at {tel.get('distance_km', '?')}km from border. "
                f"Weather {tel.get('weather', 'unknown')}, {tel.get('time_of_day', 'unknown')}. "
                f"Threat {ml.get('threat_level', 'UNKNOWN')} (score {ml.get('threat_score', '?')})."
            )
        for det in db.vision_detections.find().sort("created_at", -1).limit(CONTEXT_RECORD_LIMIT):
            objects = ", ".join(
                f"{d.get('object')} ({d.get('confidence')}%)"
                for d in det.get("detections", [])[:5]
            ) or "no objects above threshold"
            lines.append(f"- DETECTION: {det.get('total_objects', 0)} object(s): {objects}.")
    except Exception:
        logger.exception("Failed to build assistant context.")
        return "Telemetry retrieval failed."

    return "\n".join(lines) if lines else "No telemetry records found in the database."


@assistant_bp.route("/status", methods=["GET"])
def assistant_status():
    """Whether a live model is configured, so the UI can label offline mode."""
    return jsonify({"status": "success", "online": is_online()}), 200


@assistant_bp.route("/ask", methods=["POST"])
@token_required
def ask_assistant():
    """Answer an analyst question grounded in recent database records."""
    data = require_json(request.get_json(silent=True) or {})
    question = require_str(data, "question", max_length=2000)

    context = get_latest_telemetry()
    result = query_intelligence_assistant(question, context)

    log_audit_event(current_user().get("user_id", "unknown"), "ASSISTANT_QUERY",
                    question[:200], request.remote_addr or "")

    return jsonify({
        "status": "success",
        "answer": result["answer"],
        "online": result["online"],
        "model": result["model"],
    }), 200


@assistant_bp.route("/report", methods=["POST"])
@token_required
def generate_report():
    """Generate and persist a narrative intelligence report."""
    context = get_latest_telemetry()
    result = generate_tactical_report(context)

    user = current_user()
    doc = {
        "report": result["answer"],
        "online": result["online"],
        "model": result["model"],
        "generated_by": user.get("user_id"),
        "created_at": datetime.now(timezone.utc),
        "status": "generated",
    }

    db = get_db()
    if db is not None:
        doc["_id"] = db.intelligence_reports.insert_one(doc).inserted_id

    log_audit_event(user.get("user_id", "unknown"), "REPORT_GENERATED", "",
                    request.remote_addr or "")

    serialized = serialize_doc(doc)
    return jsonify({
        "status": "success",
        "report_id": serialized.get("id"),
        "persisted": db is not None,
        "online": result["online"],
        "content": result["answer"],
    }), 200
