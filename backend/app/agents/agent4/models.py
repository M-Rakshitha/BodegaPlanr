from __future__ import annotations

from pydantic import BaseModel


class Agent4RequestCategory(BaseModel):
    category: str
    score: float
    rationale: str


class Agent4RequestHoliday(BaseModel):
    holiday: str
    demand_multiplier: float


class Agent4Request(BaseModel):
    categories: list[Agent4RequestCategory]
    holidays: list[Agent4RequestHoliday] = []
    population_density: float | None = None
    location_zip: str | None = None
    requested_items: list[str] = []


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
