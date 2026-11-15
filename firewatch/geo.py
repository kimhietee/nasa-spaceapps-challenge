"""Grid snapping and polygon helpers (all vectorized)."""
import numpy as np
import shapely
from shapely.geometry import shape

from .config import CONFIG, VOLCANOES

W, S, E, N = CONFIG["ph_bbox"]
RES = CONFIG["grid_res_deg"]
NX = int(round((E - W) / RES)) + 1


def snap_cells(lon, lat):
    """Return (cell_id, cell_lon, cell_lat) arrays. IDs are stable because the grid origin is fixed."""
    lon = np.asarray(lon, dtype=float)
    lat = np.asarray(lat, dtype=float)
    ix = np.floor((lon - W) / RES).astype(np.int64)
    iy = np.floor((lat - S) / RES).astype(np.int64)
    ids = iy * NX + ix
    return ids, W + (ix + 0.5) * RES, S + (iy + 0.5) * RES


def inside(geom_json, lon, lat):
    """Boolean mask: which points fall inside (or on the edge of) a GeoJSON polygon."""
    return shapely.intersects_xy(shape(geom_json), np.asarray(lon, float), np.asarray(lat, float))


def geojson_bbox(geom_json):
    minx, miny, maxx, maxy = shape(geom_json).bounds
    return [minx, miny, maxx, maxy]


def haversine_km(lon1, lat1, lon2, lat2):
    lon1, lat1, lon2, lat2 = map(np.radians, (lon1, lat1, lon2, lat2))
    a = np.sin((lat2 - lat1) / 2) ** 2 + np.cos(lat1) * np.cos(lat2) * np.sin((lon2 - lon1) / 2) ** 2
    return 6371.0 * 2 * np.arcsin(np.sqrt(a))


def near_volcano(lon, lat, radius_km=None):
    """Array of volcano names (or None) for each point."""
    radius_km = radius_km or CONFIG["volcano_radius_km"]
    lon = np.asarray(lon, float)
    lat = np.asarray(lat, float)
    out = np.full(lon.shape, None, dtype=object)
    for name, vlon, vlat in VOLCANOES:
        mask = haversine_km(lon, lat, vlon, vlat) <= radius_km
        out[mask & (out == None)] = name  # noqa: E711
    return out
