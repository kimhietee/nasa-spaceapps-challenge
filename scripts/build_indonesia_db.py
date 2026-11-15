"""Build an Indonesia FIRMS SQLite database using only Python's standard library."""
import argparse
from datetime import date, datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3


SCHEMA = """
PRAGMA foreign_keys = ON;
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE source_file (
    source_id INTEGER PRIMARY KEY,
    relative_path TEXT NOT NULL UNIQUE,
    sha256 TEXT NOT NULL UNIQUE,
    size_bytes INTEGER NOT NULL,
    geographic_scope TEXT NOT NULL,
    imported_at_utc TEXT NOT NULL,
    record_count INTEGER NOT NULL DEFAULT 0,
    first_acquired_at_utc TEXT,
    last_acquired_at_utc TEXT
);
CREATE TABLE detection (
    detection_id INTEGER PRIMARY KEY,
    source_id INTEGER NOT NULL REFERENCES source_file(source_id),
    source_row INTEGER NOT NULL CHECK (source_row > 0),
    sensor TEXT NOT NULL CHECK (sensor IN ('MODIS', 'VIIRS_SNPP')),
    instrument TEXT NOT NULL,
    satellite TEXT NOT NULL,
    acquired_at_utc TEXT NOT NULL,
    latitude REAL NOT NULL CHECK (latitude BETWEEN -90 AND 90),
    longitude REAL NOT NULL CHECK (longitude BETWEEN -180 AND 180),
    frp_mw REAL NOT NULL CHECK (frp_mw >= 0),
    confidence_value TEXT NOT NULL,
    confidence_numeric INTEGER,
    confidence_category TEXT,
    detection_type INTEGER CHECK (detection_type IN (0, 1, 2, 3)),
    daynight TEXT NOT NULL CHECK (daynight IN ('D', 'N')),
    collection_version TEXT NOT NULL,
    scan_km REAL,
    track_km REAL,
    brightness_k REAL,
    bright_t31_k REAL,
    UNIQUE (source_id, source_row),
    CHECK ((sensor = 'MODIS' AND confidence_numeric BETWEEN 0 AND 100
            AND confidence_numeric IS NOT NULL AND confidence_category IS NULL)
        OR (sensor = 'VIIRS_SNPP' AND confidence_category IN ('l', 'n', 'h')
            AND confidence_category IS NOT NULL AND confidence_numeric IS NULL))
);
"""
INDEXES = """
CREATE INDEX idx_detection_time ON detection(acquired_at_utc);
CREATE INDEX idx_detection_sensor_time ON detection(sensor, acquired_at_utc);
CREATE INDEX idx_detection_location ON detection(longitude, latitude);
"""
INSERT = "INSERT INTO detection VALUES (NULL," + ",".join("?" for _ in range(19)) + ")"


def iter_records(path):
    """Read a JSON array a chunk at a time, including delimiter validation."""
    decoder = json.JSONDecoder()
    with Path(path).open(encoding="utf-8-sig") as stream:
        buffer, position, eof = "", 0, False

        def refill():
            nonlocal buffer, position, eof
            chunk = stream.read(65536)
            buffer = buffer[position:] + chunk
            position = 0
            eof = not chunk
            if len(buffer) > 1048576:
                raise ValueError("A single record exceeds 1 MiB")

        def peek():
            nonlocal position
            while True:
                while position < len(buffer) and buffer[position].isspace():
                    position += 1
                if position < len(buffer):
                    return buffer[position]
                if eof:
                    return ""
                refill()

        if peek() != "[":
            raise ValueError("Expected a JSON array")
        position += 1
        if peek() != "]":
            while True:
                peek()
                while True:
                    try:
                        record, end = decoder.raw_decode(buffer, position)
                        position = end
                        break
                    except json.JSONDecodeError:
                        if eof:
                            raise ValueError("Incomplete or invalid JSON record") from None
                        refill()
                if not isinstance(record, dict):
                    raise ValueError("Each record must be an object")
                yield record
                delimiter = peek()
                if delimiter == "]":
                    break
                if delimiter != ",":
                    raise ValueError("Expected a comma between records")
                position += 1
                if peek() == "]":
                    raise ValueError("Trailing commas are not valid JSON")
        position += 1
        if peek():
            raise ValueError("Unexpected content after JSON array")


def numeric(value, minimum=-math.inf, maximum=math.inf):
    if isinstance(value, bool):
        raise ValueError("Boolean supplied for a numeric field")
    result = float(value)
    if not math.isfinite(result) or not minimum <= result <= maximum:
        raise ValueError(f"Invalid numeric value: {value!r}")
    return result


def detection_values(row, source_id, row_number):
    instrument = str(row["instrument"]).strip().upper()
    satellite = str(row["satellite"]).strip().upper()
    confidence = str(row["confidence"]).strip()
    if instrument == "MODIS" and satellite in {"TERRA", "AQUA"}:
        sensor = "MODIS"
        confidence_numeric = numeric(row["confidence"], 0, 100)
        if not confidence_numeric.is_integer():
            raise ValueError("MODIS confidence must be an integer")
        confidence_numeric = int(confidence_numeric)
        confidence_category = None
    elif instrument in {"SNPP", "VIIRS"} and satellite in {"SNPP", "S-NPP", "SUOMI-NPP", "NPP", "N"}:
        sensor = "VIIRS_SNPP"
        confidence_numeric = None
        confidence_category = {"low": "l", "nominal": "n", "high": "h"}.get(confidence.lower(), confidence.lower())
        if confidence_category not in {"l", "n", "h"}:
            raise ValueError("Invalid VIIRS confidence")
    else:
        raise ValueError("Unsupported instrument/satellite")
    day = date.fromisoformat(str(row["acq_date"]))
    if day.year not in range(2022, 2026):
        raise ValueError("Acquisition date outside 2022-2025")
    time = str(row["acq_time"]).strip()
    if not time.isascii() or not time.isdigit() or not 1 <= len(time) <= 4:
        raise ValueError("Invalid acquisition time")
    time = time.zfill(4)
    timestamp = datetime(day.year, day.month, day.day, int(time[:2]), int(time[2:]))
    daynight = str(row["daynight"]).strip().upper()
    if daynight not in {"D", "N"}:
        raise ValueError("Invalid daynight")
    kind = row.get("type")
    if kind is not None:
        if str(kind).strip() not in {"0", "1", "2", "3"}:
            raise ValueError("Invalid detection type")
        kind = int(kind)
    version = str(row["version"]).strip()
    if not version:
        raise ValueError("Missing collection version")
    optional = [None if row.get(key) is None else numeric(row[key], 0)
                for key in ("scan", "track", "brightness", "bright_t31")]
    return (source_id, row_number, sensor, str(row["instrument"]), str(row["satellite"]),
            timestamp.strftime("%Y-%m-%dT%H:%M:%SZ"),
            numeric(row["latitude"], -90, 90), numeric(row["longitude"], -180, 180),
            numeric(row["frp"], 0), confidence, confidence_numeric, confidence_category,
            kind, daynight, version, *optional)


def file_hash(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1048576), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_database(inputs, output):
    inputs, output = Path(inputs), Path(output)
    files = sorted(inputs.rglob("fire_archive_*.json"))
    if not files:
        raise ValueError(f"No fire_archive_*.json files in {inputs}")
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidental replacement of an existing database.
    output.touch(exist_ok=False)
    conn = None
    try:
        conn = sqlite3.connect(output)
        conn.executescript(SCHEMA)
        now = datetime.now(timezone.utc).isoformat()
        metadata = {
            "schema_version": "indonesia-detections-1.0", "country_code": "IDN",
            "data_status": "NASA FIRMS", "built_at_utc": now,
            "geographic_scope": "Indonesia archive requests; boundary membership unverified",
            "quality_policy": "All validated source rows retained, including low confidence and nonvegetation types",
            "version_policy": "Original version strings preserved without reinterpretation",
            "coverage_status": "unknown",
        }
        conn.executemany("INSERT INTO meta VALUES (?,?)", metadata.items())
        for path in files:
            digest = file_hash(path)
            cursor = conn.execute(
                "INSERT INTO source_file(relative_path,sha256,size_bytes,geographic_scope,imported_at_utc) VALUES (?,?,?,?,?)",
                (path.relative_to(inputs).as_posix(), digest, path.stat().st_size, metadata["geographic_scope"], now))
            source_id = cursor.lastrowid
            batch, count, first, last = [], 0, None, None
            for count, row in enumerate(iter_records(path), 1):
                try:
                    values = detection_values(row, source_id, count)
                except (KeyError, TypeError, ValueError, OverflowError) as error:
                    raise ValueError(f"{path.name}, row {count}: {error}") from error
                timestamp = values[5]
                first = timestamp if first is None else min(first, timestamp)
                last = timestamp if last is None else max(last, timestamp)
                batch.append(values)
                if len(batch) == 5000:
                    conn.executemany(INSERT, batch)
                    batch.clear()
            conn.executemany(INSERT, batch)
            if not count:
                raise ValueError(f"Empty archive: {path}")
            if file_hash(path) != digest:
                raise ValueError(f"Source changed during import: {path}")
            conn.execute("UPDATE source_file SET record_count=?,first_acquired_at_utc=?,last_acquired_at_utc=? WHERE source_id=?",
                         (count, first, last, source_id))
            print(f"Imported {path.name}: {count:,} records", flush=True)
        conn.commit()
        conn.executescript(INDEXES)
        conn.execute("ANALYZE")
        conn.commit()
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok" or conn.execute("PRAGMA foreign_key_check").fetchone():
            raise ValueError(f"Database integrity check failed: {integrity}")
        counts = dict(conn.execute("SELECT sensor, COUNT(*) FROM detection GROUP BY sensor"))
        if sum(counts.values()) != conn.execute("SELECT SUM(record_count) FROM source_file").fetchone()[0]:
            raise ValueError("Imported counts do not match source counts")
        conn.close()
        return counts
    except BaseException:
        if conn is not None:
            conn.close()
        output.unlink(missing_ok=True)
        raise


def main():
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=root / "data/processed")
    parser.add_argument("--db-path", type=Path, default=root / "data/indonesia.db")
    args = parser.parse_args()
    try:
        counts = build_database(args.input_dir, args.db_path)
    except (OSError, ValueError, sqlite3.Error) as error:
        parser.exit(1, f"Database build failed: {error}\n")
    print(json.dumps({"database": str(args.db_path), "records_by_sensor": counts, "integrity": "ok"}, indent=2))


if __name__ == "__main__":
    main()
