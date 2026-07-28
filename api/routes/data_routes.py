"""Data hub endpoints: GIS markers, analytics aggregates, CSV and PDF export."""
import csv
import io
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

from flask import (
    Blueprint, Response, jsonify, request, send_file, stream_with_context,
)

from database.mongodb import get_db
from middleware.auth import token_required, current_user, log_audit_event
from middleware.validation import ValidationError
from services.report_service import generate_pdf_report, ReportError

logger = logging.getLogger(__name__)
data_bp = Blueprint("data", __name__)

# Area of operations the tactical map centres on. Kept here so the API and the
# frontend cannot drift into different hemispheres, which they previously had.
AO_CENTRE = {"lat": 34.05, "lng": 72.40}

# Clearly-labelled demo markers, used only when the database holds no georeferenced
# records. Coordinates sit inside AO_CENTRE, unlike the old Los Angeles fixtures.
DEMO_MARKERS = [
    {"id": "T1", "type": "Threat", "lat": 34.0522, "lng": 72.3437, "severity": "CRITICAL",
     "label": "Tank detected - Sector Alpha"},
    {"id": "T2", "type": "Threat", "lat": 34.1200, "lng": 72.4100, "severity": "HIGH",
     "label": "UAV detected - Sector Bravo"},
    {"id": "T3", "type": "Threat", "lat": 33.9800, "lng": 72.5000, "severity": "MEDIUM",
     "label": "Convoy movement - Sector Charlie"},
    {"id": "P1", "type": "Patrol", "lat": 34.0800, "lng": 72.3800, "status": "Active",
     "label": "Patrol unit Echo-7"},
    {"id": "P2", "type": "Patrol", "lat": 33.9500, "lng": 72.4500, "status": "Active",
     "label": "Patrol unit Delta-3"},
    {"id": "S1", "type": "Sensor", "lat": 34.0300, "lng": 72.3200, "status": "Online",
     "label": "Radar station RS-01"},
    {"id": "S2", "type": "Sensor", "lat": 34.1000, "lng": 72.5200, "status": "Online",
     "label": "Thermal sensor TS-04"},
]


@data_bp.route("/map-markers", methods=["GET"])
@token_required
def get_map_markers():
    """GIS markers for the tactical map.

    Returns georeferenced predictions when available, otherwise a demo set that
    is explicitly flagged with ``is_demo`` so the UI can label it.
    """
    db = get_db()
    markers = []

    if db is not None:
        try:
            cursor = db.threat_predictions.find(
                {"location.lat": {"$exists": True}}
            ).sort("created_at", -1).limit(100)
            for doc in cursor:
                loc = doc.get("location", {})
                ml = doc.get("ml_output", {})
                markers.append({
                    "id": str(doc["_id"]),
                    "type": "Threat",
                    "lat": loc["lat"],
                    "lng": loc["lng"],
                    "severity": ml.get("threat_level", "UNKNOWN"),
                    "label": f"{doc.get('telemetry', {}).get('object', 'Unknown')} "
                             f"(score {ml.get('threat_score', '?')})",
                })
        except Exception:
            logger.exception("Failed to load map markers from database.")

    is_demo = not markers
    return jsonify({
        "status": "success",
        "centre": AO_CENTRE,
        "is_demo": is_demo,
        "markers": DEMO_MARKERS if is_demo else markers,
    }), 200


@data_bp.route("/analytics", methods=["GET"])
@token_required
def get_analytics():
    """Aggregates that back the Data Hub charts.

    Computed from stored records. When the database is empty the response says
    so rather than returning invented figures.
    """
    db = get_db()
    if db is None:
        return jsonify({
            "status": "success", "available": False,
            "reason": "Database not connected.",
            "trend": [], "object_breakdown": [], "sector_risk": [],
        }), 200

    since = datetime.now(timezone.utc) - timedelta(hours=24)

    try:
        predictions = list(db.threat_predictions.find({"created_at": {"$gte": since}}))
        detections = list(db.vision_detections.find({"created_at": {"$gte": since}}))
    except Exception:
        logger.exception("Analytics aggregation failed.")
        return jsonify({
            "status": "error",
            "message": "Could not compute analytics.",
        }), 500

    if not predictions and not detections:
        return jsonify({
            "status": "success", "available": False,
            "reason": "No activity recorded in the last 24 hours.",
            "trend": [], "object_breakdown": [], "sector_risk": [],
        }), 200

    # Threat count per 4-hour bucket.
    buckets = defaultdict(lambda: {"threats": 0, "detections": 0})
    for pred in predictions:
        created = pred.get("created_at")
        if created:
            buckets[created.hour // 4 * 4]["threats"] += 1
    for det in detections:
        created = det.get("created_at")
        if created:
            buckets[created.hour // 4 * 4]["detections"] += det.get("total_objects", 0)

    trend = [
        {"time": f"{hour:02d}:00",
         "threats": buckets[hour]["threats"],
         "detections": buckets[hour]["detections"]}
        for hour in range(0, 24, 4)
    ]

    # Object class distribution across both engines.
    counter = Counter()
    for pred in predictions:
        obj = pred.get("telemetry", {}).get("object")
        if obj:
            counter[obj] += 1
    for det in detections:
        for d in det.get("detections", []):
            if d.get("object"):
                counter[d["object"]] += 1
    object_breakdown = [{"name": name, "value": count} for name, count in counter.most_common(6)]

    # Mean threat score grouped by terrain, used as the "sector" dimension.
    by_terrain = defaultdict(list)
    for pred in predictions:
        terrain = pred.get("telemetry", {}).get("terrain")
        score = pred.get("ml_output", {}).get("threat_score")
        if terrain and score is not None:
            by_terrain[terrain].append(score)
    sector_risk = [
        {"name": terrain, "risk": round(sum(scores) / len(scores), 1)}
        for terrain, scores in sorted(by_terrain.items())
    ]

    return jsonify({
        "status": "success",
        "available": True,
        "window_hours": 24,
        "trend": trend,
        "object_breakdown": object_breakdown,
        "sector_risk": sector_risk,
    }), 200


@data_bp.route("/export.csv", methods=["GET"])
@token_required
def export_csv():
    """Export prediction history as CSV for offline analysis.

    Streamed row-by-row so a large export never materialises in memory.
    """
    dataset = request.args.get("dataset", "predictions")
    if dataset not in {"predictions", "detections"}:
        raise ValidationError(
            "'dataset' must be 'predictions' or 'detections'.", "dataset"
        )

    db = get_db()
    if db is None:
        return jsonify({
            "status": "error",
            "message": "Export is unavailable: database not connected.",
        }), 503

    try:
        max_rows = min(int(request.args.get("limit", 5000)), 20000)
    except (TypeError, ValueError):
        max_rows = 5000

    def rows():
        buffer = io.StringIO()
        writer = csv.writer(buffer)

        def flush():
            value = buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            return value

        if dataset == "predictions":
            writer.writerow([
                "timestamp", "object", "confidence", "weather", "terrain",
                "time_of_day", "distance_km", "threat_score", "threat_level",
            ])
            yield flush()
            cursor = db.threat_predictions.find().sort("created_at", -1).limit(max_rows)
            for doc in cursor:
                tel = doc.get("telemetry", {})
                ml = doc.get("ml_output", {})
                created = doc.get("created_at")
                writer.writerow([
                    created.isoformat() if hasattr(created, "isoformat") else created,
                    tel.get("object"), tel.get("confidence"), tel.get("weather"),
                    tel.get("terrain"), tel.get("time_of_day"), tel.get("distance_km"),
                    ml.get("threat_score"), ml.get("threat_level"),
                ])
                yield flush()
        else:
            writer.writerow([
                "timestamp", "filename", "total_objects", "top_object",
                "top_confidence", "source_class", "review_status",
            ])
            yield flush()
            cursor = db.vision_detections.find().sort("created_at", -1).limit(max_rows)
            for doc in cursor:
                dets = doc.get("detections", [])
                top = dets[0] if dets else {}
                created = doc.get("created_at")
                writer.writerow([
                    created.isoformat() if hasattr(created, "isoformat") else created,
                    doc.get("original_filename"), doc.get("total_objects", 0),
                    top.get("object", ""), top.get("confidence", ""),
                    top.get("source_class", ""), doc.get("status", ""),
                ])
                yield flush()

    filename = f"aegisai_{dataset}_{datetime.now(timezone.utc):%Y%m%d_%H%M%S}.csv"
    log_audit_event(current_user().get("user_id", "unknown"), "DATA_EXPORTED",
                    filename, request.remote_addr or "")

    return Response(
        stream_with_context(rows()),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@data_bp.route("/download-report", methods=["GET"])
@token_required
def download_report():
    """Generate and stream the PDF situation report."""
    try:
        buffer, filename = generate_pdf_report(
            requested_by=current_user().get("user_id", "unknown")
        )
    except ReportError as exc:
        return jsonify({"status": "error", "message": str(exc)}), 500
    except Exception:
        logger.exception("PDF generation failed.")
        return jsonify({
            "status": "error",
            "message": "Report generation failed. The incident has been logged.",
        }), 500

    log_audit_event(current_user().get("user_id", "unknown"), "REPORT_EXPORTED",
                    filename, request.remote_addr or "")

    # Streamed straight from memory: nothing is written to disk, so there is no
    # cleanup step that can fail or leave stale reports behind.
    return send_file(buffer, as_attachment=True, download_name=filename,
                     mimetype="application/pdf")
