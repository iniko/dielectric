"""Kramers-Kronig causality/consistency check.

A naive finite-band Hilbert transform is **biased** because the KK integral runs 0→∞. Instead we
use the **singly-subtractive** KK relation (which removes the integrand's singularity at Ω=ω) and a
fitted model to supply the **out-of-band tail**, so the check is not corrupted by truncation. We
also estimate the residual truncation error and warn that the tail is model-extrapolated beyond the
measured band.

KK relation (positive loss ε'' = -Im(ε*), engineering convention):

    ε'(ω) - ε∞ = (2/π) ∫₀^∞ [Ω ε''(Ω) - ω ε''(ω)] / (Ω² - ω²) dΩ
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..models.base import DielectricModel
from ..spectrum import Spectrum
from ..units import FloatArray


@dataclass(frozen=True)
class KKResult:
    """Outcome of a Kramers-Kronig consistency check."""

    predicted_eps_real: FloatArray  # KK-predicted ε' at the measured frequencies
    measured_eps_real: FloatArray
    residual_rms: float  # relative RMS difference (KK vs measured ε')
    eps_inf: float
    truncation_estimate: float  # rough relative size of the out-of-band tail contribution
    band_extrapolated: bool
    warnings: tuple[str, ...]

    @property
    def is_consistent(self) -> bool:
        return self.residual_rms < 0.05  # 5% default tolerance


def _kk_predict_eps_real(
    omega_eval: FloatArray,
    omega_grid: FloatArray,
    loss_grid: FloatArray,
    eps_inf: float,
) -> FloatArray:
    """Singly-subtractive KK integral of ``loss_grid`` (= ε'') evaluated at ``omega_eval``."""
    out = np.empty(omega_eval.size)
    for i, w in enumerate(omega_eval):
        num = omega_grid * loss_grid - w * np.interp(w, omega_grid, loss_grid)
        integrand = num / (omega_grid**2 - w**2)
        # The subtraction makes the integrand finite at Ω=ω; guard the exact grid coincidence.
        bad = ~np.isfinite(integrand)
        if bad.any():
            integrand[bad] = 0.0
        out[i] = eps_inf + (2.0 / np.pi) * np.trapezoid(integrand, omega_grid)
    return out


def kramers_kronig_check(
    spectrum: Spectrum,
    *,
    model: DielectricModel | None = None,
    eps_inf: float | None = None,
    decades_pad: float = 3.0,
    n_tail: int = 400,
) -> KKResult:
    """Check KK consistency of ``spectrum``; use ``model`` (if given) for the out-of-band tail.

    Without a model, the loss is taken as constant-extrapolated beyond the band, which is less
    accurate — a warning is issued. ``eps_inf`` defaults to the model's value or the
    highest-frequency measured ε'.
    """
    f = spectrum.frequency_hz
    omega = 2.0 * np.pi * f
    warnings: list[str] = []

    # Wide angular-frequency grid: measured band padded by ``decades_pad`` decades each side.
    lo = np.log10(f[0]) - decades_pad
    hi = np.log10(f[-1]) + decades_pad
    f_grid = np.geomspace(10.0**lo, 10.0**hi, n_tail)
    omega_grid = 2.0 * np.pi * f_grid

    if model is not None:
        loss_grid = model.loss(f_grid)
        tail_eps = float(np.real(model.epsilon(f_grid[-1:]))[0])
        eps_inf_val = eps_inf if eps_inf is not None else tail_eps
    else:
        # Constant-extrapolate measured loss outside the band (cruder; warn).
        lm = spectrum.loss
        loss_grid = np.interp(f_grid, f, lm, left=lm[0], right=lm[-1])
        eps_inf_val = eps_inf if eps_inf is not None else float(spectrum.eps_real[-1])
        warnings.append(
            "no model supplied: the out-of-band loss is constant-extrapolated, so the KK tail is "
            "approximate. Provide a fitted model for a trustworthy check."
        )
        warnings.append(
            "KK is evaluated using data extrapolated beyond the measured band "
            f"({f[0]:.3g}–{f[-1]:.3g} Hz)."
        )

    predicted = _kk_predict_eps_real(omega, omega_grid, loss_grid, eps_inf_val)
    measured = spectrum.eps_real
    scale = np.abs(measured) + 1e-9
    residual_rms = float(np.sqrt(np.mean(((predicted - measured) / scale) ** 2)))

    # Truncation estimate: contribution of the padded tail relative to the in-band integral.
    in_band = (f_grid >= f[0]) & (f_grid <= f[-1])
    tail_weight = float(np.sum(np.abs(loss_grid[~in_band]))) / (
        float(np.sum(np.abs(loss_grid))) + 1e-30
    )

    return KKResult(
        predicted_eps_real=predicted,
        measured_eps_real=measured,
        residual_rms=residual_rms,
        eps_inf=eps_inf_val,
        truncation_estimate=tail_weight,
        band_extrapolated=model is not None,
        warnings=tuple(warnings),
    )
