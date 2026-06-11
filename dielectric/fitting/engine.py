"""Generic non-linear least-squares engine for any ``DielectricModel``.

Minimises the stacked real/imaginary residual ``[Re(ε_model−ε_data), Im(ε_model−ε_data)]``. Key
choices (see memory ``fitting-log-scale-tau``):

* multi-decade parameters (τ) are optimised in **log10 space**, or scipy's finite-difference
  Jacobian floor destroys the τ column and the fit silently diverges; the covariance is mapped back
  to natural units with the delta method (``dx/dz = ln(10)·x``);
* fits are weighted by the Type A per-point SEM (``sigma``) so reduced χ² is physically meaningful;
* a small **multistart** guards against local minima.
"""

from __future__ import annotations

import hashlib
import re

import numpy as np
from scipy.optimize import least_squares

from ..models.base import DielectricModel
from ..spectrum import Spectrum
from ..units import FloatArray
from .result import FitResult

# Default parameter bounds by name (or name prefix for multipole terms like ``tau_2``).
_DEFAULT_BOUNDS: dict[str, tuple[float, float]] = {
    "eps_inf": (1.0, 1.0e3),
    "delta_eps": (0.0, 1.0e7),
    "tau": (1.0e-14, 1.0e-6),
    "alpha": (0.0, 0.99),
    "beta": (1.0e-3, 1.0),
    "sigma": (0.0, 1.0e3),
    "sigma_dc": (0.0, 1.0e3),
    "A": (0.0, 1.0e7),
    "n": (1.0e-3, 0.999),
}


def _bound_for(name: str) -> tuple[float, float]:
    base = re.sub(r"_\d+$", "", name)  # tau_2 -> tau, delta_eps_1 -> delta_eps
    return _DEFAULT_BOUNDS.get(base, (-np.inf, np.inf))


def _is_log_scaled(name: str, log_scale: tuple[str, ...]) -> bool:
    base = re.sub(r"_\d+$", "", name)
    return any(name == s or base == s for s in log_scale)


def _data_hash(spectrum: Spectrum) -> str:
    h = hashlib.sha256()
    h.update(np.ascontiguousarray(spectrum.frequency_hz).tobytes())
    h.update(np.ascontiguousarray(spectrum.epsilon).tobytes())
    return h.hexdigest()[:16]


def fit(
    spectrum: Spectrum,
    template: DielectricModel,
    *,
    p0: dict[str, float] | None = None,
    bounds: dict[str, tuple[float, float]] | None = None,
    log_scale: tuple[str, ...] = ("tau",),
    weighted: bool = True,
    multistart: int = 4,
    seed: int = 0,
    max_nfev: int = 10000,
) -> FitResult:
    """Fit ``template``'s parameters to ``spectrum`` and return a :class:`FitResult`.

    ``template`` supplies the model class, the parameter ordering, and (unless ``p0`` is given) the
    starting values. ``log_scale`` names parameters optimised in log10 space.
    """
    names = template.param_names
    start = dict(template.params)
    if p0:
        start.update(p0)
    user_bounds = bounds or {}

    f = spectrum.frequency_hz
    eps_data = spectrum.epsilon

    # Per-point weights from Type A SEM (real → ε', imag → ε''); fall back to unweighted.
    use_weights = weighted and spectrum.sem is not None
    if use_weights:
        assert spectrum.sem is not None
        sigma_re = np.real(spectrum.sem).astype(np.float64)
        sigma_im = np.imag(spectrum.sem).astype(np.float64)
        floor_re = np.median(sigma_re[sigma_re > 0]) if np.any(sigma_re > 0) else 1.0
        floor_im = np.median(sigma_im[sigma_im > 0]) if np.any(sigma_im > 0) else 1.0
        sigma_re = np.where(sigma_re > 0, sigma_re, floor_re)
        sigma_im = np.where(sigma_im > 0, sigma_im, floor_im)
        # Cap the weight dynamic range: with few repeats the SEM is itself noisy and a couple of
        # coincidentally-tight points get a near-zero σ that would dominate weighted χ² and
        # destabilise model selection. Floor each σ at 10% of its component median (≤10× weighting).
        sigma_re = np.maximum(sigma_re, 0.1 * float(np.median(sigma_re)))
        sigma_im = np.maximum(sigma_im, 0.1 * float(np.median(sigma_im)))
    else:
        sigma_re = np.ones_like(f)
        sigma_im = np.ones_like(f)

    log_flags = [_is_log_scaled(n, log_scale) for n in names]

    def to_z(values: dict[str, float]) -> FloatArray:
        pairs = zip(names, log_flags, strict=True)
        return np.array(
            [np.log10(values[n]) if lf else values[n] for n, lf in pairs],
            dtype=np.float64,
        )

    def from_z(z: FloatArray) -> dict[str, float]:
        return {
            n: float(10.0**zi if lf else zi)
            for n, zi, lf in zip(names, z, log_flags, strict=True)
        }

    lo: list[float] = []
    hi: list[float] = []
    for n, lf in zip(names, log_flags, strict=True):
        b_lo, b_hi = user_bounds.get(n, _bound_for(n))
        if lf:
            b_lo = np.log10(max(b_lo, 1e-300))
            b_hi = np.log10(b_hi)
        lo.append(b_lo)
        hi.append(b_hi)
    bounds_z = (np.array(lo), np.array(hi))

    def residual(z: FloatArray) -> FloatArray:
        model = template.with_params(from_z(z))
        r = model.epsilon(f) - eps_data
        return np.concatenate([np.real(r) / sigma_re, np.imag(r) / sigma_im])

    z0 = np.clip(to_z(start), bounds_z[0], bounds_z[1])
    best = least_squares(residual, z0, bounds=bounds_z, max_nfev=max_nfev)

    # Multistart: perturb the start in z-space and keep the lowest cost.
    if multistart > 0:
        rng = np.random.default_rng(seed)
        span = bounds_z[1] - bounds_z[0]
        span = np.where(np.isfinite(span), span, 1.0)
        for _ in range(multistart):
            jitter = rng.normal(0.0, 0.15, size=z0.size) * np.where(span > 0, span, 1.0)
            zc = np.clip(z0 + jitter, bounds_z[0], bounds_z[1])
            cand = least_squares(residual, zc, bounds=bounds_z, max_nfev=max_nfev)
            if cand.cost < best.cost:
                best = cand

    z_hat = best.x
    fitted = template.with_params(from_z(z_hat))
    resid_complex = fitted.epsilon(f) - eps_data
    chi2 = float(2.0 * best.cost)  # least_squares cost = 0.5 Σ resid²
    n_data = 2 * f.size
    k = len(names)
    dof = max(n_data - k, 1)

    # Covariance from the Jacobian in z-space, then delta-method to natural units.
    jac = np.asarray(best.jac, dtype=np.float64)
    jtj = jac.T @ jac
    try:
        cov_z = np.linalg.inv(jtj)
    except np.linalg.LinAlgError:
        cov_z = np.linalg.pinv(jtj)
    if not use_weights:
        cov_z = cov_z * (chi2 / dof)  # estimate noise from the residual when σ unknown

    x_hat = np.array([from_z(z_hat)[n] for n in names])
    scale = np.array(
        [np.log(10.0) * x if lf else 1.0 for x, lf in zip(x_hat, log_flags, strict=True)],
        dtype=np.float64,
    )
    cov = (scale[:, None] * cov_z) * scale[None, :]
    variances = np.clip(np.diag(cov), 0.0, np.inf)
    std = np.sqrt(variances)
    uncertainties = {n: float(s) for n, s in zip(names, std, strict=True)}

    denom = np.outer(std, std)
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = np.where(denom > 0, cov / denom, 0.0)
    np.fill_diagonal(corr, 1.0)

    # R² on the stacked real/imag data.
    stacked_data = np.concatenate([np.real(eps_data), np.imag(eps_data)])
    stacked_resid = np.concatenate([np.real(resid_complex), np.imag(resid_complex)])
    ss_tot = float(np.sum((stacked_data - np.mean(stacked_data)) ** 2))
    ss_res = float(np.sum(stacked_resid**2))
    r_squared = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")

    # Per-component diagnostics. The honest split is the mean squared pull per component (residual
    # weighted by the per-point σ; equals mean squared raw residual when unweighted) — it says, per
    # component, whether the fit lands within the Type A uncertainty. The per-component R² (variance
    # explained against each component's own mean) is a secondary view and may be negative.
    re_resid, im_resid = np.real(resid_complex), np.imag(resid_complex)
    re_data, im_data = np.real(eps_data), np.imag(eps_data)
    msp_real = (float(np.mean((re_resid / sigma_re) ** 2)) if use_weights
                else float(np.mean(re_resid**2)))
    msp_imag = (float(np.mean((im_resid / sigma_im) ** 2)) if use_weights
                else float(np.mean(im_resid**2)))

    def _r2(resid: FloatArray, data: FloatArray) -> float:
        sst = float(np.sum((data - np.mean(data)) ** 2))
        return 1.0 - float(np.sum(resid**2)) / sst if sst > 0 else float("nan")

    r_squared_real = _r2(re_resid, re_data)
    r_squared_imag = _r2(im_resid, im_data)

    log_params = tuple(n for n, lf in zip(names, log_flags, strict=True) if lf)
    # The per-point σ the fit weighted by (floored Type A SEM), packed as σ_re + jσ_im; None when
    # unweighted. Σ|resid/σ|² over the stacked real/imag residuals equals the reported χ².
    sigma_used = (sigma_re + 1j * sigma_im).astype(np.complex128) if use_weights else None

    return FitResult(
        model=fitted,
        param_uncertainties=uncertainties,
        covariance=cov,
        correlation=corr,
        frequency_hz=f,
        residuals=resid_complex,
        chi2=chi2,
        dof=dof,
        n_data=n_data,
        weighted=use_weights,
        sigma_used=sigma_used,
        r_squared=r_squared,
        msp_real=msp_real,
        msp_imag=msp_imag,
        r_squared_real=r_squared_real,
        r_squared_imag=r_squared_imag,
        success=bool(best.success),
        message=str(best.message),
        log_scaled_params=log_params,
        fit_settings={
            "log_scale": list(log_scale),
            "weighted": use_weights,
            "multistart": multistart,
            "seed": seed,
            "model": type(template).__name__,
        },
        data_hash=_data_hash(spectrum),
    )
