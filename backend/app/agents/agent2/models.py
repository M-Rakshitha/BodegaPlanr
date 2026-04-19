from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from pydantic import model_validator

from app.agents.agent1.models import DemographicProfileResponse


class BuyingBehaviorRequest(BaseModel):
    profile: DemographicProfileResponse

    @model_validator(mode="before")
    @classmethod
    def wrap_raw_profile(cls, data: object) -> object:
        if isinstance(data, dict) and "profile" not in data:
            return {"profile": data}
        return data


class BuyingBehaviorSignal(BaseModel):
    dimension: Literal["age", "race", "religion"]
    label: str
    share_pct: float
    confidence: Literal["high", "medium"]
    rationale: str
    source: str = "Agent 1 demographic profile"


class BuyingBehaviorCategory(BaseModel):
    category: str
    rationale: str
    drivers: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    source: str = ""
    source_links: list[str] = Field(default_factory=list)


class TopGroupShare(BaseModel):
    group: str
    share_pct: float
    count: int


class GroupItemSuggestion(BaseModel):
    group_type: Literal["race", "religion"]
    group: str
    share_pct: float
    count: int
    all_year_items: list[str]
    rationale: str
    source: str = ""
    source_links: list[str] = Field(default_factory=list)


class CoverageStatistics(BaseModel):
    total_groups_analyzed: int
    groups_with_data: int
    groups_without_data: int
    coverage_percentage: float


class BuyingBehaviorResponse(BaseModel):
    location: str
    top_signals: list[BuyingBehaviorSignal]
    categories: list[BuyingBehaviorCategory]
    group_item_suggestions: list[GroupItemSuggestion] = Field(default_factory=list)
    data_gaps: list[str] = Field(default_factory=list)
    coverage_statistics: CoverageStatistics = Field(default_factory=lambda: CoverageStatistics(total_groups_analyzed=0, groups_with_data=0, groups_without_data=0, coverage_percentage=0.0))