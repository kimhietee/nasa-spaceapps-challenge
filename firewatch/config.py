"""All tunable settings and preset areas live here. Edit this file, not the pipeline code."""
import math
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.getenv("FIREWATCH_DB", ROOT / "data" / "firewatch.db"))

CONFIG = {
    # West, South, East, North (approximate, verify). Also defines the fixed grid origin.
    "ph_bbox": (116.9, 4.5, 126.7, 21.2),
    "grid_res_deg": 0.01,                 # ~1 km cells
    # Quality filters
    "modis_min_confidence": 30,
    "viirs_drop_confidence": ["l", "low"],
    "drop_firms_types": [1, 2, 3],        # FIRMS 'type': 1 volcano, 2 static land source, 3 offshore
    # Static heat-source detection
    "static_min_years": 8,
    "static_min_months": 9,
    "volcano_radius_km": 5.0,
    # Harmonization rules
    "viirs_start_year": 2012,
    "overlap_fit_start_year": 2013,       # first full VIIRS year, used to fit beta
    "viirs_only_from_year": 2022,         # from here H = beta * VIIRS (MODIS Terra/Aqua aging)
    "core_start_year": 2003,              # Terra + Aqua both operating; earlier years = low confidence
    # Climatology / anomalies
    "baseline_start": 2003,
    "baseline_end": 2022,
    "default_z_threshold": 2.0,
    "min_scored_level": 3.0,              # skip scoring weeks whose baseline p90 is below this
}

# Approximate volcano locations (lon, lat). [verify] and extend as needed.
VOLCANOES = [
    ("Taal", 120.993, 14.002),
    ("Mayon", 123.686, 13.257),
    ("Kanlaon", 123.132, 10.412),
    ("Bulusan", 124.052, 12.770),
    ("Hibok-Hibok", 124.673, 9.203),
]


def box_geom(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def box_area_km2(w, s, e, n):
    mid = math.radians((s + n) / 2)
    return round((e - w) * 111.32 * math.cos(mid) * (n - s) * 110.57, 1)


def _aoi(aoi_id, name, level, box, description):
    return {"aoi_id": aoi_id, "name": name, "level": level, "geom": box_geom(*box),
            "area_km2": box_area_km2(*box), "description": description}


NOTE = "APPROXIMATE BOX, replace with an official boundary polygon (check license)."
PRESET_AOIS = [
    _aoi("PH", "Philippines", "country", CONFIG["ph_bbox"], NOTE),
    _aoi("MINDANAO", "Mindanao", "region", (121.8, 5.3, 126.7, 10.0), NOTE),
    _aoi("BUKIDNON", "Bukidnon", "province", (124.2, 7.3, 125.4, 8.7), NOTE),
    _aoi("VALENCIA", "Valencia City", "city", (124.95, 7.75, 125.25, 8.1), NOTE),
    _aoi("CENTRAL_LUZON", "Central Luzon", "region", (119.7, 14.3, 121.6, 16.4), NOTE),
    _aoi("NEGROS", "Negros Island", "island", (122.3, 9.0, 123.6, 11.1), NOTE),
]
