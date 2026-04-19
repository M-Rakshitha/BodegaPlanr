from __future__ import annotations

from pydantic import BaseModel, Field


class Agent4RequestCategory(BaseModel):
    category: str
    score: float
    rationale: str
    drivers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source: str = ""
    source_links: list[str] = Field(default_factory=list)


class Agent4RequestHoliday(BaseModel):
    holiday: str
    demand_multiplier: float


class Agent4Request(BaseModel):
    categories: list[Agent4RequestCategory]
    holidays: list[Agent4RequestHoliday] = Field(default_factory=list)
    population_density: float | None = None
    location_zip: str | None = None
    requested_items: list[str] = Field(default_factory=list)


class Agent4Recommendation(BaseModel):
    product: str
    suggested_vendor: str
    vendor_url: str | None = None
    vendor_address: str | None = None
    vendor_unit_price: float | None = None
    vendor_quantity: str | None = None
    wholesale_cost_estimate: float
    suggested_retail_price: float
    margin_pct: float
    reorder_trigger_units: int
    rationale: str
    data_source: str = "Gemini"


class Agent4Output(BaseModel):
    recommendations: list[Agent4Recommendation]
