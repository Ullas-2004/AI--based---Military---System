"""Authentication, authorisation and audit logging."""
import logging
from datetime import datetime, timedelta, timezone
from functools import wraps

import bcrypt
import jwt
from flask import request, jsonify, g

from config import config
from database.mongodb import get_db

logger = logging.getLogger(__name__)

# bcrypt hashes at most 72 bytes; anything longer raises ValueError. We reject
# it up front with a clear 400 rather than letting it become a 500.
MAX_PASSWORD_BYTES = 72
MIN_PASSWORD_LENGTH = 8

VALID_ROLES = {"analyst", "commander", "admin"}


class AuthError(ValueError):
    """Raised for caller-fixable credential problems (maps to HTTP 400)."""


def validate_password(password: str) -> None:
    """Raise AuthError if the password cannot be safely hashed or is too weak."""
    if not password:
        raise AuthError("Password is required.")
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise AuthError(
            f"Password must not exceed {MAX_PASSWORD_BYTES} bytes "
            "(accented and non-Latin characters count as more than one byte)."
        )
    if password.isdigit() or password.isalpha():
        raise AuthError("Password must mix letters with numbers or symbols.")


def hash_password(password: str) -> str:
    """Hash a password with bcrypt. Validates length first."""
    validate_password(password)
    salt = bcrypt.gensalt(rounds=config.BCRYPT_ROUNDS)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Password check that never raises on malformed or over-long input."""
    if not password or not hashed:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))
    except (ValueError, TypeError):
        # Over-long candidate or a corrupted stored hash: treat as a mismatch.
        return False


def generate_token(user_id: str, role: str) -> str:
    """Issue a short-lived HS256 JWT."""
    now = datetime.now(timezone.utc)
    payload = {
        "user_id": user_id,
        "role": role,
        "iat": now,
        "exp": now + timedelta(hours=config.TOKEN_EXPIRY_HOURS),
    }
    return jwt.encode(payload, config.JWT_SECRET_KEY, algorithm=config.JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode a JWT, returning {"error": ...} rather than raising."""
    try:
        return jwt.decode(
            token,
            config.JWT_SECRET_KEY,
            algorithms=[config.JWT_ALGORITHM],  # pinned: never trust the alg header
            options={"require": ["exp", "iat", "user_id", "role"]},
        )
    except jwt.ExpiredSignatureError:
        return {"error": "Token expired"}
    except jwt.InvalidTokenError:
        return {"error": "Invalid token"}


def _extract_token() -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return ""


def token_required(f):
    """Reject the request unless it carries a valid, unexpired JWT."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = _extract_token()
        if not token:
            return jsonify({
                "status": "error",
                "message": "Authentication required. Send an "
                           "'Authorization: Bearer <token>' header.",
            }), 401

        decoded = decode_token(token)
        if "error" in decoded:
            return jsonify({"status": "error", "message": decoded["error"]}), 401

        # Stash on flask.g rather than mutating the request object.
        g.current_user = decoded
        return f(*args, **kwargs)
    return decorated


def roles_required(*allowed_roles):
    """Require a valid token *and* one of the given roles."""
    def decorator(f):
        @wraps(f)
        @token_required
        def decorated(*args, **kwargs):
            role = g.current_user.get("role")
            if role not in allowed_roles:
                log_audit_event(
                    g.current_user.get("user_id", "unknown"),
                    "AUTHZ_DENIED",
                    f"Role '{role}' attempted {request.method} {request.path}",
                    request.remote_addr or "",
                )
                return jsonify({
                    "status": "error",
                    "message": "Insufficient privileges for this operation.",
                }), 403
            return f(*args, **kwargs)
        return decorated
    return decorator


def current_user() -> dict:
    """The decoded JWT payload for this request, or {} if unauthenticated."""
    return getattr(g, "current_user", {})


def log_audit_event(user_id: str, action: str, details: str = "",
                    ip_address: str = "") -> None:
    """Append a security event to the audit trail. Never raises."""
    db = get_db()
    if db is None:
        logger.warning("Audit event dropped (no database): %s %s", action, details)
        return
    try:
        db.audit_logs.insert_one({
            "user_id": user_id,
            "action": action,
            "details": details,
            "ip_address": ip_address,
            "timestamp": datetime.now(timezone.utc),
        })
    except Exception:  # pragma: no cover - audit must never break the request
        logger.exception("Failed to write audit event %s", action)
