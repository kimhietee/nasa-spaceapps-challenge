# Indonesia FIRMS database setup

This package contains a database built from the two supplied 2022-2025 Indonesia
archive files, its reusable builder, and tests. No third-party dependencies or
SQLite command-line installation are required.

## Install

Copy `scripts/build_indonesia_db.py` into the project's `scripts` folder,
`tests/test_indonesia_db.py` into `tests`, and `data/indonesia.db` into `data`.
Do not overwrite an existing database without reviewing it first.

The separate name `indonesia.db` prevents the old Philippines pipeline from
accidentally deleting this database. The legacy `firewatch.db` schema and API
are not compatible with this detection schema. Connecting the API and UI is a
separate task; do not point the legacy API at this file yet.

## Rebuild from the project root

```powershell
.\.venv\Scripts\python.exe -B scripts\build_indonesia_db.py
```

Default input: `data/processed/**/fire_archive_*.json`.
Default output: `data/indonesia.db`. Existing output is never overwritten.
For another build use `--db-path data/indonesia_rebuilt.db`.

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -p test_indonesia_db.py
```

## Schema

| Table | Purpose |
| --- | --- |
| `meta` | Schema version, country scope, real-data label, build time, ingestion policies, unknown observation coverage |
| `source_file` | Relative archive path, SHA-256, byte size, import time, count, first/last timestamps |
| `detection` | Source row, normalized sensor, original instrument/satellite, UTC timestamp, latitude/longitude, FRP, confidence, detection type, day/night, original version, scan/track, brightness fields |

Foreign keys and checks enforce source references, sensor/confidence contracts,
coordinate ranges and basic measurement validity. Indexes support timestamp,
sensor-plus-timestamp, and coordinate queries; source row references are unique.
The coordinate index is a basic B-tree, not a spatial boundary index.

Imports stream JSON and insert in batches of 5,000. An invalid record aborts
the build and removes the incomplete new database. The source archives remain
unchanged. All validated detections are preserved, including repeated source
records, low confidence, nonvegetation types and missing types. This is an
ingestion database, not a vegetation-only analysis result. Original source row
numbers and hashes allow tracing attributes back to the archives.

MODIS version strings `6.03` and `61.03` are preserved as supplied; their
scientific compatibility is not assumed. Indonesia membership is inherited
from the archive requests and has not been verified against a country polygon.
Missing observations are not converted into zero activity. No calibration,
historical baseline, or harmonized counts have been added.
