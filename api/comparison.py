"""Serve Indonesia sensor comparisons from SQLite, independently of the legacy PH database."""
from typing import Literal

from fastapi import APIRouter, Query

from firewatch.indonesia import database_health, weekly_comparison

router = APIRouter()


@router.get("/api/comparison/health")
def comparison_health():
    return database_health()


@router.get("/api/comparison/weekly")
def comparison_weekly(sensor: Literal["MODIS", "VIIRS_SNPP"] | None = None,
                      year: int = Query(2024, ge=2022, le=2025)):
    return weekly_comparison(year, sensor)
