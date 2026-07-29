/**
 * Single HTTP client for the AegisAI backend.
 *
 * Requests go to same-origin `/api/*`, which next.config.mjs rewrites to Flask.
 * That keeps the browser on one origin (no CORS preflight) and means the API
 * host is never baked into the client bundle.
 */
import type {
  Analytics, Categories, DetectionRecord, Forecast, HealthResponse,
  LoginResponse, MapMarkersResponse, Paginated, PredictionRecord,
  AuditLogEntry, Counterfactual, ModelCard, ReviewMetrics, ReviewStatus, User,
} from "./types";

const TOKEN_KEY = "aegis.token";
const USER_KEY = "aegis.user";

/** An API error carrying the HTTP status and the field that failed validation. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly field?: string,
  ) {
    super(message);
    this.name = "ApiError";
  }

  get isAuthError() {
    return this.status === 401 || this.status === 403;
  }
}

// --- Session storage -------------------------------------------------------
// sessionStorage rather than localStorage: the token dies with the tab, which
// limits exposure on shared analyst workstations.

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.sessionStorage.getItem(TOKEN_KEY);
}

export function getStoredUser(): User | null {
  if (typeof window === "undefined") return null;
  const raw = window.sessionStorage.getItem(USER_KEY);
  if (!raw) return null;
  try {
    return JSON.parse(raw) as User;
  } catch {
    return null;
  }
}

export function setSession(token: string, user: User): void {
  window.sessionStorage.setItem(TOKEN_KEY, token);
  window.sessionStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("aegis:session"));
}

export function clearSession(): void {
  window.sessionStorage.removeItem(TOKEN_KEY);
  window.sessionStorage.removeItem(USER_KEY);
  window.dispatchEvent(new Event("aegis:session"));
}

// --- Core request ----------------------------------------------------------

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** Skip attaching the Authorization header (login/register/health). */
  anonymous?: boolean;
  timeoutMs?: number;
}

const DEFAULT_TIMEOUT_MS = 30_000;

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { body, anonymous, timeoutMs = DEFAULT_TIMEOUT_MS, ...init } = options;

  const headers = new Headers(init.headers);
  const token = anonymous ? null : getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    // Let the browser set the multipart boundary.
    payload = body;
  } else if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }

  // AbortSignal.timeout would be simpler but is not available in every target
  // browser; an explicit controller is portable and lets us clear the timer.
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);

  let response: Response;
  try {
    response = await fetch(path, {
      ...init,
      headers,
      body: payload,
      signal: controller.signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new ApiError("The request timed out. Is the backend running?", 0);
    }
    throw new ApiError(
      "Cannot reach the AegisAI backend. Start it with: python api/app.py",
      0,
    );
  } finally {
    clearTimeout(timer);
  }

  if (response.status === 401 && !anonymous) {
    // The token is gone or expired; drop it so the UI shows the login prompt
    // instead of looping on failing requests.
    clearSession();
  }

  const contentType = response.headers.get("content-type") ?? "";
  if (!contentType.includes("application/json")) {
    if (!response.ok) {
      throw new ApiError(`Request failed (HTTP ${response.status}).`, response.status);
    }
    return response as unknown as T;
  }

  const json = await response.json();
  if (!response.ok) {
    throw new ApiError(
      json?.message ?? `Request failed (HTTP ${response.status}).`,
      response.status,
      json?.field,
    );
  }
  return json as T;
}

// --- Endpoints -------------------------------------------------------------

export const api = {
  health: () => request<HealthResponse>("/api/health", { anonymous: true }),

  auth: {
    register: (username: string, password: string) =>
      request<{ user: User }>("/api/auth/register", {
        method: "POST",
        body: { username, password, role: "analyst" },
        anonymous: true,
      }),

    login: (username: string, password: string) =>
      request<LoginResponse>("/api/auth/login", {
        method: "POST",
        body: { username, password },
        anonymous: true,
      }),

    me: () => request<{ user: User }>("/api/auth/me"),

    auditLog: (limit = 25, skip = 0) =>
      request<Paginated<AuditLogEntry>>(
        `/api/auth/audit-log?limit=${limit}&skip=${skip}`,
      ),
  },

  threats: {
    detect: (file: File) => {
      const form = new FormData();
      form.append("image", file);
      // Inference can take several seconds on CPU.
      return request<{ data: DetectionRecord; persisted: boolean }>(
        "/api/threats/detect",
        { method: "POST", body: form, timeoutMs: 120_000 },
      );
    },

    history: (limit = 25, skip = 0) =>
      request<Paginated<DetectionRecord>>(
        `/api/threats/history?limit=${limit}&skip=${skip}`,
      ),

    /** Record an analyst verdict on a detection. */
    review: (id: string, status: ReviewStatus, note = "") =>
      request<{ data: { id: string; review_status: ReviewStatus } }>(
        `/api/threats/${id}/review`,
        { method: "POST", body: { status, note } },
      ),

    reviewMetrics: () =>
      request<{ metrics: ReviewMetrics }>("/api/threats/review-metrics"),
  },

  predict: {
    categories: () =>
      request<{ categories: Categories }>("/api/predict/categories", { anonymous: true }),

    modelCard: () =>
      request<{ model_card: ModelCard }>("/api/predict/model-card", { anonymous: true }),

    counterfactuals: (telemetry: {
      object: string; confidence: number; weather: string;
      terrain: string; time_of_day: string; distance_km: number;
    }) =>
      request<{ counterfactuals: Counterfactual[]; is_robust: boolean }>(
        "/api/predict/counterfactuals",
        { method: "POST", body: telemetry },
      ),

    score: (telemetry: {
      object: string; confidence: number; weather: string;
      terrain: string; time_of_day: string; distance_km: number;
    }) =>
      request<{ data: PredictionRecord; persisted: boolean }>("/api/predict/score", {
        method: "POST",
        body: telemetry,
      }),

    history: (limit = 25, skip = 0) =>
      request<Paginated<PredictionRecord>>(
        `/api/predict/history?limit=${limit}&skip=${skip}`,
      ),

    forecast: () => request<{ forecast: Forecast }>("/api/predict/forecast"),
  },

  assistant: {
    status: () => request<{ online: boolean }>("/api/assistant/status", { anonymous: true }),

    ask: (question: string) =>
      request<{ answer: string; online: boolean; model: string | null }>(
        "/api/assistant/ask",
        { method: "POST", body: { question }, timeoutMs: 60_000 },
      ),

    report: () =>
      request<{ content: string; report_id: string | null; online: boolean }>(
        "/api/assistant/report",
        { method: "POST", timeoutMs: 60_000 },
      ),
  },

  data: {
    mapMarkers: () => request<MapMarkersResponse>("/api/data/map-markers"),
    analytics: () => request<Analytics>("/api/data/analytics"),

    /** Downloads a CSV export of the chosen dataset. */
    exportCsv: async (dataset: "predictions" | "detections"): Promise<Blob> => {
      const token = getToken();
      const response = await fetch(`/api/data/export.csv?dataset=${dataset}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        if (response.status === 401) clearSession();
        throw new ApiError(`Export failed (HTTP ${response.status}).`, response.status);
      }
      return response.blob();
    },

    /** Downloads the PDF, returning the blob so the caller controls the save. */
    downloadReport: async (): Promise<Blob> => {
      const token = getToken();
      const response = await fetch("/api/data/download-report", {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!response.ok) {
        if (response.status === 401) clearSession();
        let message = `Report generation failed (HTTP ${response.status}).`;
        try {
          message = (await response.json())?.message ?? message;
        } catch {
          /* non-JSON error body; keep the default message */
        }
        throw new ApiError(message, response.status);
      }
      return response.blob();
    },
  },
};
