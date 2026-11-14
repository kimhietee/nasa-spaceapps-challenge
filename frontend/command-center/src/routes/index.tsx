import { RealDashboard } from "@/components/firewatch/RealDashboard";
import { createFileRoute } from "@tanstack/react-router";
import { useCallback, useEffect, useMemo, useState } from "react";
import { TooltipProvider } from "@/components/ui/tooltip";
import { Header } from "@/components/firewatch/Header";
import { MapSection, type Filters } from "@/components/firewatch/MapSection";
import type { MapView } from "@/components/firewatch/FireMap";
import { Overview } from "@/components/firewatch/sections/Overview";
import { CalendarSection } from "@/components/firewatch/sections/Calendar";
import { Sensors } from "@/components/firewatch/sections/Sensors";
import { Anomalies } from "@/components/firewatch/sections/Anomalies";
import { Prediction } from "@/components/firewatch/sections/Prediction";
import { History } from "@/components/firewatch/sections/History";
import { Methodology } from "@/components/firewatch/sections/Methodology";
import { anomalyTable, getYear, summarize } from "@/lib/firewatch/analysis";
import type { HarmonizedObservation } from "@/lib/firewatch/harmonize";
import { MONTHS, PIPELINE_RUN_UTC, type Year } from "@/lib/firewatch/sample-data";
import { I18nProvider, useT, type Lang } from "@/lib/firewatch/i18n";
import { downloadText, observationsToCsv } from "@/lib/firewatch/export";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "FIREWATCH — Indonesia Satellite Fire Monitoring" },
      {
        name: "description",
        content:
          "Map-first dashboard harmonizing NASA FIRMS MODIS and VIIRS fire detections across Indonesia, with 2022–2025 history and an outlook.",
      },
      { property: "og:title", content: "FIREWATCH — Indonesia Satellite Fire Monitoring" },
      {
        property: "og:description",
        content:
          "Harmonized MODIS–VIIRS hotspots, anomaly review, historical shift analysis and predictive outlook for Indonesia.",
      },
      { property: "og:type", content: "website" },
      { name: "twitter:card", content: "summary_large_image" },
    ],
  }),
  component: RealDashboard,
});

const DEFAULT_FILTERS: Filters = {
  mode: "archive",
  year: 2025,
  month: "all",
  province: "all",
  daynight: "all",
};

function Index() {
  const [lang, setLang] = useState<Lang>("en");
  return (
    <I18nProvider lang={lang}>
      <Dashboard lang={lang} setLang={setLang} />
    </I18nProvider>
  );
}

function Dashboard({ lang, setLang }: { lang: Lang; setLang: (l: Lang) => void }) {
  const t = useT();
  const [theme, setThemeState] = useState<"dark" | "light">("dark");
  const [technical, setTechnical] = useState(false);
  const [filters, setFiltersState] = useState<Filters>(DEFAULT_FILTERS);
  const [view, setView] = useState<MapView>("harmonized");
  const [points, setPoints] = useState(true);
  const [density, setDensity] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [selected, setSelected] = useState<HarmonizedObservation | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
    const saved = localStorage.getItem("fw-theme");
    if (saved === "light" || saved === "dark") setThemeState(saved);
    const savedLang = localStorage.getItem("fw-lang");
    if (savedLang === "en" || savedLang === "id") setLang(savedLang);
  }, [setLang]);
  useEffect(() => {
    document.documentElement.classList.toggle("dark", theme === "dark");
    document.documentElement.lang = lang;
  }, [theme, lang]);
  const setTheme = (th: "dark" | "light") => {
    setThemeState(th);
    localStorage.setItem("fw-theme", th);
  };
  const changeLang = (l: Lang) => {
    setLang(l);
    localStorage.setItem("fw-lang", l);
  };

  const setFilters = useCallback((f: Partial<Filters>) => {
    setFiltersState((p) => ({ ...p, ...f }));
    if ("year" in f || "province" in f || "month" in f || "daynight" in f) setSelected(null);
    if ("month" in f || "year" in f) setPlaying(false);
  }, []);

  const year = filters.year as Year;
  const result = useMemo(() => getYear(year), [year]);
  const byId = useMemo(() => new Map(result.observations.map((o) => [o.id, o])), [result]);
  const regionObs = useMemo(
    () =>
      result.observations.filter(
        (o) =>
          (filters.province === "all" || o.province === filters.province) &&
          (filters.daynight === "all" || o.daynight === filters.daynight),
      ),
    [result, filters.province, filters.daynight],
  );
  const filtered = useMemo(
    () =>
      filters.month === "all"
        ? regionObs
        : regionObs.filter((o) => +o.date.slice(5, 7) - 1 === +filters.month),
    [regionObs, filters.month],
  );
  const summary = useMemo(() => summarize(filtered), [filtered]);
  const anomalies = useMemo(() => anomalyTable(year), [year]);

  // Monthly playback: steps through Jan → Dec of the selected year.
  useEffect(() => {
    if (!playing) return;
    const id = setInterval(
      () =>
        setFiltersState((p) => ({
          ...p,
          month: String(p.month === "all" ? 0 : (+p.month + 1) % 12),
        })),
      1400,
    );
    return () => clearInterval(id);
  }, [playing]);

  const reset = () => {
    setFiltersState(DEFAULT_FILTERS);
    setView("harmonized");
    setPoints(true);
    setDensity(false);
    setPlaying(false);
    setSelected(null);
  };
  const periodLabel = `${filters.month === "all" ? "Jan–Dec" : MONTHS[+filters.month]} ${year}${filters.province === "all" ? "" : ` · ${filters.province}`}`;

  const exportReport = () => {
    const csv = observationsToCsv(filtered, {
      report: "FIREWATCH observation export",
      data: "SAMPLE DATA — interface preview, not real detections",
      period: periodLabel,
      day_night: filters.daynight,
      matching_config: `${result.config.id} v${result.config.version}`,
      generated_utc: new Date().toISOString(),
      pipeline_run_utc: PIPELINE_RUN_UTC,
      activity_units: String(summary.activity),
      modis: String(summary.modis),
      viirs: String(summary.viirs),
      matched_groups: String(summary.matchedGroups),
      possible_groups: String(summary.possibleGroups),
    });
    downloadText(
      `firewatch-${year}-${filters.month === "all" ? "all" : MONTHS[+filters.month]!.toLowerCase()}.csv`,
      csv,
    );
  };

  const openOnMap = (id: string) => {
    const o = byId.get(id);
    if (!o) return;
    setFiltersState((p) => ({
      ...p,
      mode: "archive",
      month: "all",
      province: "all",
      daynight: "all",
    }));
    setSelected(o);
    document.getElementById("map")?.scrollIntoView({ behavior: "smooth" });
  };

  return (
    <TooltipProvider>
      <div className="min-h-screen">
        <Header
          lang={lang}
          setLang={changeLang}
          theme={theme}
          setTheme={setTheme}
          technical={technical}
          setTechnical={setTechnical}
          onExport={exportReport}
          live={false}
        />
        <main className="mx-auto max-w-[1360px] space-y-16 px-4 pb-20 pt-8 sm:px-6">
          <MapSection
            filters={filters}
            setFilters={setFilters}
            reset={reset}
            view={view}
            setView={setView}
            points={points}
            setPoints={setPoints}
            density={density}
            setDensity={setDensity}
            playing={playing}
            togglePlay={() => {
              if (!playing && filters.month === "all")
                setFiltersState((p) => ({ ...p, month: "0" }));
              setPlaying(!playing);
            }}
            technical={technical}
            mounted={mounted}
            obs={filtered}
            summary={summary}
            byId={byId}
            selected={selected}
            setSelected={setSelected}
          />
          <Overview
            s={summary}
            obs={regionObs.filter(
              (o) => filters.month === "all" || +o.date.slice(5, 7) - 1 === +filters.month,
            )}
            year={year}
            month={filters.month}
            technical={technical}
            anomalies={anomalies}
            periodLabel={periodLabel}
          />
          <CalendarSection
            obs={regionObs}
            year={year}
            monthFilter={filters.month}
            province={filters.province}
          />
          <Sensors
            s={summary}
            obs={filtered}
            result={result}
            year={year}
            technical={technical}
            setTechnical={setTechnical}
            onOpen={openOnMap}
          />
          <Anomalies
            rows={anomalies}
            year={year}
            monthFilter={filters.month}
            provinceFilter={filters.province}
          />
          <Prediction />
          <History />
          <Methodology />
        </main>
        <footer className="border-t border-border">
          <div className="mx-auto flex max-w-[1360px] flex-col justify-between gap-2 px-4 py-5 text-[11px] text-muted-foreground sm:flex-row sm:px-6">
            <span>{t("footer_l")}</span>
            <span>{t("footer_r")}</span>
          </div>
        </footer>
      </div>
    </TooltipProvider>
  );
}
