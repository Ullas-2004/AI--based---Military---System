"""Vision engine endpoints: image detection and detection history."""
import logging
import os
import uuid
from datetime import datetime, timezone

from bson import ObjectId
from bson.errors import InvalidId
from flask import Blueprint, jsonify, request
from werkzeug.utils import secure_filename

from config import config
from database.mongodb import get_db
from middleware.auth import token_required, current_user, log_audit_event
from middleware.validation import (
    ValidationError, require_json, require_str, validate_image_upload,
)
from services import event_bus
from services.vision_service import detect_objects, VisionUnavailableError
from utils.serialization import serialize_doc, parse_pagination

logger = logging.getLogger(__name__)
threat_bp = Blueprint("threat", __name__)

os.makedirs(config.UPLOAD_FOLDER, exist_ok=True)


@threat_bp.route("/detect", methods=["POST"])
@token_required
def detect_threat():
    """Validate and analyse an uploaded surveillance image."""
    file = request.files.get("image")
    ext = validate_image_upload(file)  # raises ValidationError -> 422

    # Randomised stored name: prevents collisions between analysts uploading
    # "drone1.jpg" and stops a caller from choosing a path on disk.
    original_name = secure_filename(file.filename) or f"upload.{ext}"
    stored_name = f"{uuid.uuid4().hex}.{ext}"
    filepath = os.path.join(config.UPLOAD_FOLDER, stored_name)

    try:
        file.save(filepath)
        result = detect_objects(filepath)
    except VisionUnavailableError as exc:
        _safe_unlink(filepath)
        return jsonify({"status": "error", "message": str(exc)}), 503
    finally:
        # The image has been analysed; we persist findings, not the raw frame.
        _safe_unlink(filepath)

    user = current_user()
    doc = {
        "original_filename": original_name,
        "detections": result["detections"],
        "unmapped_detections": result["unmapped"],
        "total_objects": len(result["detections"]),
        "model": result["model"],
        "uploaded_by": user.get("user_id"),
        "created_at": datetime.now(timezone.utc),
        "status": "pending_analyst_review",
    }

    db = get_db()
    if db is not None:
        doc["_id"] = db.vision_detections.insert_one(doc).inserted_id

    log_audit_event(
        user.get("user_id", "unknown"),
        "VISION_DETECT",
        f"{len(result['detections'])} object(s) in '{original_name}'",
        request.remote_addr or "",
    )

    serialized = serialize_doc(doc)

    # Announce the detection to live dashboards.
    if result["detections"]:
        top = result["detections"][0]
        event_bus.publish("detection", {
            "id": serialized.get("id"),
            "filename": original_name,
            "total_objects": len(result["detections"]),
            "top_object": top["object"],
            "top_confidence": top["confidence"],
        })

    return jsonify({
        "status": "success",
        "persisted": db is not None,
        "data": serialized,
    }), 200


# Review outcomes an analyst may record against a detection.
REVIEW_STATUSES = {
    "confirmed": "Detection verified as a genuine contact",
    "false_positive": "Detection rejected as a false positive",
    "pending_analyst_review": "Returned to the review queue",
}


@threat_bp.route("/<detection_id>/review", methods=["POST"])
@token_required
def review_detection(detection_id):
    """Record an analyst's verdict on a detection.

    This is the human-in-the-loop step: model output is a recommendation until
    a person confirms or rejects it. Verdicts are what make the false-positive
    rate measurable rather than assumed.
    """
    data = require_json(request.get_json(silent=True) or {})
    status = require_str(data, "status", allowed=set(REVIEW_STATUSES))
    note = data.get("note", "")
    if not isinstance(note, str) or len(note) > 500:
        raise ValidationError("'note' must be a string of at most 500 characters.", "note")

    try:
        object_id = ObjectId(detection_id)
    except (InvalidId, TypeError):
        raise ValidationError("Invalid detection id.", "detection_id") from None

    db = get_db()
    if db is None:
        return jsonify({
            "status": "error",
            "message": "Review is unavailable: database not connected.",
        }), 503

    user = current_user()
    result = db.vision_detections.update_one(
        {"_id": object_id},
        {"$set": {
            "status": status,
            "review": {
                "status": status,
                "note": note.strip(),
                "reviewed_by": user.get("user_id"),
                "reviewed_at": datetime.now(timezone.utc),
            },
        }},
    )

    if result.matched_count == 0:
        return jsonify({"status": "error", "message": "Detection not found."}), 404

    log_audit_event(
        user.get("user_id", "unknown"), "DETECTION_REVIEWED",
        f"{detection_id} marked {status}", request.remote_addr or "",
    )

    return jsonify({
        "status": "success",
        "message": REVIEW_STATUSES[status],
        "data": {"id": detection_id, "review_status": status},
    }), 200


@threat_bp.route("/review-queue", methods=["GET"])
@token_required
def review_queue():
    """Pending detections ordered by how much an analyst verdict would help.

    This is uncertainty sampling, the classic active-learning strategy: the
    label that teaches you most is the one the model is least sure about.
    Reviewing confidently-classified frames mostly confirms what is already
    known, so they sink to the bottom of the queue.

    Priority combines two signals:
      * detector uncertainty  - confidence nearest the accept threshold
      * ambiguity             - a frame carrying unmapped or conflicting classes
    """
    db = get_db()
    if db is None:
        return jsonify({
            "status": "error",
            "message": "Review queue is unavailable: database not connected.",
        }), 503

    limit, _ = parse_pagination(request.args)
    threshold = config.YOLO_CONFIDENCE_THRESHOLD * 100

    pending = list(
        db.vision_detections
        .find({"status": "pending_analyst_review"})
        .sort("created_at", -1)
        .limit(300)          # bounded working set, ranked in the app tier
    )

    scored = []
    for doc in pending:
        detections = doc.get("detections", [])
        if not detections:
            # Nothing detected at all is genuinely ambiguous: either an empty
            # frame or a miss. Worth a human look.
            priority, reason = 0.75, "No objects detected - possible miss"
        else:
            confidences = [d.get("confidence", 0) for d in detections]
            # Distance from the accept threshold, normalised. A detection at
            # 41% when the cutoff is 40% is maximally uncertain.
            closest = min(abs(c - threshold) for c in confidences)
            uncertainty = max(0.0, 1.0 - closest / 50.0)

            distinct = len({d.get("object") for d in detections})
            conflict = 0.2 if distinct > 1 else 0.0
            unmapped = 0.25 if doc.get("unmapped_detections") else 0.0

            priority = min(1.0, uncertainty * 0.6 + conflict + unmapped)
            lowest = min(confidences)
            if unmapped:
                reason = "Contains classes with no military analogue"
            elif conflict:
                reason = f"{distinct} different classes in one frame"
            else:
                reason = f"Lowest detection confidence {lowest:.0f}%"

        record = serialize_doc(doc)
        record["review_priority"] = round(priority, 3)
        record["review_reason"] = reason
        scored.append(record)

    scored.sort(key=lambda r: r["review_priority"], reverse=True)

    return jsonify({
        "status": "success",
        "strategy": "uncertainty sampling (active learning)",
        "data": scored[:limit],
        "pending_total": len(pending),
    }), 200


@threat_bp.route("/review-metrics", methods=["GET"])
@token_required
def review_metrics():
    """Aggregate model-quality metrics derived from analyst verdicts."""
    db = get_db()
    if db is None:
        return jsonify({
            "status": "error",
            "message": "Metrics are unavailable: database not connected.",
        }), 503

    total = db.vision_detections.estimated_document_count()
    confirmed = db.vision_detections.count_documents({"status": "confirmed"})
    false_positive = db.vision_detections.count_documents({"status": "false_positive"})
    pending = db.vision_detections.count_documents({"status": "pending_analyst_review"})
    reviewed = confirmed + false_positive

    return jsonify({
        "status": "success",
        "metrics": {
            "total": total,
            "reviewed": reviewed,
            "pending": pending,
            "confirmed": confirmed,
            "false_positive": false_positive,
            # Only meaningful once something has been reviewed; null beats 0.0,
            # which would read as "no false positives" when it means "no data".
            "false_positive_rate": (
                round(100 * false_positive / reviewed, 1) if reviewed else None
            ),
            "review_coverage": round(100 * reviewed / total, 1) if total else 0.0,
        },
    }), 200


@threat_bp.route("/history", methods=["GET"])
@token_required
def get_threat_history():
    """Paginated detection history, newest first."""
    db = get_db()
    if db is None:
        return jsonify({
            "status": "error",
            "message": "Detection history is unavailable: database not connected.",
        }), 503

    limit, skip = parse_pagination(request.args)
    cursor = db.vision_detections.find().sort("created_at", -1).skip(skip).limit(limit)
    records = [serialize_doc(r) for r in cursor]

    return jsonify({
        "status": "success",
        "data": records,
        "pagination": {
            "limit": limit,
            "skip": skip,
            "returned": len(records),
            "total": db.vision_detections.estimated_document_count(),
        },
    }), 200


def _safe_unlink(path: str) -> None:
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        logger.warning("Could not remove temporary upload %s", path)
