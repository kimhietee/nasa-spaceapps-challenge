import { useEffect, useRef, useState } from "react";
import type { Map as LMap, LayerGroup } from "leaflet";
import type { MapView } from "./FireMap";
const API = import.meta.env["VITE_ARCHIVE_API"] ?? "";
interface Props {
  query: string;
  view: MapView;
  density: boolean;
  boundaries: boolean;
  onSelect: (id: string) => void;
}
export function ArchiveMap({ query, view, density, boundaries, onSelect }: Props) {
  const element = useRef<HTMLDivElement>(null),
    map = useRef<LMap | null>(null),
    layer = useRef<LayerGroup | null>(null),
    boundary = useRef<LayerGroup | null>(null),
    leaflet = useRef<typeof import("leaflet") | null>(null),
    callback = useRef(onSelect);
  callback.current = onSelect;
  const [ready, setReady] = useState(false),
    [viewport, setViewport] = useState(0),
    [status, setStatus] = useState("Loading all selected observations…"),
    [failed, setFailed] = useState(false);
  useEffect(() => {
    let cancelled = false;
    import("leaflet").then((mod) => {
      if (cancelled || !element.current || map.current) return;
      const L = mod;
      leaflet.current = L;
      const m = L.map(element.current, {
        preferCanvas: true,
        minZoom: 4,
        maxZoom: 16,
        zoomControl: false,
      }).fitBounds([
        [-11, 95],
        [6, 141],
      ]);
      map.current = m;
      layer.current = L.layerGroup().addTo(m);
      boundary.current = L.layerGroup().addTo(m);
      L.control.zoom({ position: "topright" }).addTo(m);
      const base = "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas";
      L.tileLayer(base + "/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
        maxNativeZoom: 16,
        attribution:
          "Basemap © Esri, HERE, Garmin, OpenStreetMap contributors · NASA FIRMS real archive",
      }).addTo(m);
      L.tileLayer(base + "/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}", {
        maxNativeZoom: 16,
      }).addTo(m);
      m.on("moveend", () => setViewport((v) => v + 1));
      setReady(true);
    });
    return () => {
      cancelled = true;
      map.current?.remove();
      map.current = null;
    };
  }, []);
  useEffect(() => {
    const m = map.current,
      L = leaflet.current,
      g = layer.current;
    if (!ready || !m || !L || !g) return;
    const abort = new AbortController();
    setFailed(false);
    setStatus("Loading all selected observations…");
    const b = m.getBounds();
    const q = new URLSearchParams(query);
    q.set("view", view);
    q.set("zoom", String(Math.round(m.getZoom())));
    for (const [k, n] of Object.entries({
      west: Math.max(-180, b.getWest()),
      east: Math.min(180, b.getEast()),
      south: Math.max(-90, b.getSouth()),
      north: Math.min(90, b.getNorth()),
    }))
      q.set(k, String(n));
    fetch(API + "/api/archive/map?" + q, { signal: abort.signal })
      .then(async (r) => {
        if (!r.ok) throw Error("Map data unavailable");
        return r.json();
      })
      .then((result) => {
        if (abort.signal.aborted) return;
        g.clearLayers();
        const css = (key: string) =>
          getComputedStyle(document.documentElement)
            .getPropertyValue("--" + key)
            .trim();
        const colors = [css("matched"), css("possible"), css("modis"), css("viirs")];
        for (const point of result.clusters) {
          const values =
            view === "modis"
              ? [0, 0, point.count, 0]
              : view === "viirs"
                ? [0, 0, 0, point.count]
                : [point.matched, point.possible, point.modis_only, point.viirs_only];
          const dominant = values.indexOf(Math.max(...values));
          const color = colors[dominant] ?? colors[2];
          const radius = Math.min(31, 5 + Math.log2(point.count + 1) * 2);
          if (density) {
            for (const [factor, opacity] of [
              [2.8, 0.035],
              [2.1, 0.07],
              [1.5, 0.12],
              [1, 0.2],
            ])
              L.circleMarker([point.lat, point.lon], {
                radius: radius * factor!,
                stroke: false,
                fillColor: color,
                fillOpacity: opacity!,
                interactive: false,
              }).addTo(g);
          }
          let end = 0;
          const gradient = values
            .map((n: number, i: number) => {
              const start = end;
              end += (n / point.count) * 100;
              return `${colors[i]} ${start}% ${end}%`;
            })
            .join(",");
          const isSingle = point.count === 1;
          const outlined =
            view === "harmonized" && (point.modis_only === 1 || point.viirs_only === 1) && isSingle;
          const size = isSingle ? 13 : Math.min(58, 25 + Math.log2(point.count) * 2);
          const icon = L.divIcon({
            className: "archive-map-marker",
            html: `<div style="width:${size}px;height:${size}px;position:relative;border-radius:50%;display:grid;place-items:center;background:${outlined ? "transparent" : isSingle ? color : `conic-gradient(${gradient})`};border:2px solid ${color};box-shadow:0 0 12px 5px color-mix(in oklab,${color} 35%,transparent)">${isSingle ? "" : `<span style="display:grid;place-items:center;border-radius:50%;width:calc(100% - 5px);height:calc(100% - 5px);background:var(--map-surface);color:var(--foreground);font:11px var(--font-mono)">${point.count.toLocaleString()}</span>`}</div>`,
            iconSize: [size, size],
            iconAnchor: [size / 2, size / 2],
          });
          if (point.anomaly_count > 0)
            L.circleMarker([point.lat, point.lon], {
              radius: size / 2 + 6,
              color: css("anomaly"),
              weight: 1.5,
              dashArray: "3 3",
              fill: false,
              interactive: false,
            }).addTo(g);
          L.marker([point.lat, point.lon], {
            icon,
            keyboard: true,
            title: isSingle
              ? "Inspect observation"
              : `${point.count.toLocaleString()} observations; zoom to expand`,
          })
            .bindTooltip(
              `${point.count.toLocaleString()} ${view === "harmonized" ? "activity units" : "source detections"}<br>MODIS ${point.modis.toLocaleString()} · VIIRS ${point.viirs.toLocaleString()}<br>${isSingle ? "Click for source details" : "Click to zoom; all records included"}`,
              { className: "fw-tip" },
            )
            .on("click", () => {
              if (isSingle) callback.current(point.id);
              else if (m.getZoom() < 16)
                m.setView([point.lat, point.lon], Math.min(16, m.getZoom() + 2));
              else callback.current(point.id);
            })
            .addTo(g);
        }
        setStatus(
          `${result.represented.toLocaleString()} ${view === "harmonized" ? "activity units" : "detections"} in view · ${result.total.toLocaleString()} across the full selection · all included, no paging${density ? " · density glow reflects cluster counts" : ""}`,
        );
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setFailed(true);
          setStatus(e.message);
        }
      });
    return () => abort.abort();
  }, [ready, query, view, density, viewport]);
  useEffect(() => {
    const L = leaflet.current,
      g = boundary.current;
    if (!ready || !L || !g) return;
    g.clearLayers();
    if (!boundaries) return;
    const abort = new AbortController();
    fetch(API + "/api/archive/boundaries", { signal: abort.signal })
      .then((r) => r.json())
      .then((geo) => {
        if (!abort.signal.aborted)
          L.geoJSON(geo, {
            style: { color: "#8ed3b2", weight: 1, opacity: 0.5, fillOpacity: 0 },
            interactive: false,
          }).addTo(g);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setFailed(true);
          setStatus("Province boundaries unavailable");
        }
      });
    return () => abort.abort();
  }, [ready, boundaries]);
  return (
    <>
      <div
        ref={element}
        className="fw-map h-full w-full"
        role="application"
        aria-label="Indonesia map of all selected archive records"
      />
      <div
        role={failed ? "alert" : "status"}
        className="dark absolute bottom-0 left-0 z-[550] w-full bg-background/90 px-3 py-1 text-[10px] text-foreground"
      >
        {status}
      </div>
    </>
  );
}
