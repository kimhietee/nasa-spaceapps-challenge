# FIRMS cleaned data - schema 1.0

Inputs: NASA FIRMS MODIS Collection 6.1 and VIIRS S-NPP Collection 2 JSON
requested for Indonesia, January 1 through December 31, 2024.

The shared cleaner is `scripts/clean_firms.py`. It processes one JSON array
per invocation. The old `scripts/clean_modis.py` command is replaced.
No additional Python packages are required.

## Run from the repository root (Windows PowerShell)

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -v
.\.venv\Scripts\python.exe scripts/clean_firms.py data/raw/fire_archive_M-C61_846503.json --output data/processed/modis_run_02
.\.venv\Scripts\python.exe scripts/clean_firms.py data/raw/fire_archive_SV-C2_846504.json --output data/processed/viirs_run_01
```

Use a NEW output directory for each subsequent run; existing directories
are not overwritten. The runs above already exist locally.

## Output contract

Each run contains `detections_clean.json` and `quality_report.json`.
The detection file is an object with `schema_version: "1.0"` and a
`detections` array. The backend should read that array from both sensor
outputs. No sensor observations are merged into unique fire events here.

| Field | Meaning |
|---|---|
| sensor | MODIS or VIIRS_SNPP |
| satellite | Terra, Aqua, or Suomi-NPP |
| latitude, longitude | Geographic coordinates in degrees |
| acquired_at_utc | UTC timestamp, e.g. 2024-01-01T02:14:00Z |
| frp_mw | Fire radiative power in megawatts |
| confidence_value | MODIS integer 0-100; VIIRS string l, n, or h |
| confidence_scale | MODIS_0_100 or VIIRS_L_N_H |
| daynight | D = day, N = night |
| collection_version | Original source version as a string |
| detection_type | Original NASA type code (0-3), or null if absent |
| source_file | Original filename |
| source_row | One-based record position in the input JSON array |

VIIRS l/n/h mean low/nominal/high. Confidence scales are sensor-specific;
never compare them numerically or convert them to equivalent percentages.
The downloaded VIIRS instrument and satellite both say SNPP; these are
normalized to sensor VIIRS_SNPP and satellite Suomi-NPP.

## Cleaning and limitations

The cleaner validates required fields, timestamps within 2024, global
coordinate ranges, sensor/satellite combinations, collection versions,
confidence, and finite nonnegative FRP. Exact duplicate source records
are removed within each input file; cross-file deduplication is not performed.

Low-confidence detections and all recognized detection types are retained.
Indonesia's country boundary is not independently checked. Fields not
exported remain available in the unchanged raw downloads. Both input and
output are held in memory; this is a single-year prototype, not a streaming loader.

These are satellite detections, not unique fires, burned area, or harmonized
activity. Zero detections does not establish zero fire activity.

## Verified runs

| Run folder | Input | Accepted | Duplicates | Rejected |
|---|---:|---:|---:|---:|
| modis_run_02 | 23,542 | 23,542 | 0 | 0 |
| viirs_run_01 | 104,186 | 104,186 | 0 | 0 |

The earlier modis_run_01 is preserved; its detections match modis_run_02.
Use only the latest chosen run per sensor, not all historical run folders.

The quality report records rejection reasons, one-based source rows,
counts, source filename, and input SHA-256 checksum. Raw and processed
files are excluded from Git; teammates must obtain the originals separately
and reproduce these runs, or arrange a separate data handoff.

## Team handoff

- Member 1 owns ingestion, validation, deduplication, and this shared schema.
- Backend reads the cleaned JSON and owns documented analysis filters,
  harmonization, database storage, and API responses.
- Dashboard data is not yet aggregated into daily or weekly activity.
- Map consumers use latitude/longitude and UTC timestamps.
- Backend integration must use Indonesia settings; the earlier Philippine
  defaults and historical baseline assumptions do not fit these 2024 inputs.
- Historical anomaly scoring requires an appropriate baseline; this dataset
  alone does not supply one.
- Backend pytest currently targets tests/, while these tests use test/.
  Reconcile discovery when integrating branches so neither suite is skipped.
