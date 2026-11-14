"""Compare cleaned 2024 FIRMS detections: python -m firewatch.comparison --help."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR
import json
from pathlib import Path

SENSORS = {"MODIS", "VIIRS_SNPP"}


def grid_cell(longitude, latitude):
    """Fixed global 0.01-degree grid; floor also handles negative coordinates."""
    def index(value, origin):
        return int(((Decimal(str(value)) - origin) / Decimal("0.01"))
                   .to_integral_value(rounding=ROUND_FLOOR))
    return index(longitude, Decimal(-180)), index(latitude, Decimal(-90))


def load_detections(paths):
    records = []
    for path in paths:
        payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
        if payload.get("schema_version") != "1.0" or not isinstance(payload.get("detections"), list):
            raise ValueError(f"Unsupported cleaned schema: {path}")
        records.extend(payload["detections"])
    return records


def compare(records):
    """Apply analysis filters, then count unique cell/date/sensor combinations."""
    active = defaultdict(set)
    kept = Counter()
    excluded = Counter()
    input_counts = Counter()
    for row in records:
        sensor = row["sensor"]
        if sensor not in SENSORS:
            raise ValueError(f"Unsupported sensor: {sensor}")
        input_counts[sensor] += 1
        stamp = datetime.strptime(row["acquired_at_utc"], "%Y-%m-%dT%H:%M:%SZ")
        if stamp.year != 2024:
            raise ValueError("Comparison requires 2024 data")
        lon, lat = row["longitude"], row["latitude"]
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("Invalid coordinates")
        confidence = row["confidence_value"]
        if sensor == "MODIS":
            if row["confidence_scale"] != "MODIS_0_100" or isinstance(confidence, bool) or not isinstance(confidence, int) or not 0 <= confidence <= 100:
                raise ValueError("Invalid MODIS confidence contract")
            confidence_ok = confidence >= 30
        else:
            if row["confidence_scale"] != "VIIRS_L_N_H" or confidence not in {"l", "n", "h"}:
                raise ValueError("Invalid VIIRS confidence contract")
            confidence_ok = confidence in {"n", "h"}
        if not confidence_ok:
            excluded[f"{sensor}:confidence"] += 1
            continue
        # Missing type is excluded rather than assumed to be vegetation fire.
        if row["detection_type"] != 0:
            excluded[f"{sensor}:nonvegetation_or_unknown_type"] += 1
            continue
        date = stamp.strftime("%Y-%m-%d")
        active[(sensor, date)].add(grid_cell(lon, lat))
        kept[sensor] += 1

    daily = [{"sensor": sensor, "utc_date": date, "active_cells": len(cells)}
             for (sensor, date), cells in sorted(active.items())]
    weekly_counts = Counter()
    weekly_days = Counter()
    for row in daily:
        date = datetime.strptime(row["utc_date"], "%Y-%m-%d")
        week = min(52, (date.timetuple().tm_yday - 1) // 7 + 1)
        weekly_counts[(row["sensor"], week)] += row["active_cells"]
        weekly_days[(row["sensor"], week)] += 1
    weekly = []
    for week in range(1, 53):
        for sensor in sorted(SENSORS):
            count = weekly_counts[(sensor, week)]
            weekly.append({"year": 2024, "week": week, "sensor": sensor,
                           "active_cell_days": count if count else None,
                           "days_with_retained_detections": weekly_days[(sensor, week)],
                           "coverage_status": "unknown"})
    return {"schema_version": "1.0", "mode": "sensor_comparison",
            "grid": {"resolution_degrees": 0.01, "origin_lon": -180, "origin_lat": -90},
            "daily": daily, "weekly": weekly,
            "quality": {"input_by_sensor": dict(input_counts),
                        "retained_by_sensor": dict(kept), "excluded": dict(excluded)},
            "limitations": ["Country membership inherited from archive requests; no boundary clipping.",
                            "Coverage unknown; absent detections are not confirmed zeros.",
                            "Grid cells have different physical areas across latitude.",
                            "Separate sensor series; no calibration or historical anomaly scoring."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = compare(load_detections(args.inputs))
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as file:
            json.dump(result, file, indent=2, allow_nan=False)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"Comparison failed: {error}\n")
    print(json.dumps(result["quality"], indent=2))
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
