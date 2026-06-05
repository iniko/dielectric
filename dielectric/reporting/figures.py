"""Captioned, provenance-stamped publication figures.

Uses matplotlib's object-oriented API (no global pyplot state, headless-safe) under an
``rc_context`` so the centralized publication style applies consistently. Every figure carries a
caption stating the model, N, and fit quality, plus a small data-hash stamp for reproducibility, so
a figure dropped into a paper is self-documenting. The conventional **positive** ε'' is plotted
(internal Im < 0 is negated for display).
"""

from __future__ import annotations

import matplotlib
import numpy as np
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure

from ..fitting.result import FitResult
from ..spectrum import Spectrum
from ..units import FloatArray
from .style import PUBLICATION_RCPARAMS, WONG_PALETTE


def _new_figure(figsize: tuple[float, float] = (6.0, 4.6)) -> Figure:
    fig = Figure(figsize=figsize)
    FigureCanvasAgg(fig)
    return fig


def _caption(fig: Figure, text: str, data_hash: str | None) -> None:
    stamp = f"   [data {data_hash}]" if data_hash else ""
    fig.text(0.5, 0.005, text + stamp, ha="center", va="bottom", fontsize=7.5, wrap=True)


def _dense_grid(spectrum: Spectrum, n: int = 400) -> FloatArray:
    lo, hi = spectrum.band_hz
    return np.geomspace(lo, hi, n, dtype=np.float64)


def bode_figure(
    spectrum: Spectrum,
    fit: FitResult | None = None,
    *,
    title: str = "Permittivity spectrum",
    caption: str | None = None,
) -> Figure:
    """ε'(f) and ε''(f) versus frequency (log-x), with the fitted model overlaid if given."""
    with matplotlib.rc_context(PUBLICATION_RCPARAMS):
        fig = _new_figure()
        ax1 = fig.add_subplot(2, 1, 1)
        ax2 = fig.add_subplot(2, 1, 2, sharex=ax1)
        f = spectrum.frequency_hz

        ax1.semilogx(f, spectrum.eps_real, "o", color=WONG_PALETTE[2], label="data", markersize=3)
        ax2.semilogx(f, spectrum.loss, "o", color=WONG_PALETTE[2], label="data", markersize=3)
        if fit is not None:
            fg = _dense_grid(spectrum)
            ax1.semilogx(fg, fit.model.epsilon_real(fg), "-", color=WONG_PALETTE[6], label="fit")
            ax2.semilogx(fg, fit.model.loss(fg), "-", color=WONG_PALETTE[6], label="fit")

        ax1.set_ylabel("ε′")
        ax2.set_ylabel("ε″ = −Im(ε*)")
        ax2.set_xlabel("frequency (Hz)")
        ax1.set_title(title)
        ax1.legend()

        if caption is None and fit is not None:
            caption = (
                f"{type(fit.model).__name__} fit, N = {fit.n_data // 2} points, "
                f"R² = {fit.r_squared:.4f}, reduced χ² = {fit.chi2_reduced:.2g}."
            )
        if caption:
            _caption(fig, caption, fit.data_hash if fit else None)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def cole_cole_figure(
    spectrum: Spectrum,
    fit: FitResult | None = None,
    *,
    title: str = "Cole-Cole plot",
    caption: str | None = None,
) -> Figure:
    """Cole-Cole (complex-plane) plot: ε'' = −Im(ε*) versus ε'."""
    with matplotlib.rc_context(PUBLICATION_RCPARAMS):
        fig = _new_figure(figsize=(5.2, 4.6))
        ax = fig.add_subplot(1, 1, 1)
        ax.plot(
            spectrum.eps_real, spectrum.loss, "o", color=WONG_PALETTE[2], label="data", markersize=3
        )
        if fit is not None:
            fg = _dense_grid(spectrum)
            ax.plot(
                fit.model.epsilon_real(fg), fit.model.loss(fg), "-",
                color=WONG_PALETTE[6], label="fit",
            )
        ax.set_xlabel("ε′")
        ax.set_ylabel("ε″ = −Im(ε*)")
        ax.set_title(title)
        ax.legend()
        if caption is None and fit is not None:
            caption = f"{type(fit.model).__name__} fit, R² = {fit.r_squared:.4f}."
        if caption:
            _caption(fig, caption, fit.data_hash if fit else None)
        fig.tight_layout(rect=(0, 0.04, 1, 1))
    return fig


def save_figure(fig: Figure, path: str) -> None:
    """Save a figure at publication DPI."""
    fig.savefig(path, dpi=300, bbox_inches="tight")
