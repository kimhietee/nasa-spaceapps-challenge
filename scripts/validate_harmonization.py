"""Read-only, single-province evaluation of the existing matching-based calendar."""
import argparse
from collections import Counter, defaultdict
import csv
from datetime import date, timedelta
import hashlib
import json
import math
from pathlib import Path
import sqlite3


def correlation(left, right):
    if len(left) < 2 or len(left) != len(right):
        return None
    a, b = sum(left) / len(left), sum(right) / len(right)
    numerator = sum((x - a) * (y - b) for x, y in zip(left, right))
    denominator = math.sqrt(sum((x - a) ** 2 for x in left) * sum((y - b) ** 2 for y in right))
    return numerator / denominator if denominator else None


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def collect(connection, region):
    rows = connection.execute("""SELECT year,month,date,sensor,satellite,eligible,group_id,status
        FROM observations WHERE region=? AND type=0 AND year BETWEEN 2022 AND 2025""", (region,)).fetchall()
    if not rows:
        raise ValueError(f'No presumed-vegetation observations for province: {region}')
    monthly = {(y, m): Counter() for y in range(2022, 2026) for m in range(1, 13)}
    daily = defaultdict(Counter)
    platforms = Counter()
    for row in rows:
        year, month, stamp, sensor, satellite, eligible, group, status = row
        platforms[satellite] += 1
        counts = monthly[year, month]
        counts[sensor.lower()] += 1
        counts[sensor.lower() + '_eligible'] += bool(eligible)
        daily[stamp][sensor] += 1
        contributes = sensor == 'MODIS' or group is None
        counts['activity'] += contributes
        counts['suppressed_viirs'] += sensor == 'VIIRS' and group is not None
        counts['unpaired_viirs'] += sensor == 'VIIRS' and group is None
        counts['matched_groups'] += sensor == 'MODIS' and status == 'matched'
        counts['possible_groups'] += sensor == 'MODIS' and status == 'possible'
    fields = ('modis', 'viirs', 'modis_eligible', 'viirs_eligible', 'activity',
              'suppressed_viirs', 'unpaired_viirs', 'matched_groups', 'possible_groups')
    output = [dict(year=y, month=m, **{field: counts[field] for field in fields})
              for (y, m), counts in monthly.items()]
    for row in output:
        assert row['activity'] == row['modis'] + row['viirs'] - row['suppressed_viirs']
    multiple = connection.execute("""SELECT COUNT(*) FROM (
        SELECT p.modis_id FROM candidate_pairs p JOIN observations m ON m.id=p.modis_id
        WHERE m.region=? AND m.type=0 AND p.score>=0.45
        GROUP BY p.modis_id HAVING COUNT(*)>1)""", (region,)).fetchone()[0]
    boundaries = connection.execute("""SELECT
        SUM(m.region=? AND v.region!=?), SUM(v.region=? AND m.region!=?)
        FROM groups g JOIN observations m ON m.id=g.modis_id
        JOIN observations v ON v.id=g.viirs_id""", (region,) * 4).fetchone()
    dates = []
    stamp = date(2022, 1, 1)
    while stamp <= date(2025, 12, 31):
        dates.append(str(stamp))
        stamp += timedelta(days=1)
    both = [d for d in dates if daily[d]['MODIS'] and daily[d]['VIIRS']]
    metadata = {row[0]: row[1] for row in connection.execute('SELECT key,value FROM metadata')}
    return {
        'monthly': output, 'platforms': dict(platforms),
        'multiple_candidates': multiple,
        'outbound_groups': boundaries[0] or 0, 'inbound_groups': boundaries[1] or 0,
        'days_both_detected': len(both),
        'daily_correlation': correlation([daily[d]['MODIS'] for d in dates], [daily[d]['VIIRS'] for d in dates]),
        'both_detected_correlation': correlation([daily[d]['MODIS'] for d in both], [daily[d]['VIIRS'] for d in both]),
        'monthly_correlation': correlation([r['modis'] for r in output], [r['viirs'] for r in output]),
        'processed_at': metadata.get('processed_at', 'not recorded'),
        'config': json.loads(metadata.get('config', '{}')),
    }


def percentage(part, whole):
    return f'{100 * part / whole:.1f}%' if whole else 'unavailable'


def write_report(result, region, database_hash, destination):
    destination.mkdir(parents=True, exist_ok=True)
    monthly = result['monthly']
    csv_path = destination / 'harmonization_monthly.csv'
    with csv_path.open('w', newline='', encoding='utf-8') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(monthly[0]))
        writer.writeheader()
        writer.writerows(monthly)
    totals = {key: sum(row[key] for row in monthly) for key in monthly[0] if key not in ('year', 'month')}
    lines = [
        '# Harmonization pilot validation', '',
        f'Province: **{region}**. Period: **2022–2025, UTC**. Selection: **type 0, presumed vegetation fires**.', '',
        'This is a one-province diagnostic of the existing method, not a national validation or ground-truth fire assessment.', '',
        '## Reproducibility', '',
        f'- Archive processed at: `{result["processed_at"]}`.',
        f'- Archive SHA-256 before and after the run: `{database_hash}` (unchanged).',
        '- Database opened with SQLite `mode=ro`. No archive rows, matching assignments, or application settings changed.',
        '- `harmonization_monthly.csv` contains all 48 selected year/month bins and exact integer counts.',
        f'- Recorded matching configuration: `{json.dumps(result["config"], sort_keys=True)}`.', '',
        '## Annual counts', '',
        '| Year | MODIS | VIIRS | VIIRS / MODIS | Grouped activity | Reduction from raw sum |',
        '|---|---:|---:|---:|---:|---:|',
    ]
    for year in range(2022, 2026):
        rows = [r for r in monthly if r['year'] == year]
        m, v, activity = (sum(r[key] for r in rows) for key in ('modis', 'viirs', 'activity'))
        ratio = f'{v / m:.2f}' if m else 'unavailable'
        lines.append(f'| {year} | {m:,} | {v:,} | {ratio} | {activity:,} | {percentage(m + v - activity, m + v)} |')
    lines += [
        '', '## What the matching accomplishes', '',
        f'- Raw detections: **{totals["modis"] + totals["viirs"]:,}**; grouped activity: **{totals["activity"]:,}**.',
        f'- Removes **{totals["suppressed_viirs"]:,}** paired VIIRS representatives from this province\'s raw sum.',
        f'- MODIS-anchored groups: **{totals["matched_groups"]:,} matched**, **{totals["possible_groups"]:,} possible**.',
        f'- Matching-eligible observations: MODIS **{totals["modis_eligible"]:,}**, VIIRS **{totals["viirs_eligible"]:,}**. Lower-quality type-0 observations remain in the calendar as unmatched observations.',
        '- Every month satisfies activity = MODIS + VIIRS − paired VIIRS in the selected province.',
        f'- **{result["outbound_groups"]}** MODIS anchors have partners outside this province; **{result["inbound_groups"]}** VIIRS members have anchors outside it. Regional grouped activity uses MODIS date/province.', '',
        '## Remaining sensor dependence', '',
        f'- Unpaired VIIRS observations contribute **{percentage(totals["unpaired_viirs"], totals["activity"])}** of grouped activity.',
        f'- **{result["multiple_candidates"]:,}** MODIS observations have more than one VIIRS candidate above the assignment score threshold. One-to-one assignment cannot consolidate all such candidates; they are not necessarily the same fire.',
        f'- Platform counts: `{json.dumps(result["platforms"], sort_keys=True)}`. The MODIS aggregate and single VIIRS platform do not have identical sampling.',
        '- A reduction in double-counting does not establish a sensor-independent measurement or remove resolution, overpass, cloud, or detection differences.', '',
        '## Temporal agreement diagnostics', '',
    ]
    for label, key in [('Monthly count correlation (48 bins)', 'monthly_correlation'),
                       ('Daily count correlation (1,461 date bins)', 'daily_correlation'),
                       (f'Daily count correlation on the {result["days_both_detected"]:,} dates with detections from both sensors', 'both_detected_correlation')]:
        value = result[key]
        lines.append(f'- {label}: **{value:.3f}**.' if value is not None else f'- {label}: unavailable (constant/insufficient data).')
    lines += [
        '- The first two correlations use zero recorded detections for empty bins. This is only a count-series convention: observation coverage and absence of fires remain unknown.',
        '- Both-detected-day correlation has selection bias and is a sensitivity check, not a corrected estimate. Correlation can reflect a common burning season; it does not measure detection accuracy or calibration.', '',
        '## Decision for the next milestone', '',
        '**Accounting is supported; sensor-independent harmonization is not established.** Keep the existing groups as a provisional association layer with source counts alongside them. Do not label them confirmed fires or a calibrated cross-sensor record.', '',
        'Next, compare daily active cells on a fixed shared grid with the existing grouped series in this same province. Examine grid-size sensitivity, sensor ratios, and seasonal patterns. If any calibration is fitted, reserve 2025 for evaluation and fit only on 2022–2024. Retain or change the calendar metric only after that comparison; active cells also require validation and do not measure burned area.', '',
        'The mentor-approved region/month anomaly method remains unchanged. This diagnostic does not validate forecast accuracy, the optimality of matching assignments, or the completeness of satellite observation coverage.', '',
        '## Repeat', '',
        'From the repository root (replace the database path if your launcher uses an override):', '',
        '```powershell',
        '.\\.venv\\Scripts\\python.exe scripts/validate_harmonization.py `',
        '  --db "../firewatch-command-center-preview/backend/data/firewatch.sqlite" `',
        f'  --region "{region}" --output docs/validation',
        '```',
    ]
    report = destination / 'harmonization_validation.md'
    report.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report, csv_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--region', default='Central Kalimantan')
    parser.add_argument('--output', type=Path, default=Path('docs/validation'))
    args = parser.parse_args()
    path = args.db.resolve(strict=True)
    before = digest(path)
    with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True) as connection:
        result = collect(connection, args.region)
    if digest(path) != before:
        raise RuntimeError('Archive changed during validation; rerun against a stable archive.')
    for output in write_report(result, args.region, before, args.output):
        print(output.resolve())


if __name__ == '__main__':
    main()
