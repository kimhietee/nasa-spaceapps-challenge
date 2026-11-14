import unittest

from scripts.clean_firms import clean_record, process


# Synthetic fixture, not a real satellite observation.
SAMPLE = {
    "latitude": -3.2,
    "longitude": 114.9,
    "acq_date": "2024-01-01",
    "acq_time": "214",
    "confidence": "59",
    "instrument": "MODIS",
    "satellite": "Terra",
    "daynight": "D",
    "frp": 6.9,
    "version": "61.03",
    "type": "0",
}


class CleaningTests(unittest.TestCase):
    def test_standardizes_time_and_confidence(self):
        result = clean_record(SAMPLE)
        self.assertEqual(result["acquired_at_utc"], "2024-01-01T02:14:00Z")
        self.assertEqual(result["confidence_value"], 59)

    def test_rejects_invalid_values(self):
        for changes in (
            {"latitude": 91},
            {"longitude": float("nan")},
            {"frp": -1},
            {"confidence": 101},
            {"acq_time": "2460"},
            {"acq_date": "2023-01-01"},
            {"instrument": "VIIRS"},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    clean_record({**SAMPLE, **changes})

    def test_duplicates_and_rejections_are_counted(self):
        rows = [SAMPLE, dict(SAMPLE), {**SAMPLE, "latitude": 99}]
        clean, report = process(rows, "mock.json")
        self.assertEqual(len(clean), 1)
        self.assertEqual(report["exact_duplicates_removed"], 1)
        self.assertEqual(report["rejected_records"], 1)
        self.assertEqual(report["rejections"][0]["source_row"], 3)

    def test_preserves_distinct_satellite_observations(self):
        rows = [SAMPLE, {**SAMPLE, "satellite": "Aqua"}]
        clean, report = process(rows, "mock.json")
        self.assertEqual(len(clean), 2)
        self.assertEqual(report["exact_duplicates_removed"], 0)

    def test_empty_input(self):
        clean, report = process([], "mock.json")
        self.assertEqual(clean, [])
        self.assertEqual(report["input_records"], 0)


    def test_viirs_archive_fields(self):
        record = {**SAMPLE, "instrument": "SNPP", "satellite": "SNPP",
                  "version": "2", "confidence": "n"}
        result = clean_record(record)
        self.assertEqual(result["sensor"], "VIIRS_SNPP")
        self.assertEqual(result["satellite"], "Suomi-NPP")
        self.assertEqual(result["confidence_value"], "n")
        self.assertEqual(result["confidence_scale"], "VIIRS_L_N_H")
        for confidence in ("l", "h"):
            self.assertEqual(clean_record({**record, "confidence": confidence})[
                "confidence_value"], confidence)
        for changes in ({"confidence": "59"}, {"version": "20"},
                        {"satellite": "NOAA-20"}):
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    clean_record({**record, **changes})

    def test_viirs_aliases_and_types_are_preserved(self):
        for label, expected in (("low", "l"), ("nominal", "n"), ("high", "h")):
            for detection_type in range(4):
                record = {**SAMPLE, "instrument": "VIIRS", "satellite": "N",
                          "version": "2", "confidence": label, "type": detection_type}
                result = clean_record(record)
                self.assertEqual(result["confidence_value"], expected)
                self.assertEqual(result["detection_type"], detection_type)

    def test_rejects_malformed_modis_version(self):
        for version in ("610", "61garbage"):
            with self.subTest(version=version):
                with self.assertRaises(ValueError):
                    clean_record({**SAMPLE, "version": version})


if __name__ == "__main__":
    unittest.main()