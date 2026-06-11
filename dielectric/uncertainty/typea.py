"""Type A (repeated-measurement) statistics — combine repeats into a mean spectrum + SEM.

Given N repeat spectra of one sample on a shared frequency grid, compute the complex mean and the
per-frequency standard error of the mean (SEM) of ε' and ε'' separately. The SEM is what weights
the fit (``Spectrum.sem``), so reduced χ² is physically meaningful. An optional robust repeat-level
outlier screen (k·MAD, via scikit-learn's robust scaling) excludes a repeat with e.g. a bad probe
contact before averaging.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..constants import EPSILON_0
from ..spectrum import Spectrum, SpectrumMetadata
from ..units import ComplexArray, FloatArray, angular_frequency


@dataclass(frozen=True)
class TypeAResult:
    """Mean spectrum with per-point SEM, plus which repeats were excluded and why."""

    mean: Spectrum  # carries sem (real=SEM ε', imag=SEM ε'')
    n_repeats_used: int
    excluded_indices: tuple[int, ...]
    repeat_zscores: FloatArray  # robust z-score per repeat (consensus distance), original order
    outlier_k_used: float | None = None  # the screening threshold actually applied (None = off)
    manual_exclude: tuple[int, ...] = ()  # repeats the caller forced out
    manual_keep: tuple[int, ...] = ()  # repeats the caller forced in despite the rule

    @property
    def n_repeats_total(self) -> int:
        return self.n_repeats_used + len(self.excluded_indices)

    @property
    def combined_sem(self) -> ComplexArray:
        assert self.mean.sem is not None
        return self.mean.sem

    def reason(self, index: int) -> str:
        """Why repeat ``index`` was kept or excluded — for transparent display."""
        if index in self.manual_exclude:
            return "excluded (manual)"
        if index in self.excluded_indices:
            return "excluded (k·MAD rule)"
        if index in self.manual_keep:
            return "kept (manual override)"
        return "kept"


@dataclass(frozen=True)
class TypeABudgetScalars:
    """A Type A result reduced to one scalar budget term: the band **median** of ε' and its SEM.

    A GUM budget quotes one number per component while the SEM varies with frequency; the median
    over the band is the disclosed, robust choice (state it in the measurand definition).
    """

    eps_real_median: float
    eps_real_sem_median: float
    dof: float  # n_repeats_used - 1


def budget_scalars(result: TypeAResult) -> TypeABudgetScalars:
    """Reduce a :class:`TypeAResult` to a scalar Type A budget term (median over the band)."""
    if result.n_repeats_used < 2:
        raise ValueError(
            f"a Type A budget term needs >= 2 used repeats, got {result.n_repeats_used}"
        )
    assert result.mean.sem is not None
    return TypeABudgetScalars(
        eps_real_median=float(np.median(result.mean.eps_real)),
        eps_real_sem_median=float(np.median(result.mean.sem.real)),
        dof=float(result.n_repeats_used - 1),
    )


@dataclass(frozen=True)
class TypeABand:
    """Type A confidence band of a mean spectrum (mean ± k·SEM), in display quantities.

    ``sigma`` is the effective conductivity σ_eff = -ω·ε₀·Im(ε*); its band follows from the SEM of
    Im(ε*) by linear propagation. ``k`` is the coverage factor (1.96 ≈ 95% for many repeats).
    """

    frequency_hz: FloatArray
    eps_real: FloatArray
    eps_real_lo: FloatArray
    eps_real_hi: FloatArray
    sigma: FloatArray
    sigma_lo: FloatArray
    sigma_hi: FloatArray
    coverage_k: float


def confidence_band(result: TypeAResult, *, k: float = 1.96) -> TypeABand:
    """Mean ± ``k``·SEM band for ε' and σ_eff from a :class:`TypeAResult`."""
    mean = result.mean
    if mean.sem is None:  # pragma: no cover - combine_repeats always sets sem
        raise ValueError("the mean spectrum carries no SEM; cannot form a confidence band")
    f = mean.frequency_hz
    sem_re = np.real(mean.sem)
    sem_im = np.imag(mean.sem)
    eps_real = mean.eps_real
    sigma = mean.effective_conductivity
    d_sigma = k * angular_frequency(f) * EPSILON_0 * sem_im  # |∂σ/∂Im(ε)| · k·SEM
    return TypeABand(
        frequency_hz=f,
        eps_real=eps_real,
        eps_real_lo=eps_real - k * sem_re,
        eps_real_hi=eps_real + k * sem_re,
        sigma=sigma,
        sigma_lo=sigma - d_sigma,
        sigma_hi=sigma + d_sigma,
        coverage_k=k,
    )


@dataclass(frozen=True)
class RepeatDistribution:
    """Per-repeat ε' and ε'' samples at one frequency, with mean/std and a normality p-value."""

    frequency_hz: float
    eps_real_samples: FloatArray
    eps_imag_samples: FloatArray
    eps_real_mean: float
    eps_real_std: float
    eps_imag_mean: float
    eps_imag_std: float
    shapiro_p_real: float  # NaN when fewer than 3 repeats
    shapiro_p_imag: float


def _shapiro_p(x: FloatArray) -> float:
    if x.size < 3:
        return float("nan")
    from scipy.stats import shapiro

    try:
        return float(shapiro(x).pvalue)
    except ValueError:  # pragma: no cover - e.g. all-identical samples
        return float("nan")


def repeat_distribution(
    spectra: tuple[Spectrum, ...] | list[Spectrum],
    frequencies_hz: tuple[float, ...] | list[float],
) -> list[RepeatDistribution]:
    """Gather the per-repeat ε' / ε'' samples at each requested frequency (nearest grid point).

    For each frequency the closest measured grid point is used, and the across-repeat sample is
    summarised with mean, std (ddof=1), and a Shapiro-Wilk normality p-value — the inputs a student
    needs to judge whether the repeat scatter is Gaussian before quoting a Type A SEM.
    """
    spectra = tuple(spectra)
    if len(spectra) < 1:
        raise ValueError("need at least one repeat for a distribution")
    f = _assert_shared_grid(spectra)
    stack = np.array([s.epsilon for s in spectra])  # (n_repeats, n_freq)
    out: list[RepeatDistribution] = []
    for fq in frequencies_hz:
        idx = int(np.argmin(np.abs(f - fq)))
        re = np.real(stack[:, idx]).astype(np.float64)
        im = np.imag(stack[:, idx]).astype(np.float64)
        out.append(
            RepeatDistribution(
                frequency_hz=float(f[idx]),
                eps_real_samples=re,
                eps_imag_samples=im,
                eps_real_mean=float(np.mean(re)),
                eps_real_std=float(np.std(re, ddof=1)) if re.size > 1 else 0.0,
                eps_imag_mean=float(np.mean(im)),
                eps_imag_std=float(np.std(im, ddof=1)) if im.size > 1 else 0.0,
                shapiro_p_real=_shapiro_p(re),
                shapiro_p_imag=_shapiro_p(im),
            )
        )
    return out


def _assert_shared_grid(spectra: tuple[Spectrum, ...], *, rtol: float = 1e-6) -> FloatArray:
    f0 = spectra[0].frequency_hz
    for s in spectra[1:]:
        if s.frequency_hz.shape != f0.shape or not np.allclose(
            s.frequency_hz, f0, rtol=rtol
        ):
            raise ValueError(
                "repeats are not on a shared frequency grid; align or interpolate before combining "
                "(no silent resampling)."
            )
    return f0


def combine_repeats(
    spectra: tuple[Spectrum, ...] | list[Spectrum],
    *,
    outlier_k: float | None = 3.5,
    manual_exclude: tuple[int, ...] | list[int] = (),
    manual_keep: tuple[int, ...] | list[int] = (),
    sample_id: str | None = None,
    temperature_c: float | None = None,
) -> TypeAResult:
    """Combine repeat spectra into a Type A mean + SEM, optionally screening outlier repeats.

    Parameters
    ----------
    outlier_k:
        If not ``None``, a repeat whose robust z-score of consensus-distance exceeds ``outlier_k``
        is excluded from the mean/SEM (k·MAD rule, a Hampel identifier). ``None`` disables the
        screen and keeps every repeat.
    manual_exclude:
        Repeat indices (original order) the caller forces out regardless of the rule.
    manual_keep:
        Repeat indices the caller forces back in even if the rule flagged them. Takes precedence
        over the rule but not over ``manual_exclude``.

    ``repeat_zscores`` is always computed for **every** input repeat (in original order) so the
    decision is auditable even for screened or manually-overridden repeats.
    """
    spectra = tuple(spectra)
    if len(spectra) < 1:
        raise ValueError("need at least one repeat to combine")
    f = _assert_shared_grid(spectra)
    stack = np.array([s.epsilon for s in spectra])  # (n_repeats, n_freq)
    n = stack.shape[0]
    forced_out = {i for i in manual_exclude if 0 <= i < n}
    forced_in = {i for i in manual_keep if 0 <= i < n}

    # Robust per-repeat outlier screen: each repeat's median relative distance from the consensus
    # (median spectrum), turned into a robust z-score (median/MAD) — the same robust-scaling idea as
    # sklearn, applied to the consensus-distance summary (the meaningful per-repeat statistic).
    consensus = np.median(stack, axis=0)
    scale = np.abs(consensus) + 1e-30
    distance = np.median(np.abs(stack - consensus) / scale, axis=1)  # one value per repeat
    med = float(np.median(distance))
    mad = float(np.median(np.abs(distance - med)))
    zscores = (distance - med) / (1.4826 * mad) if mad > 0 else np.zeros(n)

    screen_on = outlier_k is not None and n >= 4
    # inline the None-check so mypy narrows `outlier_k` inside the comparison
    keep_mask = (
        zscores <= outlier_k if outlier_k is not None and n >= 4 else np.ones(n, dtype=bool)
    )
    # Apply manual overrides: forced-in repeats are kept, forced-out repeats are dropped.
    for i in forced_in:
        keep_mask[i] = True
    for i in forced_out:
        keep_mask[i] = False
    if not keep_mask.any():  # never drop everything
        keep_mask = np.ones(n, dtype=bool)
        forced_out = set()
    excluded = tuple(int(i) for i in np.flatnonzero(~keep_mask))
    used = stack[keep_mask]
    n_used = used.shape[0]

    mean_eps = used.mean(axis=0)
    if n_used > 1:
        sem_re = np.std(np.real(used), axis=0, ddof=1) / np.sqrt(n_used)
        sem_im = np.std(np.imag(used), axis=0, ddof=1) / np.sqrt(n_used)
    else:
        sem_re = np.zeros(f.size)
        sem_im = np.zeros(f.size)
    sem = sem_re + 1j * sem_im

    metadata = SpectrumMetadata(
        source=sample_id,
        temperature_c=temperature_c,
        extra={"n_repeats": str(n_used), "type": "type_a_mean"},
    )
    mean_spectrum = Spectrum(f, mean_eps, sem=sem, metadata=metadata)
    return TypeAResult(
        mean=mean_spectrum,
        n_repeats_used=n_used,
        excluded_indices=excluded,
        repeat_zscores=zscores,
        outlier_k_used=outlier_k if screen_on else None,
        manual_exclude=tuple(sorted(forced_out)),
        manual_keep=tuple(sorted(forced_in)),
    )
