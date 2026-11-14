import unittest
from firewatch.comparison import compare, grid_cell


def detection(**changes):
    row = {"sensor": "MODIS", "latitude": -3.2, "longitude": 114.9,
           "acquired_at_utc": "2024-01-01T02:14:00Z", "confidence_value": 59,
           "confidence_scale": "MODIS_0_100", "detection_type": 0}
    return {**row, **changes}


class ComparisonTests(unittest.TestCase):
    def test_repeated_overpasses_count_once_but_dates_and_sensors_separate(self):
        rows = [detection(), detection(acquired_at_utc="2024-01-01T06:00:00Z"),
                detection(acquired_at_utc="2024-01-02T02:14:00Z"),
                detection(sensor="VIIRS_SNPP", confidence_value="n", confidence_scale="VIIRS_L_N_H")]
        result = compare(rows)
        self.assertEqual([r["active_cells"] for r in result["daily"]], [1, 1, 1])
        self.assertEqual(result["weekly"][0]["active_cell_days"], 2)

    def test_filters_and_missing_type(self):
        result = compare([detection(confidence_value=29), detection(detection_type=2),
                          detection(detection_type=None), detection(confidence_value=30)])
        self.assertEqual(result["quality"]["retained_by_sensor"], {"MODIS": 1})
        self.assertEqual(sum(result["quality"]["excluded"].values()), 3)

    def test_grid_boundaries(self):
        self.assertEqual(grid_cell(0, 0), (18000, 9000))
        self.assertEqual(grid_cell(-0.001, -0.001), (17999, 8999))
        self.assertEqual(grid_cell(114.9, -3.2), grid_cell(114.909, -3.191))
        self.assertNotEqual(grid_cell(114.9, -3.2), grid_cell(114.91, -3.2))

    def test_leap_year_and_last_week(self):
        result = compare([detection(acquired_at_utc="2024-12-31T23:59:00Z")])
        self.assertEqual(result["weekly"][-2]["active_cell_days"], 1)
        self.assertIsNone(result["weekly"][0]["active_cell_days"])
        self.assertEqual(result["weekly"][0]["coverage_status"], "unknown")

    def test_invalid_contract(self):
        for change in ({"confidence_scale": "VIIRS_L_N_H"},
                       {"acquired_at_utc": "2023-01-01T00:00:00Z"}):
            with self.assertRaises(ValueError):
                compare([detection(**change)])

    def test_empty_input(self):
        result = compare([])
        self.assertEqual(result["daily"], [])
        self.assertTrue(all(r["active_cell_days"] is None for r in result["weekly"]))


if __name__ == "__main__":
    unittest.main()
