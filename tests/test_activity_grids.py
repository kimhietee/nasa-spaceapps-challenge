"""Grid diagnostics use synthetic coordinates; no real records are modified."""
import math

import pytest

from scripts.compare_activity_grids import EARTH_KM, compare, grid_cell, project, summarize, write_results


def longitude(x_km):
    return 114 + math.degrees(x_km / (EARTH_KM * math.cos(math.radians(-2))))


def test_repeated_detections_collapse_per_sensor_per_day_not_across_days():
    rows = [('2022-01-01', 'MODIS', 114.001, -1.999, 1, None)] * 2
    rows += [('2022-01-01', 'VIIRS', 114.001, -1.999, 1, None),
             ('2022-01-02', 'MODIS', 114.001, -1.999, 1, None)]
    output = compare(rows, 1)
    assert len(output) == 48
    first = output[0]
    assert first['modis_detections'] == 3
    assert first['modis_cells'] == 2
    assert first['viirs_cells'] == 1
    assert first['union_cells'] == 2
    assert first['shared_cells'] == 1
    assert first['grouped_activity'] == 4  # Original activity units are a different measure.
    assert output[1]['union_cells'] == 0


def test_quality_diagnostic_does_not_change_primary_counts():
    rows = [('2022-01-01', 'MODIS', 114, -2, 1, 'g'),
            ('2022-01-01', 'VIIRS', 114, -2, 1, 'g'),
            ('2022-01-01', 'VIIRS', 115, -2, 0, None)]
    primary = summarize(compare(rows, 1))
    quality = summarize(compare(rows, 1, eligible_only=True))
    assert primary['union_cells'] == 2
    assert quality['union_cells'] == 1
    assert primary['grouped_activity'] == 2
    assert quality['grouped_activity'] == 1
    assert primary['viirs_only_share'] == .5
    assert quality['jaccard'] == 1


def test_floor_and_half_cell_offset_expose_boundary_sensitivity():
    assert project(114, -2) == (0, 0)
    assert grid_cell(longitude(-.1), -2, 1)[0] == -1
    rows = [('2022-01-01', 'MODIS', longitude(-.1), -2, 1, None),
            ('2022-01-01', 'VIIRS', longitude(.1), -2, 1, None)]
    assert summarize(compare(rows, 1))['union_cells'] == 2
    assert summarize(compare(rows, 1, offset=.5))['union_cells'] == 1


@pytest.mark.parametrize('size', [0, -1, float('nan'), float('inf')])
def test_invalid_grid_sizes_are_rejected(size):
    with pytest.raises(ValueError):
        grid_cell(114, -2, size)


def test_reports_keep_all_grid_quality_origin_combinations(tmp_path):
    rows = [('2022-01-01', 'MODIS', 114, -2, 1, None)]
    report, csv_file = write_results(rows, 'synthetic-hash', tmp_path)
    assert len(csv_file.read_text().splitlines()) == 577
    text = report.read_text(encoding='utf-8')
    assert 'different units' in text
    assert 'No calibration is fitted' in text
    assert 'not independent validation' in text
    assert 'not an equal-area' in text
