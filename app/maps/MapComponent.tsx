"use client";
import { useMemo } from "react";
import { MapContainer, TileLayer, Marker, Popup, Circle } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";

import type { MapMarker } from "@/lib/types";

const SEVERITY_COLOURS: Record<string, string> = {
  CRITICAL: "#ff3366",
  HIGH: "#ffb800",
  MEDIUM: "#00e5ff",
  LOW: "#00ff9d",
  UNKNOWN: "#94a3b8",
};

const TYPE_COLOURS: Record<MapMarker["type"], string> = {
  Threat: "#ff3366",
  Patrol: "#00ff9d",
  Sensor: "#00e5ff",
};

/**
 * Icons are built from inline SVG rather than remote PNGs.
 *
 * The previous implementation loaded marker images from raw.githubusercontent.com
 * and cdnjs, so the map rendered without pins whenever those hosts were blocked
 * or the venue network was unreliable. A divIcon has no network dependency.
 */
function buildIcon(colour: string): L.DivIcon {
  const svg = `
    <svg xmlns="http://www.w3.org/2000/svg" width="26" height="38" viewBox="0 0 26 38">
      <path d="M13 0C5.8 0 0 5.8 0 13c0 9.4 13 25 13 25s13-15.6 13-25C26 5.8 20.2 0 13 0z"
            fill="${colour}" stroke="#05070d" stroke-width="2"/>
      <circle cx="13" cy="13" r="5" fill="#05070d"/>
    </svg>`;

  return L.divIcon({
    html: svg,
    className: "aegis-marker",       // no default leaflet background
    iconSize: [26, 38],
    iconAnchor: [13, 38],
    popupAnchor: [0, -34],
  });
}

interface MapComponentProps {
  markers: MapMarker[];
  centre: { lat: number; lng: number };
}

export default function MapComponent({ markers, centre }: MapComponentProps) {
  // Icons are pure functions of colour; build each one once.
  const icons = useMemo(() => {
    const cache = new Map<string, L.DivIcon>();
    for (const colour of [...Object.values(TYPE_COLOURS), ...Object.values(SEVERITY_COLOURS)]) {
      if (!cache.has(colour)) cache.set(colour, buildIcon(colour));
    }
    return cache;
  }, []);

  const iconFor = (marker: MapMarker) => {
    const colour = marker.type === "Threat"
      ? SEVERITY_COLOURS[marker.severity ?? "UNKNOWN"] ?? TYPE_COLOURS.Threat
      : TYPE_COLOURS[marker.type];
    return icons.get(colour) ?? buildIcon(colour);
  };

  return (
    <MapContainer
      center={[centre.lat, centre.lng]}
      zoom={11}
      style={{ height: "100%", width: "100%" }}
      zoomControl
      scrollWheelZoom={false}   /* avoid hijacking page scroll */
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors &copy; <a href="https://carto.com/">CARTO</a>'
        url="https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png"
      />

      {markers.map((marker) => (
        <Marker key={marker.id} position={[marker.lat, marker.lng]} icon={iconFor(marker)}>
          <Popup>
            <p style={{ margin: 0, fontWeight: 700 }}>{marker.label}</p>
            <p style={{ margin: "4px 0 0", fontSize: 12, opacity: 0.75 }}>
              {marker.type}
              {marker.severity ? ` | Severity: ${marker.severity}` : ""}
              {marker.status ? ` | Status: ${marker.status}` : ""}
            </p>
          </Popup>
        </Marker>
      ))}

      {markers
        .filter((m) => m.type === "Threat")
        .map((marker) => {
          const colour = SEVERITY_COLOURS[marker.severity ?? "UNKNOWN"];
          return (
            <Circle
              key={`radius-${marker.id}`}
              center={[marker.lat, marker.lng]}
              radius={2500}
              pathOptions={{
                color: colour,
                fillColor: colour,
                fillOpacity: 0.12,
                weight: 1,
              }}
            />
          );
        })}
    </MapContainer>
  );
}
