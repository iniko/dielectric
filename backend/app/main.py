"""FastAPI app — a thin HTTP layer over the ``dielectric`` library.

Two workflows: Dielectric Analysis (upload any number of measurement and validation sets → fit →
verify → report) and the Uncertainty Budget sandbox (pure GUM calculation, no upload).
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

import dielectric

from . import schemas, services
from .store import STORE

app = FastAPI(title="dielectric API", version=dielectric.__version__)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "library_version": dielectric.__version__}


@app.get("/api/materials", response_model=list[schemas.MaterialOut])
def materials() -> list[schemas.MaterialOut]:
    return services.list_materials()


@app.post("/api/sets", response_model=schemas.SetSummary)
async def upload_set(
    files: list[UploadFile] = File(...),
    role: str = Form(...),
    name: str = Form("set"),
    reference: str = Form("saline"),
    molarity: float = Form(0.154),
    temperature_c: float = Form(25.0),
    salinity_psu: float | None = Form(None),
    operator: str | None = Form(None),
    instrument: str | None = Form(None),
    measurement_date: str | None = Form(None),
) -> schemas.SetSummary:
    if role not in ("measurement", "validation"):
        raise HTTPException(400, "role must be 'measurement' or 'validation'")
    payload = [(f.filename or "upload.csv", await f.read()) for f in files]
    if not payload:
        raise HTTPException(400, "no files uploaded")
    # Optional, free-text provenance fields; absent → today's behaviour (back-compat).
    meta = {
        k: v
        for k, v in (
            ("operator", operator),
            ("instrument", instrument),
            ("measurement_date", measurement_date),
        )
        if v
    }
    try:
        if role == "measurement":
            sid, corrected = services.make_measurement_set(payload, name, temperature_c, meta)
            obj: object = STORE.measurement_sets[sid]
        else:
            sid, corrected = services.make_validation_set(
                payload, name, reference, molarity, temperature_c, salinity_psu, meta
            )
            obj = STORE.validation_sets[sid]
    except Exception as exc:  # malformed upload
        raise HTTPException(422, f"could not parse uploaded files: {exc}") from exc
    return services.set_summary(sid, obj, role, corrected)  # type: ignore[arg-type]


@app.post("/api/campaigns", response_model=schemas.CampaignSummary)
def create_campaign(req: schemas.CampaignCreate) -> schemas.CampaignSummary:
    for i in req.measurement_set_ids:
        if i not in STORE.measurement_sets:
            raise HTTPException(404, f"unknown measurement set '{i}'")
    for i in req.validation_set_ids:
        if i not in STORE.validation_sets:
            raise HTTPException(404, f"unknown validation set '{i}'")
    if not req.measurement_set_ids:
        raise HTTPException(400, "a campaign needs at least one measurement set")
    cid = services.build_campaign(req)
    return schemas.CampaignSummary(
        id=cid, measurement_set_ids=req.measurement_set_ids,
        validation_set_ids=req.validation_set_ids, temperature_c=req.temperature_c,
    )


@app.post("/api/campaigns/{campaign_id}/analyze", response_model=schemas.CampaignAnalysis)
def analyze(campaign_id: str, req: schemas.AnalyzeRequest) -> schemas.CampaignAnalysis:
    if campaign_id not in STORE.campaigns:
        raise HTTPException(404, "unknown campaign")
    try:
        return services.analyze_campaign(campaign_id, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.post("/api/campaigns/{campaign_id}/fit", response_model=schemas.FitOut)
def fit(campaign_id: str, req: schemas.FitRequest) -> schemas.FitOut:
    if campaign_id not in STORE.campaigns:
        raise HTTPException(404, "unknown campaign")
    try:
        return services.fit_campaign(campaign_id, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}/kk", response_model=schemas.KKDetailOut)
def kk(campaign_id: str) -> schemas.KKDetailOut:
    if campaign_id not in STORE.campaigns:
        raise HTTPException(404, "unknown campaign")
    return services.kk_campaign(campaign_id)


@app.get("/api/sets/{set_id}/repeats", response_model=schemas.RepeatsOut)
def repeats(set_id: str, frequencies: str | None = None) -> schemas.RepeatsOut:
    try:
        freqs = [float(x) for x in frequencies.split(",") if x.strip()] if frequencies else []
    except ValueError as exc:
        raise HTTPException(400, "frequencies must be a comma-separated list of GHz") from exc
    try:
        return services.repeats_for_set(set_id, freqs)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/sets/{set_id}/screening", response_model=schemas.RepeatsOut)
def set_screening(set_id: str, req: schemas.ScreeningRequest) -> schemas.RepeatsOut:
    try:
        return services.set_screening(set_id, req)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.get("/api/sets/{set_id}/validation", response_model=schemas.ValidationDetailOut)
def get_validation(set_id: str) -> schemas.ValidationDetailOut:
    try:
        return services.validation_detail(set_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/sets/{set_id}/validation", response_model=schemas.ValidationDetailOut)
def set_validation(
    set_id: str, req: schemas.ValidationConfigRequest
) -> schemas.ValidationDetailOut:
    try:
        return services.set_validation_config(set_id, req)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"could not resolve reference '{req.reference}': {exc}") from exc


@app.post("/api/sets/{set_id}/reference-match", response_model=schemas.ReferenceMatchOut)
def reference_match(set_id: str, req: schemas.ReferenceMatchRequest) -> schemas.ReferenceMatchOut:
    try:
        return services.reference_match_for_set(set_id, req)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, f"could not resolve reference '{req.reference}': {exc}") from exc


@app.post("/api/sets/{set_id}/saline-sweep", response_model=schemas.SalineSweepOut)
def saline_sweep(set_id: str) -> schemas.SalineSweepOut:
    try:
        return services.saline_sweep_for_set(set_id)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@app.post("/api/campaigns/{campaign_id}/compare", response_model=schemas.CompareOut)
def compare(campaign_id: str, req: schemas.CompareRequest) -> schemas.CompareOut:
    if campaign_id not in STORE.campaigns:
        raise HTTPException(404, "unknown campaign")
    try:
        return services.compare_campaign(campaign_id, req)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@app.get("/api/campaigns/{campaign_id}/compare/report")
def compare_report(
    campaign_id: str, baseline: str | None = None, fmt: str = "pdf"
) -> FileResponse:
    if fmt not in ("pdf", "docx", "html"):
        raise HTTPException(400, "fmt must be 'pdf', 'docx', or 'html'")
    if campaign_id not in STORE.campaigns:
        raise HTTPException(404, "unknown campaign")
    try:
        path = services.generate_comparison_report(campaign_id, baseline, fmt)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html",
    }[fmt]
    return FileResponse(path, media_type=media, filename=f"comparison_report.{fmt}")


@app.get("/api/campaigns/{campaign_id}/campaign-report")
def campaign_report(
    campaign_id: str, baseline: str | None = None, fmt: str = "pdf"
) -> FileResponse:
    if fmt not in ("pdf", "docx", "html"):
        raise HTTPException(400, "fmt must be 'pdf', 'docx', or 'html'")
    if campaign_id not in STORE.campaigns:
        raise HTTPException(404, "unknown campaign")
    try:
        path = services.generate_campaign_report(campaign_id, baseline, fmt)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html",
    }[fmt]
    return FileResponse(path, media_type=media, filename=f"campaign_report.{fmt}")


@app.get("/api/campaigns/{campaign_id}/report")
def report(campaign_id: str, sample: str, fmt: str = "pdf") -> FileResponse:
    if fmt not in ("pdf", "docx", "html"):
        raise HTTPException(400, "fmt must be 'pdf', 'docx', or 'html'")
    try:
        path = services.generate_report(campaign_id, sample, fmt)
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    media = {
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "html": "text/html",
    }[fmt]
    return FileResponse(path, media_type=media, filename=f"{Path(sample).stem}_report.{fmt}")


@app.post("/api/budget", response_model=schemas.BudgetResult)
def budget(req: schemas.BudgetRequest) -> schemas.BudgetResult:
    if not req.components:
        raise HTTPException(400, "the budget needs at least one component")
    return services.compute_budget(req)
