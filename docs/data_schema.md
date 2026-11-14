# MODIS cleaned data — schema 1.0

Input: NASA FIRMS MODIS Collection 6.1 JSON requested for Indonesia, 2024.

Output: `data/processed/modis_run_01/modis_clean.json`

The JSON object contains `schema_version` and a `detections` array.

| Field | Meaning |
|---|---|
| sensor | MODIS |
| satellite | Terra or Aqua |
| latitude, longitude | Geographic coordinates in degrees |
| acquired_at_utc | Acquisition timestamp, e.g. 2024-01-01T02:14:00Z |
| frp_mw | Fire radiative power in megawatts |
| confidence_value | Original MODIS confidence, integer 0–100 |
| confidence_scale | MODIS_0_100; do not interpret as VIIRS confidence |
| daynight | D = day, N = night |
| collection_version | Original source version |
| detection_type | Original NASA type code, or null if absent |
| source_file | Original filename |
| source_row | One-based record position in the input JSON array |

## Cleaning and limitations

The cleaner validates required output fields, timestamps within 2024,
coordinate ranges, confidence, and nonnegative finite FRP.
It removes exact duplicate source records.

Low-confidence detections and all recognized detection types are retained.
Indonesia’s country boundary is not independently checked.
Fields not exported remain available in the unchanged raw download.

These are satellite detections, not unique fires, burned area, or
harmonized activity. Zero detections does not establish zero fire activity.

## Initial run

- Input records: 23,542
- Accepted: 23,542
- Exact duplicates removed: 0
- Rejected: 0

`quality_report.json` records rejection reasons and the input SHA-256 checksum.
Raw and processed datasets are excluded from Git.

## Team handoff

- Member 2: use this detection schema for harmonization; document later filtering.
- Member 3: dashboard data is not yet aggregated into daily activity.
- Member 4: use latitude/longitude for markers and UTC timestamps for filtering.
- VIIRS support remains pending inspection of its downloaded file.