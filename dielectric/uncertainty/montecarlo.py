"""Monte-Carlo uncertainty propagation through an arbitrary user callable.

Reproducible by construction: every run takes a recorded ``seed`` (stored so a figure regenerates
bit-for-bit) and reports a convergence check (does the spread stabilise as the sample count grows?).
Supports correlated inputs (full covariance, e.g. from a :class:`FitResult`) or independent inputs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from ..units import FloatArray


@dataclass(frozen=True)
class MonteCarloResult:
    """Distribution summary of a propagated quantity."""

    mean: FloatArray
    std: FloatArray
    percentiles: dict[int, FloatArray]  # 2.5 / 50 / 97.5 by default
    samples: FloatArray  # (n_samples, output_dim)
    seed: int
    n_samples: int
    converged: bool
    convergence_change: float  # relative change in std between half and full sample

    @property
    def scalar(self) -> tuple[float, float]:
        """``(mean, std)`` for a scalar output."""
        return float(np.ravel(self.mean)[0]), float(np.ravel(self.std)[0])


def monte_carlo(
    func: Callable[[FloatArray], FloatArray | float],
    mean: FloatArray,
    uncertainty: FloatArray,
    *,
    n_samples: int = 2000,
    seed: int = 0,
    convergence_tol: float = 0.05,
) -> MonteCarloResult:
    """Propagate input uncertainty through ``func`` by Monte-Carlo sampling.

    Parameters
    ----------
    mean:
        Nominal input vector.
    uncertainty:
        Either a 1-D vector of independent standard uncertainties, or a 2-D covariance matrix
        (correlated inputs, e.g. a fit covariance).
    """
    rng = np.random.default_rng(seed)
    mean = np.atleast_1d(np.asarray(mean, dtype=np.float64))
    unc = np.asarray(uncertainty, dtype=np.float64)

    if unc.ndim == 2:
        draws = rng.multivariate_normal(mean, unc, size=n_samples)
    else:
        draws = rng.normal(mean, unc, size=(n_samples, mean.size))

    outputs = np.array([np.atleast_1d(func(x)) for x in draws], dtype=np.float64)

    mean_out = outputs.mean(axis=0)
    std_out = outputs.std(axis=0, ddof=1)
    pcts = {
        p: np.percentile(outputs, p, axis=0) for p in (2, 50, 98)
    }

    half = max(n_samples // 2, 1)
    std_half = outputs[:half].std(axis=0, ddof=1)
    change = float(np.max(np.abs(std_half - std_out) / (np.abs(std_out) + 1e-30)))
    converged = change < convergence_tol

    return MonteCarloResult(
        mean=mean_out,
        std=std_out,
        percentiles=pcts,
        samples=outputs,
        seed=seed,
        n_samples=n_samples,
        converged=converged,
        convergence_change=change,
    )
