"""Core science: sensor normalization, weekly grid, calibration, harmonized series,
climatology, anomalies and critical periods. Used by both the pipeline and the API."""
import numpy as np
import pandas as pd

from .config import CONFIG


# ---------------------------------------------------------------- sensors
def normalize_sensor(instrument, satellite, n):
    """Map FIRMS instrument/satellite columns to MODIS | VIIRS_SNPP | VIIRS_NOAA20 | VIIRS_NOAA21 | VIIRS_OTHER."""
    inst = instrument.astype(str).str.upper().str.strip() if instrument is not None else pd.Series([""] * n)
    sat = satellite.astype(str).str.upper().str.strip() if satellite is not None else pd.Series([""] * n)
    inst, sat = inst.reset_index(drop=True), sat.reset_index(drop=True)
    is_modis = inst.str.contains("MODIS") | (~inst.str.contains("VIIRS") & sat.isin(["TERRA", "AQUA", "T", "A"]))
    out = np.where(is_modis, "MODIS", "VIIRS_OTHER").astype(object)
    out[(~is_modis) & sat.isin(["N", "SUOMI-NPP", "SNPP", "S-NPP", "NPP"])] = "VIIRS_SNPP"
    out[(~is_modis) & sat.isin(["N20", "NOAA-20", "NOAA20"])] = "VIIRS_NOAA20"
    out[(~is_modis) & sat.isin(["N21", "NOAA-21", "NOAA21"])] = "VIIRS_NOAA21"
    return out


# ---------------------------------------------------------------- weekly grid
def make_grid(years, sensor_ranges):
    """Year x week frame. *_avail says whether that sensor had any data coverage that week
    (weeks outside a sensor's data range become NULL, not 0)."""
    g = pd.MultiIndex.from_product([list(years), range(1, 53)], names=["year", "week"]).to_frame(index=False)
    start = pd.to_datetime(g["year"].astype(str) + "-01-01") + pd.to_timedelta((g["week"] - 1) * 7, unit="D")
    end = start + pd.to_timedelta(6, unit="D")
    last = g["week"] == 52
    end[last] = pd.to_datetime(g.loc[last, "year"].astype(str) + "-12-31")
    for key in ("modis", "viirs"):
        lo, hi = sensor_ranges.get(key, (None, None))
        if lo is None:
            g[f"{key}_avail"] = False
        else:
            g[f"{key}_avail"] = ((end >= pd.Timestamp(lo)) & (start <= pd.Timestamp(hi))).to_numpy()
    return g


def aggregate_aoi(sub_cw, grid):
    """Sum cell-days per year/week for MODIS and (all selected) VIIRS inside one AOI."""
    m = (sub_cw[sub_cw["sensor"] == "MODIS"].groupby(["year", "week"], as_index=False)["cell_days"].sum()
         .rename(columns={"cell_days": "modis_cd"}))
    v = (sub_cw[sub_cw["sensor"].str.startswith("VIIRS")].groupby(["year", "week"], as_index=False)["cell_days"].sum()
         .rename(columns={"cell_days": "viirs_cd"}))
    df = grid.merge(m, on=["year", "week"], how="left").merge(v, on=["year", "week"], how="left")
    df["modis_cd"] = df["modis_cd"].fillna(0.0).where(df["modis_avail"], np.nan)
    df["viirs_cd"] = df["viirs_cd"].fillna(0.0).where(df["viirs_avail"], np.nan)
    return df.drop(columns=["modis_avail", "viirs_avail"])


# ---------------------------------------------------------------- calibration
def calibrate_overlap(year, modis, viirs, fit_start=None, fit_end=None):
    """Fit MODIS ~ beta * VIIRS (through the origin) on weeks where both sensors have data."""
    fit_start = fit_start or CONFIG["overlap_fit_start_year"]
    fit_end = fit_end or CONFIG["baseline_end"]
    year, m, v = np.asarray(year), np.asarray(modis, float), np.asarray(viirs, float)
    mask = (year >= fit_start) & (year <= fit_end) & ~np.isnan(m) & ~np.isnan(v)
    period = f"{fit_start}-{fit_end}"
    if mask.sum() < 10 or np.sum(v[mask] ** 2) == 0:
        return {"beta": None, "r2": None, "rmse": None, "bias": None, "n_weeks": int(mask.sum()),
                "method": "none (no usable overlap)", "fit_period": period,
                "ols_slope": None, "ols_intercept": None, "ols_rmse": None}
    mm, vv = m[mask], v[mask]
    beta = float(np.sum(mm * vv) / np.sum(vv ** 2))
    pred = beta * vv
    sse, sst = float(np.sum((mm - pred) ** 2)), float(np.sum((mm - mm.mean()) ** 2))
    slope, intercept = np.polyfit(vv, mm, 1)
    ols_pred = slope * vv + intercept
    return {"beta": round(beta, 4), "r2": round(1 - sse / sst, 4) if sst > 0 else None,
            "rmse": round(float(np.sqrt(sse / len(mm))), 3), "bias": round(float(np.mean(pred - mm)), 3),
            "n_weeks": int(mask.sum()), "method": "least squares through origin: MODIS = beta x VIIRS",
            "fit_period": period, "ols_slope": round(float(slope), 4), "ols_intercept": round(float(intercept), 3),
            "ols_rmse": round(float(np.sqrt(np.mean((mm - ols_pred) ** 2))), 3)}


def build_harmonized_series(year, modis, viirs, beta):
    """MODIS-equivalent series.
    - before overlap_fit_start_year: H = MODIS
    - overlap_fit_start_year .. viirs_only_from_year-1: H = mean(MODIS, beta*VIIRS)
    - from viirs_only_from_year: H = beta*VIIRS (falls back to MODIS if VIIRS is missing)
    Returns (harmonized, viirs_calibrated, low_confidence, source_label)."""
    year = np.asarray(year)
    m, v = np.asarray(modis, float), np.asarray(viirs, float)
    vcal = beta * v if beta is not None else np.full(len(m), np.nan)
    h = m.copy()
    src = np.full(len(m), "MODIS", dtype=object)
    if beta is not None:
        blend = (year >= CONFIG["overlap_fit_start_year"]) & (year < CONFIG["viirs_only_from_year"]) & ~np.isnan(vcal)
        h[blend] = np.where(np.isnan(m[blend]), vcal[blend], 0.5 * (m[blend] + vcal[blend]))
        src[blend] = "BLEND"
        only = (year >= CONFIG["viirs_only_from_year"]) & ~np.isnan(vcal)
        h[only] = vcal[only]
        src[only] = "VIIRS_CAL"
    low_conf = year < CONFIG["core_start_year"]
    return h, vcal, low_conf, src


# ---------------------------------------------------------------- climatology and anomalies
def compute_climatology_and_anomalies(df, baseline_start=None, baseline_end=None):
    """df needs: year, week, harmonized, low_confidence. Returns (climatology rows, df with pct_rank and z).
    Note: baseline years include the year being scored. Weeks with a near-zero baseline are not scored."""
    bs = baseline_start or CONFIG["baseline_start"]
    be = baseline_end or CONFIG["baseline_end"]
    base = df[(df["year"] >= bs) & (df["year"] <= be) & (df["low_confidence"] == 0) & df["harmonized"].notna()]
    label = f"{bs}-{be}"
    clim, stats = [], {}
    for week, g in base.groupby("week"):
        vals = g["harmonized"].to_numpy()
        med = float(np.median(vals))
        scale = 1.4826 * float(np.median(np.abs(vals - med)))
        if scale == 0:
            scale = float(vals.std())
        p10, p25, p75, p90 = (float(x) for x in np.percentile(vals, [10, 25, 75, 90]))
        stats[int(week)] = (vals, med, scale, p90)
        clim.append({"week": int(week), "median": round(med, 2), "p10": round(p10, 2), "p25": round(p25, 2),
                     "p75": round(p75, 2), "p90": round(p90, 2), "n_years": int(len(vals)), "baseline": label})
    pct, z = np.full(len(df), np.nan), np.full(len(df), np.nan)
    weeks, hv = df["week"].to_numpy(), df["harmonized"].to_numpy()
    for i in range(len(df)):
        st = stats.get(int(weeks[i]))
        if st is None or np.isnan(hv[i]) or st[3] < CONFIG["min_scored_level"]:
            continue
        vals, med, scale, _ = st
        pct[i] = 100 * (np.sum(vals < hv[i]) + 0.5 * np.sum(vals == hv[i])) / len(vals)
        if scale > 0:
            z[i] = (hv[i] - med) / scale
    out = df.copy()
    out["pct_rank"] = np.round(pct, 1)
    out["z"] = np.round(z, 2)
    return clim, out


def detect_critical_periods(clim_rows, threshold_pct=90):
    """Weeks whose climatological median is in the top (100-threshold)% of the 52 weeks, merged into periods."""
    if not clim_rows:
        return {"threshold_level": None, "periods": []}
    meds = {r["week"]: r["median"] for r in clim_rows}
    level = float(np.percentile(list(meds.values()), threshold_pct))
    weeks = sorted(w for w, m in meds.items() if m >= level and m > 0)
    periods, cur = [], []
    for w in weeks:
        if cur and w == cur[-1] + 1:
            cur.append(w)
        else:
            if cur:
                periods.append(cur)
            cur = [w]
    if cur:
        periods.append(cur)
    return {"threshold_level": round(level, 2),
            "periods": [{"start_week": p[0], "end_week": p[-1],
                         "mean_level": round(float(np.mean([meds[w] for w in p])), 2)} for p in periods]}
