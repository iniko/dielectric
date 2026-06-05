"""One centralized, publication-quality plotting style applied consistently everywhere.

Colorblind-safe palette (Wong 2011) and journal-friendly typography/rcParams.
"""

from __future__ import annotations

#: Colorblind-safe qualitative palette (Wong, Nature Methods 2011).
WONG_PALETTE: tuple[str, ...] = (
    "#000000",  # black
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
    "#009E73",  # bluish green
    "#F0E442",  # yellow
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#CC79A7",  # reddish purple
)

#: rcParams for a clean, publication-ready look.
PUBLICATION_RCPARAMS: dict[str, object] = {
    "figure.dpi": 120,
    "savefig.dpi": 300,
    "figure.figsize": (6.0, 4.2),
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.labelsize": 10,
    "axes.linewidth": 0.8,
    "axes.grid": True,
    "grid.alpha": 0.3,
    "grid.linewidth": 0.5,
    "legend.frameon": False,
    "legend.fontsize": 9,
    "lines.linewidth": 1.6,
    "lines.markersize": 4,
    "xtick.direction": "in",
    "ytick.direction": "in",
    "axes.prop_cycle": __import__("cycler").cycler(color=list(WONG_PALETTE)),
    "savefig.bbox": "tight",
}
