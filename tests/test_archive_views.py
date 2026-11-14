"""Exercise additive API routes against a disposable database, without network sockets."""
import asyncio
import hashlib
import sqlite3

import httpx
import pytest

from backend.api import app, database
from backend.ingest import SCHEMA


@pytest.fixture
def archive(tmp_path, monkeypatch):
    path = tmp_path / 'test.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        for i, (stamp, sensor, frp, daynight) in enumerate([
            ('2024-01-01', 'MODIS', 20, 'D'), ('2024-01-01', 'MODIS', 40, 'D'),
            ('2024-01-01', 'VIIRS', 100, 'N'), ('2024-02-29', 'VIIRS', 0, 'D'),
            ('2023-12-31', 'MODIS', 99, 'D'), ('2024-01-02', 'VIIRS', None, 'D')]):
            conn.execute('''INSERT INTO observations
                (id,year,month,date,sensor,frp,daynight,region,lat,lon,status)
                VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
                (str(i), int(stamp[:4]), int(stamp[5:7]), stamp, sensor, frp, daynight,
                 'Bali', -2, 110, 'modis-only' if sensor == 'MODIS' else 'viirs-only'))
    monkeypatch.setenv('FIREWATCH_ARCHIVE_DB', str(path))
    return path


def get(path):
    async def request():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='http://test') as client:
            return await client.get(path)
    return asyncio.run(request())


def test_calendar_covers_leap_year_and_preserves_unknown(archive):
    data = get('/api/archive/calendar-year?year=2024').json()
    assert len(data['days']) == 366
    assert next(row for row in data['days'] if row['date'] == '2024-02-29')['activity'] == 1
    assert data['days'][0]['activity'] == 3
    assert data['days'][2]['activity'] is None
    assert data['activity'] == 5
    assert len(get('/api/archive/calendar-year?year=2023').json()['days']) == 365


def test_heatmap_uses_mean_frp_and_keeps_sensors_separate(archive):
    modis = get('/api/archive/frp-heatmap?year=2024&month=1&sensor=MODIS').json()
    assert modis['cells'][0]['mean_frp_mw'] == 30
    assert modis['cells'][0]['count'] == 2
    viirs = get('/api/archive/frp-heatmap?year=2024&month=1&sensor=VIIRS').json()
    assert viirs['cells'][0]['mean_frp_mw'] == 100
    zero = get('/api/archive/frp-heatmap?year=2024&month=2&sensor=VIIRS').json()
    assert zero['cells'][0]['mean_frp_mw'] == 0
    assert get('/api/archive/frp-heatmap?year=2024&sensor=MODIS&west=0&east=10').json()['cells'] == []
    assert get('/api/archive/frp-heatmap?year=2024&sensor=MODIS&daynight=N').json()['cells'] == []


def test_reads_do_not_change_database_and_writes_are_rejected(archive):
    original = hashlib.sha256(archive.read_bytes()).digest()
    get('/api/archive/calendar-year?year=2024')
    get('/api/archive/frp-heatmap?year=2024')
    assert hashlib.sha256(archive.read_bytes()).digest() == original
    with database() as conn:
        with pytest.raises(sqlite3.OperationalError):
            conn.execute('DELETE FROM observations')


@pytest.mark.parametrize('path', [
    '/api/archive/calendar-year?year=2026',
    '/api/archive/calendar-year?year=2024&start_date=2024-03-01&end_date=2024-01-01',
    '/api/archive/frp-heatmap?sensor=ALL', '/api/archive/frp-heatmap?west=50&east=20',
    '/api/archive/frp-heatmap?month=13',
])
def test_invalid_filters(archive, path):
    assert get(path).status_code == 422


def test_existing_dashboard_contract_is_preserved(archive):
    data = get('/api/archive/dashboard?year=2024&limit=0').json()
    assert data['summary']['total'] == 5
    assert data['summary']['activity'] == 5
    assert data['observations'] == []
    assert {'monthly', 'daily', 'scope', 'map_page'} <= data.keys()


def test_map_returns_observation_extents_without_changing_counts(archive):
    from backend.api import anomalies, map_data
    anomalies.cache_clear()
    original = hashlib.sha256(archive.read_bytes()).digest()
    try:
        data = map_data(year=2024, month=None, region=None, daynight=None,
                        start_date=None, end_date=None, view='modis', zoom=5,
                        west=-180, east=180, south=-90, north=90)
        assert data['represented'] == 2
        cell = data['clusters'][0]
        assert cell['south'] == cell['north'] == -2
        assert cell['west'] == cell['east'] == 110
        assert cell['scan_km'] is None
        assert hashlib.sha256(archive.read_bytes()).digest() == original
    finally:
        anomalies.cache_clear()


def test_forecast_selects_lower_error_model_without_future_training(monkeypatch):
    from backend import api
    monkeypatch.setattr(api, 'history', lambda **kwargs: [
        {'year': year, 'monthly': [{'period': month, 'activity': (year - 2021) * 10 + month}
                                 for month in range(1, 13)]}
        for year in range(2022, 2026)
    ])
    api.forecast.cache_clear()
    try:
        result = api.forecast()
        assert result['model'] == 'seasonal_naive'
        first = result['backtest'][0]
        assert first['year'] == 2024
        assert first['seasonal_mean'] == 16  # Only January 2022 and 2023.
        assert first['seasonal_naive'] == 21
        assert result['outlook'][0]['point'] == 41
        assert result['outlook'][0]['low'] == 31
        assert result['outlook'][0]['high'] == 51
    finally:
        api.forecast.cache_clear()
