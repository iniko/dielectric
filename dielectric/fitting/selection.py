"""Automatic model selection with parsimony guardrails and a user override.

Fits a panel of candidate models, ranks them by small-sample-corrected AIC (AICc) and BIC, and
recommends one — but never just "lowest residual": it prefers the simpler nested model unless a
richer one improves AICc by a meaningful margin, and it flags over-parameterized fits. The user can
override the recommendation by model label and/or number of poles while still seeing where their
choice ranks.
"""

from __future__ import annotations

import math
import re
import warnings
from dataclasses import dataclass, replace

from ..spectrum import Spectrum
from .fitters import (
    FAMILIES,
    LADDER_FAMILIES,
    FitFn,
    compose_fitter,
    parse_model_label,
)
from .result import FitResult

#: ΔAICc below which two models are "indistinguishable", so the simpler one wins (Burnham-Anderson).
PARSIMONY_DELTA_AICC = 2.0

#: A fit is "degenerate" (parameters unidentifiable) if its largest regularized relative parameter
#: uncertainty exceeds this. Such a fit may have a low AICc yet be physically meaningless (e.g. a
#: slow relaxation pole absorbing the DC-conduction tail, collapsing σ to ~0 with a huge error bar).
DEGENERACY_THRESHOLD = 1.0

#: A degenerate model is only rejected for a non-degenerate one if the latter fits *comparably well*
#: (R² within this tolerance of the best fit). Otherwise we never trade a good-but-underdetermined
#: fit for a qualitatively worse one (e.g. a poor Jonscher fit when few repeats are averaged).
R2_RECOMMEND_TOL = 0.01

#: A weighted fit with reduced χ² above this is flagged: the model misfit exceeds the Type A
#: uncertainty, so the unscaled parameter covariance is optimistic by roughly √χ²ᵣ.
CHI2_MISFIT_WARN = 5.0

#: Per-parameter scale used to regularize relative uncertainty so a legitimately-near-zero parameter
#: (e.g. α→0 in the Debye limit) is not falsely flagged.
_PARAM_SCALE: dict[str, float] = {
    "eps_inf": 1.0,
    "delta_eps": 1.0,
    "tau": 0.0,  # τ > 0 always; use plain relative uncertainty
    "alpha": 0.1,
    "beta": 0.1,
    "sigma": 0.1,
    "sigma_dc": 0.1,
    "A": 1.0,
    "n": 0.1,
}

def max_relative_uncertainty(result: FitResult) -> float:
    """Largest regularized relative parameter uncertainty ``u / (|value| + scale)`` over the fit.

    The per-parameter ``scale`` floor prevents a near-zero-but-well-determined parameter from being
    flagged while still catching a genuinely unconstrained one (large ``u`` with tiny ``|value|``).
    """
    worst = 0.0
    for name in result.model.param_names:
        value = abs(result.params[name])
        unc = result.param_uncertainties.get(name, float("inf"))
        base = re.sub(r"_\d+$", "", name)
        scale = _PARAM_SCALE.get(base, 0.0)
        rel = unc / (value + scale) if (value + scale) > 0 else float("inf")
        worst = max(worst, rel)
    return worst


class ModelSelectionWarning(UserWarning):
    """Raised when a candidate is over-parameterized or a forced model is sub-optimal."""


def default_candidates(max_poles: int = 3) -> dict[str, FitFn]:
    """The default panel: the 5 classics + the Debye/Cole-Cole ladders (1..max_poles) with DC σ."""
    candidates: dict[str, FitFn] = {}
    for family in FAMILIES:  # the 5 single-pole classics, no DC term
        label, fn = compose_fitter(family, 1, dc_sigma=False)
        candidates[label] = fn
    for family in LADDER_FAMILIES:  # Debye/Cole-Cole × {1..max_poles} poles + DC σ
        for n in range(1, max_poles + 1):
            label, fn = compose_fitter(family, n, dc_sigma=True)
            candidates[label] = fn
    return candidates


@dataclass(frozen=True)
class RankedFit:
    """One candidate's fit plus its place in the ranking."""

    label: str
    result: FitResult
    delta_aicc: float
    overparameterized: bool
    degenerate: bool  # parameters unidentifiable (see DEGENERACY_THRESHOLD)
    max_rel_uncertainty: float
    excluded_reason: str = ""  # why it was kept out of the recommendation pool ("" = eligible)


@dataclass(frozen=True)
class ModelSelectionResult:
    """Outcome of :func:`select_model`."""

    ranking: tuple[RankedFit, ...]  # sorted best → worst by AICc
    recommended: RankedFit  # parsimony-aware automatic pick
    chosen: RankedFit  # what to use downstream (== recommended unless overridden)
    overridden: bool
    warnings: tuple[str, ...]
    rationale: str = ""  # plain-language "why this model" for the recommendation

    def table(self) -> str:
        head = f"{'model':<30}{'k':>3}{'χ²_red':>12}{'AICc':>12}{'ΔAICc':>10}{'BIC':>12}{'R²':>10}"
        rows = [head, "-" * len(head)]
        for rf in self.ranking:
            r = rf.result
            mark = " *" if rf.label == self.chosen.label else ""
            flag = (
                " (overparam)"
                if rf.overparameterized
                else " (degenerate)"
                if rf.degenerate
                else ""
            )
            rows.append(
                f"{rf.label:<30}{r.n_params:>3}{r.chi2_reduced:>12.4g}{r.aicc:>12.4g}"
                f"{rf.delta_aicc:>10.2f}{r.bic:>12.4g}{r.r_squared:>10.6f}{mark}{flag}"
            )
        return "\n".join(rows)


def select_model(
    spectrum: Spectrum,
    *,
    candidates: dict[str, FitFn] | None = None,
    force_model: str | None = None,
    n_poles: int | None = None,
    dc_sigma: bool | None = None,
    max_poles: int = 3,
) -> ModelSelectionResult:
    """Fit and rank candidate models; recommend one; honor an optional override.

    The customization controls **compose**: ``force_model`` (a family name or a full grammar label),
    ``n_poles``, and ``dc_sigma`` combine into one model rather than overriding each other.

    Parameters
    ----------
    force_model:
        A family (``"Debye"``) or full label (``"Cole-Cole (2 poles) + DC σ"``) to use instead of
        the automatic pick. Merges with ``n_poles``/``dc_sigma`` (a conflict raises ``ValueError``).
    n_poles:
        Pole count. With ``force_model`` it sets that family's pole count; alone it constrains the
        panel to the Debye/Cole-Cole ladders at this count, auto-selecting within (not an override).
    dc_sigma:
        With ``force_model`` it adds/removes the family's DC-conductivity term; alone it constrains
        the panel to models with (True) or without (False) a DC-σ term, then auto-selects.
    """
    if n_poles is not None and not 1 <= n_poles <= max_poles:
        raise ValueError(
            f"n_poles must be between 1 and {max_poles} (got {n_poles}); "
            "leave it unset for automatic selection"
        )

    panel = dict(candidates or default_candidates(max_poles))
    warns: list[str] = []
    forced_label: str | None = None

    if force_model is not None:
        fam, label_n, label_dc = parse_model_label(force_model)
        if n_poles is not None and label_n != 1 and n_poles != label_n:
            raise ValueError(
                f"conflicting pole counts: label '{force_model}' says {label_n}, n_poles={n_poles}"
            )
        if dc_sigma is False and label_dc:
            raise ValueError(
                f"conflicting DC-σ: label '{force_model}' includes a DC-σ term but dc_sigma=False"
            )
        eff_n = n_poles if n_poles is not None else label_n
        eff_dc = dc_sigma if dc_sigma is not None else label_dc
        forced_label, forced_fn = compose_fitter(fam, eff_n, eff_dc)
        panel[forced_label] = forced_fn
    elif n_poles is not None:
        dcs: tuple[bool, ...] = (dc_sigma,) if dc_sigma is not None else (False, True)
        panel = {}
        for fam in LADDER_FAMILIES:
            for dc in dcs:
                label, fn = compose_fitter(fam, n_poles, dc)
                panel[label] = fn
        warns.append(
            f"candidate panel constrained to {n_poles}-pole "
            f"{' / '.join(LADDER_FAMILIES)} models (user setting)."
        )
    elif dc_sigma is not None:
        panel = {k: v for k, v in panel.items() if k.endswith(" + DC σ") == dc_sigma}
        warns.append(
            f"candidate panel constrained to models "
            f"{'with' if dc_sigma else 'without'} a DC-σ term (user setting)."
        )

    fitted: list[tuple[str, FitResult]] = []
    for label, fitfn in panel.items():
        try:
            fitted.append((label, fitfn(spectrum)))
        except Exception as exc:  # a candidate that cannot be fit is skipped, not fatal
            warns.append(f"candidate '{label}' failed to fit: {exc}")

    if not fitted:
        raise RuntimeError("no candidate model could be fit to this spectrum")

    fitted.sort(key=lambda lr: lr[1].aicc)
    best_aicc = fitted[0][1].aicc
    ranking: list[RankedFit] = []
    for label, res in fitted:
        overparam = res.n_data - res.n_params - 1 <= 0
        mru = max_relative_uncertainty(res)
        degenerate = mru > DEGENERACY_THRESHOLD
        ranking.append(RankedFit(label, res, res.aicc - best_aicc, overparam, degenerate, mru))

    # Recommendation. Restrict to models that describe the data comparably well (R² within
    # R2_RECOMMEND_TOL of the best non-over-parameterized fit) — this excludes qualitatively worse
    # models like a poor Jonscher fit. Among those, prefer identifiable (non-degenerate) ones; only
    # if none are identifiable do we keep the well-fitting-but-underdetermined set (and warn). Then
    # take the most parsimonious within the AICc parsimony band. This avoids two failure modes:
    # chasing a lower AICc into a collapsed-σ fit, and abandoning the right physical family for a
    # much worse fit just because its few parameters happen to be identifiable.
    non_over = [rf for rf in ranking if not rf.overparameterized] or list(ranking)
    best_r2 = max(rf.result.r_squared for rf in non_over)
    good_fit = [rf for rf in non_over if rf.result.r_squared >= best_r2 - R2_RECOMMEND_TOL]
    identifiable = [rf for rf in good_fit if not rf.degenerate]
    pool = identifiable or good_fit
    best_pool_aicc = min(rf.result.aicc for rf in pool)
    within = [rf for rf in pool if rf.result.aicc - best_pool_aicc <= PARSIMONY_DELTA_AICC]
    recommended = min(within or pool, key=lambda rf: (rf.result.n_params, rf.result.aicc))
    if not identifiable:
        warns.append(
            "every well-fitting candidate has unidentifiable parameters (often too few repeats or "
            "too narrow a band); the recommendation fits well but is underdetermined — inspect the "
            "parameter uncertainties before trusting it."
        )

    # Record, per candidate, why it is not the recommendation (machine-readable, drives the UI).
    good_ids = {id(rf) for rf in good_fit}
    pool_ids = {id(rf) for rf in pool}
    within_ids = {id(rf) for rf in within}
    r2_floor = best_r2 - R2_RECOMMEND_TOL

    def _excluded_reason(rf: RankedFit) -> str:
        if rf.label == recommended.label:
            return ""
        if rf.overparameterized:
            return f"over-parameterized (k={rf.result.n_params} ≥ N−1={rf.result.n_data - 1})"
        if id(rf) not in good_ids:
            return f"fit quality below tolerance (R²={rf.result.r_squared:.4f} < {r2_floor:.4f})"
        if id(rf) not in pool_ids:
            return (
                f"parameters unidentifiable (max relative uncertainty {rf.max_rel_uncertainty:.1f})"
            )
        if id(rf) not in within_ids:
            return (
                f"ΔAICc {rf.result.aicc - best_pool_aicc:.1f} above the parsimony band "
                f"(≤ {PARSIMONY_DELTA_AICC:.0f})"
            )
        return f"within the parsimony band but less parsimonious than '{recommended.label}'"

    ranking = [replace(rf, excluded_reason=_excluded_reason(rf)) for rf in ranking]
    recommended = next(rf for rf in ranking if rf.label == recommended.label)

    for rf in ranking:
        if rf.overparameterized:
            warns.append(
                f"'{rf.label}' is over-parameterized for this data "
                f"(k={rf.result.n_params}, N={rf.result.n_data}); AICc is unreliable."
            )
        elif rf.degenerate:
            warns.append(
                f"'{rf.label}' has unidentifiable parameters (max relative uncertainty "
                f"{rf.max_rel_uncertainty:.1f}); a lower AICc here is not physically trustworthy."
            )

    # Plain-language "why this model" for the recommendation.
    n_unident = sum(1 for rf in ranking if "unidentifiable" in rf.excluded_reason)
    if identifiable:
        rationale = (
            f"Recommended '{recommended.label}': the most parsimonious identifiable model "
            f"(k = {recommended.result.n_params}; all parameter uncertainties bounded, max "
            f"relative uncertainty {recommended.max_rel_uncertainty:.2f} ≤ 1) within "
            f"ΔAICc ≤ {PARSIMONY_DELTA_AICC:.0f} of the best well-fitting candidate "
            f"(R² = {recommended.result.r_squared:.4f})."
        )
        if n_unident:
            rationale += (
                f" {n_unident} candidate(s) with lower AICc were excluded from the recommendation "
                f"because their parameters are unidentifiable (see the ranking flags)."
            )
    else:
        rationale = (
            f"Recommended '{recommended.label}': no candidate was fully identifiable on this data, "
            f"so the most parsimonious well-fitting model was chosen — its parameters are "
            f"underdetermined, so treat their uncertainties with caution."
        )

    # Override handling.
    chosen = recommended
    overridden = False
    if forced_label is not None:
        match = next((rf for rf in ranking if rf.label == forced_label), None)
        if match is None:
            raise ValueError(
                f"forced model '{forced_label}' is not among the candidates "
                f"(available: {', '.join(rf.label for rf in ranking)})"
            )
        chosen = match
        overridden = True
        if match.label != recommended.label:
            msg = (
                f"using overridden model '{match.label}' (ΔAICc={match.delta_aicc:+.2f} vs best); "
                f"the parsimony-recommended model is '{recommended.label}'."
            )
            warns.append(msg)
            warnings.warn(ModelSelectionWarning(msg), stacklevel=2)

    # Goodness-of-fit disclosure: for a weighted fit, reduced χ² ≫ 1 means the model misfit
    # exceeds the Type A uncertainty — the parameter covariance (which assumes model adequacy)
    # is then optimistic by roughly √χ²ᵣ. Say so rather than quoting bare uncertainties.
    chi2r = chosen.result.chi2_reduced
    if chosen.result.weighted and chi2r > CHI2_MISFIT_WARN:
        warns.append(
            f"the chosen fit has reduced χ² = {chi2r:.1f} ≫ 1: the model does not describe the "
            f"data within the Type A uncertainty, so the quoted parameter uncertainties (which "
            f"assume model adequacy) may be optimistic by ~√χ²ᵣ ≈ {chi2r**0.5:.1f}×."
        )

    # Band-edge pole disclosure: a relaxation peaking outside the measured band is constrained only
    # by the dispersion tail — its Δε aliases σ_dc, so the extrapolated parameters are unreliable.
    band_lo, band_hi = spectrum.band_hz
    for name, value in chosen.result.params.items():
        if re.fullmatch(r"tau(_\d+)?", name) and value > 0:
            f_peak = 1.0 / (2.0 * math.pi * value)
            if f_peak < band_lo or f_peak > band_hi:
                warns.append(
                    f"a relaxation pole peaks at {f_peak / 1e9:.3g} GHz, outside the measured band "
                    f"{band_lo / 1e9:.2g}–{band_hi / 1e9:.2g} GHz — it is constrained only by the "
                    f"dispersion tail (extrapolation); its Δε trades off against σ_dc, so treat "
                    f"the extrapolated parameters with caution."
                )

    return ModelSelectionResult(
        ranking=tuple(ranking),
        recommended=recommended,
        chosen=chosen,
        overridden=overridden,
        warnings=tuple(warns),
        rationale=rationale,
    )
