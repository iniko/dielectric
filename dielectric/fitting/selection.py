"""Automatic model selection with parsimony guardrails and a user override.

Fits a panel of candidate models, ranks them by small-sample-corrected AIC (AICc) and BIC, and
recommends one — but never just "lowest residual": it prefers the simpler nested model unless a
richer one improves AICc by a meaningful margin, and it flags over-parameterized fits. The user can
override the recommendation by model label and/or number of poles while still seeing where their
choice ranks.
"""

from __future__ import annotations

import warnings
from collections.abc import Callable
from dataclasses import dataclass

from ..models.cole_davidson import ColeDavidson
from ..models.havriliak_negami import HavriliakNegami
from ..models.jonscher import JonscherUniversal
from ..spectrum import Spectrum
from .engine import fit
from .fitters import (
    _guess,
    fit_cole_cole,
    fit_cole_cole_conductivity,
    fit_debye,
    fit_multipole,
)
from .result import FitResult

#: ΔAICc below which two models are "indistinguishable", so the simpler one wins (Burnham-Anderson).
PARSIMONY_DELTA_AICC = 2.0

#: A fit is "degenerate" (parameters unidentifiable) if its largest regularized relative parameter
#: uncertainty exceeds this. Such a fit may have a low AICc yet be physically meaningless (e.g. a
#: slow relaxation pole absorbing the DC-conduction tail, collapsing σ to ~0 with a huge error bar).
DEGENERACY_THRESHOLD = 1.0

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

FitFn = Callable[[Spectrum], FitResult]


def max_relative_uncertainty(result: FitResult) -> float:
    """Largest regularized relative parameter uncertainty ``u / (|value| + scale)`` over the fit.

    The per-parameter ``scale`` floor prevents a near-zero-but-well-determined parameter from being
    flagged while still catching a genuinely unconstrained one (large ``u`` with tiny ``|value|``).
    """
    import re

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


def _fit_cole_davidson(s: Spectrum) -> FitResult:
    eps_inf, terms, _ = _guess(s, 1, with_conductivity=False)
    delta, tau, _ = terms[0]
    return fit(s, ColeDavidson(eps_inf, delta, tau, 0.7))


def _fit_havriliak_negami(s: Spectrum) -> FitResult:
    eps_inf, terms, _ = _guess(s, 1, with_conductivity=False)
    delta, tau, _ = terms[0]
    return fit(s, HavriliakNegami(eps_inf, delta, tau, 0.1, 0.8))


def _fit_jonscher(s: Spectrum) -> FitResult:
    eps_inf = max(float(s.eps_real[-1]), 1.0)
    return fit(s, JonscherUniversal(eps_inf, 1.0, 0.6))


def _multipole_fitter(n: int) -> FitFn:
    """Return a typed single-argument fitter for an N-pole (+DC σ) model."""

    def _fit(s: Spectrum) -> FitResult:
        return fit_multipole(s, n, with_conductivity=True)

    return _fit


def default_candidates(max_poles: int = 3) -> dict[str, FitFn]:
    """The default panel of candidate models (label → fitter)."""
    candidates: dict[str, FitFn] = {
        "Debye": fit_debye,
        "Cole-Cole": fit_cole_cole,
        "Cole-Davidson": _fit_cole_davidson,
        "Havriliak-Negami": _fit_havriliak_negami,
        "Jonscher": _fit_jonscher,
        "Cole-Cole + DC σ": fit_cole_cole_conductivity,
    }
    for n in range(2, max_poles + 1):
        candidates[f"MultiPole(N={n}) + DC σ"] = _multipole_fitter(n)
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


@dataclass(frozen=True)
class ModelSelectionResult:
    """Outcome of :func:`select_model`."""

    ranking: tuple[RankedFit, ...]  # sorted best → worst by AICc
    recommended: RankedFit  # parsimony-aware automatic pick
    chosen: RankedFit  # what to use downstream (== recommended unless overridden)
    overridden: bool
    warnings: tuple[str, ...]

    def table(self) -> str:
        head = f"{'model':<24}{'k':>3}{'χ²_red':>12}{'AICc':>12}{'ΔAICc':>10}{'BIC':>12}{'R²':>10}"
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
                f"{rf.label:<24}{r.n_params:>3}{r.chi2_reduced:>12.4g}{r.aicc:>12.4g}"
                f"{rf.delta_aicc:>10.2f}{r.bic:>12.4g}{r.r_squared:>10.6f}{mark}{flag}"
            )
        return "\n".join(rows)


def select_model(
    spectrum: Spectrum,
    *,
    candidates: dict[str, FitFn] | None = None,
    force_model: str | None = None,
    n_poles: int | None = None,
    max_poles: int = 3,
) -> ModelSelectionResult:
    """Fit and rank candidate models; recommend one; honor an optional override.

    Parameters
    ----------
    force_model:
        A candidate label (e.g. ``"Havriliak-Negami"``) to use instead of the automatic pick.
    n_poles:
        Force an N-pole Cole-Cole (+DC σ) model — the "number of poles" override. Takes precedence
        over ``force_model``.
    """
    panel = dict(candidates or default_candidates(max_poles))
    if n_poles is not None and f"MultiPole(N={n_poles}) + DC σ" not in panel:
        panel[f"MultiPole(N={n_poles}) + DC σ"] = _multipole_fitter(n_poles)

    warns: list[str] = []
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

    # Recommendation: only among *acceptable* fits — not over-parameterized and not degenerate
    # (identifiable parameters). Among those, re-reference ΔAICc to the best acceptable fit and pick
    # the most parsimonious within the parsimony band, so we never chase a lower AICc into a
    # physically meaningless fit (e.g. a collapsed σ). Fall back to all fits only if none qualify.
    acceptable = [rf for rf in ranking if not rf.overparameterized and not rf.degenerate]
    pool = acceptable or ranking
    best_pool_aicc = min(rf.result.aicc for rf in pool)
    within = [rf for rf in pool if rf.result.aicc - best_pool_aicc <= PARSIMONY_DELTA_AICC]
    recommended = min(within, key=lambda rf: rf.result.n_params) if within else min(
        pool, key=lambda rf: rf.result.aicc
    )
    if not acceptable:
        warns.append(
            "every candidate is over-parameterized or has unidentifiable parameters; the "
            "recommendation is the least-bad fit — inspect parameter uncertainties first."
        )

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

    # Override handling.
    chosen = recommended
    overridden = False
    forced_label: str | None = None
    if n_poles is not None:
        forced_label = f"MultiPole(N={n_poles}) + DC σ"
    elif force_model is not None:
        forced_label = force_model
    if forced_label is not None:
        match = next((rf for rf in ranking if rf.label == forced_label), None)
        if match is None:
            raise ValueError(
                f"forced model '{forced_label}' is not among the candidates: "
                f"{[rf.label for rf in ranking]}"
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

    return ModelSelectionResult(
        ranking=tuple(ranking),
        recommended=recommended,
        chosen=chosen,
        overridden=overridden,
        warnings=tuple(warns),
    )
