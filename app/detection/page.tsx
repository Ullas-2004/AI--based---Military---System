"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { Crosshair, Upload, X, AlertTriangle, ScanLine } from "lucide-react";

import { api, ApiError } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import type { DetectionRecord } from "@/lib/types";
import { AuthRequired, ErrorState, PageHeader, Spinner } from "@/components/ui";

const ACCEPTED_TYPES = [
  "image/jpeg", "image/png", "image/bmp", "image/webp", "image/tiff",
];
const MAX_BYTES = 10 * 1024 * 1024;

/** Deterministic colour per class so the same object keeps its colour. */
const BOX_COLOURS = ["#00e5ff", "#ff3366", "#ffb800", "#00ff9d", "#8a5cff"];
function colourFor(label: string) {
  let hash = 0;
  for (let i = 0; i < label.length; i += 1) hash = (hash * 31 + label.charCodeAt(i)) | 0;
  return BOX_COLOURS[Math.abs(hash) % BOX_COLOURS.length];
}

export default function DetectionPage() {
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  const [file, setFile] = useState<File | null>(null);
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [imageSize, setImageSize] = useState<{ w: number; h: number } | null>(null);
  const [result, setResult] = useState<DetectionRecord | null>(null);
  const [isAnalysing, setAnalysing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isDragging, setDragging] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  // Object URLs are leaked memory until revoked.
  useEffect(() => {
    if (!previewUrl) return;
    return () => URL.revokeObjectURL(previewUrl);
  }, [previewUrl]);

  const selectFile = useCallback((candidate: File | undefined) => {
    setError(null);
    setResult(null);
    if (!candidate) return;

    // Mirror the server rules so the user gets instant feedback.
    if (!ACCEPTED_TYPES.includes(candidate.type)) {
      setError(`Unsupported file type "${candidate.type || "unknown"}". Use JPEG, PNG, BMP, WebP or TIFF.`);
      return;
    }
    if (candidate.size > MAX_BYTES) {
      setError(`File is ${(candidate.size / 1024 / 1024).toFixed(1)} MB. The limit is 10 MB.`);
      return;
    }

    setFile(candidate);
    setImageSize(null);
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return URL.createObjectURL(candidate);
    });
  }, []);

  const reset = useCallback(() => {
    setFile(null);
    setResult(null);
    setError(null);
    setImageSize(null);
    setPreviewUrl((old) => {
      if (old) URL.revokeObjectURL(old);
      return null;
    });
    if (inputRef.current) inputRef.current.value = "";
  }, []);

  const runAnalysis = useCallback(async () => {
    if (!file) return;
    setAnalysing(true);
    setError(null);
    try {
      const response = await api.threats.detect(file);
      setResult(response.data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Detection failed unexpectedly.");
    } finally {
      setAnalysing(false);
    }
  }, [file]);

  if (authLoading) return <Spinner label="Checking session" />;
  if (!isAuthenticated) return <AuthRequired />;

  return (
    <div className="space-y-6">
      <PageHeader
        eyebrow="Computer Vision"
        icon={Crosshair}
        title="Vision"
        accent="Engine"
        actions={
          file && (
            <button
              onClick={reset}
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-white/5 border border-white/15 text-gray-200 hover:bg-white/10 transition-colors"
            >
              <X className="w-4 h-4" aria-hidden="true" />
              Clear
            </button>
          )
        }
      />

      <div className="grid gap-6 lg:grid-cols-2">
        {/* --- Upload ------------------------------------------------------ */}
        <section className="glass-panel rounded-2xl p-6" aria-labelledby="upload-heading">
          <h2 id="upload-heading" className="text-lg font-bold text-white mb-1">
            Surveillance image
          </h2>
          <p className="text-sm text-gray-400 mb-5">
            JPEG, PNG, BMP, WebP or TIFF. Maximum 10 MB.
          </p>

          <input
            ref={inputRef}
            type="file"
            accept={ACCEPTED_TYPES.join(",")}
            className="sr-only"
            id="image-upload"
            onChange={(e) => selectFile(e.target.files?.[0])}
          />

          <label
            htmlFor="image-upload"
            onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
            onDragLeave={() => setDragging(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDragging(false);
              selectFile(e.dataTransfer.files?.[0]);
            }}
            className={`flex flex-col items-center justify-center gap-3 h-56 rounded-2xl border-2 border-dashed cursor-pointer transition-colors ${
              isDragging
                ? "border-aegis-accent bg-aegis-accent/10"
                : "border-white/20 hover:border-aegis-accent/60 hover:bg-white/5"
            }`}
          >
            <Upload className="w-9 h-9 text-aegis-accent" aria-hidden="true" />
            <span className="text-gray-200 font-medium">
              {file ? file.name : "Click to upload or drag an image here"}
            </span>
            {file && (
              <span className="text-xs text-aegis-muted">
                {(file.size / 1024).toFixed(0)} KB
              </span>
            )}
          </label>

          {error && (
            <p role="alert" className="mt-4 flex items-start gap-2 text-sm text-aegis-danger">
              <AlertTriangle className="w-4 h-4 mt-0.5 shrink-0" aria-hidden="true" />
              {error}
            </p>
          )}

          <button
            onClick={runAnalysis}
            disabled={!file || isAnalysing}
            className="mt-5 w-full inline-flex items-center justify-center gap-2 px-5 py-3.5 rounded-xl bg-gradient-to-r from-aegis-accent to-aegis-accent-secondary text-aegis-bg font-bold transition-opacity hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <ScanLine className={`w-5 h-5 ${isAnalysing ? "animate-pulse" : ""}`} aria-hidden="true" />
            {isAnalysing ? "Analysing..." : "Run analysis"}
          </button>
        </section>

        {/* --- Preview with overlay ---------------------------------------- */}
        <section className="glass-panel rounded-2xl p-6" aria-labelledby="preview-heading">
          <h2 id="preview-heading" className="text-lg font-bold text-white mb-5">
            Detection overlay
          </h2>

          {!previewUrl ? (
            <div className="h-56 flex items-center justify-center text-aegis-muted text-sm">
              Upload an image to see results.
            </div>
          ) : (
            <div className="relative inline-block max-w-full">
              {/* eslint-disable-next-line @next/next/no-img-element -- blob: URL
                  of a user-selected file; next/image cannot optimise it. */}
              <img
                src={previewUrl}
                alt={file ? `Preview of ${file.name}` : "Uploaded surveillance image"}
                className="max-w-full h-auto rounded-xl"
                onLoad={(e) =>
                  setImageSize({
                    w: e.currentTarget.naturalWidth,
                    h: e.currentTarget.naturalHeight,
                  })
                }
              />
              {result && imageSize && (
                <svg
                  viewBox={`0 0 ${imageSize.w} ${imageSize.h}`}
                  className="absolute inset-0 w-full h-full pointer-events-none"
                  aria-hidden="true"
                >
                  {result.detections.map((d, i) => {
                    const colour = colourFor(d.object);
                    return (
                      <g key={`${d.object}-${i}`}>
                        <rect
                          x={d.bbox.x1}
                          y={d.bbox.y1}
                          width={d.bbox.x2 - d.bbox.x1}
                          height={d.bbox.y2 - d.bbox.y1}
                          fill="none"
                          stroke={colour}
                          strokeWidth={Math.max(2, imageSize.w / 300)}
                        />
                        <text
                          x={d.bbox.x1 + 4}
                          y={Math.max(d.bbox.y1 - 6, 14)}
                          fill={colour}
                          fontSize={Math.max(14, imageSize.w / 45)}
                          fontWeight="bold"
                        >
                          {d.object} {d.confidence}%
                        </text>
                      </g>
                    );
                  })}
                </svg>
              )}
            </div>
          )}
        </section>
      </div>

      {/* --- Results ------------------------------------------------------- */}
      {isAnalysing && <Spinner label="Running inference" />}

      {result && !isAnalysing && (
        <section className="glass-panel rounded-2xl p-6" aria-labelledby="results-heading">
          <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
            <h2 id="results-heading" className="text-lg font-bold text-white">
              {result.total_objects} object{result.total_objects === 1 ? "" : "s"} detected
            </h2>
            <span className="text-xs text-aegis-muted font-mono">{result.model}</span>
          </div>

          {result.detections.length === 0 ? (
            <p className="text-gray-400 text-sm">
              No objects above the confidence threshold were found in this image.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <caption className="sr-only">Detected objects with confidence scores</caption>
                <thead className="text-xs uppercase tracking-wider text-aegis-muted border-b border-white/10">
                  <tr>
                    <th scope="col" className="py-3 pr-4">Threat class</th>
                    <th scope="col" className="py-3 pr-4">Source class</th>
                    <th scope="col" className="py-3 pr-4">Confidence</th>
                    <th scope="col" className="py-3">Bounding box</th>
                  </tr>
                </thead>
                <tbody>
                  {result.detections.map((d, i) => (
                    <tr key={`${d.object}-${i}`} className="border-b border-white/5">
                      <td className="py-3 pr-4">
                        <span
                          className="inline-flex items-center gap-2 font-semibold text-white"
                        >
                          <span
                            className="w-2.5 h-2.5 rounded-full"
                            style={{ backgroundColor: colourFor(d.object) }}
                            aria-hidden="true"
                          />
                          {d.object}
                        </span>
                      </td>
                      <td className="py-3 pr-4 text-aegis-muted font-mono text-xs">
                        {d.source_class}
                      </td>
                      <td className="py-3 pr-4 text-gray-200">{d.confidence}%</td>
                      <td className="py-3 text-aegis-muted font-mono text-xs">
                        {Math.round(d.bbox.x1)}, {Math.round(d.bbox.y1)} to{" "}
                        {Math.round(d.bbox.x2)}, {Math.round(d.bbox.y2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Unmapped classes are shown, not hidden. */}
          {result.unmapped_detections.length > 0 && (
            <div className="mt-5 p-4 rounded-xl bg-aegis-warning/10 border border-aegis-warning/30">
              <p className="text-sm font-semibold text-aegis-warning mb-1">
                {result.unmapped_detections.length} detection(s) had no military analogue
              </p>
              <p className="text-xs text-gray-300">
                {result.unmapped_detections
                  .map((u) => `${u.source_class} (${u.confidence}%)`)
                  .join(", ")}
                . These were excluded from threat scoring rather than defaulted to a class.
              </p>
            </div>
          )}

          <p className="mt-5 text-xs text-aegis-muted leading-relaxed">
            Classes are derived from COCO-trained YOLO weights and mapped onto a
            military taxonomy as a documented proxy. Confirm every detection
            before acting on it.
          </p>
        </section>
      )}

      {error && !isAnalysing && !result && file && (
        <ErrorState message={error} onRetry={runAnalysis} />
      )}
    </div>
  );
}
