import { useState } from "react";
import {
  BarChart,
  Bar,
  LineChart,
  Line,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
const fmt = (n: number | null | undefined) =>
  n == null ? "—" : n.toLocaleString(undefined, { maximumFractionDigits: 1 });
export function ActivityOverview({
  monthly,
  anomalies,
  label,
}: {
  monthly: any[];
  anomalies: any;
  label: string;
}) {
  return (
    <div className="grid gap-3 lg:grid-cols-[1.6fr_1fr]">
      <div className="panel p-5">
        <h3>Harmonized activity</h3>
        <p className="mt-1 text-xs text-muted-foreground">Monthly activity units · {label}</p>
        <div className="mt-5 h-[270px]">
          <ResponsiveContainer>
            <BarChart data={monthly}>
              <CartesianGrid vertical={false} stroke="var(--border)" strokeDasharray="3 3" />
              <XAxis dataKey="label" tick={{ fontSize: 11 }} />
              <YAxis width={55} tick={{ fontSize: 10 }} />
              <Tooltip
                contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
              />
              <Bar
                name="Activity units"
                dataKey="activity"
                fill="var(--primary)"
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Matched/possible groups counted once, plus unmatched observations. All selected records
          contribute.
        </p>
      </div>
      <div className="panel p-5">
        <h3>Anomaly review</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          Exploratory signals · {anomalies?.year ?? 2025}
        </p>
        {anomalies?.data?.slice(0, 4).map((r: any) => (
          <a
            href="#anomalies"
            className="my-4 flex justify-between border-b border-border pb-3 text-xs"
            key={r.region + r.month}
          >
            <span>
              {r.region}
              <small className="mt-1 block text-muted-foreground">
                {MONTHS[r.month - 1]} · {fmt(r.observed)} vs median {fmt(r.median)}
              </small>
            </span>
            <span className="text-anomaly">z {r.z.toFixed(1)} ›</span>
          </a>
        ))}
        <div className="mt-5 rounded border border-possible/40 bg-possible/5 p-3 text-xs text-possible">
          Anomalies are statistical signals, not confirmed incidents or official warnings. Coverage
          is unknown.
        </div>
      </div>
    </div>
  );
}
export function SensorHarmonization({ summary: s }: { summary: any }) {
  const outcomes = [
    ["Matched groups", s?.matched, "var(--matched)"],
    ["Possible", s?.possible, "var(--possible)"],
    ["MODIS-only", s?.modis_only, "var(--modis)"],
    ["VIIRS-only", s?.viirs_only, "var(--viirs)"],
  ] as const;
  return (
    <section id="sensors" className="scroll-mt-32">
      <div className="eyebrow">SENSOR HARMONIZATION</div>
      <h2 className="my-3 text-2xl">MODIS–VIIRS comparison</h2>
      <p className="mb-5 text-sm text-muted-foreground">
        Original products side by side, with evidence linking candidate corresponding observations.
      </p>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="panel p-5">
          <h3>Sensor contribution</h3>
          <p className="my-2 text-xs text-muted-foreground">
            Source detections stay separate; activity counts each provisional group once.
          </p>
          <div className="my-5 grid grid-cols-3 gap-2">
            {[
              ["MODIS", s?.modis, "var(--modis)", "Terra / Aqua"],
              ["VIIRS", s?.viirs, "var(--viirs)", "Suomi-NPP"],
              ["HARMONIZED", s?.activity, "var(--primary)", "Activity units"],
            ].map(([label, value, color, caption]) => (
              <div className="rounded border border-border p-3" key={String(label)}>
                <small className="text-muted-foreground">{label}</small>
                <div className="my-3 font-mono text-2xl">{fmt(value as number)}</div>
                <div className="mb-2 h-1 rounded" style={{ background: String(color) }} />
                <small className="text-[10px] text-muted-foreground">{caption}</small>
              </div>
            ))}
          </div>
          <div className="text-[10px] tracking-wider text-muted-foreground">
            HARMONIZATION OUTCOME
          </div>
          <div
            className="my-2 flex h-3 overflow-hidden rounded"
            aria-label="Harmonization outcome proportions"
          >
            {outcomes.map(([label, value, color]) => (
              <div
                key={label}
                title={`${label}: ${fmt(value)}`}
                style={{
                  background: color,
                  width: `${s?.activity ? ((value ?? 0) / s.activity) * 100 : 0}%`,
                }}
              />
            ))}
          </div>
          <div className="flex flex-wrap gap-3 text-[10px]">
            {outcomes.map(([label, value, color]) => (
              <span key={label}>
                <i className="legend-dot !h-2 !w-2" style={{ background: color }} />
                {label} <b className="ml-1">{fmt(value)}</b>
              </span>
            ))}
          </div>
          <p className="mt-5 rounded border border-border p-3 text-xs text-muted-foreground">
            VIIRS has finer spatial sampling and often reports more detections. A candidate match
            does not prove the same physical fire.
          </p>
        </div>
        <div className="panel p-5">
          <h3>Side-by-side metrics</h3>
          <p className="my-2 text-xs text-muted-foreground">
            Native product values; confidence scales are never merged.
          </p>
          <table className="archive-table">
            <thead>
              <tr>
                <th>Metric</th>
                <th className="text-modis">MODIS</th>
                <th className="text-viirs">VIIRS</th>
              </tr>
            </thead>
            <tbody>
              {[
                ["Source detections", s?.modis, s?.viirs],
                ["In matched groups", s?.modis_matched, s?.viirs_matched],
                ["Unmatched (sensor-only)", s?.modis_only, s?.viirs_only],
                [
                  "Match rate",
                  s?.modis ? `${((100 * s.modis_matched) / s.modis).toFixed(1)}%` : "—",
                  s?.viirs ? `${((100 * s.viirs_matched) / s.viirs).toFixed(1)}%` : "—",
                ],
                [
                  "Median FRP (MW)",
                  s?.frp_by_sensor?.MODIS?.median,
                  s?.frp_by_sensor?.VIIRS?.median,
                ],
              ].map(([label, m, v]) => (
                <tr key={String(label)}>
                  <td>{label}</td>
                  <td>{typeof m === "string" ? m : fmt(m)}</td>
                  <td>{typeof v === "string" ? v : fmt(v)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-5 text-xs text-muted-foreground">
            Match rate = matched source observations ÷ selected source observations for that sensor.
            Groups are anchored on MODIS date and region. FRP is summarized separately, never summed
            across duplicate views.
          </p>
        </div>
      </div>
    </section>
  );
}
export function SituationShift({
  history,
  regions,
  region,
}: {
  history: any[];
  regions: string[];
  region: string;
}) {
  const [metric, setMetric] = useState("activity");
  const max = Math.max(1, ...history.map((r) => r.summary.activity));
  const min = Math.min(...history.map((r) => r.summary.activity));
  return (
    <section id="history" className="scroll-mt-32">
      <div className="eyebrow">NASA FIRMS ARCHIVE</div>
      <h2 className="my-3 text-2xl">2022–2025 situation &amp; shift</h2>
      <p className="mb-5 text-sm text-muted-foreground">
        How observed activity changed across four years—direction, timing and geography. Same
        calendar months · {region || "Indonesia nationally"}.
      </p>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {history.map((r, i) => {
          const peak = r.monthly.reduce((a: any, b: any) => (b.activity > a.activity ? b : a), {
            activity: -1,
            period: 1,
          });
          return (
            <div className="panel p-4" key={r.year}>
              <div className="flex justify-between">
                <h3>{r.year}</h3>
                <span className="rounded bg-muted px-2 text-[9px]">
                  {r.summary.activity === max
                    ? "HIGHEST"
                    : r.summary.activity === min
                      ? "LOWEST"
                      : "PEAK " + MONTHS[peak.period - 1]}
                </span>
              </div>
              <div className="mt-4 font-mono text-3xl">{fmt(r.summary.activity)}</div>
              <small className="text-muted-foreground">harmonized activity units</small>
              <div className="mb-3 mt-4 h-1 rounded bg-muted">
                <div
                  className="h-full rounded bg-primary"
                  style={{ width: `${(r.summary.activity / max) * 100}%` }}
                />
              </div>
              <div className="mb-2 flex h-1 overflow-hidden rounded">
                <div
                  style={{
                    width: `${(r.summary.modis / r.summary.total) * 100}%`,
                    background: "var(--modis)",
                  }}
                />
                <div className="flex-1 bg-viirs" />
              </div>
              <p className="text-[10px] text-muted-foreground">
                MODIS {fmt(r.summary.modis)} · VIIRS {fmt(r.summary.viirs)}
              </p>
              <div className="mt-4 border-t border-border pt-3 text-xs">
                {r.summary.change_pct == null
                  ? "Baseline year"
                  : `${r.summary.change_pct >= 0 ? "+" : ""}${r.summary.change_pct.toFixed(1)}% vs ${r.year - 1}`}
              </div>
              <p className="mt-2 text-[10px] text-muted-foreground">
                {r.summary.days_with_records} dates with records · coverage unknown
              </p>
            </div>
          );
        })}
      </div>
      <div className="mt-3 grid gap-3 lg:grid-cols-[1.6fr_1fr]">
        <div className="panel p-5">
          <div className="flex flex-wrap justify-between gap-2">
            <h3>Monthly comparison · same calendar months</h3>
            <select
              aria-label="History metric"
              value={metric}
              onChange={(e) => setMetric(e.target.value)}
            >
              <option value="activity">Activity</option>
              <option value="matched">Matched</option>
              <option value="modis_only">MODIS-only</option>
              <option value="viirs_only">VIIRS-only</option>
            </select>
          </div>
          <div className="mt-4 h-[300px]">
            <ResponsiveContainer>
              <LineChart
                data={MONTHS.map((label, i) => ({
                  label,
                  ...Object.fromEntries(
                    history.map((r) => [
                      String(r.year),
                      r.monthly.find((m: any) => m.period === i + 1)?.[metric] ?? null,
                    ]),
                  ),
                }))}
              >
                <CartesianGrid stroke="var(--border)" vertical={false} />
                <XAxis dataKey="label" tick={{ fontSize: 10 }} />
                <YAxis width={55} tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ background: "var(--card)", border: "1px solid var(--border)" }}
                />
                <Legend />
                {[2022, 2023, 2024, 2025].map((y, i) => (
                  <Line
                    key={y}
                    name={String(y)}
                    dataKey={String(y)}
                    stroke={
                      ["var(--modis)", "var(--viirs)", "var(--possible)", "var(--primary)"][i]
                    }
                    dot={false}
                    isAnimationActive={false}
                  />
                ))}
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
        <div className="panel p-5">
          <h3>Regional share of national activity</h3>
          <p className="my-2 text-xs text-muted-foreground">
            Percent of each year's activity units · change in percentage points.
          </p>
          <div className="max-h-[310px] overflow-auto">
            <table className="archive-table">
              <thead>
                <tr>
                  <th>Region</th>
                  {history.map((r) => (
                    <th key={r.year}>{String(r.year).slice(2)}</th>
                  ))}
                  <th>Δ24→25</th>
                </tr>
              </thead>
              <tbody>
                {regions.map((name) => {
                  const share = (r: any) =>
                    r?.summary.activity
                      ? ((r.regions.find((p: any) => p.region === name)?.activity ?? 0) /
                          r.summary.activity) *
                        100
                      : 0;
                  const delta =
                    share(history.find((r) => r.year === 2025)) -
                    share(history.find((r) => r.year === 2024));
                  return (
                    <tr key={name}>
                      <td>{name}</td>
                      {history.map((r) => (
                        <td key={r.year}>{share(r).toFixed(1)}</td>
                      ))}
                      <td>
                        {delta >= 0 ? "+" : ""}
                        {delta.toFixed(1)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
      <div className="mt-3 rounded border border-primary/20 bg-notice p-5">
        <div className="eyebrow mb-3">WHAT CHANGED? · GENERATED FROM COMPUTED METRICS</div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {history.map((r, i) => {
            const peak = r.monthly.reduce((a: any, b: any) => (b.activity > a.activity ? b : a), {
              activity: -1,
              period: 1,
            });
            const prior = history[i - 1];
            const changes = r.regions
              .map((p: any) => ({
                name: p.region,
                delta:
                  (r.summary.activity ? p.activity / r.summary.activity : 0) * 100 -
                  (prior?.summary.activity
                    ? (prior.regions.find((x: any) => x.region === p.region)?.activity ?? 0) /
                      prior.summary.activity
                    : 0) *
                    100,
              }))
              .sort((a: any, b: any) => b.delta - a.delta);
            return (
              <p className="text-xs leading-relaxed" key={r.year}>
                <b>{r.year}</b>
                <br />
                {r.summary.change_pct == null
                  ? "Baseline year."
                  : `Activity ${r.summary.change_pct >= 0 ? "rose" : "fell"} ${Math.abs(r.summary.change_pct).toFixed(1)}% vs ${r.year - 1}.`}{" "}
                Peak month {MONTHS[peak.period - 1]}; {r.regions[0]?.region} held the largest share.{" "}
                {prior && changes.length > 0
                  ? `${changes[0].name} gained the most share (${changes[0].delta >= 0 ? "+" : ""}${changes[0].delta.toFixed(1)} pp).`
                  : ""}
              </p>
            );
          })}
        </div>
        <p className="mt-4 text-[10px] text-muted-foreground">
          Changes describe satellite detection concentration, not proven changes in fire incidents
          or burned area. Product versions and unknown observation coverage affect comparisons.
        </p>
      </div>
    </section>
  );
}
