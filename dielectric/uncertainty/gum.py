"""GUM / JCGM-100 uncertainty budget engine.

Combines Type A and Type B uncertainty components into a combined standard uncertainty and an
expanded uncertainty (with a coverage factor from the Welch-Satterthwaite effective degrees of
freedom). Includes the **input-uncertainty injection**: because calibration/inversion is out of
scope, the budget must let the user add an explicit "trust the probe software ±X %" term so it is
never silently optimistic. The default coaxial-probe template enumerates the standard contributors.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class UncertaintyComponent:
    """One GUM uncertainty contribution.

    ``standard_uncertainty`` is u_i in the input quantity's units; ``sensitivity`` is the
    coefficient c_i = ∂(measurand)/∂x_i. The contribution to the measurand is ``c_i · u_i``.
    """

    name: str
    standard_uncertainty: float
    sensitivity: float = 1.0
    dof: float = math.inf
    kind: str = "B"  # "A" (statistical) or "B" (other)
    note: str = ""

    @property
    def contribution(self) -> float:
        return abs(self.sensitivity * self.standard_uncertainty)

    @classmethod
    def type_a(
        cls, name: str, std: float, dof: float, *, sensitivity: float = 1.0
    ) -> UncertaintyComponent:
        return cls(name, std, sensitivity, dof, kind="A", note="Type A repeatability")

    @classmethod
    def rectangular(
        cls, name: str, half_width: float, *, sensitivity: float = 1.0, note: str = ""
    ) -> UncertaintyComponent:
        """Type B from a rectangular (uniform) distribution of half-width ``a``: u = a/√3."""
        return cls(name, half_width / math.sqrt(3.0), sensitivity, math.inf, "B", note)

    @classmethod
    def relative_input(
        cls, name: str, relative: float, nominal: float, *, note: str = ""
    ) -> UncertaintyComponent:
        """The input-uncertainty injection: a relative uncertainty (e.g. ±2 %) on a nominal value.

        Use this to fold in an opaque 'trust the probe software / inversion ±X %' term so the budget
        is honest about the calibration/inversion step that is out of this toolkit's scope.
        """
        return cls(
            name,
            abs(relative) * abs(nominal),
            1.0,
            math.inf,
            "B",
            note or f"input/inversion uncertainty ±{relative * 100:.1f}%",
        )


@dataclass(frozen=True)
class GUMBudget:
    """A JCGM-100 uncertainty budget for one measurand."""

    measurand: str
    nominal_value: float
    components: tuple[UncertaintyComponent, ...]
    unit: str = ""

    @property
    def combined_standard_uncertainty(self) -> float:
        return math.sqrt(sum(c.contribution**2 for c in self.components))

    @property
    def effective_dof(self) -> float:
        """Welch-Satterthwaite effective degrees of freedom."""
        uc = self.combined_standard_uncertainty
        if uc == 0:
            return math.inf
        denom = 0.0
        for c in self.components:
            if math.isfinite(c.dof) and c.dof > 0:
                denom += c.contribution**4 / c.dof
        if denom == 0:
            return math.inf
        return uc**4 / denom

    def coverage_factor(self, level: float = 0.95) -> float:
        """Coverage factor k from the t-distribution at ``effective_dof`` (≈2 for large dof)."""
        nu = self.effective_dof
        if not math.isfinite(nu):
            return 1.96 if abs(level - 0.95) < 1e-6 else 2.576
        try:
            from scipy.stats import t

            return float(t.ppf(0.5 + level / 2.0, nu))
        except Exception:  # pragma: no cover - scipy always present here
            return 2.0

    def expanded_uncertainty(self, level: float = 0.95) -> float:
        return self.coverage_factor(level) * self.combined_standard_uncertainty

    @property
    def relative_expanded(self) -> float:
        u = self.expanded_uncertainty()
        return u / abs(self.nominal_value) if self.nominal_value else math.nan

    def table(self, level: float = 0.95) -> str:
        rows = [
            f"GUM budget for {self.measurand} = {self.nominal_value:.6g} {self.unit}".rstrip(),
            f"{'component':<34}{'kind':>5}{'u_i·c_i':>14}{'dof':>8}",
            "-" * 61,
        ]
        for c in self.components:
            dof = "inf" if not math.isfinite(c.dof) else f"{c.dof:.0f}"
            rows.append(f"{c.name:<34}{c.kind:>5}{c.contribution:>14.4g}{dof:>8}")
        uc = self.combined_standard_uncertainty
        k = self.coverage_factor(level)
        rows += [
            "-" * 61,
            f"{'combined standard uncertainty u_c':<34}{'':>5}{uc:>14.4g}",
            f"effective dof = {self.effective_dof:.1f}   k({level:.0%}) = {k:.3f}   "
            f"U = {self.expanded_uncertainty(level):.4g} {self.unit}".rstrip(),
        ]
        return "\n".join(rows)


def coaxial_probe_permittivity_budget(
    nominal_eps: float,
    *,
    type_a_std: float,
    type_a_dof: float,
    fit_std: float,
    calibration_relative: float = 0.02,
    temperature_sensitivity: float = 0.0,
    temperature_half_width_c: float = 0.0,
    input_inversion_relative: float = 0.0,
) -> GUMBudget:
    """Default coaxial-probe permittivity budget enumerating the standard contributors.

    Components: Type A repeatability, model-fit (parameter) uncertainty, probe-calibration (Type B
    relative), temperature, and — strongly encouraged — an explicit input/inversion uncertainty
    (the 'trust the probe software ±X %' injection).
    """
    comps: list[UncertaintyComponent] = [
        UncertaintyComponent.type_a("repeatability (Type A)", type_a_std, type_a_dof),
        UncertaintyComponent("model-fit (parameter) uncertainty", fit_std, kind="B"),
        UncertaintyComponent.relative_input(
            "probe calibration", calibration_relative, nominal_eps, note="probe-calibration Type B"
        ),
    ]
    if temperature_half_width_c > 0 and temperature_sensitivity != 0:
        comps.append(
            UncertaintyComponent.rectangular(
                "temperature",
                temperature_half_width_c,
                sensitivity=temperature_sensitivity,
                note="±half-width on T × dε/dT",
            )
        )
    if input_inversion_relative > 0:
        comps.append(
            UncertaintyComponent.relative_input(
                "input/inversion (probe software)", input_inversion_relative, nominal_eps
            )
        )
    return GUMBudget("ε'", nominal_eps, tuple(comps), unit="")
