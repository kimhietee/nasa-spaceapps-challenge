import hashlib
import sqlite3

import pytest

from backend.api import database
from backend.ingest import SCHEMA
from backend.seasonality import summarize_periods
from backend.views import critical_periods


def test_typical_months_require_all_years_and_keep_ties():
    rows = []
    for month, values in [(1, [5, 10, 100, 20]), (2, [20, 10, 15, 15]),
                          (3, [999, 999, 999]), (4, [0, 0, 0, 0])]:
        rows += [dict(year=2022 + i, month=month, activity=value) for i, value in enumerate(values)]
    result = summarize_periods(rows)
    assert result['typical_peak_months'] == [1, 2]
    assert result['months'][0]['median'] == 15
    assert result['months'][0]['min'] == 5
    assert result['months'][0]['max'] == 100
    assert result['months'][2]['median'] is None
    assert result['months'][2]['counts']['2025'] is None
    assert result['months'][3]['median'] == 0
    assert result['years'][3]['peak_months'] == [1]


def test_empty_and_zero_only_records_never_become_positive_peaks():
    assert summarize_periods([])['available'] is False
    result = summarize_periods([dict(year=year, month=1, activity=0) for year in range(2022, 2026)])
    assert result['available'] is True
    assert result['typical_peak_months'] == []
    assert all(year['peak_months'] == [] for year in result['years'])


def test_reference_scope_matches_recorded_grouped_counts_without_writes(tmp_path, monkeypatch):
    path = tmp_path / 'synthetic.sqlite'
    with sqlite3.connect(path) as conn:
        conn.executescript(SCHEMA)
        for year in range(2022, 2026):
            for i, (region, daynight, kind, sensor, group) in enumerate([
                ('A', 'D', 0, 'MODIS', 'g'), ('A', 'D', 0, 'VIIRS', 'g'),
                ('A', 'D', 1, 'MODIS', None), ('B', 'N', 0, 'VIIRS', None)]):
                conn.execute('''INSERT INTO observations
                    (id,year,month,region,daynight,type,sensor,group_id)
                    VALUES (?,?,1,?,?,?,?,?)''', (f'{year}-{i}', year, region, daynight, kind, sensor, group))
    monkeypatch.setenv('FIREWATCH_ARCHIVE_DB', str(path))
    original = hashlib.sha256(path.read_bytes()).digest()
    critical_periods.cache_clear()
    try:
        vegetation = critical_periods(region='A', daynight='D', detection_type='vegetation')
        assert vegetation['months'][0]['median'] == 1
        assert vegetation['typical_peak_months'] == [1]
        assert critical_periods(region='A', daynight='D', detection_type='all')['months'][0]['median'] == 2
        assert critical_periods(region='A', daynight='N', detection_type='vegetation')['available'] is False
        assert vegetation['scope']['start_date'] == '2022-01-01'
        assert vegetation['scope']['region'] == 'A'
        with database() as conn:
            with pytest.raises(sqlite3.OperationalError):
                conn.execute('DELETE FROM observations')
        assert hashlib.sha256(path.read_bytes()).digest() == original
    finally:
        critical_periods.cache_clear()
