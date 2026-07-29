"""Centralised configuration for the AegisAI backend.

This module is the single source of truth for every tunable setting. Nothing
else in the codebase should call ``os.getenv`` directly, so that defaults,
validation and production safety checks all live in one place.
"""
import os
import secrets
from dotenv import load_dotenv

# Load the .env that sits at the repository root (one level above api/).
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, default))
    except (TypeError, ValueError):
        return default


class Config:
    # --- Runtime -----------------------------------------------------------
    ENV = os.getenv("FLASK_ENV", "production").strip().lower()
    IS_PRODUCTION = ENV == "production"
    DEBUG = _env_bool("FLASK_DEBUG", default=not IS_PRODUCTION)
    HOST = os.getenv("HOST", "127.0.0.1")
    PORT = _env_int("PORT", 5332)

    # --- Security ----------------------------------------------------------
    # A generated fallback keeps development working without a .env, but it is
    # regenerated on every boot so tokens never survive a restart. That is a
    # deliberate nuisance: it makes a missing secret obvious instead of silently
    # shipping a well-known key.
    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY") or secrets.token_urlsafe(48)
    JWT_ALGORITHM = "HS256"
    TOKEN_EXPIRY_HOURS = _env_int("TOKEN_EXPIRY_HOURS", 12)
    BCRYPT_ROUNDS = _env_int("BCRYPT_ROUNDS", 12)

    # --- Rate limiting -----------------------------------------------------
    # Deliberately generous in development so test suites are not throttled;
    # tighten these in production via the environment.
    RATE_LIMIT_ENABLED = _env_bool("RATE_LIMIT_ENABLED", default=True)
    RATE_LIMIT_LOGIN = _env_int("RATE_LIMIT_LOGIN", 8)
    RATE_LIMIT_LOGIN_WINDOW = _env_int("RATE_LIMIT_LOGIN_WINDOW", 60)
    RATE_LIMIT_REGISTER = _env_int("RATE_LIMIT_REGISTER", 30)
    RATE_LIMIT_REGISTER_WINDOW = _env_int("RATE_LIMIT_REGISTER_WINDOW", 300)

    # Browsers are only allowed to call the API from these origins. In
    # development the Next.js dev server is the only legitimate caller; in
    # production this must be set explicitly.
    CORS_ORIGINS = [
        o.strip()
        for o in os.getenv(
            "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
        ).split(",")
        if o.strip()
    ]

    # --- Database ----------------------------------------------------------
    MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "aegis_ai_db")
    MONGO_TIMEOUT_MS = _env_int("MONGO_TIMEOUT_MS", 5000)

    # --- Uploads -----------------------------------------------------------
    # Uploaded frames land here only for the duration of inference; PDF reports
    # are rendered in memory and never touch disk.
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
    MAX_CONTENT_LENGTH = _env_int("MAX_UPLOAD_MB", 10) * 1024 * 1024
    ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "bmp", "webp", "tif", "tiff"}
    # Magic-number prefixes, checked so a .txt renamed to .jpg is still rejected.
    IMAGE_MAGIC_PREFIXES = (
        b"\xff\xd8\xff",              # JPEG
        b"\x89PNG\r\n\x1a\n",         # PNG
        b"BM",                        # BMP
        b"II*\x00",                   # TIFF little-endian
        b"MM\x00*",                   # TIFF big-endian
    )

    # --- Models ------------------------------------------------------------
    MODEL_DIR = os.path.join(BASE_DIR, "models")
    THREAT_MODEL_PATH = os.path.join(MODEL_DIR, "threat_model.json")
    QUANTILE_MODEL_PATH = os.path.join(MODEL_DIR, "quantile_model.json")
    MODEL_CARD_PATH = os.path.join(MODEL_DIR, "model_card.json")
    ENCODERS_PATH = os.path.join(MODEL_DIR, "encoders.json")
    YOLO_WEIGHTS_PATH = os.path.join(BASE_DIR, "yolov8n.pt")
    YOLO_CONFIDENCE_THRESHOLD = float(os.getenv("YOLO_CONFIDENCE_THRESHOLD", "0.4"))

    # --- LLM ---------------------------------------------------------------
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    @classmethod
    def validate(cls) -> list:
        """Return a list of fatal misconfigurations. Empty means safe to boot."""
        problems = []
        if cls.IS_PRODUCTION:
            if not cls.JWT_SECRET_KEY:
                problems.append("JWT_SECRET_KEY must be set in production.")
            elif len(cls.JWT_SECRET_KEY.encode()) < 32:
                problems.append(
                    "JWT_SECRET_KEY must be at least 32 bytes (RFC 7518 section 3.2)."
                )
            if cls.DEBUG:
                problems.append("FLASK_DEBUG must be off in production.")
            if "*" in cls.CORS_ORIGINS:
                problems.append("CORS_ORIGINS must not be '*' in production.")
        return problems


config = Config()
