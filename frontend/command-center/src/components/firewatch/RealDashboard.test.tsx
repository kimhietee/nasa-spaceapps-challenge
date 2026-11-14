import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/react";
import { RealDashboard } from "./RealDashboard";
vi.mock("./ArchiveMap", () => ({
  ArchiveMap: ({ query }: { query: string }) => <div data-testid="archive-map" data-query={query}>Map renderer</div>,
}));
vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: any) => <div>{children}</div>,
  LineChart: () => <div>Monthly chart</div>,
  BarChart: () => <div>Monthly activity bar chart</div>,
  Bar: () => null,
  Legend: () => null,
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  CartesianGrid: () => null,
}));
const summary = {
  total: 25,
  modis: 10,
  viirs: 15,
  matched: 2,
  possible: 1,
  modis_only: 7,
  viirs_only: 12,
  activity: 22,
};
beforeEach(() => {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => ({
      ok: true,
      json: async () => {
        if (url.includes("/sensitivity") || url.includes("/candidates"))
          return { data: [], total: 0 };
        if (url.includes("/meta"))
          return { records: 617112, regions: ["Bali"], processed_at: "2026-11-14", config: {} };
        if (url.includes("/history"))
          return [
            {
              year: 2025,
              summary: { ...summary, days_with_records: 30 },
              monthly: [{ period: 9, modis: 10, viirs: 15, activity: 22 }],
              regions: [{ region: "Bali", activity: 22 }],
            },
          ];
        if (url.includes("/calendar"))
          return {
            year: 2022,
            month: 1,
            days: [{ date: "2022-01-01", day: 1, activity: 12, in_range: true }],
            thresholds: [5, 10, 15],
            weekday_offset: 6,
            activity: 12,
          };
        if (url.includes("/day?"))
          return {
            date: "2022-01-01",
            summary: { ...summary, activity: 12 },
            regions: [{ region: "Bali", activity: 12 }],
          };
        if (url.includes("/anomalies")) return { data: [], method: "Exploratory" };
        if (url.includes("/forecast")) return { available: false, reason: "Insufficient data" };
        return {
          summary,
          observations: [],
          monthly: [],
          daily: [],
          scope: { year: 2025 },
          map_page: { returned: 0, total: 25 },
        };
      },
    })),
  );
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("Real archive dashboard", () => {
  it("requests January 2022 initially and restores it when filters reset", async () => {
    render(<RealDashboard />);
    expect(screen.getByLabelText("Archive year")).toHaveValue("2022");
    expect(screen.getByLabelText("Archive month")).toHaveValue("1");
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringContaining("/api/archive/dashboard?year=2022&month=1"),
        expect.anything(),
      ),
    );
    expect(screen.getByTestId("archive-map")).toHaveAttribute("data-query", "year=2022&month=1");
    fireEvent.change(screen.getByLabelText("Archive year"), { target: { value: "0" } });
    fireEvent.change(screen.getByLabelText("Archive month"), { target: { value: "" } });
    expect(screen.getByTestId("archive-map")).toHaveAttribute("data-query", "");
    fireEvent.click(screen.getByRole("button", { name: "Reset filters" }));
    expect(screen.getByLabelText("Archive year")).toHaveValue("2022");
    expect(screen.getByLabelText("Archive month")).toHaveValue("1");
    expect(screen.getByTestId("archive-map")).toHaveAttribute("data-query", "year=2022&month=1");
  });
  it("loads metadata, legend and filters the API", async () => {
    render(<RealDashboard />);
    await screen.findByText(/617,112 imported source records/);
    expect(screen.getAllByText("MODIS-only", { exact: true }).length).toBeGreaterThan(0);
    expect(screen.getByText("Anomaly region (separate flag)")).toBeTruthy();
    fireEvent.change(screen.getByLabelText("Archive year"), { target: { value: "2024" } });
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(expect.stringContaining("year=2024"), expect.anything()),
    );
  });
  it("date ranges clear conflicting year/month and calendar reveals day details", async () => {
    render(<RealDashboard />);
    fireEvent.change(screen.getByLabelText("Archive year"), { target: { value: "2025" } });
    fireEvent.change(screen.getByLabelText("Archive month"), { target: { value: "9" } });
    fireEvent.change(screen.getByLabelText("Start date"), { target: { value: "2022-01-01" } });
    fireEvent.change(screen.getByLabelText("End date"), { target: { value: "2022-12-31" } });
    expect(screen.getByLabelText("Archive year")).toHaveValue("0");
    expect(screen.getByLabelText("Archive month")).toHaveValue("");
    await waitFor(() =>
      expect(fetch).toHaveBeenCalledWith(
        expect.stringMatching(/dashboard\?.*start_date=2022-01-01.*end_date=2022-12-31/),
        expect.anything(),
      ),
    );
    fireEvent.click(await screen.findByRole("button", { name: "2022-01-01: 12 activity units" }));
    await screen.findByRole("button", { name: "Show this day on map" });
    expect(screen.queryByText("Next page")).toBeNull();
    expect(screen.getByText("Sensor contribution")).toBeTruthy();
    expect(screen.getByText("2022–2025 situation & shift")).toBeTruthy();
  });
  it("shows a connection error instead of generated data", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 503, json: async () => ({}) }),
    );
    render(<RealDashboard />);
    expect(await screen.findByText(/Archive request failed \(503\)/)).toBeTruthy();
    expect(screen.queryByText("Sample archive")).toBeNull();
  });
});
