import { useEffect, useState } from "react";
const API = import.meta.env["VITE_ARCHIVE_API"] ?? "";
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];
export function ArchiveCalendar({
  scope,
  onShowDay,
}: {
  scope: {
    year: number | null;
    month: string;
    region: string;
    daynight: string;
    startDate: string;
    endDate: string;
  };
  onShowDay: (date: string) => void;
}) {
  const [year, setYear] = useState(2022),
    [month, setMonth] = useState(1),
    [calendar, setCalendar] = useState<any>(null),
    [day, setDay] = useState<any>(null),
    [error, setError] = useState("");
  useEffect(() => {
    if (scope.startDate) {
      setYear(Number(scope.startDate.slice(0, 4)));
      setMonth(Number(scope.startDate.slice(5, 7)));
    } else {
      if (scope.year) setYear(scope.year);
      if (scope.month) setMonth(Number(scope.month));
    }
  }, [scope.year, scope.month, scope.startDate]);
  useEffect(() => {
    const abort = new AbortController();
    setCalendar(null);
    setDay(null);
    setError("");
    const q = new URLSearchParams({ year: String(year), month: String(month) });
    if (scope.region) q.set("region", scope.region);
    if (scope.daynight) q.set("daynight", scope.daynight);
    if (scope.startDate) q.set("start_date", scope.startDate);
    if (scope.endDate) q.set("end_date", scope.endDate);
    fetch(API + "/api/archive/calendar?" + q, { signal: abort.signal })
      .then(async (r) => {
        if (!r.ok) throw Error("Calendar unavailable");
        return r.json();
      })
      .then(setCalendar)
      .catch((e) => {
        if (e.name !== "AbortError") setError(e.message);
      });
    return () => abort.abort();
  }, [year, month, scope.region, scope.daynight, scope.startDate, scope.endDate]);
  async function select(date: string) {
    setError("");
    const q = new URLSearchParams({ date });
    if (scope.region) q.set("region", scope.region);
    if (scope.daynight) q.set("daynight", scope.daynight);
    try {
      const r = await fetch(API + "/api/archive/day?" + q);
      if (!r.ok) throw Error("Day details unavailable");
      setDay(await r.json());
    } catch (e) {
      setError(String(e));
    }
  }
  function navigate(delta: number) {
    const d = new Date(Date.UTC(year, month - 1 + delta, 1));
    if (d.getUTCFullYear() < 2022 || d.getUTCFullYear() > 2025) return;
    setYear(d.getUTCFullYear());
    setMonth(d.getUTCMonth() + 1);
  }
  const thresholds = calendar?.thresholds ?? [];
  const tone = (value: number | null) =>
    value == null
      ? "unknown"
      : value <= thresholds[0]
        ? "low"
        : value <= thresholds[1]
          ? "moderate"
          : value <= thresholds[2]
            ? "high"
            : "very-high";
  return (
    <section id="calendar" className="scroll-mt-32">
      <div className="eyebrow">DAILY ACTIVITY</div>
      <h2 className="my-3 text-2xl">Activity calendar</h2>
      <p className="mb-5 text-sm text-muted-foreground">
        Day-by-day activity heatmap. Select a day to see its actual sensor and regional breakdown.
      </p>
      <div className="grid gap-3 lg:grid-cols-[1.6fr_1fr]">
        <div className="panel p-5">
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3>Harmonized activity calendar</h3>
              <p className="mt-1 text-xs text-muted-foreground">
                {MONTHS[month - 1]} {year} · {calendar?.activity?.toLocaleString() ?? "…"} known
                activity units
              </p>
            </div>
            <div className="flex gap-2">
              <button
                className="archive-button"
                aria-label="Previous calendar month"
                disabled={year === 2022 && month === 1}
                onClick={() => navigate(-1)}
              >
                ‹
              </button>
              <select
                aria-label="Calendar month"
                value={month}
                onChange={(e) => setMonth(+e.target.value)}
              >
                {MONTHS.map((m, i) => (
                  <option key={m} value={i + 1}>
                    {m}
                  </option>
                ))}
              </select>
              <select
                aria-label="Calendar year"
                value={year}
                onChange={(e) => setYear(+e.target.value)}
              >
                {[2022, 2023, 2024, 2025].map((y) => (
                  <option key={y}>{y}</option>
                ))}
              </select>
              <button
                className="archive-button"
                aria-label="Next calendar month"
                disabled={year === 2025 && month === 12}
                onClick={() => navigate(1)}
              >
                ›
              </button>
            </div>
          </div>
          {error && <p role="alert">{error}</p>}
          <div className="grid grid-cols-7 gap-1.5 text-xs">
            {["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map((d) => (
              <div className="py-2 text-center text-muted-foreground" key={d}>
                {d}
              </div>
            ))}
            {Array.from({ length: calendar?.weekday_offset ?? 0 }, (_, i) => (
              <div key={"blank" + i} />
            ))}
            {calendar?.days.map((d: any) => (
              <button
                key={d.date}
                disabled={!d.in_range}
                aria-label={`${d.date}: ${d.activity == null ? "unknown" : d.activity + " activity units"}`}
                aria-pressed={day?.date === d.date}
                className={`calendar-day calendar-${tone(d.activity)} ${day?.date === d.date ? "calendar-selected" : ""}`}
                onClick={() => select(d.date)}
              >
                <span className="text-[10px] opacity-70">{d.day}</span>
                <b className="mt-3 block font-mono">
                  {d.activity == null ? "—" : d.activity.toLocaleString()}
                </b>
              </button>
            ))}
          </div>
          <div className="mt-4 flex flex-wrap gap-3 text-[10px] text-muted-foreground">
            {["low", "moderate", "high", "very-high", "unknown"].map((t) => (
              <span key={t}>
                <i className={"mr-1 inline-block h-2 w-2 rounded calendar-" + t} />
                {t.replace("-", " ")}
              </span>
            ))}
          </div>
          <p className="mt-2 text-[10px] text-muted-foreground">
            Intensity thresholds: this month’s observed daily p50/p75/p90 (
            {thresholds.map((n: number) => Math.round(n)).join(" / ")}). Missing dates remain
            unknown; they are not confirmed zero activity. Dates outside your range are disabled.
          </p>
        </div>
        <aside className="panel p-5" aria-label="Selected day details">
          <h3>{day?.date ?? "Selected day"}</h3>
          {day ? (
            <>
              <p className="my-2 text-xs text-muted-foreground">
                Breakdown of the selected date, under the current region/day-night filters.
              </p>
              <div className="grid grid-cols-2 gap-2">
                {[
                  ["Activity units", day.summary.activity],
                  ["Matched groups", day.summary.matched],
                  ["MODIS detections", day.summary.modis],
                  ["VIIRS detections", day.summary.viirs],
                ].map(([label, value]) => (
                  <div className="rounded border border-border p-3" key={label}>
                    <small>{label}</small>
                    <div className="mt-2 font-mono text-2xl">{Number(value).toLocaleString()}</div>
                  </div>
                ))}
              </div>
              <h4 className="mb-3 mt-5 text-xs text-muted-foreground">TOP REGIONS</h4>
              {day.regions.slice(0, 6).map((r: any) => (
                <div className="mb-3 text-xs" key={r.region}>
                  <div className="flex justify-between">
                    <span>{r.region}</span>
                    <span>{r.activity.toLocaleString()}</span>
                  </div>
                  <div className="mt-1 h-1 rounded bg-muted">
                    <div
                      className="h-full rounded bg-primary"
                      style={{
                        width: `${day.summary.activity ? (r.activity / day.summary.activity) * 100 : 0}%`,
                      }}
                    />
                  </div>
                </div>
              ))}
              <p className="my-3 text-xs text-possible">
                {day.summary.possible.toLocaleString()} possible groups await review.
              </p>
              {day.summary.total === 0 && (
                <p className="text-xs">
                  No source records for this selection; satellite coverage remains unknown.
                </p>
              )}
              <button className="archive-button" onClick={() => onShowDay(day.date)}>
                Show this day on map
              </button>
            </>
          ) : (
            <p className="mt-20 text-sm text-muted-foreground">
              Tap a date to inspect MODIS, VIIRS, matched groups and regional counts.
            </p>
          )}
        </aside>
      </div>
    </section>
  );
}
