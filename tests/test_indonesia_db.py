from contextlib import closing
import importlib.util
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("builder", Path(__file__).resolve().parents[1] / "scripts/build_indonesia_db.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "processed"
        self.source.mkdir()
        self.output = self.root / "indonesia.db"
        self.row = dict(instrument="MODIS", satellite="Terra", latitude=-2.5,
                        longitude=120.5, acq_date="2022-01-03", acq_time="150",
                        confidence="53", type="2", daynight="D", frp=24.7,
                        version="6.03", scan=1.5, track=1.2, brightness=318.8, bright_t31=286.4)

    def write(self, records):
        path = self.source / "fire_archive_test.json"
        path.write_text(json.dumps(records), encoding="utf-8")
        return path

    def test_both_sensors_and_source_traceability(self):
        viirs = dict(self.row, instrument="SNPP", satellite="SNPP", confidence="n", version="2", acq_date="2025-12-31")
        self.write([self.row, viirs, self.row])
        self.assertEqual(builder.build_database(self.source, self.output), {"MODIS": 2, "VIIRS_SNPP": 1})
        with closing(sqlite3.connect(self.output)) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("SELECT collection_version,detection_type,acquired_at_utc FROM detection WHERE source_row=1").fetchone(),
                             ("6.03", 2, "2022-01-03T01:50:00Z"))
            self.assertEqual(conn.execute("SELECT record_count,LENGTH(sha256) FROM source_file").fetchone(), (3, 64))
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM detection WHERE source_row=3").fetchone()[0], 1)
            self.assertTrue(conn.execute("SELECT name FROM sqlite_master WHERE name='idx_detection_sensor_time'").fetchone())

    def test_existing_database_is_preserved(self):
        self.write([self.row])
        self.output.write_bytes(b"existing")
        with self.assertRaises(FileExistsError):
            builder.build_database(self.source, self.output)
        self.assertEqual(self.output.read_bytes(), b"existing")

    def test_invalid_row_removes_incomplete_database(self):
        self.write([dict(self.row, latitude=91)])
        with self.assertRaisesRegex(ValueError, "row 1"):
            builder.build_database(self.source, self.output)
        self.assertFalse(self.output.exists())

    def test_invalid_json_delimiters(self):
        path = self.source / "fire_archive_test.json"
        for text in ('[{"a":1},]', '[{"a":1} {"a":2}]', '[{"a":1}', '[] garbage'):
            with self.subTest(text=text):
                path.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError):
                    list(builder.iter_records(path))

    def test_streaming_chunk_boundaries(self):
        rows = [dict(self.row, note="x" * 50000) for _ in range(4)]
        self.assertEqual(list(builder.iter_records(self.write(rows))), rows)

    def test_unsupported_satellite_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "satellite"):
            builder.detection_values(dict(self.row, satellite="Unknown"), 1, 1)

    def test_missing_archives_does_not_create_database(self):
        with self.assertRaisesRegex(ValueError, "No fire_archive"):
            builder.build_database(self.source, self.output)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
