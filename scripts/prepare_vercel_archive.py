"""Download and validate the read-only archive during a Vercel build."""

from contextlib import closing
import os
from pathlib import Path
import shutil
import sqlite3
from tempfile import NamedTemporaryFile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def validate_archive(path: Path) -> None:
    with closing(sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)) as connection:
        if connection.execute("PRAGMA quick_check").fetchone() != ("ok",):
            raise ValueError("SQLite integrity check failed")
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        required = {"observations", "source_files", "rejected", "candidate_pairs", "groups", "metadata"}
        if missing := required - tables:
            raise ValueError("Wrong archive schema; missing tables: " + ", ".join(sorted(missing)))
        connection.execute(
            "SELECT id, lat, lon, year, month, sensor, status, group_id FROM observations LIMIT 1"
        ).fetchone()
        if not connection.execute(
            "SELECT value FROM metadata WHERE key='processed_at'"
        ).fetchone():
            raise ValueError("Archive is missing its processed_at metadata")


def download_archive(url: str, target: Path) -> None:
    if urlsplit(url).scheme != "https":
        raise ValueError("DB_DOWNLOAD_URL must be a direct HTTPS download URL")
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with NamedTemporaryFile(dir=target.parent, suffix=".download", delete=False) as destination:
            temporary_path = Path(destination.name)
            request = Request(url, headers={"User-Agent": "FIREWATCH-archive-build"})
            with urlopen(request, timeout=120) as response:
                shutil.copyfileobj(response, destination)
        validate_archive(temporary_path)
        temporary_path.replace(target)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main() -> None:
    url = os.environ.get("DB_DOWNLOAD_URL", "").strip()
    if not url:
        raise SystemExit("Set DB_DOWNLOAD_URL to the direct HTTPS download URL of firewatch.sqlite.")
    target = Path(__file__).resolve().parents[1] / "backend" / "data" / "firewatch.sqlite"
    try:
        download_archive(url, target)
    except (OSError, sqlite3.DatabaseError, ValueError) as error:
        raise SystemExit(f"Archive preparation failed: {error}") from error
    print(f"Validated archive: {target.stat().st_size / 1024**2:.1f} MiB")


if __name__ == "__main__":
    main()
