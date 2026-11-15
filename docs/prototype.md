# Indonesia working preview

Branch: prototype/indonesia-preview. Small real-data preview; not the final dashboard.

Run from repository root:

```powershell
.\.venv\Scripts\python.exe -m uvicorn api.main:app --port 8011
```

Open http://127.0.0.1:8011/prototype . Requires the existing
 data/processed/comparison_run_01/comparison.json file.

Try selecting MODIS, changing the week range, and resetting filters.
Full-year totals: MODIS 17,478; VIIRS S-NPP 65,207 active cell-days.
The chart and table use the actual comparison API. Both series share a vertical
scale; nulls remain unknown. No combined harmonized metric, live feed, or map
is claimed. Full 2022-2025 ingestion and matching remain pending.
