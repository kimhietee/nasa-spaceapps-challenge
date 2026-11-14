"""Validate MODIS JSON records and export standardized detections."""
import argparse
import hashlib
import json
import math
from datetime import datetime
from pathlib import Path


def number(value, name, minimum, maximum):
    if isinstance(value, bool):
        raise ValueError(f"{name}: boolean is not a number")

    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"{name}: outside allowed range")
    return result


def clean_record(record):
    if not isinstance(record, dict):
        raise ValueError("record must be an object")

    if str(record["instrument"]).strip().upper() != "MODIS":
        raise ValueError("instrument must be MODIS")

    satellite = str(record["satellite"]).strip().title()
    if satellite not in {"Terra", "Aqua"}:
        raise ValueError("unrecognized MODIS satellite")

    date = str(record["acq_date"]).strip()
    time = str(record["acq_time"]).strip()
    if not time.isascii() or not time.isdigit() or not 1 <= len(time) <= 4:
        raise ValueError("acq_time must contain 1–4 digits")

    timestamp = datetime.strptime(
        f"{date} {time.zfill(4)}", "%Y-%m-%d %H%M"
    )
    if timestamp.year != 2024:
        raise ValueError("acquisition date is outside 2024")

    daynight = str(record["daynight"]).strip().upper()
    if daynight not in {"D", "N"}:
        raise ValueError("daynight must be D or N")

    confidence = number(record["confidence"], "confidence", 0, 100)
    if not confidence.is_integer():
        raise ValueError("MODIS confidence must be an integer")

    version = str(record["version"]).strip()
    if not version.startswith("61"):
        raise ValueError("expected MODIS Collection 6.1")

    detection_type = record.get("type")
    if detection_type is not None:
        detection_type = str(detection_type).strip()
        if detection_type not in {"0", "1", "2", "3"}:
            raise ValueError("unrecognized detection type")
        detection_type = int(detection_type)

    return {
        "sensor": "MODIS",
        "satellite": satellite,
        "latitude": number(record["latitude"], "latitude", -90, 90),
        "longitude": number(record["longitude"], "longitude", -180, 180),
        "acquired_at_utc": timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "frp_mw": number(record["frp"], "frp", 0, float("inf")),
        "confidence_value": int(confidence),
        "confidence_scale": "MODIS_0_100",
        "daynight": daynight,
        "collection_version": version,
        "detection_type": detection_type,
    }


def process(records, source_file):
    clean = []
    rejected = []
    seen = set()
    duplicates = 0

    for row_number, record in enumerate(records, start=1):
        try:
            result = clean_record(record)
            # Compare the entire source record, including fields not exported.
            fingerprint = json.dumps(
                record, sort_keys=True, allow_nan=False
            )
        except (KeyError, TypeError, ValueError, OverflowError) as error:
            rejected.append({
                "source_row": row_number,
                "reason": str(error),
            })
            continue

        if fingerprint in seen:
            duplicates += 1
            continue

        seen.add(fingerprint)
        result["source_file"] = source_file
        result["source_row"] = row_number
        clean.append(result)

    clean.sort(key=lambda row: (
        row["acquired_at_utc"],
        row["satellite"],
        row["latitude"],
        row["longitude"],
    ))

    report = {
        "input_records": len(records),
        "accepted_records": len(clean),
        "exact_duplicates_removed": duplicates,
        "rejected_records": len(rejected),
        "rejections": rejected,
    }
    return clean, report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        source_bytes = args.input.read_bytes()
        records = json.loads(source_bytes.decode("utf-8-sig"))
        if not isinstance(records, list):
            raise ValueError("expected a JSON array of records")
        clean, report = process(records, args.input.name)
    except (OSError, UnicodeError, ValueError) as error:
        parser.exit(1, f"Cannot process input: {error}\n")

    report["source_file"] = args.input.name
    report["source_sha256"] = hashlib.sha256(source_bytes).hexdigest()

    # A new output directory prevents accidental replacement of earlier runs.
    args.output.mkdir(parents=True, exist_ok=False)
    for filename, contents in (
        ("modis_clean.json", {"schema_version": "1.0", "detections": clean}),
        ("quality_report.json", report),
    ):
        with (args.output / filename).open("w", encoding="utf-8") as file:
            json.dump(contents, file, indent=2, allow_nan=False)

    print(f"Accepted: {len(clean)}")
    print(f"Duplicates removed: {report['exact_duplicates_removed']}")
    print(f"Rejected: {report['rejected_records']}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()