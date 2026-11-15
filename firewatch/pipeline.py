"""Build the FIREWATCH PH database.

    python -m firewatch.pipeline                      # demo (synthetic) data
    python -m firewatch.pipeline --firms-dir data\\raw  # real NASA FIRMS CSV downloads
"""
import argparse
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

from .config import CONFIG, DB_PATH, PRESET_AOIS
from .db import init_db
from .demo_data import make_demo_firms
from .geo import geojson_bbox, inside, near_volcano, snap_cells
from .harmonize import (aggregate_aoi, build_harmonized_series, calibrate_overlap,
                        compute_climatology_and_anomalies, detect_critical_periods, make_grid, normalize_sensor)


def load_firms_csvs(firms_dir):
    files = sorted(Path(firms_dir).rglob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No .csv files found in {firms_dir}")
    frames = [pd.read_csv(f, low_memory=False) for f in files]
    return pd.concat(frames, ignore_index=True)


def clean_firms(raw):
    """Steps 1-3: parse, clip to the Philippines box, normalize sensors, quality filters, dates."""
    w, s, e, n = CONFIG["ph_bbox"]
    raw = raw.copy()
    for col in ("latitude", "longitude"):
        raw[col] = pd.to_numeric(raw[col], errors="coerce")
    raw["frp"] = pd.to_numeric(raw["frp"], errors="coerce").fillna(0.0) if "frp" in raw else 0.0
    raw["acq_date"] = pd.to_datetime(raw["acq_date"], errors="coerce")
    raw = raw.dropna(subset=["latitude", "longitude", "acq_date"])
    raw = raw[raw.longitude.between(w, e) & raw.latitude.between(s, n)].reset_index(drop=True)

    raw["sensor"] = normalize_sensor(raw.get("instrument"), raw.get("satellite"), len(raw))

    keep = np.ones(len(raw), dtype=bool)
    is_modis = (raw["sensor"] == "MODIS").to_numpy()
    conf = raw["confidence"] if "confidence" in raw else pd.Series([np.nan] * len(raw))
    modis_conf = pd.to_numeric(conf, errors="coerce").fillna(0).to_numpy()
    keep &= ~is_modis | (modis_conf >= CONFIG["modis_min_confidence"])
    viirs_conf = conf.astype(str).str.strip().str.lower().to_numpy()
    keep &= is_modis | ~np.isin(viirs_conf, CONFIG["viirs_drop_confidence"])
    if "type" in raw.columns:
        ftype = pd.to_numeric(raw["type"], errors="coerce").fillna(0).astype(int).to_numpy()
        keep &= ~np.isin(ftype, CONFIG["drop_firms_types"])
    cleaned = raw[keep].copy()

    # Core VIIRS series = Suomi-NPP only (a constant number of overpasses per day). If the user only has
    # another VIIRS satellite, keep whatever VIIRS data exists.
    if (cleaned["sensor"] == "VIIRS_SNPP").any():
        cleaned = cleaned[cleaned["sensor"].isin(["MODIS", "VIIRS_SNPP"])].copy()

    cleaned["year"] = cleaned["acq_date"].dt.year.astype(int)
    cleaned["month"] = cleaned["acq_date"].dt.month.astype(int)
    doy = cleaned["acq_date"].dt.day_of_year.astype(int)
    cleaned["week"] = np.minimum(52, (doy - 1) // 7 + 1)   # fixed 7-day bins, not ISO weeks
    cleaned["utc_date"] = cleaned["acq_date"].dt.strftime("%Y-%m-%d")
    return cleaned


def build_cells(cleaned):
    """Steps 4-5: snap to the 0.01 degree grid and flag static heat sources."""
    cleaned["cell_id"], cleaned["cell_lon"], cleaned["cell_lat"] = snap_cells(cleaned["longitude"], cleaned["latitude"])
    stats = (cleaned.groupby(["cell_id", "cell_lon", "cell_lat"])
             .agg(n_years=("year", "nunique"), n_months=("month", "nunique")).reset_index())
    volc = near_volcano(stats["cell_lon"], stats["cell_lat"])
    persistent = ((stats["n_years"] >= CONFIG["static_min_years"]) &
                  (stats["n_months"] >= CONFIG["static_min_months"])).to_numpy()
    is_static = (volc != None) | persistent  # noqa: E711
    reason = np.where(volc != None, volc, np.where(persistent, "Persistent multi-year thermal source", None))  # noqa: E711
    cells = pd.DataFrame({"cell_id": stats["cell_id"], "lon": stats["cell_lon"], "lat": stats["cell_lat"],
                          "is_static": is_static.astype(int), "static_reason": reason})
    geoms = {a["aoi_id"]: a["geom"] for a in PRESET_AOIS}
    lon, lat = cells["lon"].to_numpy(), cells["lat"].to_numpy()
    cells["admin1"] = np.select([inside(geoms["MINDANAO"], lon, lat), inside(geoms["CENTRAL_LUZON"], lon, lat),
                                 inside(geoms["NEGROS"], lon, lat)], ["Mindanao", "Central Luzon", "Negros"], "Philippines")
    cells["admin2"] = np.select([inside(geoms["VALENCIA"], lon, lat), inside(geoms["BUKIDNON"], lon, lat)],
                                ["Valencia City", "Bukidnon"], "")
    return cells


def build_cell_weeks(cleaned):
    """Step 6: one flag per cell, UTC day and sensor, then sum to cell-days per week."""
    cell_days = (cleaned.groupby(["cell_id", "year", "week", "utc_date", "sensor"], as_index=False)
                 .agg(frp_sum=("frp", "sum")))
    cell_days["cell_days"] = 1
    cw = (cell_days.groupby(["cell_id", "year", "week", "sensor"], as_index=False)
          .agg(cell_days=("cell_days", "sum"), frp_sum=("frp_sum", "sum")))
    cw["frp_sum"] = cw["frp_sum"].round(2)
    return cw


def sensor_ranges(cleaned):
    out = {}
    for key, mask in (("modis", cleaned["sensor"] == "MODIS"), ("viirs", cleaned["sensor"].str.startswith("VIIRS"))):
        sub = cleaned.loc[mask, "acq_date"]
        out[key] = (sub.min().strftime("%Y-%m-%d"), sub.max().strftime("%Y-%m-%d")) if len(sub) else (None, None)
    return out


def run_pipeline(firms_dir=None, db_path=DB_PATH, seed=42):
    demo = firms_dir is None
    data_status = "DEMO DATA" if demo else "NASA FIRMS"
    source_label = "SYNTHETIC_DEMO" if demo else "USER_FIRMS_ARCHIVE"
    raw = make_demo_firms(seed=seed) if demo else load_firms_csvs(firms_dir)
    total_raw = len(raw)

    cleaned = clean_firms(raw)
    if cleaned.empty:
        raise ValueError("No detections left after cleaning. Check bbox, columns and filters.")
    cells = build_cells(cleaned)
    cell_week = build_cell_weeks(cleaned)
    static_ids = set(cells.loc[cells.is_static == 1, "cell_id"])
    cw_veg = cell_week[~cell_week["cell_id"].isin(static_ids)]   # default series excludes static sources

    ranges = sensor_ranges(cleaned)
    years = range(int(cleaned["year"].min()), int(cleaned["year"].max()) + 1)
    grid = make_grid(years, ranges)

    conn = init_db(db_path)
    cells.to_sql("cell", conn, if_exists="append", index=False)
    cell_week.to_sql("cell_week", conn, if_exists="append", index=False)
    cur = conn.cursor()
    summary = {"data_status": data_status, "raw_rows": int(total_raw), "cleaned_rows": int(len(cleaned)),
               "cells": int(len(cells)), "static_cells": int(cells["is_static"].sum()), "aois": {}}

    for aoi in PRESET_AOIS:
        aid, geom = aoi["aoi_id"], aoi["geom"]
        cur.execute("INSERT INTO aoi VALUES (?,?,?,?,?,?,?)",
                    (aid, aoi["name"], aoi["level"], json.dumps(geom), json.dumps(geojson_bbox(geom)),
                     aoi["area_km2"], aoi["description"]))
        in_ids = set(cells.loc[inside(geom, cells["lon"], cells["lat"]), "cell_id"])
        df = aggregate_aoi(cw_veg[cw_veg["cell_id"].isin(in_ids)], grid)

        cal = calibrate_overlap(df["year"], df["modis_cd"], df["viirs_cd"])
        h, vcal, low_conf, src = build_harmonized_series(df["year"], df["modis_cd"], df["viirs_cd"], cal["beta"])
        df["viirs_cal_cd"], df["harmonized"], df["h_source"] = vcal, h, src
        df["low_confidence"] = low_conf.astype(int)
        clim, scored = compute_climatology_and_anomalies(df)
        scored["aoi_id"] = aid
        cols = ["aoi_id", "year", "week", "modis_cd", "viirs_cd", "viirs_cal_cd", "harmonized", "h_source",
                "pct_rank", "z", "low_confidence"]
        scored[cols].to_sql("aoi_week", conn, if_exists="append", index=False)

        cur.execute("INSERT INTO calibration VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (aid, "all", cal["beta"], cal["r2"], cal["rmse"], cal["bias"], cal["n_weeks"], cal["method"],
                     cal["fit_period"], cal["ols_slope"], cal["ols_intercept"], cal["ols_rmse"]))
        for c in clim:
            cur.execute("INSERT INTO climatology VALUES (?,?,?,?,?,?,?,?,?)",
                        (aid, c["week"], c["median"], c["p10"], c["p25"], c["p75"], c["p90"], c["n_years"], c["baseline"]))
        for thr in (75, 80, 90):
            cp = detect_critical_periods(clim, thr)
            for p in cp["periods"]:
                cur.execute("INSERT INTO critical_period VALUES (?,?,?,?,?,?)",
                            (aid, thr, p["start_week"], p["end_week"], p["mean_level"], cp["threshold_level"]))
        summary["aois"][aid] = {"cells_in_aoi": len(in_ids), "beta": cal["beta"], "r2": cal["r2"], "rmse": cal["rmse"]}

    now = datetime.datetime.now(datetime.timezone.utc)
    cur.execute("INSERT INTO ingest_log VALUES (?,?,?,?,?,?,?,?)",
                (f"run-{now:%Y%m%d%H%M%S}", source_label, data_status, str(cleaned["acq_date"].min().date()),
                 str(cleaned["acq_date"].max().date()), int(total_raw), now.isoformat(),
                 "Harmonized MODIS + VIIRS S-NPP pipeline (cell-days, weekly bins, beta calibration)"))
    meta = {"data_status": data_status, "built_at": now.isoformat(), "min_year": years.start, "max_year": years.stop - 1,
            "modis_range": json.dumps(ranges["modis"]), "viirs_range": json.dumps(ranges["viirs"]),
            "config": json.dumps({k: v for k, v in CONFIG.items()})}
    cur.executemany("INSERT INTO meta VALUES (?,?)", list(meta.items()))
    conn.commit()
    conn.close()
    return summary


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Build the FIREWATCH PH harmonized SQLite database")
    ap.add_argument("--firms-dir", default=None, help="Folder with real NASA FIRMS CSVs (omit for demo data)")
    ap.add_argument("--db-path", default=str(DB_PATH), help="Output SQLite path")
    args = ap.parse_args()
    print(json.dumps(run_pipeline(args.firms_dir, args.db_path), indent=2))
