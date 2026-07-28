# AegisAI API Reference

Base URL: `http://127.0.0.1:5332`
From the browser, call the same paths on the Next.js origin (`http://localhost:3000/api/...`); Next rewrites them to Flask, so there is no CORS preflight.

All responses are JSON with a top-level `status` of `"success"` or `"error"`.
Error bodies carry a human-readable `message`, and validation failures also
carry the offending `field`.

## Authentication

Protected endpoints require a bearer token:

```
Authorization: Bearer <jwt>
```

Tokens are HS256, expire after `TOKEN_EXPIRY_HOURS` (default 12) and carry
`user_id` and `role` claims. A missing or invalid token returns **401**; a valid
token with insufficient role returns **403**.

| Status | Meaning |
| --- | --- |
| 200 / 201 | Success |
| 401 | Missing, malformed or expired token |
| 403 | Authenticated but role not permitted |
| 404 / 405 | No such endpoint / method not allowed |
| 409 | Conflict (duplicate username) |
| 413 | Upload exceeds `MAX_UPLOAD_MB` |
| 422 | Input validation failed |
| 500 | Unexpected server error (details are logged, never returned) |
| 503 | A dependency (database, vision engine) is unavailable |

---

## System

### `GET /api/health` — public
Liveness plus subsystem readiness.

```json
{
  "status": "success",
  "version": "2.0.0",
  "environment": "development",
  "subsystems": { "database": true, "threat_model": true, "assistant": false }
}
```

---

## Authentication endpoints

### `POST /api/auth/register` — public
Creates an analyst account. Self-service registration cannot claim a privileged role.

Body: `{ "username": "analyst1", "password": "Str0ngPass!", "role": "analyst" }`

Rules: username 3–32 chars matching `[A-Za-z0-9._-]`; password ≥ 8 characters,
≤ 72 **bytes**, and must mix letters with digits or symbols.

Returns **201**, or **409** if the username is taken, **422** on validation failure.

### `POST /api/auth/login` — public
Body: `{ "username": "analyst1", "password": "Str0ngPass!" }`

Returns `{ "token": "...", "user": { "id", "username", "role" } }`.
Unknown usernames and wrong passwords return an identical **401** so account
existence cannot be probed.

### `GET /api/auth/me` — authenticated
Returns the caller's identity and token expiry. Used to restore a session.

### `GET /api/auth/audit-log` — **admin or commander only**
Paginated security audit trail, newest first.
Query: `?limit=50&skip=0` (limit clamped to 1–100).

---

## Vision engine

### `POST /api/threats/detect` — authenticated
`multipart/form-data` with an `image` field.

Accepts JPEG, PNG, BMP, WebP, TIFF. Validated by extension **and** magic number,
so a renamed text file is rejected with **422**. Files over `MAX_UPLOAD_MB`
return **413**. The uploaded frame is deleted after inference; only findings are
persisted.

```json
{
  "status": "success",
  "persisted": true,
  "data": {
    "id": "...",
    "original_filename": "patrol-01.jpg",
    "total_objects": 2,
    "model": "yolov8n (COCO proxy classes)",
    "detections": [
      {
        "object": "Soldier",
        "source_class": "person",
        "is_proxy_class": true,
        "confidence": 86.57,
        "bbox": { "x1": 48.5, "y1": 398.6, "x2": 245.3, "y2": 902.7 }
      }
    ],
    "unmapped_detections": [{ "source_class": "giraffe", "confidence": 71.2 }]
  }
}
```

`unmapped_detections` lists objects with no military analogue. They are reported
rather than silently coerced into a low-threat class.

Returns **503** if the YOLO weights cannot be loaded.

### `GET /api/threats/history` — authenticated
Paginated detection history. Query: `?limit=25&skip=0`.

---

## Predictive engine

### `GET /api/predict/categories` — public
The exact enum values the scorer accepts. Build UI inputs from this rather than
hard-coding a second copy.

### `POST /api/predict/score` — authenticated

```json
{
  "object": "Tank",        // must be one of /categories DetectedObject
  "confidence": 95,        // 0-100
  "weather": "Fog",
  "terrain": "Desert",
  "time_of_day": "Night",
  "distance_km": 2.0       // 0-500
}
```

Every field is validated. An unknown `object` returns **422** listing the valid
values — it is *not* mapped to a default class. Out-of-range numbers return
**422** rather than producing a score.

Response: `{ "threat_score": 91.88, "threat_level": "CRITICAL", "model_version": "xgboost-regressor-v2" }`

Bands: `LOW` < 40 ≤ `MEDIUM` < 60 ≤ `HIGH` < 80 ≤ `CRITICAL`.

### `GET /api/predict/history` — authenticated
Paginated scoring history.

### `GET /api/predict/forecast` — authenticated
Aggregate outlook computed from stored predictions. When there is no history it
returns `{ "available": false, "reason": "..." }` rather than inventing figures.

---

## Generative assistant

### `GET /api/assistant/status` — public
`{ "online": false }` when no `GROQ_API_KEY` is configured.

### `POST /api/assistant/ask` — authenticated
Body: `{ "question": "Summarise recent activity" }` (max 2000 chars).

Answers are grounded in the most recent database records. In offline mode the
response returns the retrieved telemetry verbatim and sets `online: false`; it
never fabricates threat scores.

### `POST /api/assistant/report` — authenticated
Generates and persists a narrative situational report. No body required.

---

## Data hub

### `GET /api/data/map-markers` — authenticated
Georeferenced markers plus the area-of-operations centre. `is_demo: true`
indicates the fallback demonstration set.

### `GET /api/data/analytics` — authenticated
24-hour aggregates backing the Data Hub charts: `trend`, `object_breakdown`,
`sector_risk`. Returns `available: false` when there is nothing to aggregate.

### `GET /api/data/download-report` — authenticated
Streams a generated PDF situation report (`application/pdf`). The file is
deleted from disk once the response closes.
