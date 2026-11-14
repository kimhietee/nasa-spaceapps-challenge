"""Serve the precomputed 2024 comparison independently of the legacy database."""
import json
import os
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException

router = APIRouter()
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data/processed/comparison_run_01/comparison.json"


@router.get("/api/comparison/weekly")
def comparison_weekly(sensor: Literal["MODIS", "VIIRS_SNPP"] | None = None):
    path = Path(os.getenv("FIREWATCH_COMPARISON", str(DEFAULT_PATH)))
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload["schema_version"] != "1.0" or payload["mode"] != "sensor_comparison":
            raise ValueError("Unsupported comparison schema")
        rows = payload["weekly"]
        if not isinstance(rows, list) or any(
            row["sensor"] not in {"MODIS", "VIIRS_SNPP"} or row["year"] != 2024
            or not 1 <= row["week"] <= 52
            or row["coverage_status"] != "unknown"
            or (row["active_cell_days"] is not None and
                (not isinstance(row["active_cell_days"], int) or row["active_cell_days"] < 0))
            for row in rows
        ):
            raise ValueError("Invalid weekly rows")
        grid, limitations = payload["grid"], payload["limitations"]
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        raise HTTPException(503, "Comparison unavailable. Generate a valid comparison file first.")
    return {"schema_version": "1.0", "mode": "sensor_comparison",
            "data_status": "NASA FIRMS", "geographic_scope": "Indonesia archive request",
            "unit": "active cell-days per week", "calibrated": False,
            "coverage_status": "unknown", "grid": grid,
            "data": [row for row in rows if sensor is None or row["sensor"] == sensor],
            "limitations": limitations}
