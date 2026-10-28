"""HTTP API. All data comes from pipeline outputs; nothing here computes detection logic."""
from typing import Literal, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import db, settings
from app.pipeline import llm
from app.services import results

router = APIRouter()
Size = Literal["small", "medium", "full"]


class RunRequest(BaseModel):
    size: Size = "small"
    repro: bool = False


def _get(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except results.NotAvailable as exc:
        raise HTTPException(404, str(exc))


@router.get("/health")
def health():
    storage = {"kind": "postgres", "schema_prefix": settings.DB_SCHEMA_PREFIX} if db.enabled() else {"kind": "sqlite"}
    return {"status": "ok", "storage": storage, "llm_configured": llm.configured()}


@router.get("/runs")
def list_runs():
    return [{"size": s, **results.status(s)} for s in results.SIZES]


@router.post("/runs", status_code=202)
def start_run(req: RunRequest):
    try:
        return results.start_run(req.size, req.repro)
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.get("/runs/{size}")
def run_status(size: Size):
    return results.status(size)


@router.get("/{size}/overview")
def overview(size: Size):
    return _get(results.overview, size)


@router.get("/{size}/alerts")
def alerts(size: Size, alert_type: Optional[str] = None, classification: Optional[str] = None,
           severity: Optional[str] = None, store_id: Optional[str] = None, q: Optional[str] = None,
           limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    return _get(results.alerts, size, alert_type, classification, severity, store_id, q, limit, offset)


@router.get("/{size}/alerts/{alert_id}")
def alert_detail(size: Size, alert_id: str):
    a = _get(results.alert_detail, size, alert_id)
    if not a:
        raise HTTPException(404, f"Alert {alert_id} not found")
    return a


@router.post("/{size}/alerts/{alert_id}/explain")
def explain(size: Size, alert_id: str):
    a = _get(results.one, size, "SELECT * FROM shrinkage_alert WHERE alert_id = ?", (alert_id,))
    if not a:
        raise HTTPException(404, f"Alert {alert_id} not found")
    try:
        return llm.explain(a)
    except llm.LLMNotConfigured as exc:
        raise HTTPException(503, str(exc))
    except OSError as exc:  # network / provider errors
        raise HTTPException(502, f"LLM request failed: {exc}")


@router.get("/{size}/validation")
def validation(size: Size):
    return _get(results.validation, size)


@router.get("/{size}/ground-truth")
def ground_truth(size: Size):
    return _get(results.ground_truth, size)
