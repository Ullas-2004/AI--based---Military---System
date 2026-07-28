# AegisAI User Manual

## 1. Introduction

AegisAI is an analyst workspace for reviewing surveillance imagery, scoring
threat telemetry, and producing intelligence reports.

> **Before you begin:** every score this system produces is *advisory decision
> support*. The threat model is trained on synthetic data and the object
> detector uses stock COCO weights mapped onto military classes. Confirm every
> finding before acting on it.

## 2. Starting the system

1. Ensure **MongoDB** is running (optional — without it the app still loads, but
   nothing is saved and login is unavailable).
2. Start the backend from the repository root:
   ```bash
   python api/app.py
   ```
3. Start the frontend in a second terminal:
   ```bash
   npm run dev
   ```
4. Open <http://localhost:3000>.

The status indicator in the top bar shows live backend and database health.

## 3. Accounts and roles

Go to **Security** in the sidebar.

- **Register** creates an `analyst` account. Usernames are 3–32 characters
  (letters, digits, `.`, `_`, `-`). Passwords must be at least 8 characters, no
  more than 72 bytes, and must mix letters with digits or symbols.
- **Login** issues a token valid for 12 hours. It is stored in the browser tab
  and cleared when the tab closes or you sign out.

| Role | Capabilities |
| --- | --- |
| `analyst` | All intelligence modules |
| `commander` | Analyst capabilities plus the security audit trail |
| `admin` | Full access |

Privileged roles are assigned out of band — self-service registration cannot
claim them. Promote a user directly in MongoDB:

```js
db.users.updateOne({ username: "yourname" }, { $set: { role: "commander" } })
```

## 4. Dashboard

Shows counts of critical predictions and detected objects, the mean threat
score, and a 24-hour outlook — all computed from stored records. If a panel says
"insufficient data", there genuinely is none yet; run some detections or
assessments first.

## 5. Vision Engine — analysing imagery

1. Open **Vision Engine**.
2. Drag an image onto the upload area, or click to browse. JPEG, PNG, BMP, WebP
   and TIFF are accepted, up to 10 MB.
3. Press **Run analysis**. Inference takes a few seconds on CPU.
4. Results appear as bounding boxes over your image plus a detail table.

Each row shows both the **threat class** (the military label) and the
**source class** (what the detector actually saw). If a detection has no
military analogue it is listed separately under a warning rather than being
counted as a low-threat object.

The uploaded image is deleted after analysis; only the findings are stored.

## 6. Predictive Intel — scoring telemetry

1. Open **Predictive Intel**.
2. Choose the object, terrain, weather and time of day; set confidence and
   distance with the sliders.
3. Press **Calculate threat score**.

The result is a 0–99 score and a band:

| Band | Score |
| --- | --- |
| LOW | below 40 |
| MEDIUM | 40 – 59 |
| HIGH | 60 – 79 |
| CRITICAL | 80 and above |

All six inputs affect the outcome. Low detection confidence discounts the score;
terrain interacts with object type (armour in open desert scores higher than the
same armour in mountains).

## 7. Threat Intelligence — history

Two tabs: **Vision detections** and **Threat assessments**. Both are newest
first and show the full telemetry behind each record, so any score can be
audited back to its inputs.

## 8. GIS Tactical Map

Threat, patrol and sensor markers with severity-coloured radii around threats.
When no georeferenced records exist yet, a clearly-labelled demonstration set is
shown. Map tiles require internet access.

## 9. Data Hub — analytics and reports

Charts aggregate the last 24 hours of activity. **Export situation report**
generates a PDF containing recent detections, recent assessments and a
methodology note.

## 10. AI Assistant

Ask questions about recorded telemetry, or press **Auto-generate report** for a
narrative summary.

If no `GROQ_API_KEY` is configured, the assistant runs in **offline mode**: it
returns the retrieved telemetry verbatim and labels itself clearly. It will not
invent analysis.

## 11. Settings

Live subsystem status (database, threat model, assistant), your session details,
and the system's known limitations.

## 12. Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| "Cannot reach the AegisAI backend" | Flask is not running. Start `python api/app.py`. |
| Status pill shows "database offline" | MongoDB is not running. Stateless pages still work. |
| "Authentication required" on every page | Not signed in, or the token expired. Sign in again from **Security**. |
| Audit trail shows "Insufficient privileges" | Your role is `analyst`. A `commander` or `admin` role is required. |
| Vision Engine returns 503 | YOLO weights failed to load. Check `api/yolov8n.pt` exists. |
| Threat model shows offline in Settings | Run `python api/train_threat_model.py`. |
| Map is blank | Tile CDN unreachable. Markers still render over the dark background. |
