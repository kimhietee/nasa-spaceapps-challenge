# Harmonization pilot validation

Province: **Central Kalimantan**. Period: **2022–2025, UTC**. Selection: **type 0, presumed vegetation fires**.

This is a one-province diagnostic of the existing method, not a national validation or ground-truth fire assessment.

## Reproducibility

- Archive processed at: `2026-11-14T10:33:01.941287+00:00`.
- Archive SHA-256 before and after the run: `71083cb034242e4d4663a2797ffddce936625b858db1d152d667c24d01577994` (unchanged).
- Database opened with SQLite `mode=ro`. No archive rows, matching assignments, or application settings changed.
- `harmonization_monthly.csv` contains all 48 selected year/month bins and exact integer counts.
- Recorded matching configuration: `{"footprint": "unavailable: scan/track retained but orientation not provided", "formula": "0.6 * distance_score + 0.4 * time_score", "grouping": "maximum-weight one-to-one assignment; unmatched retained", "id": "center-1km-30min-v1", "matched": 0.7, "max_distance_km": 1, "max_time_min": 30, "possible": 0.45}`.

## Annual counts

| Year | MODIS | VIIRS | VIIRS / MODIS | Grouped activity | Reduction from raw sum |
|---|---:|---:|---:|---:|---:|
| 2022 | 302 | 1,374 | 4.55 | 1,648 | 1.7% |
| 2023 | 7,676 | 33,223 | 4.33 | 39,862 | 2.5% |
| 2024 | 1,301 | 4,453 | 3.42 | 5,551 | 3.5% |
| 2025 | 780 | 3,878 | 4.97 | 4,651 | 0.2% |

## What the matching accomplishes

- Raw detections: **52,987**; grouped activity: **51,712**.
- Removes **1,275** paired VIIRS representatives from this province's raw sum.
- MODIS-anchored groups: **419 matched**, **854 possible**.
- Matching-eligible observations: MODIS **9,416**, VIIRS **40,582**. Lower-quality type-0 observations remain in the calendar as unmatched observations.
- Every month satisfies activity = MODIS + VIIRS − paired VIIRS in the selected province.
- **1** MODIS anchors have partners outside this province; **3** VIIRS members have anchors outside it. Regional grouped activity uses MODIS date/province.

## Remaining sensor dependence

- Unpaired VIIRS observations contribute **80.5%** of grouped activity.
- **671** MODIS observations have more than one VIIRS candidate above the assignment score threshold. One-to-one assignment cannot consolidate all such candidates; they are not necessarily the same fire.
- Platform counts: `{"Aqua": 7231, "SNPP": 42928, "Terra": 2828}`. The MODIS aggregate and single VIIRS platform do not have identical sampling.
- A reduction in double-counting does not establish a sensor-independent measurement or remove resolution, overpass, cloud, or detection differences.

## Temporal agreement diagnostics

- Monthly count correlation (48 bins): **0.997**.
- Daily count correlation (1,461 date bins): **0.865**.
- Daily count correlation on the 403 dates with detections from both sensors: **0.856**.
- The first two correlations use zero recorded detections for empty bins. This is only a count-series convention: observation coverage and absence of fires remain unknown.
- Both-detected-day correlation has selection bias and is a sensitivity check, not a corrected estimate. Correlation can reflect a common burning season; it does not measure detection accuracy or calibration.

## Decision for the next milestone

**Accounting is supported; sensor-independent harmonization is not established.** Keep the existing groups as a provisional association layer with source counts alongside them. Do not label them confirmed fires or a calibrated cross-sensor record.

Next, compare daily active cells on a fixed shared grid with the existing grouped series in this same province. Examine grid-size sensitivity, sensor ratios, and seasonal patterns. If any calibration is fitted, reserve 2025 for evaluation and fit only on 2022–2024. Retain or change the calendar metric only after that comparison; active cells also require validation and do not measure burned area.

The mentor-approved region/month anomaly method remains unchanged. This diagnostic does not validate forecast accuracy, the optimality of matching assignments, or the completeness of satellite observation coverage.

## Repeat

From the repository root (replace the database path if your launcher uses an override):

```powershell
.\.venv\Scripts\python.exe scripts/validate_harmonization.py `
  --db "../firewatch-command-center-preview/backend/data/firewatch.sqlite" `
  --region "Central Kalimantan" --output docs/validation
```
