"""``FitResult`` — the structured outcome of fitting a model to a spectrum.

Carries fitted parameters with uncertainties, per-point residuals, goodness-of-fit, information
criteria for model selection (AIC/AICc/BIC), and the reproducibility fields (data hash + fit
settings) that the reporting layer stamps into a manifest.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..models.base import DielectricModel
from ..units import ComplexArray, FloatArray


@dataclass(frozen=True)
class FitResult:
    """Result of fitting one :class:`DielectricModel` to one spectrum."""

    model: DielectricModel  # fitted model (best parameters)
    param_uncertainties: dict[str, float]  # 1σ standard uncertainties
    covariance: FloatArray  # parameter covariance matrix (natural units, log params mapped back)
    correlation: FloatArray  # parameter correlation matrix
    frequency_hz: FloatArray
    residuals: ComplexArray  # ε_model - ε_data (internal convention)
    chi2: float  # weighted χ² (Σ |resid/σ|²); == Σ|resid|² when σ=1
    dof: int  # degrees of freedom = N - k
    n_data: int  # N = 2 · n_freq (stacked real/imag residuals)
    weighted: bool  # whether real measurement σ (Type A SEM) was used
    r_squared: float
    success: bool
    message: str
    log_scaled_params: tuple[str, ...] = ()
    fit_settings: dict[str, object] = field(default_factory=dict)
    data_hash: str | None = None
    # Per-point σ the fit actually weighted by (real part = σ for ε', imag = σ for ε''); None when
    # the fit was unweighted. Lets callers form standardized residuals whose Σ(·²) == χ².
    sigma_used: ComplexArray | None = None
    # Per-component goodness of fit. msp = mean squared pull (residual/σ, or raw residual when
    # unweighted) for ε' and ε'' separately — the honest "does it fit within Type A uncertainty"
    # split. r_squared_real/imag are variance-explained per component (secondary; may be negative).
    msp_real: float = float("nan")
    msp_imag: float = float("nan")
    r_squared_real: float = float("nan")
    r_squared_imag: float = float("nan")

    # -- goodness of fit ------------------------------------------------------------------------

    @property
    def n_params(self) -> int:
        return self.model.n_params

    @property
    def standardized_residuals(self) -> ComplexArray:
        """Residuals divided by the per-point σ used in the fit (dimensionless 'pulls').

        Re/Im parts are each scaled by their own σ; Σ|standardized|² equals the weighted χ². When
        the fit was unweighted (no measurement σ), the raw residuals are returned unchanged.
        """
        if self.sigma_used is None:
            return self.residuals
        out: ComplexArray = (
            np.real(self.residuals) / np.real(self.sigma_used)
            + 1j * np.imag(self.residuals) / np.imag(self.sigma_used)
        )
        return out

    @property
    def chi2_reduced(self) -> float:
        return self.chi2 / self.dof if self.dof > 0 else float("nan")

    @property
    def rmse(self) -> float:
        """Root-mean-square of the complex residual magnitude."""
        return float(np.sqrt(np.mean(np.abs(self.residuals) ** 2)))

    # -- information criteria (weighted-χ² basis; N = 2·n_freq) ----------------------------------

    @property
    def aic(self) -> float:
        k = self.n_params
        return self.chi2 + 2 * k

    @property
    def aicc(self) -> float:
        """Small-sample corrected AIC. Falls back to +inf when N ≤ k+1 (over-parameterized)."""
        k = self.n_params
        n = self.n_data
        if n - k - 1 <= 0:
            return float("inf")
        return self.aic + 2 * k * (k + 1) / (n - k - 1)

    @property
    def bic(self) -> float:
        k = self.n_params
        return self.chi2 + k * float(np.log(self.n_data))

    @property
    def params(self) -> dict[str, float]:
        return self.model.params

    def summary(self) -> str:
        lines = [
            f"{type(self.model).__name__}  (k={self.n_params}, N={self.n_data})",
            f"  χ²_red = {self.chi2_reduced:.4g}   R² = {self.r_squared:.6f}"
            f"   AICc = {self.aicc:.4g}   BIC = {self.bic:.4g}",
        ]
        for name in self.model.param_names:
            val = self.params[name]
            unc = self.param_uncertainties.get(name, float("nan"))
            lines.append(f"  {name} = {val:.6g} ± {unc:.3g}")
        return "\n".join(lines)
