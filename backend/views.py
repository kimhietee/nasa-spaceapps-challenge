"""Additive, read-only views for the annual calendar and sensor-specific FRP map."""
from datetime import date, timedelta
from typing import Literal
import math
from fastapi import APIRouter, HTTPException, Query

router = APIRouter()


@router.get('/api/archive/calendar-year')
def calendar_year(year: int = Query(2022, ge=2022, le=2025), region: str | None = None,
                  daynight: Literal['D', 'N'] | None = None,
                  start_date: date | None = None, end_date: date | None = None, detection_type: Literal['vegetation', 'all'] = 'all'):
    from .api import database, filters, series
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, 'Invalid date range')
    where, params = filters(year, None, region, daynight, detection_type)
    if start_date:
        where += ' AND date>=?'
        params.append(str(start_date))
    if end_date:
        where += ' AND date<=?'
        params.append(str(end_date))
    with database() as conn:
        observed = {row['period']: row for row in series(conn, where, params, 'date')}
    days = []
    stamp = date(year, 1, 1)
    while stamp.year == year:
        row = observed.get(str(stamp))
        days.append({'date': str(stamp), 'day': stamp.day, 'month': stamp.month,
                     'in_range': (not start_date or stamp >= start_date) and (not end_date or stamp <= end_date),
                     'activity': row['activity'] if row else None})
        stamp += timedelta(days=1)
    values = sorted(row['activity'] for row in days if row['activity'] is not None)
    def percentile(q):
        position = (len(values) - 1) * q
        lower, upper = math.floor(position), math.ceil(position)
        return values[lower] + (values[upper] - values[lower]) * (position - lower)
    return {'year': year, 'days': days, 'activity': sum(values),
            'thresholds': [percentile(q) for q in (0.5, 0.75, 0.9)] if values else [],
            'coverage': 'unknown; missing detections are not confirmed zero activity'}


@router.get('/api/archive/frp-heatmap')
def frp_heatmap(year: int | None = Query(None, ge=2022, le=2025),
                month: int | None = Query(None, ge=1, le=12), region: str | None = None,
                daynight: Literal['D', 'N'] | None = None,
                start_date: date | None = None, end_date: date | None = None,
                sensor: Literal['MODIS', 'VIIRS'] = 'VIIRS', zoom: int = Query(5, ge=4, le=16),
                west: float = Query(-180, ge=-180, le=180), east: float = Query(180, ge=-180, le=180),
                south: float = Query(-90, ge=-90, le=90), north: float = Query(90, ge=-90, le=90), detection_type: Literal['vegetation', 'all'] = 'all'):
    from .api import database, selection
    if west > east or south > north:
        raise HTTPException(422, 'Invalid viewport bounds')
    where, params = selection(year, month, region, daynight, start_date, end_date, detection_type)
    where += ' AND sensor=? AND frp IS NOT NULL AND frp>=0 AND lon BETWEEN ? AND ? AND lat BETWEEN ? AND ?'
    params += [sensor, west, east, south, north]
    # Cap resolution to keep the heatmap an aggregate even at street zoom.
    step = 360 / (2 ** min(zoom, 10) * 4)
    with database() as conn:
        rows = conn.execute(f'''SELECT CAST((lon+180)/? AS INTEGER) gx,
            CAST((lat+90)/? AS INTEGER) gy, AVG(frp) mean_frp_mw, COUNT(*) count
            FROM observations WHERE {where} GROUP BY gx,gy ORDER BY gx,gy''', [step, step] + params)
        cells = [dict(row) for row in rows]
    return {'cells': cells, 'step': step, 'sensor': sensor, 'unit': 'MW',
            'statistic': 'mean source FRP per occupied map cell; sensors are never combined',
            'coverage': 'transparent cells have no retained FRP data; observation coverage is unknown'}
