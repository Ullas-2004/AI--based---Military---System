"""Helpers for turning MongoDB documents into JSON-safe structures."""
from datetime import datetime, date

from bson import ObjectId

DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100


def serialize_value(value):
    """Recursively convert BSON/datetime values into JSON-safe equivalents."""
    if isinstance(value, ObjectId):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serialize_value(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [serialize_value(v) for v in value]
    return value


def serialize_doc(doc: dict) -> dict:
    """Serialize a single document, normalising ``_id`` to a string ``id``."""
    if doc is None:
        return None
    out = {k: serialize_value(v) for k, v in doc.items()}
    if "_id" in out:
        out["id"] = out.pop("_id")
    return out


def parse_pagination(args) -> tuple:
    """Read and clamp ``limit``/``skip`` query parameters.

    Clamping matters: without it a caller can request the entire collection and
    turn one HTTP request into an unbounded serialisation job.
    """
    try:
        limit = int(args.get("limit", DEFAULT_PAGE_SIZE))
    except (TypeError, ValueError):
        limit = DEFAULT_PAGE_SIZE
    try:
        skip = int(args.get("skip", 0))
    except (TypeError, ValueError):
        skip = 0
    return max(1, min(limit, MAX_PAGE_SIZE)), max(0, skip)
