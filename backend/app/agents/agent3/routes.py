from __future__ import annotations

from fastapi import APIRouter

from .models import HolidayCalendarRequest, HolidayCalendarResponse
from .service import ReligiousHolidayCalendarBuilder

router = APIRouter(prefix="/agents/agent-3", tags=["agent-3"])
builder = ReligiousHolidayCalendarBuilder()


@router.post("/calendar", response_model=HolidayCalendarResponse)
async def build_holiday_calendar(request: HolidayCalendarRequest) -> HolidayCalendarResponse:
    return await builder.build_calendar(request.profile, request.horizon_days)