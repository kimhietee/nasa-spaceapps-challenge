"""Read-only access to the Indonesia detections database."""
from contextlib import contextmanager
from functools import lru_cache
import os
from pathlib import Path
import sqlite3

from fastapi import HTTPException

from .comparison import grid_cell

DEFAULT_PATH = Path(__file__).resolve().parents[1] / "data/indonesia.db"
DATABASE_ERROR = "Indonesia database unavailable. Check data/indonesia.db or FIREWATCH_INDONESIA_DB."
LIMITATIONS = [
    "Country membership inherited from archive requests; no boundary clipping.",
    "Coverage unknown; absent detections are not confirmed zeros.",
    "Grid cells have different physical areas across latitude.",
    "Separate sensor series; no calibration or historical anomaly scoring.",
]


def database_path():
    return Path(os.getenv("FIREWATCH_INDONESIA_DB", str(DEFAULT_PATH))).resolve()


@contextmanager
def open_database(path):
    conn = None
    try:
        # mode=ro prevents a missing path from becoming an empty database.
        conn = sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=5)
        yield conn
    except sqlite3.Error as error:
        raise HTTPException(503, DATABASE_ERROR) from error
    finally:
        if conn is not None:
            conn.close()


def read_metadata(conn):
    metadata = dict(conn.execute("SELECT key, value FROM meta"))
    if (metadata.get("schema_version") != "indonesia-detections-1.0"
            or metadata.get("country_code") != "IDN"
            or metadata.get("data_status") != "NASA FIRMS"):
        raise HTTPException(503, "Expected an Indonesia FIRMS detections database (schema version 1.0).")
    return {
        "data_status": metadata["data_status"], "country_code": metadata["country_code"],
        "data_version": f"NASA FIRMS@{metadata.get('built_at_utc')}",
        "database_schema_version": metadata["schema_version"],
    }


def database_health():
    with open_database(database_path()) as conn:
        metadata = read_metadata(conn)
        conn.execute("""SELECT sensor, acquired_at_utc, longitude, latitude,
                               detection_type, confidence_numeric, confidence_category
                        FROM detection LIMIT 0""")
        count, first, last = conn.execute(
            "SELECT SUM(record_count), MIN(first_acquired_at_utc), MAX(last_acquired_at_utc) FROM source_file"
        ).fetchone()
    return {"status": "ok", "database": "sqlite", "source_record_count": count or 0,
            "first_acquired_at_utc": first, "last_acquired_at_utc": last, **metadata}


def database_signature(path):
    try:
        stat = path.stat()
        wal_path = path.with_name(path.name + "-wal")
        wal = wal_path.stat() if wal_path.exists() else None
        return (stat.st_mtime_ns, stat.st_size,
                None if wal is None else (wal.st_mtime_ns, wal.st_size))
    except OSError as error:
        raise HTTPException(503, DATABASE_ERROR) from error


def grid_cell_id(longitude, latitude):
    x, y = grid_cell(longitude, latitude)
    return f"{x}:{y}"


@lru_cache(maxsize=16)
def _weekly_counts(path, signature, year, sensor):
    """Cache only small aggregates, keyed by the database file's current version."""
    params = [f"{year}-01-01T00:00:00Z", f"{year + 1}-01-01T00:00:00Z"]
    sensor_filter = ""
    if sensor is not None:
        sensor_filter = " AND sensor = ?"
        params.append(sensor)
    with open_database(Path(path)) as conn:
        metadata = read_metadata(conn)
        conn.create_function("grid_cell_id", 2, grid_cell_id, deterministic=True)
        # Deduplicate by cell, UTC date, and sensor before calculating weekly totals.
        rows = conn.execute("""
            WITH cells AS (
                SELECT DISTINCT sensor, substr(acquired_at_utc, 1, 10) AS utc_date,
                                grid_cell_id(longitude, latitude) AS cell_id
                FROM detection
                WHERE acquired_at_utc >= ? AND acquired_at_utc < ?
                  AND detection_type = 0
                  AND ((sensor = 'MODIS' AND confidence_numeric >= 30)
                    OR (sensor = 'VIIRS_SNPP' AND confidence_category IN ('n', 'h')))
            """ + sensor_filter + """
            ), daily AS (
                SELECT sensor, utc_date, COUNT(*) AS active_cells
                FROM cells GROUP BY sensor, utc_date
            )
            SELECT sensor,
                   min(52, (CAST(strftime('%j', utc_date) AS INTEGER) - 1) / 7 + 1) AS week,
                   SUM(active_cells), COUNT(*)
            FROM daily GROUP BY sensor, week ORDER BY week, sensor
        """, params).fetchall()
    return tuple(rows), metadata


def weekly_comparison(year, sensor=None):
    path = database_path()
    rows, metadata = _weekly_counts(str(path), database_signature(path), year, sensor)
    counts = {(name, week): (count, days) for name, week, count, days in rows}
    sensors = (sensor,) if sensor is not None else ("MODIS", "VIIRS_SNPP")
    weekly = []
    for week in range(1, 53):
        for name in sensors:
            count, days = counts.get((name, week), (None, 0))
            weekly.append({"year": year, "week": week, "sensor": name,
                           "active_cell_days": count, "days_with_retained_detections": days,
                           "coverage_status": "unknown"})
    return {"schema_version": "1.0", "mode": "sensor_comparison", "year": year,
            "geographic_scope": "Indonesia archive request", "unit": "active cell-days per week",
            "calibrated": False, "coverage_status": "unknown",
            "grid": {"resolution_degrees": 0.01, "origin_lon": -180, "origin_lat": -90},
            "data": weekly, "limitations": list(LIMITATIONS), **metadata}
