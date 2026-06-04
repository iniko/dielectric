"""Uncertainty quantification: Type A statistics, Monte Carlo, and a GUM budget engine."""

from __future__ import annotations

from .typea import TypeAResult, combine_repeats

__all__ = [
    "TypeAResult",
    "combine_repeats",
]
