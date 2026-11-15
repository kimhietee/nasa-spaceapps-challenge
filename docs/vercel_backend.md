# Deploy the archive backend to Vercel

Use the complete repository for a separate backend project. The frontend project
uses `frontend/command-center` as its root; this backend project uses the repository root.

## Prepare the archive

The API needs the processed `firewatch.sqlite` archive, not `data/indonesia.db`.
The local launcher currently falls back to
`../firewatch-command-center-preview/backend/data/firewatch.sqlite`.
Keep the original downloads and existing database intact.

Stop any importer, then make a standalone SQLite backup. For example, from the repository root:

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; from pathlib import Path; from contextlib import closing; p=Path('../firewatch-command-center-preview/backend/data/firewatch.sqlite').resolve(); out=Path('archive-deployment.sqlite'); assert p.is_file(), 'Archive not found'; assert not out.exists(), 'Backup already exists'; src=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True); dst=sqlite3.connect(out); src.backup(dst); dst.close(); src.close()"
```

Upload that backup to a GitHub Release as `firewatch.sqlite` only if its contents
are intended to be public. Copy the direct HTTPS asset download URL, not the release
page URL. Private assets need authenticated downloading, which this build script
does not configure. Never place the database in frontend public assets.

The archive is downloaded at build time, validated for integrity and schema, and
included in the Python function bundle. A failed download does not replace an
existing database. No ingest, matching, or remote download runs on API startup.

## Create the Vercel project

1. Commit and push the deployment files yourself.
2. Import the complete repository at https://vercel.com/new as a separate project.
3. Set Root Directory to `./` and Framework Preset to FastAPI.
4. Leave Install Command and Output Directory at their defaults. The root
   `requirements.txt` includes `backend/requirements.txt`.
5. Use the Build Command from `vercel.json`: `python scripts/prepare_vercel_archive.py`.
   There is no Uvicorn start command on Vercel.
6. Set the following environment variables for Production and Preview, then deploy.

| Variable | Value |
| --- | --- |
| `DB_DOWNLOAD_URL` | Direct HTTPS download URL for the prepared archive |
| `FIREWATCH_ARCHIVE_DB` | `backend/data/firewatch.sqlite` |
| `FIREWATCH_ALLOWED_ORIGINS` | Exact frontend origins, comma-separated, e.g. `https://your-web.vercel.app,https://yourdomain.com` |
| `VERCEL_SUPPORT_LARGE_FUNCTIONS` | `1` |

The inspected local archive is 526,573,568 bytes (about 502 MiB) before dependencies,
so it exceeds the standard Python function bundle limit. This deployment requires
an eligible project with Large Functions support (up to 5 GB, currently beta),
Fluid Compute and Active CPU enabled. Check the actual bundled size in the build.
If needed, set `VERCEL_ANALYZE_BUILD_OUTPUT=1` to report large files.

Local CORS origins remain allowed. Add preview frontend origins explicitly if
needed; no wildcard for all `vercel.app` projects is enabled.

## Verify and connect

Open the assigned backend origin at these paths:

- `/docs` should return the API documentation.
- `/api/archive/meta` should return real archive metadata.
- `/api/archive/map?year=2022&month=1&zoom=5` should return clusters and counts.
- `/api/archive/boundaries` should return the boundary GeoJSON.

Test the production API while signed out. A public frontend must be able to call
it without a Vercel login wall. Opening `/docs` alone does not validate the database.

In the frontend Vercel project, set `VITE_ARCHIVE_API` to the backend's HTTPS
origin with no trailing slash or `/api/archive`, then redeploy the frontend.
Add the frontend's stable production origin to `FIREWATCH_ALLOWED_ORIGINS` on the
backend and redeploy after changing it. The frontend's Nitro preset must target
Vercel for its separate deployment.

## Limits and updates

The bundled archive is read-only. Prepare new snapshots locally, publish a new
asset URL and redeploy to update it. Runtime writes and cached responses are not
persistent storage.

Hobby functions have a maximum duration of 300 seconds. Normal buffered responses
are limited to 4.5 MB; test broad map selections as well as January 2022. A successful
deploy does not prove that every archive query meets these limits.

References:
- https://vercel.com/docs/frameworks/backend/fastapi
- https://vercel.com/docs/functions/limitations

## Local checks

```powershell
.\.venv\Scripts\python.exe -B -m pytest -p no:cacheprovider tests/test_vercel_deployment.py backend/test_archive.py tests/test_archive_views.py -q
```
