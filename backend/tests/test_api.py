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


def test_upload_detects_format_and_lifts_instrument() -> None:
    # Provenance the loader used to discard is now surfaced on the summary.
    summary = _upload("h02s19m*.csv", "measurement")
    assert summary["detected_format"] == "agilent_csv"
    assert "E8362B" in (summary["instrument"] or "")


def test_upload_accepts_optional_operator_and_instrument_override() -> None:
    # Optional provenance fields round-trip; an explicit instrument overrides the detected one.
    summary = _upload(
        "h02s19m*.csv", "measurement",
        operator="N. Istuk", instrument="Custom rig X", measurement_date="2026-06-09",
    )
    assert summary["instrument"] == "Custom rig X"
    assert summary["detected_format"] == "agilent_csv"


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
    pdf = client.get(f"/api/campaigns/{cid}/report", params={"sample": meas["name"], "fmt": "pdf"})
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
    # omitted dof means infinite, modelled as JSON null (not a numeric sentinel)
    assert body["contributions"][1]["dof"] is None


def test_budget_validation_rejects_bad_components() -> None:
    base = {"nominal_value": 58.0}
    bad = [
        {"name": "u<0", "standard_uncertainty": -1.0},
        {"name": "dof=0", "standard_uncertainty": 0.5, "dof": 0},
        {"name": "kind", "standard_uncertainty": 0.5, "kind": "C"},
        {"name": "", "standard_uncertainty": 0.5},
    ]
    for comp in bad:
        resp = client.post("/api/budget", json={**base, "components": [comp]})
        assert resp.status_code == 422, comp


def test_budget_type_a_requires_dof() -> None:
    resp = client.post("/api/budget", json={
        "nominal_value": 58.0,
        "components": [{"name": "rep", "standard_uncertainty": 0.5, "kind": "A"}],  # no dof
    })
    assert resp.status_code == 422
    assert "dof" in resp.text


def test_list_sets_and_typea_summary() -> None:
    meas = _upload("h02s19m*.csv", "measurement", limit=6)
    listed = client.get("/api/sets").json()
    assert any(s["id"] == meas["id"] and s["role"] == "measurement" for s in listed)

    resp = client.get(f"/api/sets/{meas['id']}/typea-summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == meas["name"]
    assert body["dof"] == body["n_used"] - 1 >= 1
    assert body["eps_real_sem_median"] > 0
    assert 0 < body["eps_real_median"] < 100  # plausible ε' for the bundled tissue data
    # the imported term composes into a valid budget
    budget = client.post("/api/budget", json={
        "nominal_value": body["eps_real_median"],
        "components": [{
            "name": "repeatability (Type A)",
            "standard_uncertainty": body["eps_real_sem_median"],
            "dof": body["dof"], "kind": "A",
        }],
    })
    assert budget.status_code == 200

    assert client.get("/api/sets/nope/typea-summary").status_code == 404


def test_budget_zero_nominal_and_infinite_dof() -> None:
    resp = client.post("/api/budget", json={
        "nominal_value": 0.0,
        "components": [{"name": "cal", "standard_uncertainty": 1.0, "kind": "B"}],
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["relative_expanded"] is None  # undefined at nominal 0, not 0.0%
    assert body["effective_dof"] is None  # all Type B → infinite
    assert "effective dof = inf" in body["table"]
    assert "1e+308" not in resp.text and "1000000000" not in body["table"]


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


def test_fit_dc_sigma_constrains_panel_not_forces_family() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    on = client.post(f"/api/campaigns/{cid}/fit", json={"dc_sigma": True}).json()["results"][0]
    assert "DC σ" in on["chosen_model"]
    assert not on["overridden"]  # a panel constraint, not an override
    assert all("DC σ" in rf["label"] for rf in on["ranking"])
    off = client.post(f"/api/campaigns/{cid}/fit", json={"dc_sigma": False}).json()["results"][0]
    assert "DC σ" not in off["chosen_model"]
    assert all("DC σ" not in rf["label"] for rf in off["ranking"])
    assert any("constrained" in w for w in off["selection_warnings"])


def test_fit_ranking_marks_recommended_and_chosen() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    res = client.post(f"/api/campaigns/{cid}/fit", json={"model": "Debye"}).json()["results"][0]
    ranking = res["ranking"]
    assert sum(rf["recommended"] for rf in ranking) == 1
    chosen = next(rf for rf in ranking if rf["chosen"])
    recommended = next(rf for rf in ranking if rf["recommended"])
    assert chosen["label"] == "Debye"
    assert recommended["label"] != "Debye"  # override ≠ recommendation, both visible


def test_delete_set_forgets_it() -> None:
    meas = _upload("h02s19m*.csv", "measurement", limit=4)
    assert client.delete(f"/api/sets/{meas['id']}").status_code == 200
    assert client.get(f"/api/sets/{meas['id']}/typea-summary").status_code == 404
    assert client.delete(f"/api/sets/{meas['id']}").status_code == 404


def test_fit_rejects_out_of_range_poles() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    for bad in (0, 7):
        resp = client.post(f"/api/campaigns/{cid}/fit", json={"n_poles": bad})
        assert resp.status_code == 422, (bad, resp.text)


def test_fit_unknown_model_message_is_friendly() -> None:
    cid, _m, _v = _campaign(with_validation=False)
    resp = client.post(f"/api/campaigns/{cid}/fit", json={"model": "Nonexistent"})
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "available:" in detail
    assert "['" not in detail  # human-readable candidate list, not a Python repr


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
    analysis = client.post(f"/api/campaigns/{cid}/analyze", json={}).json()
    sample = analysis["results"][0]["sample_id"]
    resp = client.get(f"/api/campaigns/{cid}/report", params={"sample": sample, "fmt": "html"})
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


def test_validation_config_edit_and_link() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=10, name="muscle")
    v = _upload("h02v*.csv", "validation", limit=10, name="saline-qc",
                reference="saline", molarity="0.154")
    vid = v["id"]

    # default saline detail
    d = client.get(f"/api/sets/{vid}/validation").json()
    assert d["reference_label"] == "saline_0.154M"
    assert d["config"]["mass_percent"] == pytest.approx(0.9)
    assert d["saline_sweep"] is not None

    # edit by mass % and link to the muscle batch
    edited = client.post(f"/api/sets/{vid}/validation", json={
        "reference": "saline", "mass_percent": 0.9, "temperature_c": 25.0,
        "measurement_set_ids": [m["id"]],
    }).json()
    assert edited["config"]["molarity"] == pytest.approx(0.154)
    assert edited["linked_batches"] == [m["id"]]
    assert edited["verdict"]["passed"]

    # switch the reference to water → no DC σ → fails; no saline sweep
    water = client.post(f"/api/sets/{vid}/validation", json={
        "reference": "water", "temperature_c": 25.0, "measurement_set_ids": [m["id"]],
    }).json()
    assert not water["verdict"]["passed"]
    assert water["saline_sweep"] is None

    # seawater accepts salinity
    sea = client.post(f"/api/sets/{vid}/validation", json={
        "reference": "seawater", "salinity_psu": 35.0, "temperature_c": 20.0,
        "measurement_set_ids": [m["id"]],
    }).json()
    assert sea["config"]["salinity_psu"] == 35.0


def test_validation_edit_propagates_to_campaign_banner() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=10, name="muscle2")
    v = _upload("h02v*.csv", "validation", limit=10, name="qc2",
                reference="saline", molarity="0.154")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [m["id"]], "validation_set_ids": [v["id"]], "temperature_c": 37.0,
    }).json()["id"]
    # baseline saline → validates
    assert client.post(f"/api/campaigns/{cid}/analyze", json={}).json()["validation"]["validated"]
    # edit the validation reference to water → the campaign banner flips to NOT VALIDATED
    client.post(f"/api/sets/{v['id']}/validation", json={
        "reference": "water", "temperature_c": 25.0, "measurement_set_ids": [m["id"]],
    }).raise_for_status()
    again = client.post(f"/api/campaigns/{cid}/analyze", json={}).json()["validation"]
    assert not again["validated"]
    assert again["verdicts"][0]["linked_batches"] == [m["id"]]


def test_validation_detail_404_for_measurement() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=8, name="solo2")
    assert client.get(f"/api/sets/{m['id']}/validation").status_code == 404


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


def test_campaign_report_combines_batches_and_comparison() -> None:
    a = _upload("h02s19m*.csv", "measurement", limit=10, name="normal")
    b = _upload("h02v*.csv", "measurement", limit=10, name="diseased")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [a["id"], b["id"]], "temperature_c": 25.0,
    }).json()["id"]
    client.post(f"/api/campaigns/{cid}/analyze", json={}).raise_for_status()
    for fmt, head in (("pdf", b"%PDF"), ("docx", b"PK\x03\x04")):
        r = client.get(f"/api/campaigns/{cid}/campaign-report", params={"fmt": fmt})
        assert r.status_code == 200, r.text
        assert r.content[:4] == head
    r = client.get(f"/api/campaigns/{cid}/campaign-report", params={"fmt": "html"})
    html = r.content.decode()
    assert html.startswith("<!doctype html>") and "data:image/png;base64," in html
    # both batches' analysis AND the comparison section are present in the one file
    assert "Dielectric analysis: normal" in html and "Dielectric analysis: diseased" in html
    assert "separates over" in html  # comparison verdict


def test_campaign_report_single_batch_has_no_comparison() -> None:
    m = _upload("h02s19m*.csv", "measurement", limit=10, name="solo")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [m["id"]], "temperature_c": 25.0,
    }).json()["id"]
    client.post(f"/api/campaigns/{cid}/analyze", json={}).raise_for_status()
    r = client.get(f"/api/campaigns/{cid}/campaign-report", params={"fmt": "html"})
    html = r.content.decode()
    assert "Dielectric analysis: solo" in html
    assert "separates over" not in html  # no comparison with one batch


def test_compare_needs_two_sets() -> None:
    one = _upload("h02s19m*.csv", "measurement", limit=8, name="solo")
    cid = client.post("/api/campaigns", json={
        "measurement_set_ids": [one["id"]], "temperature_c": 25.0,
    }).json()["id"]
    assert client.post(f"/api/campaigns/{cid}/compare", json={}).status_code == 400
