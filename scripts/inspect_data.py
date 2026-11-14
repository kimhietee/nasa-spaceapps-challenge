"""Print the structure and first record of a NASA JSON download."""
import json
import sys
from pathlib import Path


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: inspect_data.py PATH_TO_JSON")
    path = Path(sys.argv[1])
    try:
        with path.open(encoding="utf-8-sig") as file:
            data = json.load(file)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise SystemExit(f"Could not read JSON: {error}") from error

    print(f"File: {path.name}")
    print(f"Root type: {type(data).__name__}")
    records = None
    if isinstance(data, list):
        records = data
    elif isinstance(data, dict):
        print("Top-level keys:", ", ".join(data))
        for key in ("features", "data", "results"):
            if isinstance(data.get(key), list):
                print(f"Record container: {key}")
                records = data[key]
                break
    if records is None:
        raise SystemExit("No recognized record list. Inspect the structure before cleaning.")
    print(f"Record count: {len(records)}")
    if records:
        print("First record:")
        print(json.dumps(records[0], indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
