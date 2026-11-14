# Firewatch Command Center frontend

This is the frontend previously served from the sibling `firewatch-command-center-preview` project. Its source is now inside this repository.

## Run from this repository root

```powershell
cd frontend\command-center
npm.cmd ci
npm.cmd run dev -- --host 127.0.0.1 --port 8080 --strictPort
```

Open http://127.0.0.1:8080/#map . If port 8080 is occupied by the original preview, stop that preview with Ctrl+C in its terminal first, or use port 8081.

The real-data dashboard still requires the existing archive API at http://127.0.0.1:8020. Vite forwards `/api/archive` to that service. Copying this UI does not connect it to this repository's separate `api.main` service.

The original archive backend and its local database remain in the sibling `firewatch-command-center-preview` folder. To start that service from that folder:

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.api:app --host 127.0.0.1 --port 8020
```

## Validate

```powershell
npm.cmd test
npm.cmd run build
```

Commit the source, configuration, and lockfiles. Dependencies, generated output, databases, and original downloads are excluded. Existing sample-data modules are reference/mock data; the real dashboard does not fall back to them.
