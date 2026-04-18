from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class DemographicProfileRequest(BaseModel):
    address: str | None = Field(default=None, description="Street address or full location string.")
    zip_code: str | None = Field(default=None, description="ZIP code or ZCTA.")

    @model_validator(mode="before")
    @classmethod
    def normalize_zip_alias(cls, data: object) -> object:
        if isinstance(data, dict) and "zip" in data and "zip_code" not in data:
            mutable_data = dict(data)
            mutable_data["zip_code"] = mutable_data.pop("zip")
            return mutable_data
        return data


class DemographicProfileResponse(BaseModel):
    class CountShare(BaseModel):
        count: int
        share_pct: float

    class CategoryDemographic(BaseModel):
        count: int
        share_pct: float
        subcategories: dict[str, "DemographicProfileResponse.CountShare"] = Field(default_factory=dict)

    class GeographyCoverage(BaseModel):
        geography_unit: Literal["county", "census_tract", "zcta"]
        coverage_id: str
        estimated_radius_miles: float | None = None
        explanation: str

    location: str
    geography_type: Literal["address", "zip"]
    total_pop: int
    household_count: int | None = None
    population_density_per_sq_mile: float | None = None
    geography_coverage: GeographyCoverage
    age_groups: dict[str, CountShare]
    race_demographics: dict[str, CategoryDemographic]
    religion_demographics: dict[str, CategoryDemographic] | None = None
    median_income: int | None = None
    income_tier: str
    primary_language: str
    sources: list[str]