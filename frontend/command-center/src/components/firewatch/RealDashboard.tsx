import { ArchiveMap } from "./ArchiveMap";
import { ArchiveCalendar } from "./ArchiveCalendar";
import { ActivityOverview, SensorHarmonization, SituationShift } from "./ArchiveVisuals";
import { useEffect, useMemo, useState } from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import type { MapView } from "./FireMap";
import { I18nProvider, useT, type Lang } from "@/lib/firewatch/i18n";
const API = import.meta.env["VITE_ARCHIVE_API"] ?? "";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
async function request(path: string, signal?: AbortSignal) {
  const r = await fetch(API + path, signal ? { signal } : {});
  if (!r.ok) {
    const body = await r.json().catch(() => ({}));
    throw Error(
      typeof body.detail === "string"
        ? body.detail
        : r.status < 500
          ? `Check filter values (${r.status}).`
          : `Archive request failed (${r.status}). Start the Python archive API and import the files.`,
    );
  }
  return r.json();
}
const fmt = (v: number | null | undefined) =>
  v == null ? "—" : v.toLocaleString(undefined, { maximumFractionDigits: 1 });
const palette = {
  MODIS: "var(--modis)",
  VIIRS: "var(--viirs)",
  matched: "var(--matched)",
  possible: "var(--possible)",
};
export function RealDashboard() {
  const [lang, setLang] = useState<Lang>("en");
  return (
    <I18nProvider lang={lang}>
      <ArchiveDashboard lang={lang} setLang={setLang} />
    </I18nProvider>
  );
}
function ArchiveDashboard({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  const t = useT();
  const [meta, setMeta] = useState<any>(null),
    [history, setHistory] = useState<any[]>([]),
    [data, setData] = useState<any>(null),
    [anomalies, setAnomalies] = useState<any>(null),
    [forecast, setForecast] = useState<any>(null),
    [evidence, setEvidence] = useState<any>(null),
    [sensitivity, setSensitivity] = useState<any>(null);
  const [startDate, setStartDate] = useState(""),
    [endDate, setEndDate] = useState(""),
    [year, setYear] = useState(0),
    [month, setMonth] = useState(""),
    [region, setRegion] = useState(""),
    [daynight, setDaynight] = useState(""),
    [view, setView] = useState<MapView>("harmonized"),
    [density, setDensity] = useState(false),
    [boundaries, setBoundaries] = useState(false),
    [technical, setTechnical] = useState(false),
    [selected, setSelected] = useState<any>(null),
    [error, setError] = useState(""),
    [loading, setLoading] = useState(true),
    [light, setLight] = useState(false);
  const analysisYear = year || (startDate ? Number(startDate.slice(0, 4)) : 2025);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", !light);
  }, [light]);
  useEffect(() => {
    Promise.all([
      request("/api/archive/meta"),
      request("/api/archive/history"),
      request("/api/archive/forecast"),
    ])
      .then(([m, h, f]) => {
        setMeta(m);
        setHistory(h);
        setForecast(f);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    Promise.all([request("/api/archive/candidates?limit=30"), request("/api/archive/sensitivity")])
      .then(([p, s]) => {
        setEvidence(p);
        setSensitivity(s);
      })
      .catch((e) => setError(e.message));
  }, []);
  useEffect(() => {
    const abort = new AbortController();
    setLoading(true);
    setData(null);
    setError("");
    setSelected(null);
    const q = new URLSearchParams();
    if (year && !startDate && !endDate) q.set("year", String(year));
    if (month && !startDate && !endDate) q.set("month", month);
    if (region) q.set("region", region);
    if (daynight) q.set("daynight", daynight);
    if (startDate) q.set("start_date", startDate);
    if (endDate) q.set("end_date", endDate);
    request("/api/archive/dashboard?" + q, abort.signal)
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch((e) => {
        if (e.name !== "AbortError") {
          setError(e.message);
          setLoading(false);
        }
      });
    return () => abort.abort();
  }, [year, month, region, daynight, startDate, endDate]);
  useEffect(() => {
    const abort = new AbortController();
    setAnomalies(null);
    request("/api/archive/anomalies?year=" + analysisYear, abort.signal)
      .then(setAnomalies)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, [analysisYear]);
  const monthly = useMemo(
    () =>
      MONTHS.map((label, i) => ({
        label,
        ...(data?.monthly.find((r: any) => r.period === i + 1) ?? {
          activity: null,
          modis: null,
          viirs: null,
        }),
      })),
    [data],
  );
  const mapQuery = useMemo(() => {
    const q = new URLSearchParams();
    if (year && !startDate && !endDate) q.set("year", String(year));
    if (month && !startDate && !endDate) q.set("month", month);
    if (region) q.set("region", region);
    if (daynight) q.set("daynight", daynight);
    if (startDate) q.set("start_date", startDate);
    if (endDate) q.set("end_date", endDate);
    return q.toString();
  }, [year, month, region, daynight, startDate, endDate]);
  const summary = data?.summary;
  function filter(action: () => void) {
    action();
  }
  function exportData() {
    if (!data) return;
    const blob = new Blob(
      [
        JSON.stringify(
          {
            scope: data.scope,
            summary: data.summary,
            monthly: data.monthly,
            daily: data.daily,
            coverage: data.coverage,
            config: meta?.config,
          },
          null,
          2,
        ),
      ],
      { type: "application/json" },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `firewatch-${year}-selected-analysis.json`;
    a.click();
    URL.revokeObjectURL(url);
  }
  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-[900] border-b border-border bg-background/95 backdrop-blur">
        <div className="mx-auto flex max-w-[1360px] flex-wrap items-center justify-between gap-4 px-6 py-4">
          <div>
            <b className="font-mono text-lg tracking-[.2em]">FIREWATCH</b>
            <div className="text-[10px] tracking-[.2em] text-muted-foreground">
              EARTH OBSERVATION SYSTEM
            </div>
          </div>
          <span className="rounded border border-primary/40 px-3 py-1 text-xs text-primary">
            NASA FIRMS · real archive 2022–2025
          </span>
          <div className="flex gap-2">
            <button className="archive-button" onClick={() => setTechnical(!technical)}>
              {technical ? t("responder") : t("public")}
            </button>
            <button className="archive-button" onClick={() => setLang(lang === "en" ? "id" : "en")}>
              {lang.toUpperCase()}
            </button>
            <button className="archive-button" onClick={() => setLight(!light)}>
              {light ? "Dark" : "Light"}
            </button>
            <button className="archive-button" onClick={exportData}>
              Export analysis
            </button>
          </div>
        </div>
        <nav className="mx-auto flex max-w-[1360px] gap-5 overflow-auto px-6 pb-3 text-xs text-muted-foreground">
          {[
            ["map", t("nav_map")],
            ["overview", t("nav_overview")],
            ["calendar", t("nav_calendar")],
            ["sensors", t("nav_sensors")],
            ["history", t("nav_history")],
            ["anomalies", t("nav_anomalies")],
            ["prediction", t("nav_prediction")],
            ["methodology", t("nav_method")],
          ].map(([id, label]) => (
            <a href={"#" + id} key={id}>
              {label}
            </a>
          ))}
        </nav>
      </header>
      <main className="mx-auto max-w-[1360px] space-y-10 px-4 py-7 sm:px-6">
        <section id="map" className="scroll-mt-32">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <div className="eyebrow">HISTORICAL ARCHIVE · {year || "2022–2025"}</div>
              <h1 className="mt-2 text-3xl">{t("title")}</h1>
              <p className="mt-2 text-sm text-muted-foreground">
                Real observations. Original records preserved. Candidate associations are not
                confirmed fires.
              </p>
            </div>
            <div className="text-right text-xs text-muted-foreground">
              {meta ? `${fmt(meta.records)} imported source records` : "Connecting to SQLite…"}
              <br />
              Processed: {meta?.processed_at?.slice(0, 19)} UTC
            </div>
          </div>
          <div className="panel mb-3 flex flex-wrap items-center gap-3 p-3">
            <label>
              {t("year")}{" "}
              <select
                aria-label="Archive year"
                value={year}
                onChange={(e) =>
                  filter(() => {
                    setYear(+e.target.value);
                    setStartDate("");
                    setEndDate("");
                  })
                }
              >
                <option value={0}>All years (2022–2025)</option>
                {[2022, 2023, 2024, 2025].map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
            </label>
            <label>
              {t("month")}{" "}
              <select
                aria-label="Archive month"
                value={month}
                onChange={(e) =>
                  filter(() => {
                    setMonth(e.target.value);
                    setStartDate("");
                    setEndDate("");
                  })
                }
              >
                <option value="">All months</option>
                {MONTHS.map((m, i) => (
                  <option value={i + 1} key={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            <label>
              Region{" "}
              <select
                aria-label="Archive region"
                value={region}
                onChange={(e) => filter(() => setRegion(e.target.value))}
              >
                <option value="">All regions</option>
                {meta?.regions.map((r: string) => (
                  <option key={r}>{r}</option>
                ))}
              </select>
            </label>
            <label>
              Day/night{" "}
              <select
                aria-label="Day or night"
                value={daynight}
                onChange={(e) => filter(() => setDaynight(e.target.value))}
              >
                <option value="">Day + night</option>
                <option value="D">Day</option>
                <option value="N">Night</option>
              </select>
            </label>
            <label>
              From{" "}
              <input
                className="archive-button"
                aria-label="Start date"
                type="date"
                value={startDate}
                onChange={(e) =>
                  filter(() => {
                    setStartDate(e.target.value);
                    setYear(0);
                    setMonth("");
                  })
                }
              />
            </label>
            <label>
              To{" "}
              <input
                className="archive-button"
                aria-label="End date"
                type="date"
                value={endDate}
                onChange={(e) =>
                  filter(() => {
                    setEndDate(e.target.value);
                    setYear(0);
                    setMonth("");
                  })
                }
              />
            </label>
            <button
              className="archive-button"
              onClick={() => {
                setStartDate("");
                setEndDate("");
                setYear(0);
                setMonth("");
                setRegion("");
                setDaynight("");
              }}
            >
              Reset filters
            </button>
          </div>
          <p className="mb-3 rounded border border-border bg-notice p-3 text-xs text-notice-foreground">
            Historical mode. Live feed is not configured. Coverage is unknown; dates with detections
            are not proof of complete satellite coverage.
          </p>
          {error && (
            <div role="alert" className="mb-3 border border-destructive p-4 text-destructive">
              {error}
            </div>
          )}
          <div className="panel relative h-[620px] overflow-hidden bg-map-surface">
            <div className="dark absolute left-3 top-3 z-[500] flex flex-wrap gap-2">
              {(["harmonized", "modis", "viirs"] as MapView[]).map((v) => (
                <button
                  className={
                    "archive-button " + (view === v ? "!bg-primary !text-primary-foreground" : "")
                  }
                  onClick={() => setView(v)}
                  key={v}
                >
                  {v === "harmonized" ? "Harmonized" : v.toUpperCase()}
                </button>
              ))}
              <button className="archive-button" onClick={() => setDensity(!density)}>
                {density ? "Glow density" : "Point detections"}
              </button>
              <button className="archive-button" onClick={() => setBoundaries(!boundaries)}>
                {boundaries ? "Hide boundaries" : "Province boundaries"}
              </button>
            </div>
            <ArchiveMap
              query={mapQuery}
              view={view}
              density={density}
              boundaries={boundaries}
              onSelect={async (id) => {
                try {
                  setSelected(await request("/api/archive/observation/" + encodeURIComponent(id)));
                } catch (e) {
                  setError(String(e));
                }
              }}
            />
            <div className="dark absolute bottom-8 left-3 z-[500] rounded-lg border border-foreground/70 bg-background/90 p-4 text-xs shadow-xl">
              <div className="mb-3 text-[10px] tracking-widest text-muted-foreground">
                SENSOR IDENTITY
              </div>
              <div className="flex gap-6">
                <span>
                  <i className="legend-dot bg-modis" /> MODIS
                </span>
                <span>
                  <i className="legend-dot bg-viirs" /> VIIRS
                </span>
              </div>
              <div className="mb-2 mt-4 text-[10px] tracking-widest text-muted-foreground">
                MATCH STATUS
              </div>
              <div className="grid grid-cols-2 gap-x-5 gap-y-2">
                <span>
                  <i className="legend-dot bg-matched" /> Matched
                </span>
                <span>
                  <i className="legend-dot bg-possible" /> Possible
                </span>
                <span>
                  <i className="legend-dot border-2 border-modis" /> MODIS-only
                </span>
                <span>
                  <i className="legend-dot border-2 border-viirs" /> VIIRS-only
                </span>
              </div>
              <div className="mt-3">
                <i className="legend-dot border border-dashed border-anomaly" /> Anomaly region
                (separate flag)
              </div>
            </div>
            {loading && (
              <div
                role="status"
                className="absolute right-3 top-16 z-[600] rounded bg-card p-3 text-xs"
              >
                Loading real observations…
              </div>
            )}
            {selected && (
              <div
                role="dialog"
                aria-label="Observation details"
                className="dark absolute right-3 top-16 z-[700] max-h-[460px] w-[310px] overflow-auto rounded border border-border bg-card p-4 text-sm shadow-xl"
              >
                <button
                  aria-label="Close observation"
                  className="float-right"
                  onClick={() => setSelected(null)}
                >
                  ✕
                </button>
                <b>
                  {selected.sensor} · {selected.status}
                </b>
                <p className="mt-3">
                  {selected.date} {selected.timeUtc} UTC
                </p>
                <p>
                  {selected.lat.toFixed(5)}, {selected.lon.toFixed(5)}
                </p>
                <p>{selected.province}</p>
                <p>
                  Confidence: {selected.confidence} (
                  {selected.sensor === "MODIS" ? "0–100" : "l/n/h"})
                </p>
                <p>FRP: {selected.frp ?? "unavailable"} MW</p>
                <p>
                  {selected.satellite} · {selected.product}
                </p>
                <p className="mt-2 text-xs text-muted-foreground">
                  {selected.file?.filename} · row {selected.source_row}
                </p>
                <p className="mt-2">{selected.candidates?.length} candidate links</p>
                {selected.candidates?.map((c: any) => (
                  <div
                    className="mt-2 border-t border-border pt-2 text-xs"
                    key={c.modis_id + c.viirs_id}
                  >
                    {c.label} · score {c.score.toFixed(3)}
                    <br />
                    {c.distance_km.toFixed(3)} km · {c.dt_min.toFixed(1)} min
                    <br />
                    {c.assigned ? "Assigned" : "Alternative retained"}
                  </div>
                ))}
                {technical && (
                  <details className="mt-3">
                    <summary>Original record and provenance</summary>
                    <pre className="overflow-auto text-[10px]">
                      {JSON.stringify(selected, null, 2)}
                    </pre>
                  </details>
                )}
              </div>
            )}
          </div>
          <p className="mt-2 text-xs text-muted-foreground">
            All selected records are included. Clusters expand as you zoom; no map pages or
            sampling. In Harmonized view each group appears once. Date ranges replace year/month
            filters.
          </p>
        </section>
        <section id="overview" className="scroll-mt-32">
          <div className="eyebrow">OPERATIONAL OVERVIEW</div>
          <h2 className="my-3 text-2xl">{t("nav_overview")} · selected period</h2>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            {[
              ["Source detections", summary?.total, ""],
              ["MODIS", summary?.modis, "text-modis"],
              ["VIIRS S-NPP", summary?.viirs, "text-viirs"],
              ["Matched groups", summary?.matched, "text-matched"],
              ["Possible groups", summary?.possible, "text-possible"],
              ["MODIS-only", summary?.modis_only, "text-modis"],
              ["VIIRS-only", summary?.viirs_only, "text-viirs"],
              ["Activity groups + unmatched", summary?.activity, ""],
            ].map(([label, value, color]) => (
              <div className="panel p-5" key={String(label)}>
                <div className="text-xs text-muted-foreground">{label}</div>
                <div className={"mt-3 font-mono text-2xl " + color}>{fmt(value as number)}</div>
              </div>
            ))}
          </div>
        </section>
        <ActivityOverview
          monthly={monthly}
          anomalies={{ ...anomalies, year: analysisYear }}
          label={
            startDate || endDate
              ? `${startDate || "2022-01-01"} to ${endDate || "2025-12-31"}`
              : year
                ? String(year)
                : "2022–2025 cumulative selected activity"
          }
        />
        <SensorHarmonization summary={summary} />
        <section id="source-metrics" className="panel scroll-mt-32 p-5">
          <h3 className="mb-3 text-lg">FRP in selected period · original sensor values</h3>
          <table className="archive-table">
            <thead>
              <tr>
                <th>Sensor</th>
                <th>Available records</th>
                <th>Median MW</th>
                <th>Mean MW</th>
                <th>90th percentile MW</th>
              </tr>
            </thead>
            <tbody>
              {["MODIS", "VIIRS"].map((sensor) => {
                const f = summary?.frp_by_sensor?.[sensor];
                return (
                  <tr key={sensor}>
                    <td>{sensor}</td>
                    <td>{fmt(f?.n)}</td>
                    <td>{fmt(f?.median)}</td>
                    <td>{fmt(f?.mean)}</td>
                    <td>{fmt(f?.p90)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
          <p className="mb-5 mt-2 text-xs text-muted-foreground">
            FRP is summarized separately per sensor and is not summed across matched observations as
            fire energy.
          </p>
          <h2 className="text-xl">
            {t("nav_sensors")} · selected monthly activity, {year || "2022–2025"}
          </h2>
          <p className="my-2 text-xs text-muted-foreground">
            Chart covers the full selected year nationally. Map filters apply to the cards and
            calendar. Counts are source detections, not equivalent sensor measurements.
          </p>
          <div className="h-[280px]">
            <ResponsiveContainer>
              <LineChart data={monthly}>
                <CartesianGrid stroke="var(--border)" />
                <XAxis dataKey="label" />
                <YAxis />
                <Tooltip
                  contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
                />
                <Line name="MODIS" dataKey="modis" stroke={palette.MODIS} dot={false} />
                <Line name="VIIRS" dataKey="viirs" stroke={palette.VIIRS} dot={false} />
                <Line
                  name="Activity units"
                  dataKey="activity"
                  stroke="var(--primary)"
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </section>
        <section className="panel p-5">
          <h2 className="text-xl">Matching evidence &amp; threshold review</h2>
          <p className="my-2 text-xs text-muted-foreground">
            All candidate links are preserved. Tables below cover the entire archive, independent of
            map filters. Scores are evidence rankings, not probabilities.
          </p>
          <table className="archive-table">
            <thead>
              <tr>
                <th>Distance gate</th>
                <th>Time gate</th>
                <th>Assigned groups</th>
                <th>Matched</th>
                <th>Possible</th>
              </tr>
            </thead>
            <tbody>
              {sensitivity?.data.map((r: any) => (
                <tr key={r.distance_km}>
                  <td>{r.distance_km} km</td>
                  <td>{r.time_minutes} min</td>
                  <td>{fmt(r.assigned_groups)}</td>
                  <td>{fmt(r.matched)}</td>
                  <td>{fmt(r.possible)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="my-2 text-xs text-muted-foreground">{sensitivity?.note}</p>
          <details>
            <summary>Review top 30 of {fmt(evidence?.total)} candidate pairs</summary>
            <div className="max-h-[260px] overflow-auto">
              <table className="archive-table">
                <thead>
                  <tr>
                    <th>Distance</th>
                    <th>Time</th>
                    <th>Score</th>
                    <th>Status</th>
                    <th>Assignment</th>
                    <th>Provenance</th>
                  </tr>
                </thead>
                <tbody>
                  {evidence?.data.map((r: any) => (
                    <tr key={r.modis_id + r.viirs_id}>
                      <td>{r.distance_km.toFixed(3)} km</td>
                      <td>{r.dt_min.toFixed(1)} min</td>
                      <td>{r.score.toFixed(3)}</td>
                      <td>{r.label}</td>
                      <td>{r.assigned ? "Assigned" : "Alternative"}</td>
                      <td>
                        <button
                          className="archive-button"
                          onClick={async () => {
                            try {
                              setSelected(
                                await request(
                                  "/api/archive/observation/" + encodeURIComponent(r.modis_id),
                                ),
                              );
                              document.getElementById("map")?.scrollIntoView();
                            } catch (e) {
                              setError(String(e));
                            }
                          }}
                        >
                          Inspect MODIS
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
        </section>
        <ArchiveCalendar
          scope={{ year: year || null, month, region, daynight, startDate, endDate }}
          onShowDay={(date) => {
            setYear(0);
            setMonth("");
            setStartDate(date);
            setEndDate(date);
            document.getElementById("map")?.scrollIntoView();
          }}
        />
        <SituationShift history={history} regions={meta?.regions ?? []} region="" />
        <section id="anomalies" className="panel scroll-mt-32 p-5">
          <h2 className="text-xl">
            {t("nav_anomalies")} · exploratory {analysisYear}
          </h2>
          <p className="my-2 text-xs text-muted-foreground">
            {anomalies?.method} Coverage differences can create apparent anomalies. These are not
            warnings.
          </p>
          <div className="max-h-[280px] overflow-auto">
            <table className="archive-table">
              <thead>
                <tr>
                  <th>Region</th>
                  <th>Month</th>
                  <th>Observed</th>
                  <th>Baseline median</th>
                  <th>Robust z</th>
                </tr>
              </thead>
              <tbody>
                {anomalies?.data.map((r: any) => (
                  <tr key={r.region + r.month}>
                    <td>{r.region}</td>
                    <td>{MONTHS[r.month - 1]}</td>
                    <td>{fmt(r.observed)}</td>
                    <td>{fmt(r.median)}</td>
                    <td>
                      {r.z.toFixed(2)}
                      {r.fallback ? " (fallback)" : ""}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
        <section id="prediction" className="panel scroll-mt-32 p-5">
          <h2 className="text-xl">{t("nav_prediction")} · retrospective outlook</h2>
          <p className="my-2 text-xs text-muted-foreground">
            {forecast?.limitations ?? forecast?.reason}
          </p>
          {forecast?.available && (
            <>
              <p className="text-sm">
                Model: {forecast.model} · MAE naive {fmt(forecast.mae.seasonal_naive)}, seasonal
                mean {fmt(forecast.mae.seasonal_mean)}. Expanding-window tests: 2024 and 2025.
              </p>
              <div className="my-4 grid gap-3 sm:grid-cols-3">
                {forecast.outlook.map((r: any) => (
                  <div className="rounded border border-border p-4" key={r.month}>
                    {MONTHS[r.month - 1]} 2026
                    <div className="my-2 font-mono text-xl">{fmt(r.point)}</div>
                    <small>
                      Error band {fmt(r.low)}–{fmt(r.high)}
                    </small>
                  </div>
                ))}
              </div>
              <p className="text-xs text-muted-foreground">{forecast.interval}</p>
              <details className="mt-3">
                <summary>Chronological backtest results</summary>
                <table className="archive-table">
                  <thead>
                    <tr>
                      <th>Period</th>
                      <th>Actual</th>
                      <th>Naive</th>
                      <th>Seasonal mean</th>
                    </tr>
                  </thead>
                  <tbody>
                    {forecast.backtest.map((r: any) => (
                      <tr key={r.year + "-" + r.month}>
                        <td>
                          {r.year}-{r.month}
                        </td>
                        <td>{fmt(r.actual)}</td>
                        <td>{fmt(r.seasonal_naive)}</td>
                        <td>{fmt(r.seasonal_mean)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </details>
            </>
          )}
        </section>
        <section id="methodology" className="panel scroll-mt-32 p-5">
          <h2 className="text-xl">{t("nav_method")} · transparent by design</h2>
          <p className="my-3 text-sm">
            All original rows are retained in SQLite with source SHA-256 and source row. Matching
            eligibility: MODIS confidence ≥30; VIIRS nominal/high; detection type 0. Other
            observations remain visible as unmatched. Spatial gate ≤1 km; time gate ≤30 min. Score =
            0.6 × distance evidence + 0.4 × time evidence. Matched ≥0.70; possible ≥0.45.
            Maximum-weight one-to-one assignment is a documented MVP simplification; possible groups
            are counted once as provisional activity units, anchored on the MODIS acquisition date
            and region. Scores are not probabilities.
          </p>
          <p className="mb-3 text-sm">
            Footprint IoU is unavailable because reliable pixel orientation is absent. Scan/track
            fields are retained for review. MODIS 2022 reports 6.03; later years report 61.03. Raw
            sensor counts and FRP are never treated as equivalent or summed into fire energy.
            Archive request membership is preserved; unassigned/offshore points are not silently
            deleted.
          </p>
          <p className="text-xs text-muted-foreground">
            Boundaries: geoBoundaries gbOpen IDN ADM1, ODbL 1.0; province vintage may differ from
            current administrative divisions. Map tiles: Esri and OpenStreetMap contributors. Map is
            paginated; complete counts come from SQLite, not the visible markers.
          </p>
          <details className="mt-3">
            <summary>Files, checksums and processing configuration</summary>
            <pre className="mt-3 max-h-[300px] overflow-auto text-xs">
              {JSON.stringify(meta, null, 2)}
            </pre>
          </details>
        </section>
        <footer className="py-6 text-center text-xs text-muted-foreground">
          FIREWATCH · Satellite thermal observations are not confirmed incidents. Historical archive
          only. <a href={API + "/docs"}>API documentation</a>
        </footer>
      </main>
    </div>
  );
}
