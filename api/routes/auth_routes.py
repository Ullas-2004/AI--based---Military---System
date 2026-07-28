"""Authentication endpoints: registration, login, profile and audit trail."""
import logging
import re
from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from pymongo.errors import DuplicateKeyError

from database.mongodb import get_db
from middleware.auth import (
    AuthError, hash_password, verify_password, generate_token, log_audit_event,
    token_required, roles_required, current_user, VALID_ROLES, validate_password,
)
from middleware.rate_limit import rate_limit
from middleware.validation import require_json, require_str, ValidationError
from utils.serialization import serialize_doc, parse_pagination

logger = logging.getLogger(__name__)
auth_bp = Blueprint("auth", __name__)

USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9._-]{3,32}$")
# Roles a self-service registration may claim. Privileged roles are assigned
# out of band; otherwise anyone could register themselves as an admin.
SELF_SERVICE_ROLES = {"analyst"}


def _db_or_503():
    db = get_db()
    if db is None:
        return None, (jsonify({
            "status": "error",
            "message": "Authentication is unavailable: database not connected.",
        }), 503)
    return db, None


@auth_bp.route("/register", methods=["POST"])
@rate_limit(scope="register", limit_key="RATE_LIMIT_REGISTER", window_key="RATE_LIMIT_REGISTER_WINDOW")
def register():
    """Create a new analyst account."""
    data = require_json(request.get_json(silent=True) or {})
    username = require_str(data, "username", max_length=32)
    password = data.get("password") or ""
    role = require_str(data, "role", allowed=SELF_SERVICE_ROLES, default="analyst")

    if not USERNAME_PATTERN.match(username):
        raise ValidationError(
            "Username must be 3-32 characters using letters, digits, dot, "
            "underscore or hyphen only.",
            "username",
        )
    validate_password(password)  # raises AuthError -> 400

    db, err = _db_or_503()
    if err:
        return err

    user_doc = {
        "username": username,
        "username_lower": username.lower(),
        "password": hash_password(password),
        "role": role,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }

    try:
        result = db.users.insert_one(user_doc)
    except DuplicateKeyError:
        # Unique index on username is the authoritative guard; a find-then-insert
        # check would race under concurrent registration.
        return jsonify({"status": "error", "message": "Username already exists."}), 409

    log_audit_event(str(result.inserted_id), "USER_REGISTERED",
                    f"New {role} account '{username}'", request.remote_addr or "")

    return jsonify({
        "status": "success",
        "message": f"Analyst '{username}' registered successfully.",
        "user": {"id": str(result.inserted_id), "username": username, "role": role},
    }), 201


@auth_bp.route("/login", methods=["POST"])
@rate_limit(scope="login", limit_key="RATE_LIMIT_LOGIN", window_key="RATE_LIMIT_LOGIN_WINDOW")
def login():
    """Authenticate and issue a JWT."""
    data = require_json(request.get_json(silent=True) or {})
    username = require_str(data, "username", max_length=32)
    password = data.get("password") or ""

    db, err = _db_or_503()
    if err:
        return err

    user = db.users.find_one({"username_lower": username.lower()})
    # Identical response for unknown user and wrong password: never reveal
    # which usernames exist.
    if not user or not verify_password(password, user.get("password", "")):
        log_audit_event(username, "LOGIN_FAILED", "Invalid credentials",
                        request.remote_addr or "")
        return jsonify({"status": "error", "message": "Invalid username or password."}), 401

    if user.get("status") != "active":
        log_audit_event(str(user["_id"]), "LOGIN_BLOCKED", "Account not active",
                        request.remote_addr or "")
        return jsonify({"status": "error", "message": "This account is not active."}), 403

    role = user.get("role", "analyst")
    token = generate_token(str(user["_id"]), role)
    log_audit_event(str(user["_id"]), "LOGIN_SUCCESS", f"User '{user['username']}' logged in",
                    request.remote_addr or "")

    return jsonify({
        "status": "success",
        "token": token,
        "user": {"id": str(user["_id"]), "username": user["username"], "role": role},
    }), 200


@auth_bp.route("/me", methods=["GET"])
@token_required
def profile():
    """Return the caller's own identity, used by the frontend to restore session."""
    claims = current_user()
    db = get_db()
    username = None
    if db is not None:
        from bson import ObjectId
        try:
            user = db.users.find_one({"_id": ObjectId(claims["user_id"])}, {"username": 1})
            username = user["username"] if user else None
        except Exception:
            logger.warning("Could not resolve username for %s", claims.get("user_id"))

    return jsonify({
        "status": "success",
        "user": {
            "id": claims.get("user_id"),
            "role": claims.get("role"),
            "username": username,
            "expires_at": claims.get("exp"),
        },
    }), 200


@auth_bp.route("/audit-log", methods=["GET"])
@roles_required("admin", "commander")
def get_audit_log():
    """Security audit trail. Restricted: this is sensitive security telemetry."""
    db, err = _db_or_503()
    if err:
        return err

    limit, skip = parse_pagination(request.args)
    cursor = db.audit_logs.find().sort("timestamp", -1).skip(skip).limit(limit)
    logs = [serialize_doc(entry) for entry in cursor]

    return jsonify({
        "status": "success",
        "data": logs,
        "pagination": {
            "limit": limit,
            "skip": skip,
            "returned": len(logs),
            "total": db.audit_logs.estimated_document_count(),
        },
    }), 200
