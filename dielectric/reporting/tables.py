"""Paper-ready tables (LaTeX + CSV) with uncertainty-driven formatting."""

from __future__ import annotations

import csv
import io

from ..fitting.result import FitResult
from ..fitting.selection import ModelSelectionResult
from .formatting import format_measurement


def _latexify(measurement: str) -> str:
    """Turn ``"8.01 ± 0.03)e-12"``-style output into LaTeX math."""
    s = measurement.replace("±", r"\pm")
    if "e" in s:
        # (m ± u)e-12  ->  (m \pm u)\times10^{-12}
        base, _, exp = s.rpartition("e")
        s = f"{base}" + r"\times10^{" + exp.lstrip("+") + "}"
    return f"${s}$"


def parameter_table_csv(fit: FitResult) -> str:
    """Fitted parameters as CSV: parameter, value, uncertainty, formatted."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["parameter", "value", "standard_uncertainty", "formatted"])
    for name in fit.model.param_names:
        v = fit.params[name]
        u = fit.param_uncertainties.get(name, 0.0)
        w.writerow([name, repr(v), repr(u), format_measurement(v, u)])
    w.writerow([])
    w.writerow(["R^2", repr(fit.r_squared), "", f"{fit.r_squared:.4f}"])
    w.writerow(["reduced_chi2", repr(fit.chi2_reduced), "", f"{fit.chi2_reduced:.3g}"])
    w.writerow(["AICc", repr(fit.aicc), "", f"{fit.aicc:.4g}"])
    return buf.getvalue()


def parameter_table_latex(
    fit: FitResult,
    *,
    caption: str = "Fitted dielectric model parameters.",
    label: str = "tab:dielectric_fit",
) -> str:
    """Fitted parameters as a LaTeX ``table`` with value ± uncertainty."""
    rows = [
        r"\begin{table}[t]",
        r"  \centering",
        f"  \\caption{{{caption}}}",
        f"  \\label{{{label}}}",
        r"  \begin{tabular}{lr}",
        r"    \hline",
        r"    Parameter & Value \\",
        r"    \hline",
    ]
    for name in fit.model.param_names:
        v = fit.params[name]
        u = fit.param_uncertainties.get(name, 0.0)
        rows.append(f"    {_escape(name)} & {_latexify(format_measurement(v, u))} \\\\")
    rows += [
        r"    \hline",
        f"    $R^2$ & ${fit.r_squared:.4f}$ \\\\",
        f"    reduced $\\chi^2$ & ${fit.chi2_reduced:.3g}$ \\\\",
        f"    AICc & ${fit.aicc:.4g}$ \\\\",
        r"    \hline",
        r"  \end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(rows)


def selection_table_csv(selection: ModelSelectionResult) -> str:
    """Model-selection ranking as CSV."""
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["model", "k", "chi2_reduced", "AICc", "delta_AICc", "BIC", "R2", "flag", "chosen"])
    for rf in selection.ranking:
        flag = "overparam" if rf.overparameterized else "degenerate" if rf.degenerate else ""
        w.writerow([
            rf.label, rf.result.n_params, f"{rf.result.chi2_reduced:.4g}",
            f"{rf.result.aicc:.4g}", f"{rf.delta_aicc:.2f}", f"{rf.result.bic:.4g}",
            f"{rf.result.r_squared:.6f}", flag, rf.label == selection.chosen.label,
        ])
    return buf.getvalue()


def _escape(text: str) -> str:
    return text.replace("_", r"\_")
