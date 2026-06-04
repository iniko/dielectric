"""Liquid reference dielectrics: pure water, saline (any molarity), seawater, alcohols.

Water (Kaatze 1989) is HIGH confidence (textbook-solid). Saline/seawater/alcohol parameters use
simplified, documented temperature- and concentration-dependent approximations of the
Stogryn/Peyman/NPL models and are flagged VERIFY: good for probe-validation comparison, but confirm
coefficients against the primary sources before citing absolute numbers.
"""

from __future__ import annotations

from ..models.debye import Debye
from ..models.multipole import MultiPoleRelaxation
from ..models.provenance import Confidence, Provenance
from .materials import ReferenceMaterial

_BAND = (1.0e8, 2.5e10)

KAATZE_1989 = Provenance(
    authors="Kaatze, U.",
    year=1989,
    title="Complex permittivity of water as a function of frequency and temperature",
    source="Journal of Chemical & Engineering Data 34, 371",
    doi="10.1021/je00058a001",
    confidence=Confidence.HIGH,
)
STOGRYN_PEYMAN = Provenance(
    authors="Stogryn, A.; Peyman, A., Gabriel, C., Grant, E. H.",
    year=2007,
    title="Saline (NaCl) permittivity: Debye relaxation + ionic conductivity (simplified model)",
    source="after Stogryn (1971) IEEE TMTT 19, 733; Peyman et al. (2007) Bioelectromagnetics 28",
    doi="10.1002/bem.20271",
    confidence=Confidence.VERIFY,
    note="Simplified ε_s(N), τ(T), σ(N,T) approximations; confirm against the primary polynomials.",
)
KLEIN_SWIFT = Provenance(
    authors="Klein, L. A., Swift, C. T.",
    year=1977,
    title="An improved model for the dielectric constant of sea water at microwave frequencies",
    source="IEEE Transactions on Antennas and Propagation 25, 104",
    doi="10.1109/TAP.1977.1141539",
    confidence=Confidence.VERIFY,
)
NPL_MAT23 = Provenance(
    authors="Gregory, A. P., Clarke, R. N.",
    year=2012,
    title="Tables of the complex permittivity of dielectric reference liquids up to 5 GHz",
    source="NPL Report MAT 23 (Crown copyright, freely available)",
    confidence=Confidence.VERIFY,
    note="Alcohols are multi-Debye; embedded as a single dominant relaxation — confirm vs MAT 23.",
)


def _water_params(temperature_c: float) -> tuple[float, float, float]:
    """Kaatze water (ε_s, ε∞, τ[s]) with simple linear T-corrections around 25 °C."""
    eps_s = 78.36 - 0.36 * (temperature_c - 25.0)
    eps_inf = 5.2
    tau = 8.27e-12 - 0.43e-12 * (temperature_c - 25.0)
    return eps_s, eps_inf, max(tau, 1e-12)


def water(temperature_c: float = 25.0) -> ReferenceMaterial:
    """Pure water (Kaatze 1989), single Debye. HIGH confidence at 25 °C."""
    eps_s, eps_inf, tau = _water_params(temperature_c)
    model = Debye(eps_inf, eps_s - eps_inf, tau)
    return ReferenceMaterial(
        name="water",
        model=model,
        provenance=KAATZE_1989,
        temperature_c=temperature_c,
        material_class="liquid",
        confidence=Confidence.HIGH,
        valid_band_hz=_BAND,
        aliases=("pure_water", "deionized_water"),
    )


def saline(molarity: float = 0.154, temperature_c: float = 25.0) -> ReferenceMaterial:
    """NaCl saline at the given molarity [mol/L] and temperature.

    Default 0.154 mol/L ≈ 0.9 % physiological saline. Built as water's Debye relaxation (with a
    salinity depression of ε_s) plus an ionic DC conductivity. Any molarity is accepted.
    """
    eps_s_w, eps_inf, tau = _water_params(temperature_c)
    eps_s = max(eps_s_w - 17.0 * molarity, eps_inf + 1.0)  # salinity depresses static permittivity
    sigma_25 = 10.5 * molarity * (2.718281828 ** (-0.4 * molarity))  # S/m at 25 °C (approx)
    sigma = sigma_25 * (1.0 + 0.02 * (temperature_c - 25.0))  # ~+2 %/°C
    model = MultiPoleRelaxation(eps_inf, ((eps_s - eps_inf, tau, 0.0),), sigma_dc=sigma)
    pct = molarity / 0.154 * 0.9
    return ReferenceMaterial(
        name=f"saline_{molarity:g}M",
        model=model,
        provenance=STOGRYN_PEYMAN,
        temperature_c=temperature_c,
        material_class="liquid",
        confidence=Confidence.VERIFY,
        valid_band_hz=_BAND,
        aliases=("saline", f"NaCl_{pct:.2g}pct"),
    )


def seawater(salinity_psu: float = 35.0, temperature_c: float = 20.0) -> ReferenceMaterial:
    """Standard seawater (Klein-Swift style approximation)."""
    molarity = salinity_psu / 58.44  # g/L NaCl-equivalent → mol/L (rough)
    mat = saline(molarity, temperature_c)
    return ReferenceMaterial(
        name=f"seawater_{salinity_psu:g}psu",
        model=mat.model,
        provenance=KLEIN_SWIFT,
        temperature_c=temperature_c,
        material_class="liquid",
        confidence=Confidence.VERIFY,
        valid_band_hz=_BAND,
        aliases=("seawater",),
    )


def methanol(temperature_c: float = 25.0) -> ReferenceMaterial:
    """Methanol, dominant Debye relaxation (NPL MAT 23 approximation, 25 °C)."""
    model = Debye(5.6, 32.6 - 5.6, 51e-12)
    return ReferenceMaterial(
        name="methanol", model=model, provenance=NPL_MAT23, temperature_c=temperature_c,
        material_class="liquid", confidence=Confidence.VERIFY, valid_band_hz=_BAND,
    )


def ethanol(temperature_c: float = 25.0) -> ReferenceMaterial:
    """Ethanol, dominant Debye relaxation (NPL MAT 23 approximation, 25 °C)."""
    model = Debye(4.2, 24.3 - 4.2, 163e-12)
    return ReferenceMaterial(
        name="ethanol", model=model, provenance=NPL_MAT23, temperature_c=temperature_c,
        material_class="liquid", confidence=Confidence.VERIFY, valid_band_hz=_BAND,
    )


def all_liquids() -> dict[str, ReferenceMaterial]:
    """The default liquid reference materials (at their default conditions)."""
    mats = [water(), saline(), seawater(), methanol(), ethanol()]
    return {m.name: m for m in mats}
