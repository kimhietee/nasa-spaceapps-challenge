"""SQLite schema. Rebuilt from scratch on every pipeline run."""
import sqlite3
from pathlib import Path

SCHEMA = """
CREATE TABLE cell (cell_id INTEGER PRIMARY KEY, lon REAL, lat REAL, admin1 TEXT, admin2 TEXT,
                   is_static INTEGER, static_reason TEXT);
CREATE TABLE cell_week (cell_id INTEGER, year INTEGER, week INTEGER, sensor TEXT, cell_days INTEGER, frp_sum REAL,
                        PRIMARY KEY (cell_id, year, week, sensor));
CREATE TABLE aoi (aoi_id TEXT PRIMARY KEY, name TEXT, level TEXT, geom_json TEXT, bbox_json TEXT,
                  area_km2 REAL, description TEXT);
CREATE TABLE aoi_week (aoi_id TEXT, year INTEGER, week INTEGER, modis_cd REAL, viirs_cd REAL, viirs_cal_cd REAL,
                       harmonized REAL, h_source TEXT, pct_rank REAL, z REAL, low_confidence INTEGER,
                       PRIMARY KEY (aoi_id, year, week));
CREATE TABLE calibration (aoi_id TEXT, season TEXT, beta REAL, r2 REAL, rmse REAL, bias REAL, n_weeks INTEGER,
                          method TEXT, fit_period TEXT, ols_slope REAL, ols_intercept REAL, ols_rmse REAL);
CREATE TABLE climatology (aoi_id TEXT, week INTEGER, median REAL, p10 REAL, p25 REAL, p75 REAL, p90 REAL,
                          n_years INTEGER, baseline TEXT, PRIMARY KEY (aoi_id, week));
CREATE TABLE critical_period (aoi_id TEXT, threshold INTEGER, start_week INTEGER, end_week INTEGER,
                              mean_level REAL, threshold_level REAL);
CREATE TABLE ingest_log (run_id TEXT, source TEXT, data_status TEXT, date_from TEXT, date_to TEXT,
                         rows INTEGER, created_at TEXT, notes TEXT);
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE INDEX idx_cell_week_week ON cell_week (year, week);
CREATE INDEX idx_cell_xy ON cell (lon, lat);
"""


def init_db(db_path):
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    conn = sqlite3.connect(db_path)
    conn.executescript(SCHEMA)
    return conn
