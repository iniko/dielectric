# Dielectric Desktop (Electron shell)

Wraps the existing React frontend + FastAPI backend into an offline Windows/macOS app.
The library (`dielectric/`), backend (`backend/`), and frontend (`frontend/`) are unchanged
except for a thin transport layer (`frontend/src/runtime.ts`, env-driven CORS/token in
`backend/app/main.py`). All numerics stay in the Python process — the renderer never computes.

## How it fits together

```
Electron main ──spawn──▶ FastAPI (dev: .venv │ prod: PyInstaller binary) on 127.0.0.1:<dynamic>
      │ preload(contextBridge)                         ▲
      ▼                                                │ fetch + x-dielectric-token
  Renderer (your React app) ──────────────────────────┘
```

Main picks a free port, generates a per-launch token, starts the backend, polls
`/api/health`, then shows the window. On quit it kills the backend process tree.

## Setup

```bash
# from project root
pip install -e ".[dev,report,hdf5,web]"
cd frontend && npm install && cd ..
cd desktop  && npm install
```

## Develop (Vite 5173 + FastAPI 8001 + Electron, together)

```bash
cd desktop && npm run dev:all
```

Editing `electron/*.ts` (main/preload/backend) requires a re-run; React hot-reloads via Vite.

## Build installers

```bash
cd desktop
npm run dist:mac    # → desktop/release/*.dmg   (run on macOS)
npm run dist:win    # → desktop/release/*.exe   (run on Windows)
```

PyInstaller and electron-builder do not cross-compile — build each OS on that OS (or CI).

## Before first build: add icons

Drop real icons next to the entitlements file:

- `desktop/build/icon.icns` (macOS, 512px+)
- `desktop/build/icon.ico`  (Windows, 256px)

## Signing (before distributing)

- macOS: set `CSC_LINK` / `CSC_KEY_PASSWORD`, then notarize (electron-builder `afterSign`).
- Windows: sign with an OV/EV cert to avoid SmartScreen warnings.
