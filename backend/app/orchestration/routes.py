from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.orchestration.graph import run_orchestration
from app.orchestration.models import OrchestrationRequest, OrchestratedReportResponse

router = APIRouter(prefix="/orchestration", tags=["orchestration"])


@router.post("/run", response_model=OrchestratedReportResponse)
async def run_report_orchestration(request: OrchestrationRequest) -> OrchestratedReportResponse:
    try:
        return await run_orchestration(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=500, detail=str(error)) from error
