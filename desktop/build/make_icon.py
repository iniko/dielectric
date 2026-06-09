"""Generate the app icons (icon.icns + icon.ico) from a single rendered master.

Motif: a Cole-Cole (Argand) semicircle — the visual signature of dielectric relaxation —
over a dark panel, with an epsilon glyph. Reproducible: re-run to regenerate.

    .venv/bin/python desktop/build/make_icon.py

Needs Pillow (bundled via matplotlib) and, for .icns, macOS `iconutil` (no-op elsewhere).
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402
from PIL import Image  # noqa: E402

HERE = Path(__file__).resolve().parent
NAVY = "#0a1626"
PANEL = "#102a44"
CYAN = "#22d3ee"
CYAN_SOFT = "#38e1c6"


def render_master(px: int = 1024) -> Image.Image:
    fig = plt.figure(figsize=(px / 100, px / 100), dpi=100)
    fig.patch.set_facecolor(NAVY)
    ax = fig.add_axes((0, 0, 1, 1))
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    # Inset rounded panel for depth.
    ax.add_patch(
        FancyBboxPatch(
            (0.08, 0.08), 0.84, 0.84,
            boxstyle="round,pad=0,rounding_size=0.14",
            linewidth=0, facecolor=PANEL, mutation_aspect=1,
        )
    )

    # Cole-Cole semicircle: ε'' vs ε' arc.
    cx, cy, r = 0.5, 0.36, 0.30
    th = np.linspace(0, np.pi, 200)
    x, y = cx + r * np.cos(th), cy + r * np.sin(th)
    ax.fill_between(x, cy, y, color=CYAN, alpha=0.12, zorder=1)
    ax.plot(x, y, color=CYAN, lw=10, solid_capstyle="round", zorder=3)
    ax.plot([cx - r - 0.04, cx + r + 0.04], [cy, cy], color="#2f5878", lw=4, zorder=2)

    # A few "data" dots along the arc.
    for t in np.linspace(0.12, 0.88, 6) * np.pi:
        ax.plot(cx + r * np.cos(t), cy + r * np.sin(t), "o", ms=15,
                color=CYAN_SOFT, markeredgecolor=NAVY, markeredgewidth=2, zorder=4)

    # Epsilon glyph, top-left — mathtext for the clean curvy ε (not the angular Ɛ).
    ax.text(0.225, 0.74, r"$\mathbf{\varepsilon}$", color=CYAN_SOFT, fontsize=165,
            ha="center", va="center", zorder=5)

    tmp = Path(tempfile.mkdtemp()) / "master.png"
    fig.savefig(tmp, facecolor=NAVY)
    plt.close(fig)
    return Image.open(tmp).convert("RGBA").resize((px, px), Image.LANCZOS)


def write_icns(master: Image.Image) -> None:
    if not shutil.which("iconutil"):
        print("iconutil not found (non-macOS) — skipping .icns")
        return
    iconset = Path(tempfile.mkdtemp()) / "icon.iconset"
    iconset.mkdir()
    specs = [(16, 1), (16, 2), (32, 1), (32, 2), (128, 1), (128, 2),
             (256, 1), (256, 2), (512, 1), (512, 2)]
    for size, scale in specs:
        px = size * scale
        name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
        master.resize((px, px), Image.LANCZOS).save(iconset / name)
    subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(HERE / "icon.icns")], check=True)
    print("wrote", HERE / "icon.icns")


def write_ico(master: Image.Image) -> None:
    sizes = [(s, s) for s in (16, 24, 32, 48, 64, 128, 256)]
    master.save(HERE / "icon.ico", sizes=sizes)
    print("wrote", HERE / "icon.ico")


if __name__ == "__main__":
    master = render_master()
    master.save(HERE / "icon.png")
    write_icns(master)
    write_ico(master)
