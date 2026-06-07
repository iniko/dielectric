"""TestClient integration tests for the dielectric API (real h02 uploads)."""

from __future__ import annotations

import glob
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.store import STORE

client = TestClient(app)
DATA = Path(__file__).resolve().parents[2] / "data"


def _files(pattern: str, limit: int = 5) -> list[tuple[str, tuple[str, io.BytesIO, str]]]:
    paths = sorted(glob.glob(str(DATA / pattern)))[:limit]
    return [
        ("files", (Path(p).name, io.BytesIO(Path(p).read_bytes()), "text/csv")) for p in paths
    ]


def _upload(pattern: str, role: str, limit: int = 5, **form: str) -> dict:
    resp = client.post(
        "/api/sets",
        files=_files(pattern, limit=limit),
        data={"role": role, "name": role, **form},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_health_and_materials() -> None:
    assert client.get("/api/health").json()["status"] == "ok"
    mats = client.get("/api/materials").json()
    names = {m["name"] for m in mats}
    assert "blood" in names and "water" in names
    assert any(m["confidence"] == "VERIFY" for m in mats)


def test_upload_set_reports_sign_correction_and_quality() -> None:
    summary = _upload("h02s19m*.csv", "measurement")
    assert summary["n_repeats"] == 5
    assert summary["band_ghz"][0] == pytest.approx(0.2, abs=0.01)
    assert summary["sigma_low_s_per_m"] > 0
    assert any("convention" in n for n in summary["notes"])  # positive loss was corrected


def test_full_analysis_flow() -> None:
    meas = _upload("h02s19m*.csv", "measurement", limit=12)  # enough repeats for a stable selection
    val = _upload("h02v*.csv", "validation", limit=12, reference="saline", molarity="0.154")

    campaign = client.post("/api/campaigns", json={
        "measurement_set_ids": [meas["id"]],
        "validation_set_ids": [val["id"]],
        "temperature_c": 25.0,
    }).json()
    cid = campaign["id"]

    analysis = client.post(f"/api/campaigns/{cid}/analyze", json={}).json()
    assert len(analysis["results"]) == 1
    result = analysis["results"][0]
    assert result["chosen_model"] == "Cole-Cole + DC σ"
    # σ_DC recovered ~0.8 S/m
    sigma = next(p for p in result["params"] if p["name"] == "sigma_dc")
    assert sigma["value"] == pytest.approx(0.8, abs=0.15)
    assert result["kk"]["consistent"]
    assert result["closest_materials"][0]["material"] in {"kidney", "muscle", "blood"}
    assert "non-linear least squares" in result["methods_paragraph"]
    # the plot payload is populated
    assert len(result["plot"]["frequency_hz"]) == len(result["plot"]["eps_real"]) > 10
    # the saline validation passes
    assert analysis["validation"]["validated"]

    # degenerate multipole fits are flagged in the ranking
    assert any(r["flag"] == "degenerate" for r in result["ranking"])

    # report download works
    pdf = client.get(f"/api/campaigns/{cid}/report", params={"sample": "measurement", "fmt": "pdf"})
    assert pdf.status_code == 200
    assert pdf.content[:4] == b"%PDF"


def test_override_number_of_poles() -> None:
    meas = _upload("h02s19m*.csv", "measurement")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [meas["id"]], "temperature_c": 25.0,
    }).json()["id"]
    analysis = client.post(f"/api/campaigns/{cid}/analyze", json={"n_poles": 2}).json()
    result = analysis["results"][0]
    assert "MultiPole(N=2)" in result["chosen_model"]
    assert result["overridden"]
    assert not analysis["validation"]["validated"]  # no validation set provided


def test_budget_sandbox() -> None:
    resp = client.post("/api/budget", json={
        "measurand": "ε'", "nominal_value": 58.0, "components": [
            {"name": "repeatability", "standard_uncertainty": 0.67, "dof": 13, "kind": "A"},
            {"name": "calibration", "standard_uncertainty": 1.16, "kind": "B"},
            {"name": "input/inversion", "standard_uncertainty": 1.74, "kind": "B"},
        ],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["combined_standard_uncertainty"] == pytest.approx(2.15, abs=0.1)
    assert body["expanded_uncertainty"] > body["combined_standard_uncertainty"]
    # the input/inversion term is the largest contributor
    top = max(body["contributions"], key=lambda c: c["percent"])
    assert top["name"] == "input/inversion"


def test_errors() -> None:
    assert client.post("/api/campaigns", json={"measurement_set_ids": []}).status_code == 400
    assert client.post("/api/campaigns/nope/analyze", json={}).status_code == 404
    empty_budget = client.post("/api/budget", json={"nominal_value": 1.0, "components": []})
    assert empty_budget.status_code == 400


# -- stepwise UX endpoints ----------------------------------------------------------------------


def _campaign(measure_limit: int = 12, with_validation: bool = True) -> tuple[str, str, str]:
    meas = _upload("h02s19m*.csv", "measurement", limit=measure_limit)
    val_ids = []
    val_id = ""
    if with_validation:
        val = _upload("h02v*.csv", "validation", limit=12, reference="saline", molarity="0.154")
        val_ids = [val["id"]]
        val_id = val["id"]
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [meas["id"]], "validation_set_ids": val_ids, "temperature_c": 25.0,
    }).json()["id"]
    return cid, meas["id"], val_id


def test_repeats_step_band_and_distribution() -> None:
    _cid, mid, _v = _campaign(with_validation=False)
    resp = client.get(f"/api/sets/{mid}/repeats", params={"frequencies": "1,5,10"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    band = body["band"]
    n = len(band["frequency_hz"])
    assert n > 10
    assert all(len(band[k]) == n for k in ("eps_real", "eps_real_lo", "eps_real_hi", "sigma"))
    # the band brackets the mean
    assert all(lo <= m <= hi for lo, m, hi in
               zip(band["eps_real_lo"], band["eps_real"], band["eps_real_hi"], strict=True))
    assert body["coverage_k"] > 0
    assert len(body["distributions"]) == 3
    # the distribution inspector shows every raw repeat (incl. any outlier), not just the kept ones
    assert len(body["distributions"][0]["eps_real_samples"]) == body["n_repeats"]


def test_fit_step_returns_ranking_and_residual() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    resp = client.post(f"/api/campaigns/{cid}/fit", json={"dc_sigma": True})
    assert resp.status_code == 200, resp.text
    res = resp.json()["results"][0]
    assert "DC σ" in res["chosen_model"]
    assert len(res["ranking"]) > 1
    resid = res["residual"]
    n = len(resid["frequency_hz"])
    assert n == len(resid["residual_eps_real"]) > 10
    # normalized (standardized) residuals are present alongside the raw ones
    assert len(resid["norm_eps_real"]) == len(resid["norm_loss"]) == n
    assert len(res["plot"]["fit_frequency_hz"]) > 0


def test_fit_step_rejects_fixed_params() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    resp = client.post(f"/api/campaigns/{cid}/fit", json={"fixed_params": {"eps_inf": 5.0}})
    assert resp.status_code == 400


def test_kk_step_exposes_predicted_and_measured() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    body = client.get(f"/api/campaigns/{cid}/kk").json()
    kk = body["results"][0]
    n = len(kk["frequency_hz"])
    assert len(kk["predicted_eps_real"]) == len(kk["measured_eps_real"]) == n
    assert len(kk["relative_residual"]) == n
    assert isinstance(kk["consistent"], bool)


def test_reference_match_overlay() -> None:
    _cid, mid, _v = _campaign(with_validation=False)
    resp = client.post(f"/api/sets/{mid}/reference-match", json={
        "reference": "muscle", "temperature_c": 37.0,
    })
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["reference_label"]
    ov = body["overlay"]
    assert len(ov["frequency_hz"]) == len(ov["rel_error_pct"]) == len(ov["meas_eps_real"]) > 10
    assert body["rms"] >= 0


def test_saline_sweep_is_ranked() -> None:
    _cid, _m, vid = _campaign(with_validation=True)
    rows = client.post(f"/api/sets/{vid}/saline-sweep").json()["rows"]
    assert len(rows) == 15  # 3 molarities × 5 temperatures
    assert rows == sorted(rows, key=lambda r: r["rms"])  # best match first
    # the h02 saline validation is closest to ~0.154 M
    assert rows[0]["molarity"] == 0.154


def test_html_report_is_self_contained() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    client.post(f"/api/campaigns/{cid}/analyze", json={}).raise_for_status()
    resp = client.get(
        f"/api/campaigns/{cid}/report", params={"sample": "measurement", "fmt": "html"}
    )
    assert resp.status_code == 200
    text = resp.content.decode("utf-8")
    assert text.startswith("<!doctype html>")
    assert "data:image/png;base64," in text


def test_unknown_set_404() -> None:
    assert client.get("/api/sets/nope/repeats").status_code == 404
    assert client.post("/api/sets/nope/saline-sweep").status_code == 404


def test_compare_two_batches() -> None:
    # two batches: the muscle/saline h02 measurement set vs the validation set as a second "batch"
    a = _upload("h02s19m*.csv", "measurement", limit=10, name="batchA")
    b = _upload("h02v*.csv", "measurement", limit=10, name="batchB")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [a["id"], b["id"]], "temperature_c": 25.0,
    }).json()["id"]

    resp = client.post(f"/api/campaigns/{cid}/compare", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert {bt["sample_id"] for bt in body["batches"]} == {"batchA", "batchB"}
    assert body["baseline"] == "batchA"  # default = first
    assert len(body["differences"]) == 1
    d = body["differences"][0]
    assert d["sample_id"] == "batchB" and d["baseline"] == "batchA"
    sp = d["spectrum"]
    n = len(sp["frequency_hz"])
    assert n > 10
    assert all(len(sp[k]) == n for k in
               ("delta_eps_real", "se_eps_real", "significant_eps", "delta_sigma"))
    # the two genuinely different materials differ in ε′ over much of the band
    assert sum(sp["significant_eps"]) > 0
    names = {p["name"] for p in d["params"]}
    assert {"eps_static", "eps_inf", "tau_dominant"} <= names
    assert all("z" in p and "significant" in p for p in d["params"])

    # an explicit baseline flips the comparison direction
    flipped = client.post(f"/api/campaigns/{cid}/compare", json={"baseline": "batchB"}).json()
    assert flipped["differences"][0]["sample_id"] == "batchA"


def test_repeats_expose_transparent_screening() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=12)
    body = client.get(f"/api/sets/{m['id']}/repeats").json()
    # one detail row per repeat, with filename + z-score + reason
    assert len(body["repeats"]) == body["n_repeats"]
    r0 = body["repeats"][0]
    assert r0["filename"].endswith(".csv")
    assert "zscore" in r0 and "reason" in r0
    sc = body["screening"]
    assert sc["outlier_k"] == 3.5
    assert sc["n_used"] + sc["n_excluded"] == sc["n_total"] == body["n_repeats"]
    assert "Hampel" in sc["method"] or "MAD" in sc["method"]
    assert sc["citation"]


def test_screening_keep_all_and_manual_override() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=12)
    sid = m["id"]
    # keep all → screening disabled, nothing excluded
    keep_all = client.post(f"/api/sets/{sid}/screening", json={"outlier_k": None}).json()
    assert keep_all["screening"]["outlier_k"] is None
    assert keep_all["screening"]["n_excluded"] == 0
    assert keep_all["n_used"] == keep_all["n_repeats"]
    assert keep_all["impact"] is None  # nothing excluded → no impact

    # force-exclude repeat 0 → it is dropped with a manual reason and the impact is reported
    forced = client.post(
        f"/api/sets/{sid}/screening", json={"outlier_k": 3.5, "manual_exclude": [0]}
    ).json()
    assert 0 in forced["excluded_indices"]
    assert forced["repeats"][0]["reason"] == "excluded (manual)"
    assert forced["impact"] is not None
    assert forced["impact"]["eps_real_with"] != forced["impact"]["eps_real_without"]


def test_screening_change_invalidates_and_propagates() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=12)
    sid = m["id"]
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [sid], "temperature_c": 25.0,
    }).json()["id"]
    client.post(f"/api/campaigns/{cid}/analyze", json={}).raise_for_status()
    # change the screening; the cached fit/analysis for this campaign must be dropped
    client.post(f"/api/sets/{sid}/screening", json={"outlier_k": None}).raise_for_status()
    assert cid not in STORE.fits and cid not in STORE.analyses
    # re-analyze with the new (keep-all) screening succeeds and uses all repeats downstream
    client.post(f"/api/campaigns/{cid}/analyze", json={}).raise_for_status()


def test_comparison_report_renders_all_formats() -> None:
    a = _upload("h02s19m*.csv", "measurement", limit=10, name="normal")
    b = _upload("h02v*.csv", "measurement", limit=10, name="diseased")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [a["id"], b["id"]], "temperature_c": 25.0,
    }).json()["id"]
    for fmt, head in (("pdf", b"%PDF"), ("docx", b"PK\x03\x04")):
        r = client.get(f"/api/campaigns/{cid}/compare/report", params={"fmt": fmt})
        assert r.status_code == 200, r.text
        assert r.content[:4] == head
    # HTML is self-contained and carries the batch names + a difference verdict
    html = client.get(
        f"/api/campaigns/{cid}/compare/report", params={"fmt": "html", "baseline": "normal"}
    ).content.decode("utf-8")
    assert html.startswith("<!doctype html>")
    assert "data:image/png;base64," in html  # figures embedded
    assert "diseased" in html and "normal" in html
    assert "separates over" in html  # the verdict sentence


def test_same_named_batches_stay_distinct_and_compare() -> None:
    # Two batches uploaded with the SAME requested name must not collapse (the reported bug):
    # the fits cache is keyed by name, so duplicates would otherwise drop to one → "needs two".
    a = _upload("h02s19m*.csv", "measurement", limit=10, name="tissue")
    b = _upload("h02v*.csv", "measurement", limit=10, name="tissue")
    assert a["name"] == "tissue"
    assert b["name"] == "tissue (2)"  # auto-disambiguated
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [a["id"], b["id"]], "temperature_c": 25.0,
    }).json()["id"]
    body = client.post(f"/api/campaigns/{cid}/compare", json={}).json()
    assert {bt["sample_id"] for bt in body["batches"]} == {"tissue", "tissue (2)"}
    assert len(body["differences"]) == 1


def test_compare_needs_two_sets() -> None:
    one = _upload("h02s19m*.csv", "measurement", limit=8, name="solo")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [one["id"]], "temperature_c": 25.0,
    }).json()["id"]
    assert client.post(f"/api/campaigns/{cid}/compare", json={}).status_code == 400
