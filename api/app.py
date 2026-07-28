"""AegisAI backend application factory and entry point.

Run in development:  python api/app.py
Run in production:   gunicorn -w 4 -b 0.0.0.0:5332 "app:create_app()"
"""
import logging
import os
import sys

from flask import Flask, jsonify, request
from flask_cors import CORS
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge

# Allow "python api/app.py" to resolve the sibling packages.
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from config import config  # noqa: E402
from middleware.auth import AuthError  # noqa: E402
from middleware.validation import ValidationError  # noqa: E402

logger = logging.getLogger("aegisai")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.DEBUG if config.DEBUG else logging.INFO,
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
    )
    # These libraries are extremely chatty. pymongo in particular emits a
    # structured DEBUG record per heartbeat, which buries our own logs.
    for noisy in ("werkzeug", "ultralytics", "pymongo", "httpx", "PIL", "matplotlib"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def create_app() -> Flask:
    _configure_logging()

    problems = config.validate()
    if problems:
        for problem in problems:
            logger.critical("Configuration error: %s", problem)
        raise SystemExit(
            "Refusing to start with an unsafe production configuration. "
            "See the errors above and .env.example."
        )

    app = Flask(__name__)
    app.config["MAX_CONTENT_LENGTH"] = config.MAX_CONTENT_LENGTH
    app.config["JSON_SORT_KEYS"] = False
    app.config["PROPAGATE_EXCEPTIONS"] = False

    # Scoped to known frontend origins rather than "*", and only the headers
    # and methods that are actually used.
    CORS(
        app,
        resources={r"/api/*": {"origins": config.CORS_ORIGINS}},
        allow_headers=["Content-Type", "Authorization"],
        methods=["GET", "POST", "OPTIONS"],
        max_age=600,
    )

    _register_blueprints(app)
    _register_error_handlers(app)
    _register_security_headers(app)

    logger.info(
        "AegisAI backend initialised (env=%s, debug=%s, origins=%s)",
        config.ENV, config.DEBUG, ", ".join(config.CORS_ORIGINS),
    )
    return app


def _register_blueprints(app: Flask) -> None:
    from routes.threat_routes import threat_bp
    from routes.predictive_routes import predictive_bp
    from routes.assistant_routes import assistant_bp
    from routes.data_routes import data_bp
    from routes.auth_routes import auth_bp
    from routes.stream_routes import stream_bp

    app.register_blueprint(threat_bp, url_prefix="/api/threats")
    app.register_blueprint(predictive_bp, url_prefix="/api/predict")
    app.register_blueprint(assistant_bp, url_prefix="/api/assistant")
    app.register_blueprint(data_bp, url_prefix="/api/data")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(stream_bp, url_prefix="/api/stream")

    @app.route("/api/health", methods=["GET"])
    def health_check():
        """Liveness plus subsystem readiness, so the UI can show real status."""
        from database.mongodb import is_connected
        from services.ml_service import is_ready as ml_ready
        from services.llm_service import is_online

        subsystems = {
            "database": is_connected(),
            "threat_model": ml_ready(),
            "assistant": is_online(),
            # Deliberately not probed: loading YOLO costs seconds and would make
            # the health endpoint unusable as a liveness check.
        }
        return jsonify({
            "status": "success",
            "message": "AegisAI backend is running.",
            "version": "2.0.0",
            "environment": config.ENV,
            "subsystems": subsystems,
        }), 200


def _register_error_handlers(app: Flask) -> None:
    """Convert exceptions into consistent JSON. Internals never reach clients."""

    @app.errorhandler(ValidationError)
    def _handle_validation(exc: ValidationError):
        payload = {"status": "error", "message": str(exc)}
        if exc.field:
            payload["field"] = exc.field
        return jsonify(payload), 422

    @app.errorhandler(AuthError)
    def _handle_auth(exc: AuthError):
        return jsonify({"status": "error", "message": str(exc)}), 400

    @app.errorhandler(RequestEntityTooLarge)
    def _handle_too_large(_exc):
        limit_mb = config.MAX_CONTENT_LENGTH // (1024 * 1024)
        return jsonify({
            "status": "error",
            "message": f"Upload exceeds the {limit_mb} MB limit.",
        }), 413

    @app.errorhandler(404)
    def _handle_404(_exc):
        return jsonify({
            "status": "error",
            "message": f"No such endpoint: {request.method} {request.path}",
        }), 404

    @app.errorhandler(405)
    def _handle_405(_exc):
        return jsonify({
            "status": "error",
            "message": f"{request.method} is not allowed on {request.path}",
        }), 405

    @app.errorhandler(HTTPException)
    def _handle_http(exc: HTTPException):
        return jsonify({"status": "error", "message": exc.description}), exc.code

    @app.errorhandler(Exception)
    def _handle_unexpected(exc: Exception):
        # Full detail to the log, generic message to the caller: stack traces
        # and driver errors are an information-disclosure vector.
        logger.exception("Unhandled error on %s %s", request.method, request.path)
        return jsonify({
            "status": "error",
            "message": "An internal error occurred. The incident has been logged.",
        }), 500


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def _apply_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault("Cache-Control", "no-store")
        return response


if __name__ == "__main__":
    create_app().run(host=config.HOST, port=config.PORT, debug=config.DEBUG)
