"""Use synthetic SQLite archives; never modify original downloads."""
from contextlib import closing
from io import BytesIO
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from backend.ingest import SCHEMA
from scripts import prepare_vercel_archive as build


@pytest.fixture
def archive_bytes(tmp_path):
    path = tmp_path / "synthetic.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript(SCHEMA)
        connection.execute("INSERT INTO metadata VALUES (?, ?)",
                           ("processed_at", "synthetic-test-fixture"))
        connection.commit()
    return path.read_bytes()


def test_valid_download_replaces_archive(tmp_path, monkeypatch, archive_bytes):
    target = tmp_path / "output" / "firewatch.sqlite"
    target.parent.mkdir()
    target.write_bytes(b"previous archive")
    monkeypatch.setattr(build, "urlopen", lambda request, timeout: BytesIO(archive_bytes))
    build.download_archive("https://example.com/firewatch.sqlite", target)
    assert target.read_bytes() == archive_bytes
    assert list(target.parent.iterdir()) == [target]


@pytest.mark.parametrize("payload", [b"<html>Sign in</html>", None])
def test_bad_download_preserves_archive(tmp_path, monkeypatch, payload):
    if payload is None:
        wrong = tmp_path / "wrong.sqlite"
        with closing(sqlite3.connect(wrong)) as connection:
            connection.execute("CREATE TABLE unrelated (id INTEGER)")
        payload = wrong.read_bytes()
    target = tmp_path / "output" / "firewatch.sqlite"
    target.parent.mkdir()
    target.write_bytes(b"previous archive")
    monkeypatch.setattr(build, "urlopen", lambda request, timeout: BytesIO(payload))
    with pytest.raises((sqlite3.DatabaseError, ValueError)):
        build.download_archive("https://example.com/firewatch.sqlite", target)
    assert target.read_bytes() == b"previous archive"
    assert list(target.parent.iterdir()) == [target]


def test_interrupted_download_leaves_no_partial_file(tmp_path, monkeypatch):
    def fail(request, timeout):
        raise OSError("download interrupted")
    monkeypatch.setattr(build, "urlopen", fail)
    target = tmp_path / "output" / "firewatch.sqlite"
    with pytest.raises(OSError, match="interrupted"):
        build.download_archive("https://example.com/firewatch.sqlite", target)
    assert list(target.parent.iterdir()) == []


def test_missing_url_explains_setup(monkeypatch):
    monkeypatch.delenv("DB_DOWNLOAD_URL", raising=False)
    with pytest.raises(SystemExit, match="Set DB_DOWNLOAD_URL"):
        build.main()


def test_configured_cors_allows_frontend_and_local_origins_only():
    environment = {**os.environ, "FIREWATCH_ALLOWED_ORIGINS":
                   " https://frontend.example/ , https://custom.example ",
                   "PYTHONDONTWRITEBYTECODE": "1"}
    code = """
from fastapi.testclient import TestClient
from app import app
with TestClient(app) as client:
    for origin in ['https://frontend.example', 'https://custom.example', 'http://localhost:8080']:
        response = client.options('/docs', headers={
            'Origin': origin, 'Access-Control-Request-Method': 'GET',
        })
        assert response.status_code == 200, response.text
        assert response.headers['access-control-allow-origin'] == origin
    response = client.options('/docs', headers={
        'Origin': 'https://untrusted.example', 'Access-Control-Request-Method': 'GET',
    })
    assert response.status_code == 400
    assert 'access-control-allow-origin' not in response.headers
"""
    result = subprocess.run([sys.executable, "-B", "-c", code],
                            cwd=Path(__file__).resolve().parents[1], env=environment,
                            capture_output=True, text=True, timeout=60)
    assert result.returncode == 0, result.stdout + result.stderr
