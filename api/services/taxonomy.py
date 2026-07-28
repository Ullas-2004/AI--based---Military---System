"""The single threat vocabulary shared by the vision and ML engines.

Previously the vision engine emitted COCO class names ("person", "truck") while
the threat model was trained on military classes ("Soldier", "Truck"). The
encoder silently mapped every unrecognised label to index 0 — "Civilian Car",
the *lowest* threat class — so a soldier detected near the border scored MEDIUM.

This module makes the correspondence explicit and auditable.

IMPORTANT OPERATIONAL CAVEAT
----------------------------
The bundled weights are stock ``yolov8n.pt``, trained on COCO. COCO contains no
military classes: there is no tank, no UAV and no military helicopter. The
mapping below is a *documented proxy* so the demo pipeline is coherent
end-to-end. A real deployment requires weights fine-tuned on military imagery;
until then ``is_proxy`` is True on every detection and the UI labels it as such.
"""

# Canonical classes the threat model is trained on. Order is irrelevant; the
# encoder in models/encoders.json is authoritative for index assignment.
THREAT_CLASSES = (
    "Civilian Car",
    "Helicopter",
    "Soldier",
    "Tank",
    "Truck",
    "UAV",
)

WEATHER_CLASSES = ("Clear", "Fog", "Overcast", "Rain", "Snow")
TERRAIN_CLASSES = ("Desert", "Forest", "Mountain", "Urban")
TIME_OF_DAY_CLASSES = ("Afternoon", "Evening", "Morning", "Night")

# COCO class name -> canonical threat class.
# Only defensible correspondences are listed. Anything absent is reported as
# unmapped rather than being coerced into a low-threat class.
COCO_TO_THREAT = {
    "person": "Soldier",
    "truck": "Truck",
    "bus": "Truck",
    "car": "Civilian Car",
    "motorcycle": "Civilian Car",
    "airplane": "UAV",
    "boat": "Civilian Car",
    "train": "Truck",
}

# Detections of these COCO classes are almost always background clutter in an
# aerial surveillance frame and are dropped before scoring.
COCO_IGNORED = {
    "bench", "chair", "couch", "bed", "dining table", "toilet", "tv",
    "laptop", "mouse", "remote", "keyboard", "cell phone", "book", "clock",
    "vase", "scissors", "teddy bear", "hair drier", "toothbrush", "potted plant",
}


def map_detection_class(coco_name: str):
    """Map a COCO class name to a canonical threat class.

    Returns ``(threat_class, is_mapped)``. ``threat_class`` is ``None`` when the
    detection has no military analogue — callers must surface that rather than
    silently substituting a default.
    """
    key = (coco_name or "").strip().lower()
    mapped = COCO_TO_THREAT.get(key)
    return (mapped, True) if mapped else (None, False)


def is_ignored_class(coco_name: str) -> bool:
    return (coco_name or "").strip().lower() in COCO_IGNORED
