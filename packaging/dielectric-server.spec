# PyInstaller spec for the dielectric FastAPI backend.
#
# Build (from the project root):
#   .venv/bin/pyinstaller packaging/dielectric-server.spec --noconfirm --distpath resources
# Produces resources/dielectric-server/  (onedir — faster cold start than onefile, which
# matters because Electron blocks on the /api/health probe before showing the window).
#
# uvicorn/fastapi import a lot dynamically; collect_submodules is what makes the frozen
# server actually boot. Add fpdf/docx/h5py here if you ship those extras at runtime.
import os

from PyInstaller.utils.hooks import collect_submodules, collect_data_files

# SPECPATH is injected by PyInstaller = the directory holding this spec (packaging/).
# Resolve everything from the project root so the build works from any cwd.
ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

hidden = (
    collect_submodules("uvicorn")
    + collect_submodules("dielectric")
    + [
        "backend.app.main",
        "backend.run_server",
        "fastapi",
        "anyio",
        "h11",
        "click",
        "multipart",  # python-multipart, for file uploads
    ]
)

# Bundle the library's reference data (tissue params, etc.) so it works fully offline.
datas = collect_data_files("dielectric")

a = Analysis(
    [os.path.join(ROOT, "backend", "run_server.py")],
    pathex=[ROOT],
    hiddenimports=hidden,
    datas=datas,
    excludes=["tkinter", "matplotlib.tests", "pytest"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="dielectric-server",
    console=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="dielectric-server")
