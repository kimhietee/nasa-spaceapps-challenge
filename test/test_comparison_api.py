from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import HTTPException

from api.main import app
from api.comparison import comparison_health, comparison_weekly, router
from firewatch.comparison import compare
from firewatch.indonesia import _weekly_counts
from scripts.build_indonesia_db import SCHEMA, INDEXES, INSERT, detection_values


def detection(**changes):
    return {"instrument": "MODIS", "satellite": "Terra", "latitude": -3.2,
            "longitude": 114.9, "acq_date": "2024-01-01", "acq_time": "0214",
            "confidence": "59", "type": "0", "daynight": "D", "frp": 10,
            "version": "61.03", **changes}


class ComparisonApiTests(TestCase):
    def setUp(self):
        self.folder = TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.path = Path(self.folder.name) / "indonesia.db"
        self.environment = patch.dict("os.environ", {"FIREWATCH_INDONESIA_DB": str(self.path)})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        _weekly_counts.cache_clear()
        self.rows = [
            detection(), detection(acq_time="0600"),
            detection(acq_date="2024-01-02"), detection(satellite="Aqua"),
            detection(instrument="SNPP", satellite="SNPP", confidence="n", version="2"),
            detection(confidence="29"), detection(type="2"), detection(type=None),
            detection(instrument="SNPP", satellite="SNPP", confidence="l", version="2"),
            detection(acq_date="2024-12-31", longitude=-0.001, latitude=-0.001),
            detection(acq_date="2024-01-01", longitude=114.91),
            detection(acq_date="2022-01-01", version="6.03"),
            detection(acq_date="2023-12-31"), detection(acq_date="2025-12-31"),
        ]
        self.build_database()

    def build_database(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.executescript(SCHEMA)
            conn.executescript(INDEXES)
            conn.executemany("INSERT INTO meta VALUES (?,?)", {
                "schema_version": "indonesia-detections-1.0", "country_code": "IDN",
                "data_status": "NASA FIRMS", "built_at_utc": "test",
            }.items())
            conn.execute("""INSERT INTO source_file VALUES
                         (1,'test.json','test-hash',100,'Indonesia archive request','test',?,
                          '2022-01-01T02:14:00Z','2025-12-31T02:14:00Z')""", (len(self.rows),))
            conn.executemany(INSERT, [detection_values(row, 1, i) for i, row in enumerate(self.rows, 1)])
            conn.commit()

    def test_output_matches_reference_counting(self):
        reference = []
        for row in self.rows:
            if row["acq_date"].startswith("2024"):
                values = detection_values(row, 1, 1)
                reference.append({"sensor": values[2], "longitude": values[7], "latitude": values[6],
                                  "acquired_at_utc": values[5], "detection_type": values[12],
                                  "confidence_value": values[10] if values[2] == "MODIS" else values[11],
                                  "confidence_scale": "MODIS_0_100" if values[2] == "MODIS" else "VIIRS_L_N_H"})
        result = comparison_weekly(year=2024)
        self.assertEqual(result["data"], compare(reference)["weekly"])
        self.assertEqual(result["coverage_status"], "unknown")
        self.assertFalse(result["calibrated"])
        self.assertEqual(result["year"], 2024)
        self.assertIsNone(result["data"][2]["active_cell_days"])

    def test_sensor_filter(self):
        result = comparison_weekly(year=2024, sensor="VIIRS_SNPP")
        self.assertEqual(len(result["data"]), 52)
        self.assertTrue(all(row["sensor"] == "VIIRS_SNPP" for row in result["data"]))
        self.assertEqual(result["data"][0]["active_cell_days"], 1)

    def test_each_supported_year(self):
        for year in (2022, 2023, 2024, 2025):
            result = comparison_weekly(year=year)
            self.assertEqual(len(result["data"]), 104)
            self.assertTrue(all(row["year"] == year for row in result["data"]))
            if year != 2024:
                self.assertEqual(sum(row["active_cell_days"] or 0 for row in result["data"]), 1)
        self.assertEqual(comparison_weekly(year=2025)["data"][-2]["active_cell_days"], 1)

    def test_validation(self):
        self.assertIn("/api/comparison/weekly", app.openapi()["paths"])
        route = next(route for route in router.routes if route.path == "/api/comparison/weekly")
        fields = {field.name: field for field in route.dependant.query_params}
        for name, value in (("sensor", "BAD"), ("year", "2021"), ("year", "2026"), ("year", "abc")):
            _, errors = fields[name].validate(value, {}, loc=("query", name))
            self.assertTrue(errors)
        self.assertEqual(fields["year"].default, 2024)

    def test_health(self):
        result = comparison_health()
        self.assertEqual(result["country_code"], "IDN")
        self.assertEqual(result["source_record_count"], len(self.rows))

    def assert_unavailable(self):
        for call in (comparison_health, lambda: comparison_weekly(year=2024)):
            with self.assertRaises(HTTPException) as context:
                call()
            self.assertEqual(context.exception.status_code, 503)

    def test_missing_database_is_not_created(self):
        self.path.unlink()
        self.assert_unavailable()
        self.assertFalse(self.path.exists())

    def test_invalid_database(self):
        self.path.write_bytes(b"not a sqlite database")
        self.assert_unavailable()

    def test_wrong_country_or_schema(self):
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE meta SET value='PH' WHERE key='country_code'")
            conn.commit()
        self.assert_unavailable()

    def test_repeated_requests_reuse_aggregates_and_updates_invalidate_cache(self):
        first = comparison_weekly(year=2024)
        self.assertEqual(comparison_weekly(year=2024), first)
        self.assertEqual(_weekly_counts.cache_info().hits, 1)
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute("UPDATE detection SET detection_type=2")
            conn.commit()
        result = comparison_weekly(year=2024)
        self.assertTrue(all(row["active_cell_days"] is None for row in result["data"]))

    def test_connection_is_read_only(self):
        from firewatch.indonesia import open_database
        with self.assertRaises(HTTPException):
            with open_database(self.path) as conn:
                conn.execute("DELETE FROM detection")
        self.assertEqual(comparison_health()["source_record_count"], len(self.rows))
