# Indonesia comparison API

The comparison endpoint reads `data/indonesia.db`, not an archive or comparison
JSON file. Set `FIREWATCH_INDONESIA_DB` to use another database path. The
connection is read-only and validates the Indonesia database schema.

Run from the project root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8011
```

| URL | Expected result |
| --- | --- |
| `/api/comparison/health` | `status: ok`, `database: sqlite`, `country_code: IDN`, source record count 617112 |
| `/api/comparison/weekly` | 104 sensor-week rows for 2024 |
| `/api/comparison/weekly?year=2022` | 104 sensor-week rows for 2022 |
| `/api/comparison/weekly?year=2025&sensor=VIIRS_SNPP` | 52 VIIRS rows for 2025 |
| `/prototype` | Existing prototype, using database-derived 2024 results |

Supported years are 2022-2025. The default remains 2024 because the current
prototype labels its chart as 2024. No frontend code changes are needed for
that preview. A year selector is a separate UI task.

The old `/api/health` and `/api/aois/...` routes still belong to the separate
Philippines pipeline. Use `/api/comparison/health` for this Indonesia database.

Counting preserves the existing comparison rules: MODIS confidence >=30,
VIIRS nominal/high, type 0 only, unique 0.01-degree global grid cell per UTC
date and sensor, then weekly sums. Terra and Aqua share the MODIS series.
Weeks use fixed bins capped at 52, not ISO weeks. Missing detections remain
null because observation coverage is unknown. No calibration is applied.

Only 52 or 104 rows reach the browser. Aggregation runs inside SQLite using
the existing Decimal-based grid calculation to preserve grid boundaries.
Small results are cached in each API process by database path, file version,
year and sensor; changed database or WAL file signatures invalidate them.
The first request for a selection computes its aggregates again after a
restart. The cache does not modify the database.

Validation:

```powershell
.\.venv\Scripts\python.exe -B -m pytest -q -p no:cacheprovider
```

Verified in the preparation workspace: 36 tests and 16 subtests passed with
`--ignore=tests/test_api.py`. The legacy HTTP tests were excluded because the
restricted Windows session's local socket creation hangs in TestClient.
The updated tests call the route functions directly and validate the actual
FastAPI query fields and OpenAPI registration. A running-server HTTP smoke
check is still required after installation.

The complete 2024 result matches the original Python comparison function,
row for row. MODIS totals 17,478 and VIIRS totals 65,207 active cell-days.
All four years and both sensor filters were checked against the installed
database. Measured direct first-query times were 0.3-1.6 seconds; repeated
queries took about 1 ms. These are local query timings, not HTTP benchmarks.
