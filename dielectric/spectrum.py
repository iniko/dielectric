"""The ``Spectrum`` value object — the single thing every layer consumes.

Fitting, verification, uncertainty, and reporting all operate on a :class:`Spectrum`. By the time a
``Spectrum`` exists it is guaranteed to be in the internal ``e^{jωt}`` convention (Im(ε*) < 0 for
loss): sign detection happens *only* at the I/O boundary (:mod:`dielectric.convention`), so nothing
downstream re-checks the sign.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .constants import EPSILON_0
from .units import BoolArray, ComplexArray, FloatArray, angular_frequency


@dataclass(frozen=True)
class SpectrumMetadata:
    """Provenance/context for a spectrum that downstream layers may need."""

    source: str | None = None  # e.g. originating file name
    temperature_c: float | None = None  # measurement temperature [°C], if known
    content_hash: str | None = None  # hash of the raw input, for the reproducibility manifest
    extra: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class QualityReport:
    """Pre-fit data-quality assessment — run *before* fitting so a confident fit on bad data is
    caught early."""

    n_points: int
    frequency_span_decades: float
    median_relative_noise: float  # rough fractional noise from local smoothness
    n_outliers: int
    outlier_indices: tuple[int, ...]
    sampling_is_log_uniform: bool
    warnings: tuple[str, ...]

    @property
    def ok(self) -> bool:
        return not self.warnings


@dataclass(frozen=True)
class Spectrum:
    """Complex relative permittivity ε*(f) on a frequency grid (internal convention).

    Parameters
    ----------
    frequency_hz:
        Strictly increasing frequency grid [Hz].
    epsilon:
        Complex relative permittivity, Im(ε*) ≤ 0 for a lossy medium.
    sem:
        Optional per-point standard error of the mean (complex: real part is SEM of ε', imaginary
        part is SEM of ε''), produced by Type A averaging of repeats. Used as fit weights.
    metadata:
        :class:`SpectrumMetadata`.
    """

    frequency_hz: FloatArray
    epsilon: ComplexArray
    sem: ComplexArray | None = None
    metadata: SpectrumMetadata = field(default_factory=SpectrumMetadata)

    def __post_init__(self) -> None:
        f = np.asarray(self.frequency_hz, dtype=np.float64)
        eps = np.asarray(self.epsilon, dtype=np.complex128)
        if f.ndim != 1 or eps.ndim != 1:
            raise ValueError("frequency_hz and epsilon must be 1-D")
        if f.shape != eps.shape:
            raise ValueError(f"length mismatch: {f.shape} frequencies vs {eps.shape} epsilon")
        if f.size < 2:
            raise ValueError("a spectrum needs at least 2 points")
        if np.any(np.diff(f) <= 0):
            raise ValueError("frequency_hz must be strictly increasing")
        object.__setattr__(self, "frequency_hz", f)
        object.__setattr__(self, "epsilon", eps)
        if self.sem is not None:
            sem = np.asarray(self.sem, dtype=np.complex128)
            if sem.shape != f.shape:
                raise ValueError("sem must match the frequency grid")
            object.__setattr__(self, "sem", sem)

    # -- convenient views -----------------------------------------------------------------------

    @property
    def eps_real(self) -> FloatArray:
        return np.real(self.epsilon)

    @property
    def eps_imag(self) -> FloatArray:
        """Im(ε*), internal convention (≤ 0 for loss)."""
        return np.imag(self.epsilon)

    @property
    def loss(self) -> FloatArray:
        """ε'' = -Im(ε*), the conventional positive loss for display."""
        return -np.imag(self.epsilon)

    @property
    def band_hz(self) -> tuple[float, float]:
        return float(self.frequency_hz[0]), float(self.frequency_hz[-1])

    @property
    def effective_conductivity(self) -> FloatArray:
        """σ_eff(f) = -ω·ε₀·Im(ε*) [S/m]."""
        return -angular_frequency(self.frequency_hz) * EPSILON_0 * np.imag(self.epsilon)

    def in_band(self, frequency_hz: FloatArray) -> BoolArray:
        lo, hi = self.band_hz
        f = np.asarray(frequency_hz, dtype=np.float64)
        return (f >= lo) & (f <= hi)

    def with_metadata(self, **changes: object) -> Spectrum:
        return replace(self, metadata=replace(self.metadata, **changes))  # type: ignore[arg-type]

    # -- pre-fit quality pass -------------------------------------------------------------------

    def quality_report(
        self,
        *,
        outlier_sigma: float = 5.0,
        min_decades: float = 1.0,
    ) -> QualityReport:
        """Assess noise, outliers, and sampling adequacy before fitting."""
        f = self.frequency_hz
        eps = self.epsilon
        n = f.size
        decades = float(np.log10(f[-1] / f[0]))

        # Noise/outlier proxy: each interior point's deviation from the midpoint of its two
        # neighbours, |ε_i - ½(ε_{i-1}+ε_{i+1})| (half the discrete second difference). This is
        # exactly zero for a linear trend and small for smooth curvature, so it isolates noise and
        # genuine spikes without mistaking the relaxation's shape for either. Endpoints have no
        # midpoint and are excluded from outlier flagging.
        scale = np.abs(eps) + 1e-30
        rel_resid = np.zeros(n)
        if n >= 3:
            midpoint = 0.5 * (eps[:-2] + eps[2:])
            rel_resid[1:-1] = np.abs(eps[1:-1] - midpoint) / scale[1:-1]
        interior = rel_resid[1:-1] if n >= 3 else rel_resid
        median_noise = float(np.median(interior)) if interior.size else 0.0

        # A point is an outlier only if it is large on ALL three gates: robust z-score (MAD),
        # several times the typical noise, and above an absolute relative floor. The triple gate
        # stops machine-precision curvature wiggles on clean data from being flagged.
        mad = float(np.median(np.abs(rel_resid - np.median(rel_resid))))
        noise_scale = max(1.4826 * mad, 1e-12)
        robust_z = np.abs(rel_resid - np.median(rel_resid)) / noise_scale
        is_outlier = np.zeros(n, dtype=bool)
        is_outlier[1:-1] = (
            (robust_z[1:-1] > outlier_sigma)
            & (rel_resid[1:-1] > 5.0 * median_noise)
            & (rel_resid[1:-1] > 1e-3)
        )
        outlier_idx = tuple(int(i) for i in np.flatnonzero(is_outlier))

        # Sampling: are the points log-uniform (typical of VNA sweeps)?
        log_f = np.log10(f)
        steps = np.diff(log_f)
        log_uniform = bool(np.std(steps) / (np.mean(steps) + 1e-30) < 0.05)

        warns: list[str] = []
        if decades < min_decades:
            warns.append(
                f"frequency span is only {decades:.2f} decades (< {min_decades}); multi-decade "
                "relaxation parameters may be poorly constrained."
            )
        if median_noise > 0.02:
            warns.append(
                f"median relative point-to-point noise ≈ {median_noise:.1%}; consider averaging "
                "more repeats before trusting a fit."
            )
        if outlier_idx:
            warns.append(
                f"{len(outlier_idx)} outlier point(s) at indices {outlier_idx} "
                f"(> {outlier_sigma}σ robust); inspect before fitting."
            )
        if not log_uniform:
            warns.append(
                "frequency sampling is not log-uniform; AICc point counts and visual fit weighting "
                "assume reasonably uniform log-spacing."
            )

        return QualityReport(
            n_points=n,
            frequency_span_decades=decades,
            median_relative_noise=median_noise,
            n_outliers=len(outlier_idx),
            outlier_indices=outlier_idx,
            sampling_is_log_uniform=log_uniform,
            warnings=tuple(warns),
        )
