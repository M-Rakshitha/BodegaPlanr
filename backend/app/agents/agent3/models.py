from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.agent1.models import DemographicProfileResponse


class HolidayCalendarRequest(BaseModel):
    profile: DemographicProfileResponse
    horizon_days: int = Field(default=90, ge=14, le=180)

    @model_validator(mode="before")
    @classmethod
    def wrap_raw_profile(cls, data: object) -> object:
        if isinstance(data, dict) and "profile" not in data:
            mutable = dict(data)
            mutable["profile"] = data
            return mutable
        return data


class HolidayDemandEvent(BaseModel):
    holiday: str
    tradition: Literal["jewish", "islamic", "christian", "hindu", "sikh", "community"]
    start_date: date
    end_date: date
    days_until: int
    relevant_population_pct: float
    expected_demand_categories: list[str] = Field(default_factory=list)
    stock_up_window: str
    estimated_demand_multiplier: float
    matched_religion_demographics: list[str] = Field(default_factory=list)
    matched_race_demographics: list[str] = Field(default_factory=list)
    geography_context: str = ""
    demographic_rationale: str = ""
    source: str
    source_links: list[str] = Field(default_factory=list)


class DemographicsSummary(BaseModel):
    top_religions_used: list[str] = Field(default_factory=list)
    top_races_used: list[str] = Field(default_factory=list)
    country_context: str = ""


class HolidayCalendarResponse(BaseModel):
    location: str
    generated_at: str
    horizon_days: int
    window_start: date
    window_end: date
    demographics_used: DemographicsSummary = Field(default_factory=DemographicsSummary)
    events: list[HolidayDemandEvent] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    sources_used: list[str] = Field(default_factory=list)