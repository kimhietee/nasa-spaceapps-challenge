import json
from unittest import TestCase
from unittest.mock import patch
from tempfile import TemporaryDirectory
from pathlib import Path
from fastapi.testclient import TestClient
from api.main import app
from firewatch.comparison import compare


class ComparisonApiTests(TestCase):
    def test_output_and_sensor_filter(self):
        payload = compare([])
        with TemporaryDirectory() as folder:
            path = Path(folder) / "comparison.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with patch.dict("os.environ", {"FIREWATCH_COMPARISON": str(path)}):
                with TestClient(app) as client:
                    response = client.get("/api/comparison/weekly")
                    self.assertEqual(response.status_code, 200)
                    result = response.json()
                    self.assertEqual(result["data"], payload["weekly"])
                    self.assertEqual(result["coverage_status"], "unknown")
                    self.assertFalse(result["calibrated"])
                    filtered = client.get("/api/comparison/weekly?sensor=MODIS").json()
                    self.assertEqual(len(filtered["data"]), 52)
                    self.assertTrue(all(r["sensor"] == "MODIS" for r in filtered["data"]))
                    self.assertEqual(client.get("/api/comparison/weekly?sensor=BAD").status_code, 422)

    def test_missing_and_invalid_file(self):
        with TemporaryDirectory() as folder:
            path = Path(folder) / "comparison.json"
            with patch.dict("os.environ", {"FIREWATCH_COMPARISON": str(path)}):
                with TestClient(app) as client:
                    self.assertEqual(client.get("/api/comparison/weekly").status_code, 503)
                    path.write_text("{}", encoding="utf-8")
                    self.assertEqual(client.get("/api/comparison/weekly").status_code, 503)
