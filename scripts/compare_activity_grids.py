"""Compare fixed-grid cell-days with existing activity counts; never modify the archive."""
import argparse
from collections import Counter, defaultdict
import csv
import math
from pathlib import Path
import sqlite3

try:
    from .validate_harmonization import correlation, digest
except ImportError:  # Direct execution from the repository root.
    from validate_harmonization import correlation, digest


EARTH_KM = 6371.0088


def project(lon, lat):
    """Spherical equirectangular pilot grid, true scale at 2 degrees south."""
    return (EARTH_KM * math.radians(lon - 114) * math.cos(math.radians(-2)),
            EARTH_KM * math.radians(lat + 2))


def grid_cell(lon, lat, size_km, offset=0):
    if not math.isfinite(size_km) or size_km <= 0:
        raise ValueError('Grid size must be a positive finite number')
    x, y = project(lon, lat)
    return math.floor(x / size_km - offset), math.floor(y / size_km - offset)


def compare(rows, size_km, offset=0, eligible_only=False):
    cells = defaultdict(lambda: {'MODIS': set(), 'VIIRS': set()})
    counts = defaultdict(Counter)
    for stamp, sensor, lon, lat, eligible, group_id in rows:
        if eligible_only and not eligible:
            continue
        cells[stamp][sensor].add(grid_cell(lon, lat, size_km, offset))
        counts[stamp][sensor] += 1
        counts[stamp]['grouped'] += sensor == 'MODIS' or group_id is None
    monthly = {(year, month): Counter() for year in range(2022, 2026) for month in range(1, 13)}
    for stamp, sensors in cells.items():
        m, v = sensors['MODIS'], sensors['VIIRS']
        result = monthly[int(stamp[:4]), int(stamp[5:7])]
        result.update(modis_detections=counts[stamp]['MODIS'], viirs_detections=counts[stamp]['VIIRS'],
                      grouped_activity=counts[stamp]['grouped'], modis_cells=len(m), viirs_cells=len(v),
                      union_cells=len(m | v), shared_cells=len(m & v),
                      viirs_only_cells=len(v - m), modis_only_cells=len(m - v))
    return [dict(quality='eligible_only' if eligible_only else 'retained_type0',
                 grid_km=size_km, offset_fraction=offset, year=year, month=month,
                 **{key: value[key] for key in ('modis_detections', 'viirs_detections', 'grouped_activity',
                    'modis_cells', 'viirs_cells', 'union_cells', 'shared_cells',
                    'viirs_only_cells', 'modis_only_cells')})
            for (year, month), value in monthly.items()]


def summarize(months):
    total = {key: sum(row[key] for row in months) for key in
             ('modis_detections', 'viirs_detections', 'grouped_activity', 'modis_cells',
              'viirs_cells', 'union_cells', 'shared_cells', 'viirs_only_cells')}
    def ratio(a, b):
        return a / b if b else None
    return {**total,
            'raw_ratio': ratio(total['viirs_detections'], total['modis_detections']),
            'cell_ratio': ratio(total['viirs_cells'], total['modis_cells']),
            'jaccard': ratio(total['shared_cells'], total['union_cells']),
            'viirs_only_share': ratio(total['viirs_only_cells'], total['union_cells']),
            'monthly_correlation': correlation([r['modis_cells'] for r in months], [r['viirs_cells'] for r in months]),
            'grouped_union_correlation': correlation([r['grouped_activity'] for r in months], [r['union_cells'] for r in months])}


def display(value, percent=False):
    if value is None:
        return 'unavailable'
    return f'{value * 100:.1f}%' if percent else f'{value:.3f}'


def write_results(rows, database_hash, destination):
    destination.mkdir(parents=True, exist_ok=True)
    monthly = []
    trials = []
    for eligible in (False, True):
        for size in (1, 2, 5):
            for offset in (0, 0.5):
                result = compare(rows, size, offset, eligible)
                monthly.extend(result)
                trials.append((result[0]['quality'], size, offset, summarize(result)))
    csv_file = destination / 'grid_comparison_monthly.csv'
    with csv_file.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(monthly[0]))
        writer.writeheader()
        writer.writerows(monthly)
    lines = [
        '# Shared-grid activity pilot', '',
        'Central Kalimantan; 2022–2025; presumed vegetation fires (type 0); UTC days.', '',
        '## Method', '',
        '- Nominal 1, 2 and 5 km grids, each tested at the base origin and a half-cell shift in both axes.',
        '- Fixed spherical equirectangular coordinates: x = R × radians(lon − 114) × cos(−2°); y = R × radians(lat + 2), with R = 6371.0088 km. This near-equator pilot approximation is not an equal-area or globally distance-accurate grid.',
        '- Projection reference: https://proj.org/en/stable/operations/projections/eqc.html (spherical forward formulas). No projection dependency was added.',
        '- An active cell-day is one grid cell with at least one retained detection on one UTC day. Repeated detections from a sensor/satellite in the same cell/day count once.',
        '- Monthly numbers are sums of daily cell counts, not distinct cells over the month. The combined series is the per-day spatial union of MODIS and VIIRS cells, not their sum.',
        '- Province membership follows observation centers; intersecting cells are not clipped to a province polygon. A cell is a display/analysis bin, not an observed fire footprint or burned area.',
        '- Primary scope retains all type-0 observations, matching the current calendar. The eligible-only diagnostic keeps the stored matching-eligible rows (MODIS confidence ≥30, VIIRS nominal/high, type 0). It changes no stored records or production filters.',
        '- Existing grouped counts are reported separately because detections/groups and cell-days have different units; their numerical difference is not an accuracy error.',
        '- No calibration is fitted. 2025 results below are descriptive sensitivity checks, not independent validation of a tuned method.', '',
        '## All retained type-0 observations', '',
        '| Grid km | Offset | MODIS cell-days | VIIRS cell-days | VIIRS/MODIS | Union cell-days | Shared/union | VIIRS-only/union | Monthly correlation |',
        '|---|---|---:|---:|---:|---:|---:|---:|---:|',
    ]
    for quality, size, offset, values in trials:
        if quality == 'retained_type0':
            lines.append(f'| {size} | {offset} | {values["modis_cells"]:,} | {values["viirs_cells"]:,} | {display(values["cell_ratio"])} | {values["union_cells"]:,} | {display(values["jaccard"], True)} | {display(values["viirs_only_share"], True)} | {display(values["monthly_correlation"])} |')
    raw = trials[0][3]
    lines += ['', f'Baseline: MODIS **{raw["modis_detections"]:,}**, VIIRS **{raw["viirs_detections"]:,}**, raw VIIRS/MODIS **{display(raw["raw_ratio"])}**, existing grouped activity **{raw["grouped_activity"]:,}**.', '',
              '## Quality-controlled sensitivity', '',
              '| Grid km | Offset | MODIS cell-days | VIIRS cell-days | VIIRS/MODIS | Union cell-days |',
              '|---|---|---:|---:|---:|---:|']
    for quality, size, offset, values in trials:
        if quality == 'eligible_only':
            lines.append(f'| {size} | {offset} | {values["modis_cells"]:,} | {values["viirs_cells"]:,} | {display(values["cell_ratio"])} | {values["union_cells"]:,} |')
    lines += ['', '## Annual grid-size sensitivity (base origin, all retained type 0)', '',
              '| Year | Grid km | MODIS cell-days | VIIRS cell-days | VIIRS/MODIS | Union cell-days |',
              '|---|---|---:|---:|---:|---:|']
    for year in range(2022, 2026):
        for size in (1, 2, 5):
            values = summarize([r for r in monthly if r['quality'] == 'retained_type0' and r['grid_km'] == size and r['offset_fraction'] == 0 and r['year'] == year])
            lines.append(f'| {year} | {size} | {values["modis_cells"]:,} | {values["viirs_cells"]:,} | {display(values["cell_ratio"])} | {values["union_cells"]:,} |')
    lines += ['', '## Grid-origin sensitivity', '',
              '| Grid km | Union change after half-cell shift | VIIRS/MODIS change |',
              '|---|---:|---:|']
    for size in (1, 2, 5):
        base, shifted = [v for quality, s, _, v in trials if quality == 'retained_type0' and s == size]
        delta = shifted['union_cells'] / base['union_cells'] - 1 if base['union_cells'] else None
        ratio_delta = shifted['cell_ratio'] - base['cell_ratio'] if shifted['cell_ratio'] is not None and base['cell_ratio'] is not None else None
        lines.append(f'| {size} | {display(delta, True)} | {display(ratio_delta)} |')
    lines += ['', '## Seasonal-pattern check', '',
              '| Year | Existing grouped peak month | 1 km union peak month | 2 km union peak month | 5 km union peak month |',
              '|---|---|---|---|---|']
    def peaks(year, size, metric):
        series = [r for r in monthly if r['quality'] == 'retained_type0' and r['offset_fraction'] == 0 and r['grid_km'] == size and r['year'] == year]
        highest = max(r[metric] for r in series)
        return ', '.join(f'{r["month"]:02}' for r in series if r[metric] == highest) if highest else 'unavailable'
    for year in range(2022, 2026):
        lines.append(f'| {year} | {peaks(year, 1, "grouped_activity")} | {peaks(year, 1, "union_cells")} | {peaks(year, 2, "union_cells")} | {peaks(year, 5, "union_cells")} |')
    for quality, size, offset, values in trials:
        if quality == 'retained_type0' and offset == 0:
            lines.append(f'\n{size} km union versus existing grouped monthly-pattern correlation: **{display(values["grouped_union_correlation"])}**.')
    lines.append('\nPeak months are numbered 01–12. Pooled correlations can be dominated by the large 2023 burning season; neither correlation nor agreement on peak months establishes measurement accuracy.')
    lines += ['', '## Interpretation and next decision', '',
              'Aggregation can reduce repeated sampling of nearby activity, but a sensor ratio closer to one alone does not prove accuracy. Larger cells also merge spatially separate activity; same-cell/day overlap does not prove the same fire or simultaneous observation.',
              'Shared/union measures agreement among recorded active cell-days, not detection probability. Cloud, overpass, platform, and missing-coverage differences remain. Empty date bins mean no recorded detections, not confirmed absence of fire.',
              '**Recommendation: retain the current provisional grouped activity as the production calendar measure for this milestone.** The grid pilot has not established a sensor-independent replacement. A 1 km active-cell view is a reasonable separate diagnostic candidate: larger grids merge more location detail without resolving the residual sensor differences. This is a conservative product recommendation for this pilot, not proof that 1 km is scientifically optimal.',
              'Keep the mentor-approved anomaly method unchanged. If a grid measure is adopted later, document its different units, fixed origin and resolution, validate beyond this province, and update dependent summaries consistently. Do not silently replace activity units with cell-days or add a correction factor merely to force sensor totals to match.', '',
              '## Reproduction', '',
              f'Archive SHA-256 before/after: `{database_hash}` (unchanged). The database was opened with `mode=ro`.', '',
              '```powershell',
              '.\\.venv\\Scripts\\python.exe scripts/compare_activity_grids.py `',
              '  --db "../firewatch-command-center-preview/backend/data/firewatch.sqlite" `',
              '  --output docs/validation',
              '```', '',
              '`grid_comparison_monthly.csv` includes every month for all 12 grid/origin/quality combinations (576 rows).']
    report = destination / 'grid_comparison.md'
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report, csv_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('docs/validation'))
    args = parser.parse_args()
    path = args.db.resolve(strict=True)
    before = digest(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as c:
        rows = c.execute("""SELECT date,sensor,lon,lat,eligible,group_id FROM observations
            WHERE region='Central Kalimantan' AND type=0 AND year BETWEEN 2022 AND 2025""").fetchall()
    if not rows:
        raise ValueError('No Central Kalimantan type-0 observations found')
    if digest(path) != before:
        raise RuntimeError('Archive changed during evaluation; rerun on a stable snapshot')
    for output in write_results(rows, before, args.output):
        print(output.resolve())


if __name__ == '__main__':
    main()
