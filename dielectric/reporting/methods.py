"""Methods-paragraph generator — publication-ready prose describing the analysis.

The single highest-leverage feature for getting students to write reproducibly: it emits a
journal-style methods snippet citing the model equation and source, the fit quality, the
Kramers-Kronig check, and the validation status, with every parameter reported as value ± u.
"""

from __future__ import annotations

from .. import __version__
from ..fitting.catalog import model_info, structure_phrase
from ..fitting.result import FitResult
from ..fitting.selection import ModelSelectionResult
from ..verification.kramers_kronig import KKResult
from ..verification.validation import CampaignValidation
from .formatting import format_measurement


def methods_paragraph(
    fit: FitResult,
    *,
    selection: ModelSelectionResult | None = None,
    kk: KKResult | None = None,
    validation: CampaignValidation | None = None,
    n_repeats: int | None = None,
    n_repeats_total: int | None = None,
    n_excluded: int = 0,
    outlier_k: float | None = None,
    band_ghz: tuple[float, float] | None = None,
) -> str:
    """Generate a publication-ready methods paragraph for one fitted spectrum.

    ``n_repeats`` is the number of repeats actually used (after screening); ``n_repeats_total`` and
    ``n_excluded`` disclose any outlier exclusion so the averaging is reported transparently.
    """
    sentences: list[str] = []

    # Describe the model from the chosen label when available (states family + pole count), else
    # from the fitted instance.
    if selection is not None:
        model_phrase = "a model comprising " + model_info(selection.chosen.label).description
    else:
        model_phrase = "a model comprising " + structure_phrase(fit.model)
    citation = fit.model.provenance.short_citation()

    # 1. Data / averaging — disclose any repeat exclusion (the rigor-critical bit).
    if band_ghz is not None:
        band = f"from {band_ghz[0]:.2g} to {band_ghz[1]:.2g} GHz"
    else:
        band = "across the measured band"
    repeats = ""
    if n_repeats:
        repeats = f" and averaged over {n_repeats} repeat measurements (Type A)"
        if n_excluded and n_repeats_total:
            repeats += (
                f", after excluding {n_excluded} of {n_repeats_total} repeats as outliers by a "
                f"robust MAD-based z-score screen (Hampel identifier, k = {outlier_k:g})"
            )
        elif outlier_k is None and n_repeats_total:
            repeats += " (no outlier screening applied; all repeats retained)"
    sentences.append(
        f"Complex relative permittivity spectra ε*(f) were acquired {band}{repeats}, with the loss "
        "stored in the engineering e^{jωt} convention (Im(ε*) < 0)."
    )

    # 2. Fit.
    param_strs = [
        format_measurement(fit.params[name], fit.param_uncertainties.get(name, 0.0))
        for name in fit.model.param_names
    ]
    params_joined = "; ".join(
        f"{n} = {p}" for n, p in zip(fit.model.param_names, param_strs, strict=True)
    )
    weighting = (
        "weighted by the Type A standard error of the mean"
        if fit.weighted
        else "with uniform weighting"
    )
    sentences.append(
        f"ε*(f) was fitted to {model_phrase} ({citation}) by non-linear least squares on the "
        f"stacked real and imaginary residuals, {weighting}, yielding {params_joined} "
        f"(R² = {fit.r_squared:.4f}, reduced χ² = {fit.chi2_reduced:.2g})."
    )

    # 3. Model selection — report the margin over the next *acceptable* (identifiable) candidate,
    # not the overall AICc-minimum, which may be a rejected degenerate fit.
    if selection is not None:
        n_cand = len(selection.ranking)
        acceptable = sorted(
            (rf for rf in selection.ranking
             if not rf.overparameterized and not rf.degenerate),
            key=lambda rf: rf.result.aicc,
        )
        runner = next((rf for rf in acceptable if rf.label != selection.chosen.label), None)
        margin = ""
        if runner is not None:
            d = runner.result.aicc - selection.chosen.result.aicc
            # d < 0 means the alternative actually ranks better (an analyst override) — say
            # "despite", never "preferred by" a negative margin.
            margin = (
                f"; it was preferred over the next identifiable model "
                f"({runner.label}) by ΔAICc = {d:.1f}"
                if d >= 0
                else f"; it was chosen despite ΔAICc = {-d:.1f} in favour of the next "
                f"identifiable model ({runner.label})"
            )
        how = (
            "selected by minimum corrected-AIC (AICc) with a parsimony and identifiability check"
            if not selection.overridden
            else "chosen by the analyst (overriding the AICc recommendation)"
        )
        sentences.append(f"The model was {how} among {n_cand} candidate models{margin}.")
        if not selection.overridden and selection.rationale:
            sentences.append(selection.rationale)

    # 4. Kramers-Kronig.
    if kk is not None:
        verdict = "consistent" if kk.is_consistent else "inconsistent"
        sentences.append(
            f"Kramers-Kronig analysis found the spectrum causally {verdict} "
            f"(relative ε' residual {kk.residual_rms * 100:.1f}%)."
        )

    # 5. Validation.
    if validation is not None:
        if validation.validated and validation.verdicts:
            v = validation.verdicts[0]
            sentences.append(
                f"The measurement chain was validated against a known {v.reference} reference "
                f"(ε' deviation {v.eps_real_rms * 100:.1f}%, σ_DC {v.sigma_measured:.2f} vs "
                f"{v.sigma_reference:.2f} S/m)."
            )
        elif validation.has_validation:
            sentences.append(
                "The campaign did NOT pass reference validation; results should be treated as "
                "provisional pending a passing QC measurement."
            )
        else:
            sentences.append(
                "No reference validation was performed, so results are reported as NOT VALIDATED."
            )

    # 6. Software.
    sentences.append(f"Analysis used the dielectric toolkit (v{__version__}).")

    return " ".join(sentences)
