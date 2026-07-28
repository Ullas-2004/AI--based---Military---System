"""PDF situation report generation."""
import io
import logging
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

from database.mongodb import get_db

logger = logging.getLogger(__name__)

RECORD_LIMIT = 10


class ReportError(RuntimeError):
    """Report generation failed for a reason worth showing the caller."""


def _clean(value) -> str:
    """Escape a value for ReportLab's mini-HTML paragraph parser.

    Database content is untrusted; an object name containing '<' would
    otherwise corrupt the document or inject markup.
    """
    return escape(str(value if value is not None else "N/A"))


def _fmt_timestamp(value) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M")
    if isinstance(value, str):
        return value[:16]
    return "N/A"


def generate_pdf_report(requested_by: str = "unknown"):
    """Build the situation report PDF.

    Returns ``(buffer, filename)`` where *buffer* is an in-memory BytesIO.
    Rendering to memory rather than a temp file means concurrent requests cannot
    collide, nothing accumulates on disk, and there is no cleanup step to fail
    (on Windows the file handle stays open past the response, so an on-close
    unlink silently left files behind).
    """
    now = datetime.now(timezone.utc)
    filename = f"AegisAI_Situation_Report_{now.strftime('%Y%m%d_%H%M%S')}.pdf"
    buffer = io.BytesIO()

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "AegisTitle", parent=styles["Heading1"], fontName="Helvetica-Bold",
        fontSize=22, spaceAfter=14, textColor=colors.HexColor("#002b5e"),
    )
    heading_style = ParagraphStyle(
        "AegisHeading", parent=styles["Heading2"], fontName="Helvetica-Bold",
        fontSize=13, spaceBefore=14, spaceAfter=6,
        textColor=colors.HexColor("#990000"),
    )
    note_style = ParagraphStyle(
        "AegisNote", parent=styles["Normal"], fontSize=8,
        textColor=colors.HexColor("#666666"),
    )

    story = [
        Paragraph("AegisAI Intelligence Command", title_style),
        Paragraph(f"<b>Generated:</b> {now.strftime('%Y-%m-%d %H:%M:%S')} UTC", styles["Normal"]),
        Paragraph(f"<b>Requested by:</b> {_clean(requested_by)}", styles["Normal"]),
        # Honest marking. The previous "SECRET // NOFORN" banner on a demo
        # system with synthetic data was misleading.
        Paragraph("<b>Handling:</b> UNCLASSIFIED // DEMONSTRATION DATA", styles["Normal"]),
        Spacer(1, 20),
    ]

    db = get_db()

    story.append(Paragraph("1. Executive Summary", heading_style))
    if db is None:
        story.append(Paragraph(
            "The intelligence database is not reachable. This report contains no "
            "operational data. Restore database connectivity and regenerate.",
            styles["Normal"],
        ))
    else:
        detection_count = db.vision_detections.estimated_document_count()
        prediction_count = db.threat_predictions.estimated_document_count()
        story.append(Paragraph(
            f"This automated report summarises the {RECORD_LIMIT} most recent vision "
            f"detections and threat predictions held by AegisAI. The system currently "
            f"holds {detection_count} detection record(s) and {prediction_count} "
            f"prediction record(s). All threat scores are advisory model output and "
            f"require analyst confirmation before acting.",
            styles["Normal"],
        ))
    story.append(Spacer(1, 12))

    # --- Section 2: detections ---------------------------------------------
    story.append(Paragraph("2. Recent Detections (Vision Engine)", heading_style))
    detection_rows = [["Timestamp", "Object", "Confidence", "Source Class"]]
    if db is not None:
        try:
            for doc in db.vision_detections.find().sort("created_at", -1).limit(RECORD_LIMIT):
                for det in doc.get("detections", [])[:1]:
                    detection_rows.append([
                        _fmt_timestamp(doc.get("created_at")),
                        _clean(det.get("object")),
                        f"{_clean(det.get('confidence'))}%",
                        _clean(det.get("source_class")),
                    ])
        except Exception:
            logger.exception("Could not read detections for report.")
            raise ReportError("Could not read detection records from the database.")

    if len(detection_rows) == 1:
        detection_rows.append(["No detections recorded", "-", "-", "-"])
    story.append(_styled_table(detection_rows, "#002b5e", [110, 110, 80, 110]))
    story.append(Spacer(1, 18))

    # --- Section 3: predictions --------------------------------------------
    story.append(Paragraph("3. Predictive Threat Assessment (ML Engine)", heading_style))
    prediction_rows = [["Object", "Terrain", "Distance (km)", "Score", "Level"]]
    if db is not None:
        try:
            for doc in db.threat_predictions.find().sort("created_at", -1).limit(RECORD_LIMIT):
                tel = doc.get("telemetry", {})
                ml = doc.get("ml_output", {})
                distance = tel.get("distance_km")
                prediction_rows.append([
                    _clean(tel.get("object")),
                    _clean(tel.get("terrain")),
                    f"{distance:.1f}" if isinstance(distance, (int, float)) else "N/A",
                    _clean(ml.get("threat_score")),
                    _clean(ml.get("threat_level")),
                ])
        except Exception:
            logger.exception("Could not read predictions for report.")
            raise ReportError("Could not read prediction records from the database.")

    if len(prediction_rows) == 1:
        prediction_rows.append(["No predictions recorded", "-", "-", "-", "-"])
    story.append(_styled_table(prediction_rows, "#990000", [100, 90, 90, 70, 80]))
    story.append(Spacer(1, 20))

    story.append(Paragraph(
        "Methodology note: threat scores are produced by a gradient-boosted regressor "
        "trained on synthetic telemetry, and object classes are derived from COCO-trained "
        "YOLO weights mapped onto a military taxonomy. Both are demonstration-grade and "
        "must not be relied upon operationally.",
        note_style,
    ))

    try:
        SimpleDocTemplate(
            buffer, pagesize=A4, title="AegisAI Situation Report",
            author="AegisAI", rightMargin=54, leftMargin=54,
            topMargin=54, bottomMargin=36,
        ).build(story)
    except Exception as exc:
        logger.exception("ReportLab failed to build the PDF.")
        raise ReportError("Could not render the PDF document.") from exc

    buffer.seek(0)
    return buffer, filename


def _styled_table(rows, header_hex: str, col_widths) -> Table:
    table = Table(rows, colWidths=col_widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_hex)),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BOTTOMPADDING", (0, 0), (-1, 0), 8),
        ("TOPPADDING", (0, 0), (-1, 0), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#999999")),
    ]))
    return table
