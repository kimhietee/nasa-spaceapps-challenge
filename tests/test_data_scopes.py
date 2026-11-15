"""Data-scope regression checks using disposable SQLite; no HTTP/event-loop sockets."""
import hashlib
import inspect
import sqlite3
from datetime import date

import pytest
from backend import api, views
from backend.ingest import SCHEMA


def call(function, **kwargs):
    defaults = {name: getattr(p.default, 'default', p.default)
                for name, p in inspect.signature(function).parameters.items()
                if p.default is not inspect.Parameter.empty}
    return function(**(defaults | kwargs))


@pytest.fixture
def archive(tmp_path, monkeypatch):
    path = tmp_path / 'archive.sqlite'
    with sqlite3.connect(path) as c:
        c.executescript(SCHEMA)
        for year in range(2022, 2026):
            for month in range(1, 13):
                for sensor, kind, frp in [('MODIS', 0, 10), ('VIIRS', 0, 20), ('MODIS', 1, 1000)]:
                    c.execute("""INSERT INTO observations
                      (id,year,month,date,sensor,type,frp,lat,lon,region,daynight,status)
                      VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (f'{year}-{month}-{sensor}-{kind}', year, month, f'{year}-{month:02}-01',
                       sensor, kind, frp, -2, 110, 'A', 'D', 'modis-only' if sensor == 'MODIS' else 'viirs-only'))
        for sensor, region in [('MODIS', 'A'), ('VIIRS', 'B')]:
            c.execute("""INSERT INTO observations
              (id,year,month,date,sensor,type,frp,lat,lon,region,daynight,status,group_id)
              VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
              (sensor, 2024, 1, '2024-01-02', sensor, 0, 30, -2, 110, region, 'D', 'matched', 'G'))
    monkeypatch.setenv('FIREWATCH_ARCHIVE_DB', str(path))
    for f in (api.history, api.anomalies, api.forecast): f.cache_clear()
    yield path
    for f in (api.history, api.anomalies, api.forecast): f.cache_clear()


def test_detection_scope_propagates_and_preserves_originals(archive):
    original = hashlib.sha256(archive.read_bytes()).digest()
    veg = call(api.dashboard, year=2024, detection_type='vegetation')
    all_types = call(api.dashboard, year=2024, detection_type='all')
    assert all_types['summary']['total'] - veg['summary']['total'] == 12
    assert veg['scope']['detection_type'] == 'vegetation'
    for mode, expected in [('vegetation', veg), ('all', all_types)]:
        calendar = call(views.calendar_year, year=2024, detection_type=mode)
        assert calendar['activity'] == expected['summary']['activity']
        history = call(api.history, detection_type=mode)
        assert history[2]['summary'] == expected['summary'] | {'change_pct': history[2]['summary']['change_pct']}
        heat = call(views.frp_heatmap, year=2024, sensor='MODIS', detection_type=mode)
        assert sum(r['count'] for r in heat['cells']) == expected['summary']['modis']
        assert sum(r['mean_frp_mw'] * r['count'] for r in heat['cells']) / sum(r['count'] for r in heat['cells']) == pytest.approx(expected['summary']['frp_by_sensor']['MODIS']['mean'])
        forecast = call(api.forecast, detection_type=mode)
        assert forecast['available']
    assert call(api.forecast, detection_type='all')['outlook'][0]['point'] > call(api.forecast, detection_type='vegetation')['outlook'][0]['point']
    assert hashlib.sha256(archive.read_bytes()).digest() == original


def test_harmonized_members_count_both_sensors_and_keep_anchor_rule(archive):
    result = call(api.map_data, year=2024, detection_type='vegetation', region='A')
    assert sum(r['count'] for r in result['clusters']) == 25
    assert sum(r['source_viirs'] for r in result['clusters']) == 13  # Includes partner over the boundary.
    assert sum(r['source_modis'] for r in result['clusters']) == 13
    assert call(api.map_data, year=2024, detection_type='vegetation', region='B')['represented'] == 0
    assert call(api.dashboard, year=2024, detection_type='vegetation', region='B')['summary']['viirs'] == 1


def test_calendar_range_keeps_years_separate_and_day_scope_matches(archive):
    start, end = date(2023, 12, 1), date(2024, 1, 31)
    totals = [call(views.calendar_year, year=y, start_date=start, end_date=end, detection_type='vegetation')['activity'] for y in (2023, 2024)]
    assert sum(totals) == call(api.dashboard, start_date=start, end_date=end, detection_type='vegetation')['summary']['activity']
    assert call(api.day_detail, date=date(2024, 1, 1), detection_type='vegetation')['summary']['total'] == 2
    assert call(api.day_detail, date=date(2024, 1, 1), detection_type='all')['summary']['total'] == 3
