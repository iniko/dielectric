"""Uncertainty-driven significant-figure formatting (GUM / PDG rounding).

Never report a bare parameter: the uncertainty sets the number of significant figures. The number of
significant figures kept on the uncertainty follows the PDG rule (1 or 2 figures depending on its
leading digits), and the value is rounded to the same decimal place.
"""

from __future__ import annotations

import math


def _uncertainty_sig_figs(uncertainty: float) -> tuple[int, int]:
    """Return ``(n_sig_figs, exponent)`` for the uncertainty per the PDG rule."""
    exp_u = math.floor(math.log10(abs(uncertainty)))
    lead3 = round(abs(uncertainty) / 10.0 ** (exp_u - 2))  # 3 significant digits, 100–999
    if lead3 >= 950:  # rounds up to the next power of ten
        exp_u += 1
        return 2, exp_u
    if 100 <= lead3 <= 354:
        return 2, exp_u
    return 1, exp_u  # 355–949


def round_to_decimal(x: float, decimals: int) -> float:
    return round(x, decimals)


def format_measurement(value: float, uncertainty: float, *, unit: str = "") -> str:
    """Format ``value ± uncertainty`` with the uncertainty setting the significant figures.

    Examples
    --------
    ``format_measurement(4.234, 0.31)`` → ``"4.2 ± 0.3"``;
    ``format_measurement(8.01e-12, 3.0e-13)`` → ``"(8.01 ± 0.03)e-12"`` (a common power of ten).
    """
    suffix = f" {unit}" if unit else ""
    if not math.isfinite(value):
        return f"{value}{suffix}"
    if not math.isfinite(uncertainty) or uncertainty <= 0:
        return f"{value:.4g}{suffix}"

    n_sig, exp_u = _uncertainty_sig_figs(uncertainty)
    decimals = -(exp_u - (n_sig - 1))  # decimal place to round both to
    u_round = round(uncertainty, decimals)
    v_round = round(value, decimals)

    exp_v = math.floor(math.log10(abs(v_round))) if v_round != 0 else 0
    if exp_v <= -4 or exp_v >= 5:
        # Scientific notation with a common power of ten taken from the value.
        factor = 10.0**exp_v
        md = max((n_sig - 1) - (exp_u - exp_v), 0)
        vm, um = v_round / factor, u_round / factor
        return f"({vm:.{md}f} ± {um:.{md}f})e{exp_v:+d}{suffix}"

    dec = max(decimals, 0)
    return f"{v_round:.{dec}f} ± {u_round:.{dec}f}{suffix}"


def format_param(name: str, value: float, uncertainty: float) -> str:
    """``"name = value ± uncertainty"`` for a fitted parameter."""
    return f"{name} = {format_measurement(value, uncertainty)}"
