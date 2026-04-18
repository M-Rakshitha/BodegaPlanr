from __future__ import annotations

from fastapi import APIRouter, HTTPException

from .models import DemographicProfileRequest, DemographicProfileResponse
from .service import DemographicProfiler

router = APIRouter(prefix="/agents/agent-1", tags=["agent-1"])
profiler = DemographicProfiler()


@router.post("/profile", response_model=DemographicProfileResponse)
async def create_profile(request: DemographicProfileRequest) -> DemographicProfileResponse:
    try:
        return await profiler.build_profile(request)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error