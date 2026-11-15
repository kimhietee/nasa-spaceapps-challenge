"""Synthetic data only; these tests never open the real archive."""
import sqlite3

import pytest

from backend.ingest import SCHEMA
from scripts.validate_harmonization import collect, correlation, digest, write_report


@pytest.fixture
def archive(tmp_path):
    path = tmp_path / 'synthetic.sqlite'
    with sqlite3.connect(path) as c:
        c.executescript(SCHEMA)
        rows = [
            ('m1', 'MODIS', 'Pilot', '2022-01-01', 'matched', 'g1', 1, 0),
            ('v1', 'VIIRS', 'Pilot', '2022-01-01', 'matched', 'g1', 1, 0),
            ('v2', 'VIIRS', 'Pilot', '2022-01-02', 'viirs-only', None, 1, 0),
            ('m2', 'MODIS', 'Pilot', '2022-01-02', 'modis-only', None, 0, 0),
            ('v3', 'VIIRS', 'Pilot', '2022-01-02', 'possible', 'g2', 1, 0),
            ('m3', 'MODIS', 'Other', '2022-01-02', 'possible', 'g2', 1, 0),
            ('volcano', 'MODIS', 'Pilot', '2022-01-01', 'modis-only', None, 0, 1),
        ]
        for id_, sensor, region, stamp, status, group, eligible, kind in rows:
            c.execute('''INSERT INTO observations
                (id,sensor,satellite,region,date,year,month,status,group_id,eligible,type)
                VALUES (?,?,?,?,?,2022,1,?,?,?,?)''',
                (id_, sensor, sensor, region, stamp, status, group, eligible, kind))
        c.executemany('INSERT INTO groups(id,modis_id,viirs_id) VALUES (?,?,?)',
                      [('g1', 'm1', 'v1'), ('g2', 'm3', 'v3')])
        c.executemany('INSERT INTO candidate_pairs(modis_id,viirs_id,score) VALUES (?,?,?)',
                      [('m1', 'v1', .8), ('m1', 'v2', .6), ('m2', 'v2', .1)])
    return path


def test_counts_preserve_boundary_anchoring_and_quality_scope(archive, tmp_path):
    before = digest(archive)
    with sqlite3.connect(archive.as_uri() + '?mode=ro', uri=True) as c:
        result = collect(c, 'Pilot')
        with pytest.raises(sqlite3.OperationalError):
            c.execute('DELETE FROM observations')
    first = result['monthly'][0]
    assert len(result['monthly']) == 48
    assert (first['modis'], first['viirs'], first['activity']) == (2, 3, 3)
    assert first['suppressed_viirs'] == 2
    assert first['matched_groups'] == 1
    assert first['possible_groups'] == 0  # The second group is anchored in Other.
    assert first['modis_eligible'] == 1  # Low quality retained in counts, not eligible counts.
    assert result['inbound_groups'] == 1
    assert result['outbound_groups'] == 0
    assert result['multiple_candidates'] == 1
    assert digest(archive) == before
    report, csv_file = write_report(result, 'Pilot', before, tmp_path / 'report')
    assert 'sensor-independent harmonization is not established' in report.read_text(encoding='utf-8')
    assert len(csv_file.read_text().splitlines()) == 49


def test_unknown_province_fails_instead_of_reporting_zero_activity(archive):
    with sqlite3.connect(archive.as_uri() + '?mode=ro', uri=True) as c:
        with pytest.raises(ValueError, match='No presumed-vegetation'):
            collect(c, 'Missing')


def test_correlation_handles_undefined_and_negative_agreement():
    assert correlation([], []) is None
    assert correlation([0, 0], [1, 2]) is None
    assert correlation([1, 2, 3], [3, 2, 1]) == pytest.approx(-1)
