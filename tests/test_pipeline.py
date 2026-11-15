import sqlite3

import pandas as pd


def test_tables_and_demo_flag(db_file):
    c = sqlite3.connect(db_file)
    assert c.execute("SELECT value FROM meta WHERE key='data_status'").fetchone()[0] == "DEMO DATA"
    for t in ("cell", "cell_week", "aoi", "aoi_week", "calibration", "climatology", "critical_period", "ingest_log"):
        assert c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] > 0


def test_static_sources_flagged(db_file):
    c = sqlite3.connect(db_file)
    reasons = {r[0] for r in c.execute("SELECT static_reason FROM cell WHERE is_static=1")}
    assert "Kanlaon" in reasons and "Persistent multi-year thermal source" in reasons


def test_calibration_quality(db_file):
    c = sqlite3.connect(db_file)
    beta, r2 = c.execute("SELECT beta, r2 FROM calibration WHERE aoi_id='PH'").fetchone()
    assert 0.1 < beta < 1.0 and r2 > 0.8


def test_harmonization_removes_2012_step(db_file):
    c = sqlite3.connect(db_file)
    df = pd.read_sql("SELECT year, modis_cd, viirs_cd, harmonized FROM aoi_week WHERE aoi_id='PH'", c)
    a = df.groupby("year").sum(min_count=1)
    naive_ratio = (a.loc[2013, "modis_cd"] + a.loc[2013, "viirs_cd"]) / a.loc[2010, "modis_cd"]
    harm_ratio = a.loc[2013, "harmonized"] / a.loc[2010, "harmonized"]
    assert naive_ratio > 2.5 and harm_ratio < 2.0 and harm_ratio < naive_ratio / 2


def test_no_zero_fill_before_viirs(db_file):
    c = sqlite3.connect(db_file)
    n = c.execute("SELECT COUNT(*) FROM aoi_week WHERE aoi_id='PH' AND year=2005 AND viirs_cd IS NOT NULL").fetchone()[0]
    assert n == 0
