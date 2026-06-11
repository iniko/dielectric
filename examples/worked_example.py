"""Worked, narrated end-to-end example on real data (load → fit → verify → uncertainty → export).

Run from the repository root::

    python examples/worked_example.py

This is the teaching front door: it walks a PhD student through the full workflow on the bundled
``h02`` saline-validation / tissue-like-sample campaign, narrating each decision. Every figure and
report it writes carries a reproducibility manifest.
"""

from __future__ import annotations

import warnings
from datetime import datetime, timezone
from pathlib import Path

from dielectric.fitting import select_model
from dielectric.io import Campaign, CampaignMetadata, MeasurementSet, ValidationSet
from dielectric.reporting import (
    ReproducibilityManifest,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    methods_paragraph,
    parameter_table_latex,
    render_docx,
    render_pdf,
    save_figure,
)
from dielectric.uncertainty import coaxial_probe_permittivity_budget, monte_carlo
from dielectric.verification import (
    find_closest_materials,
    kramers_kronig_check,
    validate_campaign,
)

DATA = Path(__file__).resolve().parent.parent / "data"
OUT = Path(__file__).resolve().parent.parent / "out"


def main() -> None:
    OUT.mkdir(exist_ok=True)
    print(__doc__)

    # 1. LOAD — a measurement set is a repeatability group; load as many repeats as you have.
    print("\n[1] Loading the sample (15 repeats) and the saline validation set (25 repeats)...")
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the loader warns per-file that positive loss was negated
        sample = MeasurementSet.from_glob(
            str(DATA / "h02s19m*.csv"), sample_id="h02_sample", temperature_c=25.0
        )
        validation = ValidationSet.from_glob(
            str(DATA / "h02v*.csv"), reference="saline",
            reference_kwargs={"molarity": 0.154}, temperature_c=25.0,
        )
    campaign = Campaign(
        measurements=(sample,), validations=(validation,),
        metadata=CampaignMetadata(title="H02 campaign", temperature_c=25.0),
    )
    print("    The 85070 export stores POSITIVE loss; the loader negated it to the internal "
          "e^{jωt} convention (Im(ε*)<0) and warned — it never silently 'fixes' data.")

    # 2. TYPE A — average the repeats; a robust k·MAD screen drops a bad probe contact.
    ta = sample.type_a()
    spectrum = ta.mean
    print(f"\n[2] Type A averaging used {ta.n_repeats_used}/{sample.n_repeats} repeats "
          f"(excluded {ta.excluded_indices or 'none'} via k·MAD). Per-point SEM weights the fit.")

    # 3. QUALITY — look before you fit.
    q = spectrum.quality_report()
    print(f"\n[3] Pre-fit quality: span {q.frequency_span_decades:.1f} decades, "
          f"noise ≈ {q.median_relative_noise:.1e}, {q.n_outliers} outlier point(s). "
          f"{'No blocking issues.' if q.ok else 'See warnings above.'}")

    # 4. HYPOTHESIS & FIT — which model? Let AICc + identifiability decide, but you can override.
    print("\n[4] Hypothesis: a conductive, high-water sample needs a relaxation + a DC-conduction "
          "term. Testing it against 11 candidate models by AICc...")
    sel = select_model(spectrum)
    print(sel.table())
    fit = sel.chosen.result
    print(f"\n    → Recommended: {sel.recommended.label}.")
    print(f"      {sel.rationale}")
    print("      (Override with select_model(s, force_model='Debye', n_poles=2, dc_sigma=True), "
          "composing family × poles × DC σ; degenerate fits are flagged and never recommended.)")
    print("    " + fit.summary().replace("\n", "\n    "))

    # 5. VERIFY — Kramers-Kronig causality, literature comparison, known-reference QC.
    kk = kramers_kronig_check(spectrum, model=fit.model)
    closest = find_closest_materials(spectrum, material_class="tissue",
                                     target_temperature_c=37.0, top=3)
    cv = validate_campaign(campaign)
    print(f"\n[5] Kramers-Kronig: {kk.residual_rms * 100:.1f}% residual "
          f"({'consistent' if kk.is_consistent else 'INCONSISTENT'}).")
    print(f"    Closest literature tissues: {', '.join(c.material for c in closest)} "
          f"(VERIFY-confidence — confirm against IFAC Appendix C).")
    print(f"    Reference QC: {cv.status}")

    # 6. UNCERTAINTY — Monte Carlo + a GUM budget with the input-uncertainty injection.
    sigma_idx = fit.model.param_names.index("sigma_dc")
    mc = monte_carlo(lambda p, i=sigma_idx: p[i], list(fit.params.values()),
                     [fit.param_uncertainties[n] for n in fit.model.param_names],
                     seed=20260605, n_samples=4000)
    budget = coaxial_probe_permittivity_budget(
        float(spectrum.eps_real[0]), type_a_std=float(ta.combined_sem.real[0]),
        type_a_dof=ta.n_repeats_used - 1, fit_std=fit.param_uncertainties["delta_eps_1"],
        temperature_sensitivity=-0.36, temperature_half_width_c=2.0, input_inversion_relative=0.03,
    )
    print(f"\n[6] Monte Carlo σ_DC = {mc.scalar[0]:.3f} ± {mc.scalar[1]:.3f} S/m "
          f"(seed {mc.seed}, converged={mc.converged}).")
    print(budget.table())
    print("    Note the input/inversion term — without it the budget would be silently optimistic.")

    # 7. EXPORT — publication-ready artifacts, each carrying a reproducibility manifest.
    timestamp = datetime.now(timezone.utc).isoformat()
    manifest = ReproducibilityManifest.from_fit(fit, timestamp=timestamp,
                                                data_source="data/h02s19m*.csv")
    save_figure(bode_figure(spectrum, fit, title="H02 sample"), str(OUT / "h02_bode.png"))
    save_figure(cole_cole_figure(spectrum, fit), str(OUT / "h02_cole.png"))
    (OUT / "h02_params.tex").write_text(parameter_table_latex(fit))
    methods = methods_paragraph(fit, selection=sel, kk=kk, validation=cv,
                                n_repeats=ta.n_repeats_used, band_ghz=(0.2, 20.0))
    (OUT / "h02_methods.txt").write_text(methods)
    report = assemble_report(title="H02 Dielectric Analysis", fit=fit, selection=sel,
                             manifest=manifest, validation=cv, kk=kk, n_repeats=ta.n_repeats_used,
                             band_ghz=(0.2, 20.0),
                             figure_paths=(str(OUT / "h02_bode.png"), str(OUT / "h02_cole.png")))
    render_docx(report, str(OUT / "h02_report.docx"))
    render_pdf(report, str(OUT / "h02_report.pdf"))

    print(f"\n[7] Wrote figures, LaTeX table, methods paragraph, and docx/pdf reports to {OUT}/")
    print("\n--- METHODS PARAGRAPH (paste-ready) ---")
    print(methods)


if __name__ == "__main__":
    main()
