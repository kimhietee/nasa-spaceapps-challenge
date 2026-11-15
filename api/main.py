"""FIREWATCH PH API. Reads the SQLite database built by `python -m firewatch.pipeline`.

    uvicorn api.main:app --reload      then open http://127.0.0.1:8000/docs
"""
import io
import json
import os
import sqlite3
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd
import shapely
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel
from shapely.geometry import shape

from firewatch.config import CONFIG, DB_PATH
from firewatch.geo import inside
from firewatch.harmonize import (aggregate_aoi, build_harmonized_series, compute_climatology_and_anomalies,
                                 detect_critical_periods, make_grid)

app = FastAPI(title="FIREWATCH PH API", version="0.2.0",
              description="Harmonized MODIS + VIIRS burning activity (index of detected activity, not fires or burned area).")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

SERIES_COL = {"harmonized": "harmonized", "modis": "modis_cd", "viirs": "viirs_cd", "viirs_cal": "viirs_cal_cd"}
MAX_POLY_VERTICES = 500


# ------------------------------------------------------------------ helpers
def get_db():
    path = Path(os.getenv("FIREWATCH_DB", DB_PATH))
    if not path.exists():
        raise HTTPException(503, "Database not built yet. Run: python -m firewatch.pipeline")
    conn = sqlite3.connect(path)
    try:
        yield conn
    finally:
        conn.close()


def q(conn, sql, params=()):
    return pd.read_sql_query(sql, conn, params=params)


def records(df):
    """DataFrame -> list of dicts with NaN converted to None (valid JSON)."""
    return df.astype(object).where(df.notna(), None).to_dict("records")


def meta(conn):
    m = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    return {"data_status": m.get("data_status"), "data_version": f"{m.get('data_status')}@{m.get('built_at')}",
            "baseline": f"{CONFIG['baseline_start']}-{CONFIG['baseline_end']}"}


def check_aoi(conn, aoi_id):
    row = conn.execute("SELECT 1 FROM aoi WHERE aoi_id=?", (aoi_id,)).fetchone()
    if not row:
        raise HTTPException(404, f"Unknown AOI '{aoi_id}'")


def weekly_frame(conn, aoi_id):
    return q(conn, "SELECT * FROM aoi_week WHERE aoi_id=? ORDER BY year, week", (aoi_id,))


def annual_summary(df):
    """Annual totals with robust z-scores (complete, non-low-confidence years only)."""
    g = df.groupby("year").agg(total=("harmonized", "sum"), weeks=("harmonized", "count"),
                               low=("low_confidence", "max")).reset_index()
    ok = g[(g.weeks == 52) & (g.low == 0)]
    med = ok.total.median()
    scale = 1.4826 * np.median(np.abs(ok.total - med)) or ok.total.std() or np.nan
    g["z"] = np.where((g.weeks == 52) & (g.low == 0), (g.total - med) / scale, np.nan)
    g["total"] = g.total.round(1)
    g["z"] = g.z.round(2)
    return g


# ------------------------------------------------------------------ endpoints
@app.get("/api/health")
def health(conn=Depends(get_db)):
    return {"status": "ok", **meta(conn)}


@app.get("/api/aois")
def list_aois(conn=Depends(get_db)):
    df = q(conn, "SELECT aoi_id, name, level, bbox_json, area_km2, description FROM aoi")
    df["bbox"] = df.pop("bbox_json").apply(json.loads)
    return {"aois": records(df), **meta(conn)}


@app.get("/api/aois/{aoi_id}/geometry")
def aoi_geometry(aoi_id: str, conn=Depends(get_db)):
    check_aoi(conn, aoi_id)
    geom = conn.execute("SELECT geom_json FROM aoi WHERE aoi_id=?", (aoi_id,)).fetchone()[0]
    return {"type": "Feature", "properties": {"aoi_id": aoi_id}, "geometry": json.loads(geom)}


@app.get("/api/aois/{aoi_id}/weekly")
def weekly(aoi_id: str, from_year: int = Query(2000, alias="from", ge=2000, le=2100),
           to_year: int = Query(2100, alias="to", ge=2000, le=2100),
           series: Literal["harmonized", "modis", "viirs", "viirs_cal"] = "harmonized",
           z_threshold: float = Query(CONFIG["default_z_threshold"], ge=0.5, le=10),
           conn=Depends(get_db)):
    check_aoi(conn, aoi_id)
    df = weekly_frame(conn, aoi_id)
    df = df[df.year.between(from_year, to_year)]
    out = pd.DataFrame({"year": df.year, "week": df.week, "value": df[SERIES_COL[series]]})
    if series == "harmonized":   # percentile / anomaly only make sense for the harmonized series
        out["pct_rank"], out["z"], out["source"] = df.pct_rank, df.z, df.h_source
        out["is_anomaly"] = (df.z.abs() >= z_threshold).fillna(False)
    out["low_confidence"] = df.low_confidence.astype(bool)
    return {"aoi_id": aoi_id, "series": series, "unit": "burning cell-days per week (MODIS-equivalent)" if series != "viirs" else "burning cell-days per week (VIIRS)",
            "data": records(out), **meta(conn)}


@app.get("/api/aois/{aoi_id}/climatology")
def climatology(aoi_id: str, conn=Depends(get_db)):
    check_aoi(conn, aoi_id)
    df = q(conn, "SELECT week, median, p10, p25, p75, p90, n_years, baseline FROM climatology WHERE aoi_id=? ORDER BY week", (aoi_id,))
    return {"aoi_id": aoi_id, "data": records(df), **meta(conn)}


@app.get("/api/aois/{aoi_id}/anomalies")
def anomalies(aoi_id: str, z: float = Query(CONFIG["default_z_threshold"], ge=0.5, le=10),
              limit: int = Query(50, ge=1, le=500), conn=Depends(get_db)):
    check_aoi(conn, aoi_id)
    df = weekly_frame(conn, aoi_id)
    weeks = df[(df.z.abs() >= z) & (df.low_confidence == 0)].copy()
    weeks["direction"] = np.where(weeks.z > 0, "higher than normal", "lower than normal")
    weeks = weeks.reindex(weeks.z.abs().sort_values(ascending=False).index).head(limit)
    years = annual_summary(df)
    top_years = years.dropna(subset=["z"]).reindex(years.dropna(subset=["z"]).z.abs().sort_values(ascending=False).index).head(5)
    return {"aoi_id": aoi_id, "z_threshold": z,
            "weeks": records(weeks[["year", "week", "harmonized", "pct_rank", "z", "direction"]]),
            "top_years": records(top_years[["year", "total", "z"]]),
            "note": "z = how unusual versus the typical value for that week (robust z-score). Weeks with near-zero baselines are not scored.",
            **meta(conn)}


@app.get("/api/aois/{aoi_id}/critical-periods")
def critical_periods(aoi_id: str, threshold: int = Query(90, description="75, 80 or 90"), conn=Depends(get_db)):
    check_aoi(conn, aoi_id)
    if threshold not in (75, 80, 90):
        raise HTTPException(422, "threshold must be 75, 80 or 90")
    df = q(conn, "SELECT start_week, end_week, mean_level, threshold_level FROM critical_period WHERE aoi_id=? AND threshold=? ORDER BY start_week", (aoi_id, threshold))
    return {"aoi_id": aoi_id, "threshold_percentile": threshold, "periods": records(df), **meta(conn)}


@app.get("/api/aois/{aoi_id}/calibration")
def calibration(aoi_id: str, conn=Depends(get_db)):
    """Parameters plus an annual before/after series for the harmonization validation chart."""
    check_aoi(conn, aoi_id)
    cal = q(conn, "SELECT * FROM calibration WHERE aoi_id=?", (aoi_id,))
    df = weekly_frame(conn, aoi_id)
    g = df.groupby("year").agg(modis=("modis_cd", "sum"), viirs=("viirs_cd", "sum"), viirs_cal=("viirs_cal_cd", "sum"),
                               harmonized=("harmonized", "sum"), weeks_with_viirs=("viirs_cd", "count")).reset_index()
    g["viirs"] = g.viirs.where(g.weeks_with_viirs > 0)
    g["viirs_cal"] = g.viirs_cal.where(g.weeks_with_viirs > 0)
    g["raw_combined"] = g.modis + g.viirs.fillna(0)   # the misleading 'just add them' series
    return {"aoi_id": aoi_id, "calibration": records(cal)[0] if len(cal) else None,
            "annual": records(g.round(1)),
            "note": "raw_combined adds MODIS and VIIRS counts naively and jumps when VIIRS starts; harmonized does not.",
            **meta(conn)}


@app.get("/api/aois/{aoi_id}/summary")
def summary(aoi_id: str, conn=Depends(get_db)):
    """Everything the summary cards need in one call."""
    check_aoi(conn, aoi_id)
    df = weekly_frame(conn, aoi_id)
    cp = q(conn, "SELECT start_week, end_week, mean_level FROM critical_period WHERE aoi_id=? AND threshold=90", (aoi_id,))
    scored = df.dropna(subset=["z"])
    latest = scored.iloc[-1] if len(scored) else None
    years = annual_summary(df).dropna(subset=["z"])
    top = years.reindex(years.z.abs().sort_values(ascending=False).index).head(1)
    cal = q(conn, "SELECT beta, r2, rmse, n_weeks FROM calibration WHERE aoi_id=?", (aoi_id,))
    return {"aoi_id": aoi_id, "critical_periods_p90": records(cp),
            "latest_scored_week": None if latest is None else {"year": int(latest.year), "week": int(latest.week),
                                                               "pct_rank": latest.pct_rank, "z": latest.z},
            "most_unusual_year": records(top[["year", "total", "z"]])[0] if len(top) else None,
            "calibration": records(cal)[0] if len(cal) else None, **meta(conn)}


@app.get("/api/aois/{aoi_id}/week-detail")
def week_detail(aoi_id: str, year: int = Query(ge=2000, le=2100), week: int = Query(ge=1, le=52),
                include_static: bool = False, conn=Depends(get_db)):
    """Burning cells inside the AOI for one week (for the map drill-down)."""
    check_aoi(conn, aoi_id)
    geom = json.loads(conn.execute("SELECT geom_json FROM aoi WHERE aoi_id=?", (aoi_id,)).fetchone()[0])
    minx, miny, maxx, maxy = shape(geom).bounds
    df = q(conn, """SELECT c.cell_id, c.lon, c.lat, c.is_static, w.sensor, w.cell_days, w.frp_sum
                    FROM cell_week w JOIN cell c ON c.cell_id = w.cell_id
                    WHERE w.year=? AND w.week=? AND c.lon BETWEEN ? AND ? AND c.lat BETWEEN ? AND ?""",
           (year, week, minx, maxx, miny, maxy))
    df = df[inside(geom, df.lon, df.lat)] if len(df) else df
    if not include_static:
        df = df[df.is_static == 0]
    return {"aoi_id": aoi_id, "year": year, "week": week, "count": len(df), "cells": records(df), **meta(conn)}


@app.get("/api/aois/{aoi_id}/export.csv")
def export_csv(aoi_id: str, conn=Depends(get_db)):
    check_aoi(conn, aoi_id)
    df = weekly_frame(conn, aoi_id).drop(columns=["aoi_id"])
    buf = io.StringIO()
    df.to_csv(buf, index=False)
    return Response(buf.getvalue(), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="firewatch_{aoi_id}_weekly.csv"'})


class PolygonBody(BaseModel):
    geometry: dict   # GeoJSON Polygon or MultiPolygon, [lon, lat] order


@app.post("/api/aoi/weekly")
def polygon_weekly(body: PolygonBody, conn=Depends(get_db)):
    """Harmonized weekly series, climatology and critical periods for a user-drawn polygon.
    Uses the national (PH) calibration factor; static heat sources are excluded."""
    try:
        geom = shape(body.geometry)
    except Exception:
        raise HTTPException(422, "geometry must be a valid GeoJSON Polygon or MultiPolygon")
    if geom.geom_type not in ("Polygon", "MultiPolygon") or not geom.is_valid or geom.is_empty:
        raise HTTPException(422, "geometry must be a valid, non-empty Polygon or MultiPolygon")
    if shapely.get_num_coordinates(geom) > MAX_POLY_VERTICES:
        raise HTTPException(422, f"polygon has too many vertices (max {MAX_POLY_VERTICES})")
    minx, miny, maxx, maxy = geom.bounds
    cells = q(conn, "SELECT cell_id, lon, lat FROM cell WHERE is_static=0 AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?",
              (minx, maxx, miny, maxy))
    ids = cells.cell_id[inside(body.geometry, cells.lon, cells.lat)] if len(cells) else cells.cell_id
    if len(ids) == 0:
        raise HTTPException(404, "No detections recorded inside this polygon (or the polygon is outside the data area).")
    conn.execute("CREATE TEMP TABLE IF NOT EXISTS sel (cell_id INTEGER)")
    conn.execute("DELETE FROM sel")
    conn.executemany("INSERT INTO sel VALUES (?)", [(int(i),) for i in ids])
    sub = q(conn, """SELECT w.year, w.week, w.sensor, SUM(w.cell_days) AS cell_days
                     FROM cell_week w JOIN sel ON sel.cell_id = w.cell_id GROUP BY w.year, w.week, w.sensor""")
    m = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    ranges = {"modis": tuple(json.loads(m["modis_range"])), "viirs": tuple(json.loads(m["viirs_range"]))}
    df = aggregate_aoi(sub, make_grid(range(int(m["min_year"]), int(m["max_year"]) + 1), ranges))
    beta = conn.execute("SELECT beta FROM calibration WHERE aoi_id='PH'").fetchone()[0]
    h, vcal, low, src = build_harmonized_series(df.year, df.modis_cd, df.viirs_cd, beta)
    df["viirs_cal_cd"], df["harmonized"], df["h_source"], df["low_confidence"] = vcal, h, src, low.astype(int)
    clim, scored = compute_climatology_and_anomalies(df)
    out = scored[["year", "week", "modis_cd", "viirs_cd", "harmonized", "pct_rank", "z", "low_confidence"]]
    return {"cells_in_polygon": int(len(ids)), "calibration_beta_used": beta, "data": records(out),
            "climatology": clim, "critical_periods_p90": detect_critical_periods(clim, 90), **meta(conn)}


from .comparison import router as comparison_router

app.include_router(comparison_router)


@app.get("/prototype", include_in_schema=False)
def prototype_preview():
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).resolve().parent.parent / "frontend/prototype/index.html")
