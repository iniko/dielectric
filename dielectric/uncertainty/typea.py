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

from ..spectrum import Spectrum, SpectrumMetadata
from ..units import ComplexArray, FloatArray


@dataclass(frozen=True)
class TypeAResult:
    """Mean spectrum with per-point SEM, plus which repeats were excluded and why."""

    mean: Spectrum  # carries sem (real=SEM ε', imag=SEM ε'')
    n_repeats_used: int
    excluded_indices: tuple[int, ...]
    repeat_zscores: FloatArray  # robust z-score per repeat (consensus distance)

    @property
    def combined_sem(self) -> ComplexArray:
        assert self.mean.sem is not None
        return self.mean.sem


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
    sample_id: str | None = None,
    temperature_c: float | None = None,
) -> TypeAResult:
    """Combine repeat spectra into a Type A mean + SEM, optionally screening outlier repeats.

    Parameters
    ----------
    outlier_k:
        If not ``None``, a repeat whose robust z-score of consensus-distance exceeds ``outlier_k``
        is excluded from the mean/SEM (k·MAD rule). ``None`` disables the screen.
    """
    spectra = tuple(spectra)
    if len(spectra) < 1:
        raise ValueError("need at least one repeat to combine")
    f = _assert_shared_grid(spectra)
    stack = np.array([s.epsilon for s in spectra])  # (n_repeats, n_freq)
    n = stack.shape[0]

    # Robust per-repeat outlier screen: each repeat's median relative distance from the consensus
    # (median spectrum), turned into a robust z-score (median/MAD) — the same robust-scaling idea as
    # sklearn, applied to the consensus-distance summary (the meaningful per-repeat statistic).
    consensus = np.median(stack, axis=0)
    scale = np.abs(consensus) + 1e-30
    distance = np.median(np.abs(stack - consensus) / scale, axis=1)  # one value per repeat
    med = float(np.median(distance))
    mad = float(np.median(np.abs(distance - med)))
    zscores = (distance - med) / (1.4826 * mad) if mad > 0 else np.zeros(n)

    if outlier_k is not None and n >= 4:
        keep_mask = zscores <= outlier_k
        if not keep_mask.any():  # never drop everything
            keep_mask = np.ones(n, dtype=bool)
    else:
        keep_mask = np.ones(n, dtype=bool)
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
    )
