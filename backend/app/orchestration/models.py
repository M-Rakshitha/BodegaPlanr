from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.agents.agent1.models import DemographicProfileResponse


class OrchestrationRequest(BaseModel):
    address: str | None = None
    zip_code: str | None = Field(default=None, alias="zip")
    include_religion: bool = True


class Agent2Category(BaseModel):
    category: str
    score: float
    rationale: str


class Agent2Output(BaseModel):
    categories: list[Agent2Category]


class Agent3HolidaySignal(BaseModel):
    holiday: str
    start_window_days: int
    demand_multiplier: float
    rationale: str


class Agent3Output(BaseModel):
    upcoming_signals: list[Agent3HolidaySignal]


class Agent4Recommendation(BaseModel):
    product: str
    suggested_vendor: str
    vendor_url: str | None = None
    wholesale_cost_estimate: float
    suggested_retail_price: float
    margin_pct: float
    reorder_trigger_units: int
    rationale: str


class Agent4Output(BaseModel):
    recommendations: list[Agent4Recommendation]


class OrchestratedReportResponse(BaseModel):
    generated_at: datetime
    location: str
    llm_model: str | None = None
    agent1: DemographicProfileResponse
    agent2: Agent2Output
    agent3: Agent3Output
    agent4: Agent4Output
