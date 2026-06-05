"""TestClient integration tests for the dielectric API (real h02 uploads)."""

from __future__ import annotations

import glob
import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app

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
