"""YOLO object detection, mapped onto the shared threat taxonomy.

The model is loaded lazily on first use so importing this module (and therefore
booting the API) does not pay the torch import cost or fail outright when the
weights are missing.
"""
import logging
import threading
from datetime import datetime, timezone

from config import config
from services.taxonomy import map_detection_class, is_ignored_class

logger = logging.getLogger(__name__)

_model = None
_load_lock = threading.Lock()
_load_failed = False


class VisionUnavailableError(RuntimeError):
    """The detection model could not be loaded."""


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _load_lock:
        if _model is not None:
            return _model
        try:
            from ultralytics import YOLO  # imported lazily: pulls in torch
            _model = YOLO(config.YOLO_WEIGHTS_PATH)
            logger.info("YOLO weights loaded from %s", config.YOLO_WEIGHTS_PATH)
            return _model
        except Exception as exc:
            logger.exception("Could not load YOLO weights.")
            raise VisionUnavailableError(
                f"Vision engine unavailable: YOLO weights failed to load ({exc})."
            ) from exc


def is_ready() -> bool:
    try:
        _get_model()
        return True
    except VisionUnavailableError:
        return False


def detect_objects(image_path: str) -> dict:
    """Run detection and return a structured, taxonomy-aware result.

    Returns a dict with:
      detections  - list of mapped detections (threat_class is never guessed)
      unmapped    - COCO classes with no military analogue, reported not hidden
      model       - which weights produced this
    """
    model = _get_model()
    threshold = config.YOLO_CONFIDENCE_THRESHOLD

    try:
        results = model(image_path, verbose=False)
    except Exception as exc:
        logger.exception("YOLO inference failed for %s", image_path)
        raise VisionUnavailableError("Detection failed for the supplied image.") from exc

    detected_at = datetime.now(timezone.utc)
    detections = []
    unmapped = []

    for result in results:
        for box in result.boxes:
            confidence = float(box.conf[0])
            if confidence < threshold:
                continue

            coco_name = model.names[int(box.cls[0])]
            if is_ignored_class(coco_name):
                continue

            threat_class, mapped = map_detection_class(coco_name)
            x1, y1, x2, y2 = (round(v, 2) for v in box.xyxy[0].tolist())

            if not mapped:
                # Surfaced to the analyst instead of being silently scored as a
                # low-threat class, which is what the old code did.
                unmapped.append({
                    "source_class": coco_name,
                    "confidence": round(confidence * 100, 2),
                })
                continue

            detections.append({
                "object": threat_class,
                "source_class": coco_name,
                "is_proxy_class": True,  # stock COCO weights, see taxonomy.py
                "confidence": round(confidence * 100, 2),
                "bbox": {"x1": x1, "y1": y1, "x2": x2, "y2": y2},
                "detected_at": detected_at,
            })

    # Highest-confidence first so the UI and PDF lead with the strongest signal.
    detections.sort(key=lambda d: d["confidence"], reverse=True)

    return {
        "detections": detections,
        "unmapped": unmapped,
        "model": "yolov8n (COCO proxy classes)",
    }
