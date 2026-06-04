"""Network-gated refresh of the reference database from authoritative open sources.

This module *documents* (and would perform, when network access is available) the refresh that
replaces the embedded VERIFY-confidence snapshot with values read directly from the authoritative
open databases, promoting them to HIGH confidence. It is intentionally **not executed** in this
build (the snapshot was compiled offline); it records exactly where the trustworthy values live.

Authoritative open sources:

* **Biological tissue** — IFAC-CNR "Dielectric Properties of Body Tissues"
  (``niremf.ifac.cnr.it/tissprop/``, Gabriel report Appendix C) and the IT'IS Foundation Tissue
  Properties database (``itis.swiss``, CC BY) — the full 4-Cole-Cole parameter set.
* **Calibration liquids** — NPL Report MAT 23 (Gregory & Clarke, 2012), Crown copyright, free.
* **Water** — Kaatze (1989) tabulated ε_s, ε∞, τ(T).
"""

from __future__ import annotations

IFAC_TISSUE_URL = "http://niremf.ifac.cnr.it/tissprop/htmlclie/htmlclie.php"
ITIS_DB_URL = "https://itis.swiss/virtual-population/tissue-properties/database/"
NPL_MAT23_REF = "NPL Report MAT 23 (Gregory & Clarke, 2012)"


def refresh_from_sources() -> None:  # pragma: no cover - network-gated, not executed in this build
    """Placeholder for the online refresh. Raises to make the offline status explicit."""
    raise NotImplementedError(
        "Online refresh is not enabled in this build. When network access is available, fetch the "
        f"4-Cole-Cole tissue table from {IFAC_TISSUE_URL} (or {ITIS_DB_URL}, CC BY) and the "
        f"calibration-liquid tables from {NPL_MAT23_REF}, then replace the embedded VERIFY values "
        "and set their Confidence to HIGH."
    )
