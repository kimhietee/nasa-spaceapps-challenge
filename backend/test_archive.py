import json
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from backend.ingest import SCHEMA, ingest, match, normalize
from backend.api import app, history, forecast, anomalies


def row(**changes):
    return {**dict(latitude=-3.2,longitude=114.9,acq_date="2024-01-01",acq_time="0214",instrument="MODIS",satellite="Terra",confidence="59",type="0",frp=4,scan=1,track=1,daynight="D",version="61.03"),**changes}

@pytest.fixture
def archive(tmp_path,monkeypatch):
    path=tmp_path/'archive.sqlite';connection=sqlite3.connect(path);connection.executescript(SCHEMA)
    rows=[row(),row(instrument='SNPP',satellite='SNPP',confidence='n',version='2'),
          row(instrument='SNPP',satellite='SNPP',confidence='h',version='2',longitude=115.9),
          row(latitude=91),row(confidence='10',acq_time='0215')]
    source=tmp_path/'fixture.json';source.write_text(json.dumps(rows))
    ingest(connection,source);match(connection);connection.close()
    monkeypatch.setenv('FIREWATCH_ARCHIVE_DB',str(path))
    history.cache_clear();forecast.cache_clear();anomalies.cache_clear()
    yield path,source
    history.cache_clear();forecast.cache_clear();anomalies.cache_clear()


def test_repeat_ingest_preserves_originals_without_duplicate_import(archive):
    path,source=archive
    with sqlite3.connect(path) as c:
        ingest(c,source)
        assert c.execute('SELECT COUNT(*) FROM source_files').fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM observations').fetchone()[0]==4
        assert c.execute('SELECT COUNT(*) FROM rejected').fetchone()[0]==1
        assert json.loads(c.execute('SELECT raw_json FROM observations LIMIT 1').fetchone()[0])==row()


def test_matching_and_unmatched_conservation(archive):
    with sqlite3.connect(archive[0]) as c:
        groups=c.execute('SELECT * FROM groups').fetchall();assert len(groups)==1
        assert c.execute('SELECT COUNT(*) FROM observations WHERE group_id IS NULL').fetchone()[0]==2
        assert c.execute("SELECT COUNT(*) FROM observations WHERE eligible=0").fetchone()[0]==1
        assert c.execute('SELECT COUNT(*) FROM candidate_pairs WHERE assigned=1').fetchone()[0]==1
        assert c.execute('SELECT MAX(distance_km),MAX(dt_min) FROM candidate_pairs').fetchone()==(0.0,0.0)
        before=c.execute('SELECT * FROM groups').fetchall();match(c)
        assert before==c.execute('SELECT * FROM groups').fetchall()


def test_api_exact_counts_pagination_and_provenance(archive):
    with TestClient(app) as client:
        r=client.get('/api/archive/dashboard?year=2024&limit=1').json()
        assert r['summary']['total']==4 and r['summary']['activity']==3
        assert r['summary']['matched']==1 and len(r['observations'])==1
        detail=client.get('/api/archive/observation/'+r['observations'][0]['id']).json()
        assert detail['raw_record']['latitude']==-3.2 and detail['file']['checksum']
        assert client.get('/api/archive/dashboard?year=2024&sensor=VIIRS').json()['summary']['total']==2
        assert client.get('/api/archive/dashboard?year=2024&month=2').json()['summary']['total']==0
        assert client.get('/api/archive/dashboard?year=2026').status_code==422
        assert client.get('/api/archive/observation/missing').status_code==404
        assert client.get('/api/archive/forecast').json()['available'] is False


def test_invalid_fields_and_collection_preservation():
    for changes in ({'longitude':float('nan')},{'acq_time':'2460'},{'confidence':'101'},{'acq_date':'2021-01-01'}):
        with pytest.raises(ValueError):normalize(row(**changes),'fixture',1)
    normalized=normalize(row(version='6.03',acq_date='2022-01-01'),'fixture',1)
    assert normalized[18]=='MODIS 6.03'


def test_midnight_candidate_and_time_gate(tmp_path):
    c=sqlite3.connect(':memory:');c.executescript(SCHEMA)
    rows=[row(acq_date='2023-12-31',acq_time='2355'),row(acq_date='2024-01-01',acq_time='0005',instrument='SNPP',satellite='SNPP',confidence='n'),row(acq_time='0130',instrument='SNPP',satellite='SNPP',confidence='h')]
    source=tmp_path/'times.json';source.write_text(json.dumps(rows));ingest(c,source);match(c)
    assert c.execute('SELECT COUNT(*) FROM candidate_pairs').fetchone()[0]==1
    assert c.execute('SELECT dt_min FROM candidate_pairs').fetchone()[0]==10
    c.close()


def test_assignment_beats_independent_greedy_and_keeps_evidence(tmp_path):
    c=sqlite3.connect(':memory:');c.executescript(SCHEMA)
    records=[row(longitude=114.9000),row(longitude=114.9045),
             row(longitude=114.9018,instrument='SNPP',satellite='SNPP',confidence='n'),
             row(longitude=114.8955,instrument='SNPP',satellite='SNPP',confidence='n')]
    source=tmp_path/'competing.json';source.write_text(json.dumps(records))
    ingest(c,source);match(c)
    # Greedy would take the strongest first pair and leave one MODIS unmatched.
    assert c.execute('SELECT COUNT(*) FROM groups').fetchone()[0]==2
    assert c.execute('SELECT COUNT(DISTINCT viirs_id) FROM groups').fetchone()[0]==2
    assert c.execute('SELECT COUNT(*) FROM candidate_pairs WHERE assigned=0').fetchone()[0]>=1
    c.close()


def test_full_selection_map_conserves_all_records_without_paging(archive):
    with TestClient(app) as client:
        all_sources=client.get('/api/archive/map?view=modis').json()
        assert all_sources['total']==2
        assert sum(p['count'] for p in all_sources['clusters'])==2
        viirs=client.get('/api/archive/map?view=viirs').json()
        assert viirs['represented']==2
        harmonized=client.get('/api/archive/map').json()
        assert harmonized['represented']==3
        assert all('modis' in p and 'viirs' in p for p in harmonized['clusters'])
        assert client.get('/api/archive/map?west=100&east=90').status_code==422


def test_explicit_range_overrides_stale_year_month_and_calendar_is_complete(archive):
    with TestClient(app) as client:
        r=client.get('/api/archive/dashboard?year=2025&month=9&start_date=2024-01-01&end_date=2024-12-31').json()
        assert r['summary']['total']==4 and r['scope']['year'] is None
        assert client.get('/api/archive/dashboard').json()['summary']['total']==4
        january=client.get('/api/archive/calendar?year=2024&month=1').json()
        assert len(january['days'])==31 and january['weekday_offset']==1
        assert january['days'][0]['activity']==3 and january['days'][1]['activity'] is None
        february=client.get('/api/archive/calendar?year=2024&month=2').json()
        assert len(february['days'])==29 and february['weekday_offset']==4
        assert len(client.get('/api/archive/calendar?year=2022&month=2').json()['days'])==28
        day=client.get('/api/archive/day?date=2024-01-01').json()
        assert day['summary']['total']==4 and day['summary']['modis']==2 and day['summary']['viirs']==2
        assert sum(r['activity'] for r in day['regions'])==3
