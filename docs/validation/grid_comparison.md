# Shared-grid activity pilot

Central Kalimantan; 2022–2025; presumed vegetation fires (type 0); UTC days.

## Method

- Nominal 1, 2 and 5 km grids, each tested at the base origin and a half-cell shift in both axes.
- Fixed spherical equirectangular coordinates: x = R × radians(lon − 114) × cos(−2°); y = R × radians(lat + 2), with R = 6371.0088 km. This near-equator pilot approximation is not an equal-area or globally distance-accurate grid.
- Projection reference: https://proj.org/en/stable/operations/projections/eqc.html (spherical forward formulas). No projection dependency was added.
- An active cell-day is one grid cell with at least one retained detection on one UTC day. Repeated detections from a sensor/satellite in the same cell/day count once.
- Monthly numbers are sums of daily cell counts, not distinct cells over the month. The combined series is the per-day spatial union of MODIS and VIIRS cells, not their sum.
- Province membership follows observation centers; intersecting cells are not clipped to a province polygon. A cell is a display/analysis bin, not an observed fire footprint or burned area.
- Primary scope retains all type-0 observations, matching the current calendar. The eligible-only diagnostic keeps the stored matching-eligible rows (MODIS confidence ≥30, VIIRS nominal/high, type 0). It changes no stored records or production filters.
- Existing grouped counts are reported separately because detections/groups and cell-days have different units; their numerical difference is not an accuracy error.
- No calibration is fitted. 2025 results below are descriptive sensitivity checks, not independent validation of a tuned method.

## All retained type-0 observations

| Grid km | Offset | MODIS cell-days | VIIRS cell-days | VIIRS/MODIS | Union cell-days | Shared/union | VIIRS-only/union | Monthly correlation |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 1 | 0 | 9,398 | 27,111 | 2.885 | 33,300 | 9.6% | 71.8% | 0.997 |
| 1 | 0.5 | 9,414 | 26,980 | 2.866 | 33,139 | 9.8% | 71.6% | 0.997 |
| 2 | 0 | 7,662 | 21,737 | 2.837 | 26,038 | 12.9% | 70.6% | 0.996 |
| 2 | 0.5 | 7,659 | 21,761 | 2.841 | 26,093 | 12.8% | 70.6% | 0.996 |
| 5 | 0 | 6,089 | 17,020 | 2.795 | 19,923 | 16.0% | 69.4% | 0.994 |
| 5 | 0.5 | 6,036 | 16,971 | 2.812 | 19,844 | 15.9% | 69.6% | 0.994 |

Baseline: MODIS **10,059**, VIIRS **42,928**, raw VIIRS/MODIS **4.268**, existing grouped activity **51,712**.

## Quality-controlled sensitivity

| Grid km | Offset | MODIS cell-days | VIIRS cell-days | VIIRS/MODIS | Union cell-days |
|---|---|---:|---:|---:|---:|
| 1 | 0 | 8,823 | 25,915 | 2.937 | 31,777 |
| 1 | 0.5 | 8,846 | 25,768 | 2.913 | 31,625 |
| 2 | 0 | 7,228 | 20,928 | 2.895 | 25,043 |
| 2 | 0.5 | 7,231 | 20,927 | 2.894 | 25,055 |
| 5 | 0 | 5,772 | 16,497 | 2.858 | 19,286 |
| 5 | 0.5 | 5,734 | 16,473 | 2.873 | 19,231 |

## Annual grid-size sensitivity (base origin, all retained type 0)

| Year | Grid km | MODIS cell-days | VIIRS cell-days | VIIRS/MODIS | Union cell-days |
|---|---|---:|---:|---:|---:|
| 2022 | 1 | 296 | 1,181 | 3.990 | 1,436 |
| 2022 | 2 | 282 | 1,114 | 3.950 | 1,336 |
| 2022 | 5 | 258 | 1,022 | 3.961 | 1,203 |
| 2023 | 1 | 7,051 | 19,206 | 2.724 | 23,371 |
| 2023 | 2 | 5,570 | 14,518 | 2.606 | 17,157 |
| 2023 | 5 | 4,280 | 10,664 | 2.492 | 12,282 |
| 2024 | 1 | 1,279 | 3,530 | 2.760 | 4,592 |
| 2024 | 2 | 1,116 | 3,161 | 2.832 | 4,001 |
| 2024 | 5 | 945 | 2,780 | 2.942 | 3,408 |
| 2025 | 1 | 772 | 3,194 | 4.137 | 3,901 |
| 2025 | 2 | 694 | 2,944 | 4.242 | 3,544 |
| 2025 | 5 | 606 | 2,554 | 4.215 | 3,030 |

## Grid-origin sensitivity

| Grid km | Union change after half-cell shift | VIIRS/MODIS change |
|---|---:|---:|
| 1 | -0.5% | -0.019 |
| 2 | 0.2% | 0.004 |
| 5 | -0.4% | 0.016 |

## Seasonal-pattern check

| Year | Existing grouped peak month | 1 km union peak month | 2 km union peak month | 5 km union peak month |
|---|---|---|---|---|
| 2022 | 09 | 09 | 09 | 09 |
| 2023 | 10 | 09 | 09 | 09 |
| 2024 | 09 | 09 | 09 | 09 |
| 2025 | 09 | 09 | 09 | 09 |

1 km union versus existing grouped monthly-pattern correlation: **0.996**.

2 km union versus existing grouped monthly-pattern correlation: **0.989**.

5 km union versus existing grouped monthly-pattern correlation: **0.979**.

Peak months are numbered 01–12. Pooled correlations can be dominated by the large 2023 burning season; neither correlation nor agreement on peak months establishes measurement accuracy.

## Interpretation and next decision

Aggregation can reduce repeated sampling of nearby activity, but a sensor ratio closer to one alone does not prove accuracy. Larger cells also merge spatially separate activity; same-cell/day overlap does not prove the same fire or simultaneous observation.
Shared/union measures agreement among recorded active cell-days, not detection probability. Cloud, overpass, platform, and missing-coverage differences remain. Empty date bins mean no recorded detections, not confirmed absence of fire.
**Recommendation: retain the current provisional grouped activity as the production calendar measure for this milestone.** The grid pilot has not established a sensor-independent replacement. A 1 km active-cell view is a reasonable separate diagnostic candidate: larger grids merge more location detail without resolving the residual sensor differences. This is a conservative product recommendation for this pilot, not proof that 1 km is scientifically optimal.
Keep the mentor-approved anomaly method unchanged. If a grid measure is adopted later, document its different units, fixed origin and resolution, validate beyond this province, and update dependent summaries consistently. Do not silently replace activity units with cell-days or add a correction factor merely to force sensor totals to match.

## Reproduction

Archive SHA-256 before/after: `71083cb034242e4d4663a2797ffddce936625b858db1d152d667c24d01577994` (unchanged). The database was opened with `mode=ro`.

```powershell
.\.venv\Scripts\python.exe scripts/compare_activity_grids.py `
  --db "../firewatch-command-center-preview/backend/data/firewatch.sqlite" `
  --output docs/validation
```

`grid_comparison_monthly.csv` includes every month for all 12 grid/origin/quality combinations (576 rows).
