"""Command-line interface: a thin end-to-end orchestrator over the library.

Example::

    dielectric analyze --measure "data/h02s19m*.csv" \\
        --validate "data/h02v*.csv" --reference saline --molarity 0.154 \\
        --temperature 25 --out out/

Loads any number of measurement and validation sets, runs the full pipeline (Type A → quality →
auto model-selection with optional override → Kramers-Kronig → literature comparison → known-
reference QC), and writes publication-ready artifacts (figures, LaTeX/CSV tables, methods paragraph,
BibTeX, reproducibility manifest, and docx/pdf reports).
"""

from __future__ import annotations

import argparse
import sys
import warnings
from datetime import datetime, timezone
from pathlib import Path

from . import __version__
from .fitting import select_model
from .io import Campaign, CampaignMetadata, MeasurementSet, ValidationSet
from .reporting import (
    ReproducibilityManifest,
    assemble_report,
    bode_figure,
    cole_cole_figure,
    methods_paragraph,
    parameter_table_csv,
    parameter_table_latex,
    render_docx,
    render_pdf,
    save_figure,
    to_bibtex,
)
from .verification import find_closest_materials, kramers_kronig_check, validate_campaign


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="dielectric", description=__doc__)
    parser.add_argument("--version", action="version", version=f"dielectric {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    a = sub.add_parser("analyze", help="run the full analysis pipeline")
    a.add_argument("--measure", action="append", required=True, metavar="GLOB",
                   help="glob for a measurement set (repeatable for multiple samples)")
    a.add_argument("--validate", action="append", default=[], metavar="GLOB",
                   help="glob for a validation set (repeatable)")
    a.add_argument("--reference", action="append", default=[], metavar="NAME",
                   help="reference material per --validate (e.g. saline)")
    a.add_argument("--molarity", type=float, default=0.154, help="saline molarity [mol/L]")
    a.add_argument("--model", default=None,
                   help="force a model family or full label, e.g. 'Debye' or "
                        "'Cole-Cole (2 poles) + DC σ' (composes with --poles/--dc-sigma)")
    a.add_argument("--poles", type=int, default=None,
                   help="pole count (1-3); composes with --model, or ladders the auto panel")
    a.add_argument("--dc-sigma", choices=("on", "off"), default=None, dest="dc_sigma",
                   help="include/exclude a DC-conductivity term (composes with --model)")
    a.add_argument("--temperature", type=float, default=25.0, help="measurement temperature [°C]")
    a.add_argument("--out", default="out", help="output directory")
    a.add_argument("--no-report", action="store_true", help="skip docx/pdf report generation")
    return parser


def _analyze(args: argparse.Namespace) -> int:
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).isoformat()

    # Validation campaign (shared across samples).
    validations: list[ValidationSet] = []
    for i, vglob in enumerate(args.validate):
        ref = args.reference[i] if i < len(args.reference) else "saline"
        kwargs = {"molarity": args.molarity} if ref == "saline" else {}
        validations.append(
            ValidationSet.from_glob(vglob, reference=ref, reference_kwargs=kwargs,
                                    temperature_c=args.temperature)
        )

    for mglob in args.measure:
        meas = MeasurementSet.from_glob(mglob, temperature_c=args.temperature)
        campaign = Campaign(measurements=(meas,), validations=tuple(validations),
                            metadata=CampaignMetadata(temperature_c=args.temperature))
        ta = meas.type_a()
        spectrum = ta.mean
        quality = spectrum.quality_report()

        dc = {"on": True, "off": False, None: None}[args.dc_sigma]
        sel = select_model(spectrum, force_model=args.model, n_poles=args.poles, dc_sigma=dc)
        fit = sel.chosen.result
        kk = kramers_kronig_check(spectrum, model=fit.model)
        cv = validate_campaign(campaign) if validations else None
        closest = find_closest_materials(spectrum, material_class="tissue",
                                         target_temperature_c=args.temperature, top=3)

        stem = meas.sample_id
        save_figure(bode_figure(spectrum, fit, title=stem), str(out / f"{stem}_bode.png"))
        save_figure(cole_cole_figure(spectrum, fit), str(out / f"{stem}_cole.png"))
        (out / f"{stem}_params.tex").write_text(parameter_table_latex(fit))
        (out / f"{stem}_params.csv").write_text(parameter_table_csv(fit))
        band_ghz = (spectrum.band_hz[0] / 1e9, spectrum.band_hz[1] / 1e9)
        methods = methods_paragraph(fit, selection=sel, kk=kk, validation=cv,
                                    n_repeats=ta.n_repeats_used, band_ghz=band_ghz)
        (out / f"{stem}_methods.txt").write_text(methods)
        (out / f"{stem}.bib").write_text(to_bibtex(fit.model))
        manifest = ReproducibilityManifest.from_fit(fit, timestamp=timestamp, data_source=mglob)
        (out / f"{stem}_manifest.json").write_text(manifest.to_json())

        if not args.no_report:
            report = assemble_report(
                title=f"Dielectric analysis: {stem}", fit=fit, selection=sel, manifest=manifest,
                validation=cv, kk=kk, n_repeats=ta.n_repeats_used,
                band_ghz=(spectrum.band_hz[0] / 1e9, spectrum.band_hz[1] / 1e9),
                figure_paths=(str(out / f"{stem}_bode.png"), str(out / f"{stem}_cole.png")),
            )
            render_docx(report, str(out / f"{stem}_report.docx"))
            render_pdf(report, str(out / f"{stem}_report.pdf"))

        # Console summary.
        print(f"\n=== {stem} ===")
        print(f"  loaded {meas.n_repeats} repeats; Type A used {ta.n_repeats_used} "
              f"(excluded {ta.excluded_indices or 'none'})")
        if quality.warnings:
            for w in quality.warnings:
                print(f"  quality: {w}")
        print(f"  selected model: {sel.chosen.label}"
              f"{' (overridden)' if sel.overridden else ''}")
        print("  " + fit.summary().replace("\n", "\n  "))
        print(f"  Kramers-Kronig residual: {kk.residual_rms * 100:.1f}% "
              f"({'consistent' if kk.is_consistent else 'INCONSISTENT'})")
        print(f"  closest tissue: {', '.join(c.material for c in closest)}")
        if cv is not None:
            print(f"  validation: {cv.status}")
        print(f"  artifacts written to {out}/{stem}_*")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # the CLI summarises warnings itself
        if args.command == "analyze":
            return _analyze(args)
    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
