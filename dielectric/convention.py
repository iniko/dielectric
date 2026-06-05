"""Sign-convention detection and correction (the single place it happens).

Engineering ``e^{jωt}`` convention: ``ε* = ε' + j·Im(ε*)`` with **Im(ε*) < 0 for lossy media**.
Internally the toolkit always stores ε* with a *negative* imaginary part.

Vendor probe software (e.g. Agilent/Keysight 85070) exports the loss column as a **positive**
number (the physics ε'' = -Im(ε*) magnitude). On load we must negate it — but we **warn rather than
silently "fix"**, because a stray sign is exactly the kind of thing a student must see and confirm,
not have quietly altered (memory: data-and-sign-convention).
"""

from __future__ import annotations

import warnings

import numpy as np

from .units import FloatArray


class ConventionWarning(UserWarning):
    """Raised when input loss data appears to use the positive-loss (physics) convention."""


def detect_and_correct_imaginary(
    imag_column: FloatArray,
    *,
    source: str = "input",
) -> tuple[FloatArray, ConventionWarning | None]:
    """Return ``(internal_imag, warning_or_None)`` for a raw imaginary/loss column.

    Decision rule (passive media never have net gain, so the median sign is unambiguous):

    * ``median(Im) > 0`` → source uses the positive-loss/physics convention → **negate once** and
      return a :class:`ConventionWarning` (the warning is also emitted via :mod:`warnings`).
    * ``median(Im) < 0`` → already internal convention → pass through, no warning.
    * ``median(Im) ≈ 0`` → effectively lossless → pass through with no warning.

    This is the *only* function in the toolkit that flips the sign of loss data.
    """
    arr = np.asarray(imag_column, dtype=np.float64)
    median = float(np.median(arr))

    if median > 0.0:
        msg = (
            f"{source}: loss column has positive median Im(ε*) = {median:.4g}, i.e. the "
            "positive-loss (physics) convention. Negating once to the internal e^{jωt} "
            "convention (Im(ε*) < 0 for lossy media). Verify this matches your instrument export."
        )
        warning = ConventionWarning(msg)
        warnings.warn(warning, stacklevel=2)
        return -arr, warning

    return arr, None
