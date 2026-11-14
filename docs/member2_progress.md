# Member 2: 2024 sensor comparison

## Checklist
- [x] Read both schema 1.0 cleaned JSON inputs.
- [x] Document and apply sensor-specific analysis filters.
- [x] Count unique cells per UTC day and sensor.
- [x] Export daily counts and 52 weekly bins per sensor.
- [x] Test repeat observations, sensors, filters, grid boundaries, year-end, and missing data.
- [x] Include both test/ and tests/ in pytest discovery.
- [x] Commit and push comparison milestone (cb2e286).
- [ ] Connect comparison results to the backend database and API.
- [ ] Align the backend geographic settings and grid with Indonesia.
- [ ] Evaluate experimental calibration on held-out periods if required.
- [ ] Supply an appropriate historical baseline before anomaly scoring.

## Run
From the repository root, using the existing Python environment:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s test -v
.\.venv\Scripts\python.exe -m firewatch.comparison data/processed/modis_run_02/detections_clean.json data/processed/viirs_run_01/detections_clean.json --output data/processed/comparison_run_01/comparison.json
```

The output already exists locally; choose a new filename to repeat the run.
Existing output files are protected against replacement.
Only supply ONE chosen input per sensor, not all historical run folders.
Raw and processed datasets remain excluded from Git.

## Analysis contract
- MODIS: retain confidence >=30. VIIRS: retain nominal/high (n/h).
- Retain detection_type 0 only. Missing type is excluded, not assumed to be 0.
- Exclusion counts are sequential: confidence first, then detection type.
- Fixed global grid: origin longitude -180, latitude -90; resolution 0.01 degrees.
  Cell indices use floor((coordinate-origin)/resolution).
- Multiple detections, including Terra/Aqua overpasses, in the same cell/day/sensor
  contribute ONE active cell-day. Different sensors remain separate.
- Weeks use the existing backend convention: min(52, floor((day_of_year-1)/7)+1).
  The final week includes the remaining year-end days. These are not ISO weeks.
- Daily entries exist only for dates with retained detections. Weekly bins without
  retained detections have null active_cell_days. Coverage is always unknown;
  neither detection presence nor absence establishes complete observation coverage.
- Grid cells vary in physical area with latitude. This is a detection activity
  comparison, not burned area or unique fires, and not a calibrated combined index.
- Country membership relies on the Indonesia archive request; no country polygon
  or Philippine bounding box is applied by this module.

## Backend integration
The module lives in firewatch/comparison.py and shares the existing package.
The existing database/API pipeline is not yet wired to this result.
Its Philippine grid and region defaults must not be mixed with this global grid:
reconcile grid indices and definitions before inserting any results.
The backend owner should handle Indonesia region configuration and the adapter.
No 2013-2022 fit or 2003-2022 historical baseline is available from 2024 inputs.
Keep historical anomaly scoring unavailable for these data.

## Verified run
Input MODIS 23,542; retained 18,214.
Input VIIRS S-NPP 104,186; retained 83,282.
14 cleaner/comparison unittest tests passed. Daily and weekly totals reconcile.
The backend's separate pytest suite was not run: backend dependencies are not
installed in this local environment. Test discovery is configured for both folders.


## Team synchronization checkpoint - 2026-11-14
- Current branch: feature/member2-harmonization; published milestone cb2e286.
- backend/setup at 6453e18 merged Member 1 PR #1. Its new merge commit
  adds no implementation changes beyond the common code already in this branch.
- main has no commits missing from this branch at this checkpoint.
- front exists remotely; frontend/backend integration has not been verified.
- Working branches and an open/merged PR do not automatically update main.
- Fetch regularly to inspect updates. Merge the agreed integration branch only
  after reviewing changes; a plain pull updates only the current tracking branch.
- After integration, run cleaner/comparison tests, the backend suite, and a real
  data API check. Passing unit tests alone does not establish full integration.
- Update this checklist after each completed milestone and record validation.
