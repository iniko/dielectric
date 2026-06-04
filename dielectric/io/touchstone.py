"""Minimal Touchstone (.s1p) reader for single-port complex spectra.

Touchstone is usually raw S-parameters, which are out of this toolkit's scope. This reader is for
exports that store the **already-inverted complex permittivity** in Touchstone form: one frequency
column and one complex value per row (RI, MA, or DB format). The complex value is taken as ε* and
converted to the internal convention (Im < 0).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..convention import detect_and_correct_imaginary
from ..spectrum import Spectrum, SpectrumMetadata
from ..units import FrequencyUnit, to_hz

_FREQ_UNITS = {
    "hz": FrequencyUnit.HZ,
    "khz": FrequencyUnit.KHZ,
    "mhz": FrequencyUnit.MHZ,
    "ghz": FrequencyUnit.GHZ,
}


def load_touchstone(path: str | Path, *, temperature_c: float | None = None) -> Spectrum:
    path = Path(path)
    unit = FrequencyUnit.HZ
    fmt = "ri"
    freqs: list[float] = []
    a_vals: list[float] = []
    b_vals: list[float] = []
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("!"):
            continue
        if line.startswith("#"):
            tokens = line[1:].lower().split()
            for tok in tokens:
                if tok in _FREQ_UNITS:
                    unit = _FREQ_UNITS[tok]
                if tok in ("ri", "ma", "db"):
                    fmt = tok
            continue
        parts = line.split()
        if len(parts) < 3:
            continue
        freqs.append(float(parts[0]))
        a_vals.append(float(parts[1]))
        b_vals.append(float(parts[2]))

    if len(freqs) < 2:
        raise ValueError(f"{path.name}: fewer than 2 data rows parsed")
    f_hz = to_hz(np.array(freqs), unit)
    a = np.array(a_vals)
    b = np.array(b_vals)
    if fmt == "ri":
        eps_re, eps_im_raw = a, b
    elif fmt == "ma":
        eps_re, eps_im_raw = a * np.cos(np.deg2rad(b)), a * np.sin(np.deg2rad(b))
    else:  # db
        mag = 10.0 ** (a / 20.0)
        eps_re, eps_im_raw = mag * np.cos(np.deg2rad(b)), mag * np.sin(np.deg2rad(b))

    eps_im, _ = detect_and_correct_imaginary(eps_im_raw, source=path.name)
    meta = SpectrumMetadata(source=path.name, temperature_c=temperature_c)
    return Spectrum(f_hz, eps_re + 1j * eps_im, metadata=meta)
