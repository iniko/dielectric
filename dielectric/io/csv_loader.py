"""CSV loaders for complex permittivity spectra.

A parameterized generic loader (column indices, header detection, comment markers, units) handles
arbitrary vendor exports; :func:`load_agilent_85070` is a thin wrapper with the right defaults for
Keysight/Agilent 85070 dielectric-probe exports.

Units are made explicit at this boundary, and the sign convention is detected here (and only here):
positive-loss data is negated to the internal ``e^{jωt}`` convention with a ``ConventionWarning``.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..convention import detect_and_correct_imaginary
from ..spectrum import Spectrum, SpectrumMetadata
from ..units import (
    FrequencyUnit,
    PermittivityKind,
    to_hz,
    to_relative_permittivity,
)


def _find_data_start(lines: list[str], header_contains: str, comment: str | None) -> int:
    """Index of the first data row: the line after one containing ``header_contains`` (else the
    first line that parses as a number)."""
    if header_contains:
        for i, line in enumerate(lines):
            if header_contains.lower() in line.lower():
                return i + 1
    for i, line in enumerate(lines):
        if comment and line.lstrip().startswith(comment):
            continue
        first = line.split(",")[0].strip()
        try:
            float(first)
            return i
        except ValueError:
            continue
    raise ValueError("could not locate the start of numeric data in the file")


def load_csv(
    path: str | Path,
    *,
    freq_col: int = 0,
    eps_real_col: int = 1,
    eps_imag_col: int = 2,
    delimiter: str = ",",
    header_contains: str = "frequency",
    comment: str | None = None,
    frequency_unit: FrequencyUnit = FrequencyUnit.HZ,
    permittivity_kind: PermittivityKind = PermittivityKind.RELATIVE,
    temperature_c: float | None = None,
) -> Spectrum:
    """Load a complex permittivity spectrum from a delimited text file.

    The loss column may be stored in either sign convention; it is detected and converted to the
    internal convention (Im < 0) here, warning if a positive-loss column was negated.
    """
    path = Path(path)
    lines = path.read_text().splitlines()
    start = _find_data_start(lines, header_contains, comment)

    freqs: list[float] = []
    re_vals: list[float] = []
    im_vals: list[float] = []
    for line in lines[start:]:
        stripped = line.strip()
        if not stripped or (comment and stripped.startswith(comment)):
            continue
        parts = [p.strip() for p in stripped.split(delimiter)]
        try:
            freqs.append(float(parts[freq_col]))
            re_vals.append(float(parts[eps_real_col]))
            im_vals.append(float(parts[eps_imag_col]))
        except (ValueError, IndexError):
            continue  # tolerate trailing blank/garbage rows

    if len(freqs) < 2:
        raise ValueError(f"{path.name}: fewer than 2 data rows parsed")

    f_hz = to_hz(np.array(freqs), frequency_unit)
    eps_re = to_relative_permittivity(np.array(re_vals), permittivity_kind)
    eps_im_raw = to_relative_permittivity(np.array(im_vals), permittivity_kind)
    eps_im, _warning = detect_and_correct_imaginary(eps_im_raw, source=path.name)

    epsilon = eps_re + 1j * eps_im
    metadata = SpectrumMetadata(source=path.name, temperature_c=temperature_c)
    return Spectrum(f_hz, epsilon, metadata=metadata)


def load_agilent_85070(
    path: str | Path,
    *,
    temperature_c: float | None = None,
) -> Spectrum:
    """Load a Keysight/Agilent 85070 dielectric-probe export.

    Format: instrument-metadata header, a blank line, a ``frequency,Tr 1  Data(e'),(e'')`` column
    header, then frequency [Hz], ε', and positive loss ε''. The positive loss is negated to the
    internal convention with a :class:`dielectric.convention.ConventionWarning`.
    """
    return load_csv(
        path,
        freq_col=0,
        eps_real_col=1,
        eps_imag_col=2,
        header_contains="frequency",
        frequency_unit=FrequencyUnit.HZ,
        permittivity_kind=PermittivityKind.RELATIVE,
        temperature_c=temperature_c,
    )
