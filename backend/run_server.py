"""Uvicorn launcher for the dielectric backend.

Used two ways:
  * dev   : python -m backend.run_server --port 8001
  * prod  : the PyInstaller binary ``dielectric-server --port <dynamic>``

Programmatic ``uvicorn.run()`` (no reload, no import-string magic) is what survives freezing.
Electron spawns this and polls ``GET /api/health`` until it answers, then shows the window.
"""

from __future__ import annotations

import argparse
import os

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Dielectric backend server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()

    # Import AFTER arg parsing so a frozen binary starts fast on --help.
    from backend.app.main import app

    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level=os.environ.get("DIELECTRIC_LOG_LEVEL", "info"),
        workers=1,  # single process; the numerics already thread internally
        access_log=False,
    )


if __name__ == "__main__":
    main()
