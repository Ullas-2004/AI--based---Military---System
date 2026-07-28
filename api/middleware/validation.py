"""Request validation helpers.

Every validator raises :class:`ValidationError`, which ``app.py`` turns into a
422 with a caller-actionable message. Internal exception text is never
forwarded to clients.
"""
from config import config


class ValidationError(ValueError):
    """Invalid caller input. Maps to HTTP 422."""

    def __init__(self, message: str, field: str = None):
        super().__init__(message)
        self.field = field


def require_json(payload) -> dict:
    if not isinstance(payload, dict):
        raise ValidationError("Request body must be a JSON object.")
    return payload


def require_str(data: dict, field: str, *, max_length: int = 200,
                allowed: set = None, default=None) -> str:
    raw = data.get(field, default)
    if raw is None:
        raise ValidationError(f"'{field}' is required.", field)
    if not isinstance(raw, str):
        raise ValidationError(f"'{field}' must be a string.", field)
    value = raw.strip()
    if not value:
        raise ValidationError(f"'{field}' must not be empty.", field)
    if len(value) > max_length:
        raise ValidationError(
            f"'{field}' must be at most {max_length} characters.", field
        )
    if allowed is not None and value not in allowed:
        options = ", ".join(sorted(allowed))
        raise ValidationError(
            f"'{field}' must be one of: {options}. Received '{value}'.", field
        )
    return value


def require_number(data: dict, field: str, *, minimum: float, maximum: float,
                   default=None) -> float:
    raw = data.get(field, default)
    if raw is None:
        raise ValidationError(f"'{field}' is required.", field)
    # bool is a subclass of int; reject it explicitly.
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise ValidationError(f"'{field}' must be a number.", field)
    value = float(raw)
    if value != value or value in (float("inf"), float("-inf")):
        raise ValidationError(f"'{field}' must be a finite number.", field)
    if not (minimum <= value <= maximum):
        raise ValidationError(
            f"'{field}' must be between {minimum} and {maximum}. Received {value}.",
            field,
        )
    return value


def validate_image_upload(file_storage) -> str:
    """Validate an uploaded image by extension *and* magic number.

    Returns the lowercased extension. Raises ValidationError otherwise.
    """
    if file_storage is None or not file_storage.filename:
        raise ValidationError("An image file is required under the 'image' field.", "image")

    name = file_storage.filename
    if "." not in name:
        raise ValidationError("File must have an extension.", "image")

    ext = name.rsplit(".", 1)[1].lower()
    if ext not in config.ALLOWED_IMAGE_EXTENSIONS:
        allowed = ", ".join(sorted(config.ALLOWED_IMAGE_EXTENSIONS))
        raise ValidationError(f"Unsupported file type '.{ext}'. Allowed: {allowed}.", "image")

    # Content sniff: a .txt renamed to .jpg must still be rejected.
    head = file_storage.stream.read(16)
    file_storage.stream.seek(0)
    if not head:
        raise ValidationError("Uploaded file is empty.", "image")
    if ext == "webp":
        is_valid = head[:4] == b"RIFF" and head[8:12] == b"WEBP"
    else:
        is_valid = any(head.startswith(sig) for sig in config.IMAGE_MAGIC_PREFIXES)
    if not is_valid:
        raise ValidationError(
            "File contents are not a valid image. The extension does not match the data.",
            "image",
        )
    return ext
