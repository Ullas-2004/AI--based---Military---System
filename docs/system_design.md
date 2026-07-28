# AegisAI System Design

## Navigation

```
/                        Landing page (module overview, honest caveats)
├── /dashboard           Live KPIs, recent scores, 24h outlook
├── /detection           Vision Engine: upload, inference, bounding-box overlay
├── /history             Detection and assessment history (tabbed)
├── /predictive          Threat scoring console
├── /maps                GIS tactical map
├── /data                Analytics charts and PDF export
├── /assistant           Generative AI chat
├── /security            Login, registration, role-gated audit trail
└── /settings            Subsystem health, session, known limitations
```

Every route above resolves. The sidebar contains no dead links.

## Data model

### `users`
```js
{
  _id, username, username_lower,   // lower-cased copy backs a case-insensitive
  password,                        //   unique index and login lookup
  role: "analyst" | "commander" | "admin",
  status: "active",
  created_at
}
```

### `vision_detections`
```js
{
  _id, original_filename,
  detections: [{
    object,           // canonical threat class
    source_class,     // what the detector actually emitted
    is_proxy_class,   // true while using COCO weights
    confidence, bbox: { x1, y1, x2, y2 }, detected_at
  }],
  unmapped_detections: [{ source_class, confidence }],
  total_objects, model, uploaded_by, created_at, status
}
```

Storing `source_class` alongside `object` is deliberate: it makes every
classification auditable back to the raw model output.

### `threat_predictions`
```js
{
  _id,
  telemetry: { object, confidence, weather, terrain, time_of_day, distance_km },
  ml_output: { threat_score, threat_level, model_version },
  scored_by, created_at
}
```

The full input is persisted with the output, so any score can be reproduced and
challenged.

### `audit_logs`
```js
{ _id, user_id, action, details, ip_address, timestamp }
```

Actions: `USER_REGISTERED`, `LOGIN_SUCCESS`, `LOGIN_FAILED`, `LOGIN_BLOCKED`,
`AUTHZ_DENIED`, `VISION_DETECT`, `ASSISTANT_QUERY`, `REPORT_GENERATED`,
`REPORT_EXPORTED`.

### `intelligence_reports`
```js
{ _id, report, online, model, generated_by, created_at, status }
```

## Workflows

### Authentication
```
Register ──> validate username/password ──> bcrypt hash ──> insert
                                                              │
                                              unique index catches duplicates
                                                              │
Login ──> lookup by username_lower ──> verify ──> issue JWT ──> audit
             │
             └─ unknown user and wrong password return an identical 401
```

### Detection to assessment
```
Upload image
   └─> validate (extension + magic number + size)
       └─> YOLO inference
           └─> map COCO class to threat class
               ├─ mapped   ──> persist detection
               └─ unmapped ──> report to analyst, exclude from scoring
                                   │
Analyst supplies telemetry ────────┘
   └─> validate all six fields
       └─> XGBoost score ──> band ──> persist with inputs
                                        └─> feeds dashboard, analytics,
                                            forecast, PDF and assistant context
```

## UI state contract

Every data-driven view handles four states explicitly. This is enforced by the
shared primitives in `components/ui.tsx`:

| State | Component | Behaviour |
| --- | --- | --- |
| Loading | `<Spinner>` | `role="status"`, `aria-live="polite"` |
| Error | `<ErrorState>` | `role="alert"`, retry action |
| Empty | `<EmptyState>` | Says *why* it is empty and what to do |
| Unauthenticated | `<AuthRequired>` | Explains and links to sign-in |

Nothing renders placeholder numbers when data is unavailable. A panel with no
data says so.

## Responsive design

| Breakpoint | Layout |
| --- | --- |
| `< 1024px` | Sidebar is an off-canvas drawer with a scrim; Escape closes it, body scroll locks, navigation dismisses it |
| `>= 1024px` | Sidebar is a fixed 16rem rail; content offset by `lg:pl-64` |

Grids collapse `4 -> 2 -> 1` columns. Tables scroll horizontally inside their
own container so the page body never scrolls sideways.

## Accessibility

- Skip link as the first tab stop, bypassing the sidebar.
- Visible `:focus-visible` ring on every interactive element.
- Semantic tables with `<caption>` and `scope` attributes.
- `role="tablist"` / `aria-selected` on tab groups; `aria-current="page"` on the
  active nav item.
- Chat log is `role="log"` with `aria-live="polite"`.
- Decorative icons are `aria-hidden`; icon-only buttons carry `aria-label`.
- `prefers-reduced-motion` disables animation and the background glows.
