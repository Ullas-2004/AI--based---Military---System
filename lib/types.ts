/** Shared API response shapes, mirroring the Flask backend contracts. */

export type ThreatLevel = "LOW" | "MEDIUM" | "HIGH" | "CRITICAL" | "UNKNOWN";

export interface ApiEnvelope {
  status: "success" | "error";
  message?: string;
  field?: string;
}

export interface User {
  id: string;
  username: string | null;
  role: "analyst" | "commander" | "admin";
}

export interface LoginResponse extends ApiEnvelope {
  token: string;
  user: User;
}

export interface Detection {
  object: string;
  source_class: string;
  is_proxy_class: boolean;
  confidence: number;
  bbox: { x1: number; y1: number; x2: number; y2: number };
  detected_at: string;
}

export interface UnmappedDetection {
  source_class: string;
  confidence: number;
}

export type ReviewStatus = "confirmed" | "false_positive" | "pending_analyst_review";

export interface Review {
  status: ReviewStatus;
  note: string;
  reviewed_by: string;
  reviewed_at: string;
}

export interface ReviewMetrics {
  total: number;
  reviewed: number;
  pending: number;
  confirmed: number;
  false_positive: number;
  /** Null until at least one detection has been reviewed. */
  false_positive_rate: number | null;
  review_coverage: number;
}

export interface DetectionRecord {
  id?: string;
  original_filename: string;
  detections: Detection[];
  unmapped_detections: UnmappedDetection[];
  total_objects: number;
  model: string;
  created_at: string;
  status: ReviewStatus | string;
  review?: Review;
}

export interface ShapFactor {
  feature: string;
  label: string;
  value: string | number;
  contribution: number;
  direction: "increases" | "decreases";
  gerund: "raising" | "lowering";
}

export interface Explanation {
  baseline: number;
  factors: ShapFactor[];
  summary: string;
  method: string;
  raw_score: number;
  was_clamped: boolean;
}

export interface PredictionInterval {
  lower: number;
  median: number;
  upper: number;
  width: number;
  nominal_coverage: number;
  confidence_level: "high" | "moderate" | "low";
  /** True when the interval straddles a threat-band boundary. */
  spans_bands: boolean;
}

export interface Counterfactual {
  field: string;
  label: string;
  from: string | number;
  to: string | number;
  new_score: number;
  new_level: ThreatLevel;
  delta: number;
  summary: string;
}

export interface ModelCard {
  model_version: string;
  trained_at: string;
  algorithm: string;
  training_samples: number;
  holdout_samples: number;
  features: string[];
  metrics: { mae: number; rmse: number; r2: number; band_accuracy: number };
  uncertainty: {
    quantiles: number[];
    nominal_coverage: number;
    empirical_coverage: number;
    mean_interval_width: number;
  };
  feature_importance: Record<string, number>;
  confusion_matrix: Record<string, Record<string, number>>;
  training_data: string;
  limitations: string[];
}

export interface MlOutput {
  threat_score: number;
  threat_level: ThreatLevel;
  model_version: string;
  explanation?: Explanation;
  interval?: PredictionInterval;
}

export interface Telemetry {
  object: string;
  confidence: number;
  weather: string;
  terrain: string;
  time_of_day: string;
  distance_km: number;
}

export interface PredictionRecord {
  id?: string;
  telemetry: Telemetry;
  ml_output: MlOutput;
  created_at: string;
}

export interface Pagination {
  limit: number;
  skip: number;
  returned: number;
  total: number;
}

export interface Paginated<T> extends ApiEnvelope {
  data: T[];
  pagination: Pagination;
}

export interface Categories {
  DetectedObject: string[];
  Weather: string[];
  Terrain: string[];
  TimeOfDay: string[];
}

export interface Forecast {
  timeframe: string;
  available: boolean;
  reason?: string;
  sample_size?: number;
  mean_threat_score?: number;
  border_risk?: ThreatLevel;
  aerial_activity_share?: number;
  ground_activity_share?: number;
  peak_threat_score?: number;
}

export interface Analytics extends ApiEnvelope {
  available: boolean;
  reason?: string;
  window_hours?: number;
  trend: { time: string; threats: number; detections: number }[];
  object_breakdown: { name: string; value: number }[];
  sector_risk: { name: string; risk: number }[];
}

export interface MapMarker {
  id: string;
  type: "Threat" | "Patrol" | "Sensor";
  lat: number;
  lng: number;
  severity?: ThreatLevel;
  status?: string;
  label: string;
}

export interface MapMarkersResponse extends ApiEnvelope {
  centre: { lat: number; lng: number };
  is_demo: boolean;
  markers: MapMarker[];
}

export interface AuditLogEntry {
  id: string;
  user_id: string;
  action: string;
  details: string;
  ip_address: string;
  timestamp: string;
}

export interface HealthResponse extends ApiEnvelope {
  version: string;
  environment: string;
  subsystems: {
    database: boolean;
    threat_model: boolean;
    assistant: boolean;
  };
}
