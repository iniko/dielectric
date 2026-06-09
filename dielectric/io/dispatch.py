"""Format-auto-detecting loader — the vendor-neutral entry point.

:func:`load_any` inspects a file's extension and content and routes it to the right reader
(Touchstone, HDF5, or delimited text). For the Agilent/Keysight 85070 CSV layout it preserves the
*exact* behaviour of :func:`load_agilent_85070` (same column layout, same defaults) so existing data
loads byte-for-byte as before — while additionally lifting the instrument-identification header
(vendor, model, serial, firmware, acquisition date) into ``SpectrumMetadata.extra`` instead of
discarding it. The detected format is recorded in ``metadata.extra["detected_format"]`` so callers
can surface it without re-sniffing.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from ..spectrum import Spectrum
from .csv_loader import load_csv
from .hdf5 import load_hdf5
from .touchstone import load_touchstone

_TOUCHSTONE_EXT = {".s1p", ".s2p", ".snp"}
_HDF5_EXT = {".h5", ".hdf5", ".he5"}

# Lines in an 85070 export's instrument header, in file order: software banner, then a comma row
# ``<vendor>,<model>,<serial>,<firmware>``, optional Title/Sub Title, then ``Date:,"..."``.
_VENDOR_TOKENS = ("agilent", "keysight", "technologies")
_INSTRUMENT_KEYS = (
    "instrument_vendor",
    "instrument_model",
    "instrument_serial",
    "instrument_firmware",
)


def _parse_instrument_header(lines: list[str]) -> dict[str, str]:
    """Best-effort lift of the 85070 instrument-identification header into metadata keys.

    Only keys that are confidently present are returned, so a generic (non-Agilent) CSV yields
    ``{}`` and is reported as a plain ``"csv"``.
    """
    meta: dict[str, str] = {}
    for raw in lines[:8]:  # the header sits above the 'frequency,...' column row
        line = raw.strip()
        if not line:
            continue
        low = line.lower()
        if "dielectric probe software" in low:
            meta["instrument_software"] = line
        elif low.startswith("date:"):
            # e.g. ``Date:,"Thursday, July 04, 2019 19:00:35"``
            value = line.split(":", 1)[1].strip().lstrip(",").strip().strip('"')
            if value:
                meta["measurement_date"] = value
        elif "," in line and any(tok in low for tok in _VENDOR_TOKENS):
            parts = [p.strip() for p in line.split(",")]
            for key, part in zip(_INSTRUMENT_KEYS, parts, strict=False):
                if part:
                    meta[key] = part
    return meta


def _tag(spectrum: Spectrum, detected_format: str, extra: dict[str, str] | None = None) -> Spectrum:
    """Return ``spectrum`` with ``detected_format`` (and any ``extra``) merged into its metadata."""
    merged = {**spectrum.metadata.extra, "detected_format": detected_format}
    if extra:
        merged.update(extra)
    return replace(spectrum, metadata=replace(spectrum.metadata, extra=merged))


def load_any(path: str | Path, *, temperature_c: float | None = None) -> Spectrum:
    """Load a complex permittivity spectrum, auto-detecting the file format.

    Dispatch order: HDF5 (by extension) → Touchstone (``.s1p``/``.snp`` or a leading ``#`` option
    line) → delimited text. The text path uses the same column layout and defaults as
    :func:`load_agilent_85070`, so an Agilent export is parsed identically to before; its instrument
    header is additionally captured into ``metadata.extra``. The detected format is recorded in
    ``metadata.extra["detected_format"]`` as ``"hdf5"``, ``"touchstone"``, ``"agilent_csv"``, or
    ``"csv"``.
    """
    path = Path(path)
    suffix = path.suffix.lower()

    if suffix in _HDF5_EXT:
        return _tag(load_hdf5(path), "hdf5")

    lines = path.read_text(errors="replace").splitlines()
    first_meaningful = next(
        (ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("!")), ""
    )
    if suffix in _TOUCHSTONE_EXT or first_meaningful.startswith("#"):
        return _tag(load_touchstone(path, temperature_c=temperature_c), "touchstone")

    # Delimited text. Default column layout == Agilent 85070 (byte-for-byte parity).
    spectrum = load_csv(path, temperature_c=temperature_c)
    header = _parse_instrument_header(lines)
    return _tag(spectrum, "agilent_csv" if header else "csv", header)
