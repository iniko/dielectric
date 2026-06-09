# Vendor-Neutral Dielectric Data Model — Architecture Review & Roadmap

> Status: living architecture document. The **Quick Wins** in §7 are **implemented**; the
> Medium- and Long-term items are proposals. Last reviewed 2026-06-09.

## Why this document exists

The Load step used to read *"Each batch is one sample's repeat CSVs (Agilent 85070 exports)."* That
sentence was the visible tip of a deeper coupling: the **backend hardcoded `load_agilent_85070`** as
the only importer, the **API schemas captured almost no measurement metadata** (a sample name and one
temperature), and the **UI copy assumed CSV-only, single-vendor** input. The toolkit's stated goal —
support data from many VNAs, probes, fixtures, and research groups, and be citable and reproducible
for PhD-grade and publication work — was blocked not by the core library but by the layers above it.

**The finding that shapes everything here:** the `dielectric/` library was *already* mostly
vendor-neutral. It ships `load_csv` (parameterized columns/units), `load_touchstone`, `load_hdf5`;
`Spectrum` operates purely on `(frequency_hz, ε*)`; `SpectrumMetadata` has an `extra: dict[str,str]`
escape hatch; `CampaignMetadata` already has `operator`/`date`/`notes`/`extra`. The lock-in lived in
`backend/app/services.py`, `backend/app/schemas.py`, and `frontend/.../LoadStep.tsx`. Generalization
is therefore mostly an **exposure + metadata-richness** problem, not a rewrite.

---

## 1 — Architectural critique (opinionated)

**The library is the asset; the backend was the liability.** The right mental model is "the API is
*narrower* than the library it wraps." `services._load_spectrum` threw away three working loaders and
pinned everything to Agilent. The fix is to widen the API to the library's existing surface, not to
add new physics. (Done — see §7.)

**Metadata is the real gap, not file formats.** Even if every vendor's file parsed perfectly, the
system still could not produce a Porter-2018-compliant record, because the *data model has nowhere to
put* instrument identity, probe geometry, calibration provenance, sample handling, or environment.
Vendor-neutrality and metadata-completeness are the same project: a `Measurement` must know *what made
it*, not just *what numbers came out*.

**Provenance was silently discarded at the door.** The Agilent CSV header carries instrument model
(`E8362B`), serial, firmware, and timestamp; `load_agilent_85070` read past all of it. For a
reproducibility-first tool aimed at PhD students, discarding the one place the instrument identifies
itself was the most ironic failure in the codebase. (Quick Win now lifts it into `metadata.extra`.)

**The `extra` dict is an unmanaged junk drawer.** `SpectrumMetadata.extra` / `CampaignMetadata.extra`
are free-form `dict[str,str]`. They are the *right* escape hatch but the *wrong* permanent home for
first-class fields like instrument or operator — untyped, unvalidated, unreportable, unsearchable.
Quick Wins use `extra`; the canonical model (§5) must promote these to typed fields.

**Single global temperature is a modelling error, not just a limitation.** `temperature_c` is one
scalar per set/campaign. Dielectric work is temperature-dependent per measurement; references are
temperature-specific. Fine for h02 (a 25 °C decision), wrong as a permanent shape.

**Verdict:** the architecture is *salvageable and well-layered* — the ABC-based model design and the
thin-service principle are good. The redesign is additive widening + a metadata spine, not a rewrite.
**Grade: B− for design, D for metadata coverage.**

---

## 2 — Vendor-specific assumption inventory

| # | Assumption | Location | Severity | Generalization | Status |
|---|---|---|---|---|---|
| 1 | Only `load_agilent_85070` is ever called | `services.py:_load_spectrum` | **Blocker** | Dispatch on detected format → existing loaders | ✅ Quick Win |
| 2 | Frequency assumed Hz; ε relative; positive-loss | `csv_loader.py` Agilent defaults | Medium | `load_csv` already parameterizes these | ◑ available, not surfaced |
| 3 | Agilent header (model/serial/fw/date) discarded | `csv_loader.py` | High | Parse header → `extra` → typed `Instrument` | ✅ Quick Win (→`extra`) |
| 4 | UI names "Agilent 85070 exports", `.csv`-only | `LoadStep.tsx` | **Visible** | Reword + widen `accept` | ✅ Quick Win |
| 5 | Upload form has no format/instrument/operator fields | `main.py`, `api.ts` | High | Optional `operator`/`instrument`/`date` fields | ✅ Quick Win |
| 6 | Sign convention only *detects*; never records what it found | `convention.py` | Medium | Record detected convention + vendor into metadata | ◑ todo |
| 7 | `SetSummary` carries no instrument/probe/calibration | `schemas.py` | High | Typed metadata block | ◑ `instrument`/`detected_format` added |
| 8 | `CampaignCreate` ignores existing `operator`/`date` | `services.build_campaign` | Medium | Populate `CampaignMetadata` | ✅ Quick Win |
| 9 | GUM budget hardcodes 2% calibration, assumes coax | `uncertainty/gum.py` | Medium | Drive Type B from a `Calibration`/`Probe` record | ✗ Medium-term |
| 10 | Repeats grouped purely by upload batch; no cross-check | `campaign.py:from_glob` | Low | Validate instrument/band consistency | ✗ Medium-term |
| 11 | Validation references limited to built-in DB | `services.py` | Low | Allow user-uploaded reference spectra | ✗ Long-term |
| 12 | In-memory store; no instrument/calibration registry | `store.py` | Long-term | Persistence layer | ✗ design only (§5) |

---

## 3 — Porter et al. (2018) compliance gap analysis

*Porter et al. (2018) — "Minimum Information for Dielectric Measurements of Biological Tissues"
(**MINDER**), a minimum-reporting framework for repeatable, reusable dielectric tissue spectroscopy.*
Statuses:
✅ captured · ◑ partial · ❌ missing · ⛔ impossible to represent today.

| Porter MINDER category | Required field | Status | Where today / why not |
|---|---|---|---|
| **Sample** | Tissue/material type | ◑ | `name` is a free string; no controlled material class on a measurement |
| | Species / origin | ❌ | no field |
| | Sample state (in/ex vivo, excised) | ❌ | no field |
| | Time post-excision | ❌ | no field |
| | Handling / preservation | ❌ | no field |
| | Sample temperature | ✅ | `temperature_c` (single scalar) |
| | Hydration / composition | ❌ | no field |
| **Subject** | Subject ID / demographics | ⛔ | no entity exists |
| | Pathology / condition | ◑ | only implied via Compare batch naming |
| **Instrument** | VNA make/model/serial | ◑ | lifted from Agilent header into `extra` (Quick Win); not typed/required |
| | Firmware/software version | ◑ | lifted into `extra` for Agilent files |
| | Measurement technique (probe/coax/waveguide) | ❌ | assumed open-ended coax |
| | Frequency range / points | ◑ | `band_ghz` captured; n-points implied, not reported |
| | Probe geometry/aperture | ❌ | no field; GUM assumes coax |
| **Calibration** | Method (OSL/TRL/…) | ❌ | no field |
| | Reference liquids/standards | ◑ | validation references exist but aren't tied to *the cal* |
| | Calibration date / drift checks | ❌ | no field |
| | De-embedding / inversion model | ◑ | sign-convention correction recorded as a warning only |
| **Environment** | Ambient T / humidity / pressure | ❌ | no field |
| **Operator** | Operator identity | ◑ | optional upload field → `extra`; `CampaignMetadata.operator` now wired |
| | Date/time of measurement | ◑ | lifted from Agilent header + optional upload field |
| **Uncertainty** | Type A repeatability | ✅ | `combine_repeats` SEM + z-scores + disclosure |
| | Type B (cal/probe/inversion) | ◑ | GUM budget exists but hardcoded 2%, not traceable |
| | Combined/expanded uncertainty (k) | ◑ | GUM supports it; not auto-attached to results |
| **Reproducibility** | Methods disclosure | ✅ | `methods_paragraph` + `ReproducibilityManifest` |
| | Raw data availability | ◑ | hash only; raw not bundled in export |
| | References for reference data | ✅ | `Provenance` with DOI/confidence on reference models |

**Score (post-Quick-Win): ~4 ✅ / ~13 ◑ / ~7 ❌ / 1 ⛔.** Strong on the *statistics of repeats*
(genuinely better than most published work), still weak on the *physical provenance of the
measurement*. The single biggest remaining lever is a typed `Instrument` + `Calibration` + `Sample`
spine (§4–§5).

---

## 4 — Standards-compliance architecture (the metadata spine)

Introduce a **metadata spine** the whole pipeline threads, layered so each Porter category maps to a
typed home (not `extra`):

- **`Sample`** — id, material_class (controlled vocab), species/origin, state, time-post-excision,
  handling, hydration, per-sample temperature, notes.
- **`Instrument`** — vendor, model, serial, firmware/software; `measurement_technique` enum
  (`open_coax_probe | coax_line | waveguide | capacitive | four_electrode | simulated`); frequency
  range/points.
- **`Probe` / `Fixture`** — type, geometry (aperture, dimensions), connector, calibration ref plane.
- **`Calibration`** — method enum, reference standards (+ provenance), date, drift checks,
  inversion/de-embedding model, detected sign convention.
- **`Environment`** — ambient T, humidity, pressure.
- **`Operator` / provenance** — identity, date/time (ISO), lab/institution, project.
- **`UncertaintyBudget`** — Type A (auto from repeats), Type B sourced from `Calibration`/`Probe`,
  combined + expanded (k), per-frequency.
- **Repeatability/reproducibility** — already strong; surface n-points, frequency coverage, and a
  cross-repeat instrument-consistency check.
- **Literature references** — extend `Provenance` (already DOI/confidence-flagged) to attach to
  samples and calibration standards, not just reference models.

Each is optional + back-compat: absent → today's behaviour; present → richer report + closes Porter
gaps. The report (`methods_paragraph`, `ReproducibilityManifest`) becomes the compliance surface —
extend it to emit a **MINDER checklist** showing captured/missing fields so a student sees exactly
what their record is missing before publication.

---

## 5 — Future-proof canonical data model (FAIR)

**Canonical entity graph:**
`Dataset` → `Campaign` → `MeasurementSet` (repeats of one `Sample` on one `Instrument`+`Calibration`)
→ `Measurement` (one spectrum) → frequency-dependent `properties`.

**JSON schema sketch** (the canonical record; vendor formats import *into* this):
```jsonc
{
  "schema_version": "1.0.0",
  "dataset": { "id": "uuid", "title": "...", "license": "CC-BY-4.0",
               "fair": { "doi": null, "persistent_id": null } },
  "sample": { "id": "h02", "material_class": "liver_tissue", "species": "porcine",
              "state": "ex_vivo", "time_post_excision_min": 30, "handling": "...",
              "temperature_c": 25.0 },
  "instrument": { "vendor": "Keysight", "model": "E8362B", "serial": "MY43021411",
                  "firmware": "A.07.50.67", "technique": "open_coax_probe",
                  "freq_range_hz": [2e8, 2e10], "n_points": 201 },
  "probe": { "type": "open_ended_coax", "aperture_mm": 2.2, "connector": "APC-3.5" },
  "calibration": { "method": "open_short_load", "standards": ["air","short","water_25C"],
                   "date": "2019-07-04", "inversion_model": "...",
                   "sign_convention": "engineering_ejwt", "loss_sign_in_file": "positive" },
  "environment": { "ambient_temp_c": 22.0, "humidity_pct": 45 },
  "provenance": { "operator": "...", "datetime": "2019-07-04T19:00:35", "lab": "...",
                  "references": [ {"doi": "...", "confidence": "HIGH"} ] },
  "measurements": [ { "repeat": 1, "source_file": "h02s19m05.csv", "content_hash": "sha256:...",
                      "frequency_hz": [...], "eps_real": [...], "eps_imag": [...] } ],
  "uncertainty": { "type_a": {...}, "type_b": [...], "coverage_factor_k": 2 }
}
```

**Backend model recommendation:** keep frozen dataclasses in the library (immutability + provenance
suit it); add Pydantic mirrors in `schemas.py`. Promote `extra`-dict fields to typed optional
attributes once stabilized.

**Database recommendation (design only):** in-memory dict → **SQLite via SQLModel** for single-lab,
**Postgres** for multi-site; store raw spectra as bundled files/HDF5 referenced by hash, metadata in
relational tables. A pure **file-based dataset bundle** (the JSON above + raw files in a zip, à la
Frictionless Data Package) is the lowest-friction FAIR export and the recommended *first* persistence
artifact even before a DB.

**Versioning strategy:** `schema_version` (semver) on every record; an `importers/` plugin registry
keyed by `(vendor, format)`; migration functions between schema versions. Never mutate a published
record — append a new version.

**Import/export architecture:** a pluggable **importer** protocol (`detect(file) -> bool`,
`load(file) -> CanonicalRecord`) so a new vendor is a plugin, not a core change. `load_any` (§7) is
the first step toward this registry. Exporters: canonical JSON, Frictionless package, and the
existing PDF/DOCX/HTML report carrying a metadata appendix.

---

## 6 — User-facing wording

| Location | Before | After (shipped) |
|---|---|---|
| Load step intro | "Each **batch** is one sample's repeat CSVs (Agilent 85070 exports)." | "Each **batch** is one sample's repeated measurements — the files from a single instrument/probe setup. CSV (including Agilent/Keysight 85070), Touchstone (.s1p), and HDF5 are supported; the format is auto-detected." |
| Staging dropzone | "Drop {role} CSVs or click to browse" | "Drop {role} files or click to browse" |
| File `accept` | `.csv` | `.csv,.txt,.s1p,.s2p,.snp,.h5,.hdf5` |
| Empty-stage errors | "Stage … CSV first." | "Stage … file first." |
| Budget component | "input/inversion (probe software)" | "data inversion (instrument/probe software)" |
| Load step (new) | — | Optional collapsed "measurement metadata (optional)": *instrument* (auto-detected), *operator*, *date* |
| Batch card | — | Shows detected format + instrument when known |

---

## 7 — Quick Wins (implemented)

**Library** — `dielectric/io/dispatch.py`: new `load_any(path)` auto-detects HDF5 (by extension),
Touchstone (`.s1p`/`.snp` or a leading `#`), else delimited text. The CSV path uses the same column
layout/defaults as `load_agilent_85070`, so an Agilent export loads **byte-for-byte identically**; its
instrument header (vendor/model/serial/firmware/date) is lifted into `metadata.extra`, and
`metadata.extra["detected_format"]` records the format. `io/__init__.py` now exports `load_any`,
`load_hdf5`, `save_hdf5`.

**Backend** — `services._load_spectrum` preserves the upload's extension and calls `load_any`;
`SetSummary` gained `instrument` + `detected_format`; the upload route accepts optional
`operator`/`instrument`/`measurement_date` (threaded into each spectrum's `extra`);
`build_campaign` now populates the previously-ignored `CampaignMetadata.operator`/`date`.

**Frontend** — Load step reworded and `accept` widened; a collapsed optional-metadata disclosure
(instrument/operator/date); the batch card surfaces detected format + instrument; Budget label
generalized.

**Tests** — `tests/test_io_dispatch.py` (Agilent byte-for-byte parity, header lift, generic CSV,
Touchstone by extension and by `#` header, HDF5 round-trip) and backend round-trip tests for
format detection + instrument override.

---

## 8 — Prioritized roadmap

**Quick Wins (done):** loader dispatch + format auto-detect; lift instrument header; optional
operator/instrument/date; vendor-neutral wording; surface format/instrument in the UI.

**Medium-term:** typed `Instrument`/`Sample`/`Calibration`/`Probe` dataclasses promoted out of
`extra`; expose `load_csv` unit/column parameters at the API for arbitrary vendor CSVs; record the
detected sign convention in metadata; drive the GUM Type B budget from a `Calibration`/`Probe` record;
cross-repeat instrument/band consistency check; emit a MINDER checklist in the report.

**Long-term:** persistence layer (SQLite/SQLModel → Postgres) with an instrument/calibration registry;
pluggable importer registry keyed by `(vendor, format)`; user-uploaded reference standards; Frictionless
data-package export with bundled raw data; per-measurement temperature and multi-site dataset support;
full FAIR DOI/persistent-id minting.
