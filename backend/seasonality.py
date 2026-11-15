"""Historical seasonal summaries; no forecast or warning thresholds."""
from statistics import median

YEARS = (2022, 2023, 2024, 2025)


def summarize_periods(rows):
    counts = {(r['year'], r['month']): r['activity'] for r in rows}
    months = []
    for month in range(1, 13):
        values = {str(year): counts.get((year, month)) for year in YEARS}
        observed = [value for value in values.values() if value is not None]
        complete = len(observed) == len(YEARS)
        months.append({'month': month, 'counts': values, 'years_with_records': len(observed),
                       'median': median(observed) if complete else None,
                       'min': min(observed) if observed else None,
                       'max': max(observed) if observed else None})
    comparable = [r for r in months if r['median'] is not None]
    largest = max((r['median'] for r in comparable), default=0)
    peaks = [r['month'] for r in comparable if largest > 0 and r['median'] == largest]
    annual = []
    for year in YEARS:
        values = {month: value for (y, month), value in counts.items() if y == year}
        highest = max(values.values(), default=0)
        annual.append({'year': year, 'months_with_records': len(values),
                       'activity': sum(values.values()) if values else None,
                       'peak_months': [m for m, value in sorted(values.items()) if highest > 0 and value == highest],
                       'peak_activity': highest if values else None})
    return {'available': bool(rows), 'months': months, 'years': annual,
            'typical_peak_months': peaks, 'comparable_months': len(comparable),
            'reference_years': list(YEARS),
            'method': 'Typical = median of the same calendar month across all four reference years. '
                      'Months missing any reference-year value are not ranked. '
                      'Ranges are observed minimum–maximum, not prediction intervals. '
                      'Peak ties are retained; zero-only months are not labeled peaks.',
            'limitations': 'Historical recorded activity, not a danger assessment or forecast. '
                           'No detections does not establish zero burning or complete observation coverage. '
                           'Annual peaks compare recorded months only.'}
