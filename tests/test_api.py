from fastapi.testclient import TestClient


def client(db_file):
    from api.main import app
    return TestClient(app)


def test_health_and_labels(db_file):
    r = client(db_file).get("/api/health").json()
    assert r["status"] == "ok" and r["data_status"] == "DEMO DATA"


def test_aois_and_404(db_file):
    c = client(db_file)
    assert len(c.get("/api/aois").json()["aois"]) == 6
    assert c.get("/api/aois/XXX/weekly").status_code == 404


def test_weekly_shapes_and_json_validity(db_file):
    c = client(db_file)
    r = c.get("/api/aois/BUKIDNON/weekly?from=2010&to=2014").json()
    assert r["data"][0].keys() >= {"year", "week", "value", "pct_rank", "z", "is_anomaly", "source", "low_confidence"}
    v = c.get("/api/aois/BUKIDNON/weekly?series=viirs&from=2010&to=2011").json()
    assert all(d["value"] is None for d in v["data"])   # VIIRS did not exist yet: null, not zero


def test_other_endpoints(db_file):
    c = client(db_file)
    assert c.get("/api/aois/PH/climatology").json()["data"]
    assert c.get("/api/aois/BUKIDNON/anomalies").json()["top_years"][0]["year"] == 2016
    assert c.get("/api/aois/BUKIDNON/critical-periods?threshold=90").json()["periods"]
    assert c.get("/api/aois/PH/calibration").json()["calibration"]["beta"] > 0
    assert c.get("/api/aois/VALENCIA/summary").json()["most_unusual_year"]
    assert c.get("/api/aois/BUKIDNON/week-detail?year=2016&week=14").json()["count"] > 0
    assert c.get("/api/aois/PH/export.csv").text.startswith("year,week")


def test_polygon_aoi(db_file):
    c = client(db_file)
    poly = {"type": "Polygon", "coordinates": [[[124.9, 7.7], [125.3, 7.7], [125.3, 8.2], [124.9, 8.2], [124.9, 7.7]]]}
    r = c.post("/api/aoi/weekly", json={"geometry": poly})
    assert r.status_code == 200 and r.json()["cells_in_polygon"] > 0
    assert c.post("/api/aoi/weekly", json={"geometry": {"type": "Point", "coordinates": [125, 8]}}).status_code == 422
    empty = {"type": "Polygon", "coordinates": [[[100, 0], [101, 0], [101, 1], [100, 1], [100, 0]]]}
    assert c.post("/api/aoi/weekly", json={"geometry": empty}).status_code == 404
