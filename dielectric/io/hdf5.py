"""Optional HDF5 read/write for spectra (requires the ``hdf5`` extra: ``pip install .[hdf5]``)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from ..spectrum import Spectrum, SpectrumMetadata


def _require_h5py() -> object:
    try:
        import h5py
    except ImportError as exc:  # pragma: no cover - exercised only without the optional dep
        raise ImportError(
            "HDF5 support needs h5py; install with `pip install dielectric[hdf5]`."
        ) from exc
    return h5py


def save_hdf5(spectrum: Spectrum, path: str | Path) -> None:
    h5py = _require_h5py()
    with h5py.File(str(path), "w") as fh:  # type: ignore[attr-defined]
        fh.create_dataset("frequency_hz", data=spectrum.frequency_hz)
        fh.create_dataset("epsilon", data=spectrum.epsilon)
        if spectrum.sem is not None:
            fh.create_dataset("sem", data=spectrum.sem)
        if spectrum.metadata.source:
            fh.attrs["source"] = spectrum.metadata.source
        if spectrum.metadata.temperature_c is not None:
            fh.attrs["temperature_c"] = spectrum.metadata.temperature_c


def load_hdf5(path: str | Path) -> Spectrum:
    h5py = _require_h5py()
    with h5py.File(str(path), "r") as fh:  # type: ignore[attr-defined]
        f = np.asarray(fh["frequency_hz"], dtype=np.float64)
        eps = np.asarray(fh["epsilon"], dtype=np.complex128)
        sem = np.asarray(fh["sem"], dtype=np.complex128) if "sem" in fh else None
        meta = SpectrumMetadata(
            source=fh.attrs.get("source", str(Path(path).name)),
            temperature_c=fh.attrs.get("temperature_c"),
        )
    return Spectrum(f, eps, sem=sem, metadata=meta)
