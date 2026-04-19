from __future__ import annotations

import csv
import os
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal, cast
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import httpx
from app.rate_limit import wait_for_outbound_slot

from .models import DemographicProfileRequest, DemographicProfileResponse

ACS_URL = "https://api.census.gov/data/2023/acs/acs5"
GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
ZIP_LOOKUP_URL = "https://api.zippopotam.us/us/{zip_code}"
FCC_COUNTY_LOOKUP_URL = "https://geo.fcc.gov/api/census/block/find"


@dataclass(frozen=True)
class Geography:
    display_name: str
    geography_type: str
    state_fips: str | None = None
    county_fips: str | None = None
    tract: str | None = None
    zip_code: str | None = None

    @property
    def coverage_id(self) -> str:
        if self.geography_type == "address" and self.state_fips and self.county_fips:
            return f"{self.state_fips}-{self.county_fips}"
        return self.zip_code or "unknown"


class DemographicProfiler:
    def __init__(self, census_api_key: str | None = None, arda_csv_path: Path | None = None) -> None:
        self.census_api_key = census_api_key or os.getenv("CENSUS_API_KEY")
        self._group_labels_cache: dict[str, dict[str, str]] = {}
        self._arda_code_name_map: dict[str, str] | None = None
        default_file = Path(__file__).resolve().parents[3] / "data" / "U.S. Religion Census - Religious Congregations and Membership Study, 2020 (County File).xlsx"
        default_group_detail_file = Path(__file__).resolve().parents[3] / "data" / "2020_USRC_Group_Detail.xlsx"
        default_codebook_file = Path(__file__).resolve().parents[3] / "data" / "arda_rcmscy20_codebook.html"
        self.arda_data_path = arda_csv_path or Path(os.getenv("ARDA_RELIGION_PATH", str(default_file)))
        self.arda_group_detail_path = Path(os.getenv("ARDA_GROUP_DETAIL_PATH", str(default_group_detail_file)))
        self.arda_codebook_path = Path(os.getenv("ARDA_CODEBOOK_PATH", str(default_codebook_file)))
        mapping_default = Path(__file__).resolve().parents[3] / "data" / "arda_denomination_names.csv"
        self.arda_mapping_path = Path(os.getenv("ARDA_DENOMINATION_MAPPING_PATH", str(mapping_default)))
        self._arda_rows_by_fips: dict[str, dict[str, str]] | None = None

    async def build_profile(self, request: DemographicProfileRequest) -> DemographicProfileResponse:
        sources: list[str] = []
        geography = await self._resolve_geography(request, sources)
        census_payload = await self._fetch_census_payload(geography, sources)

        total_pop = self._to_int(census_payload.get("B01003_001E"))
        household_count = self._to_int(census_payload.get("B11001_001E"))
        median_income = self._to_int(census_payload.get("B19013_001E"))
        age_groups = self._calculate_age_groups(census_payload)
        top_age_groups = self._top_groups(age_groups, limit=10)
        race_demographics = self._calculate_race_demographics(census_payload, total_pop)
        religion_demographics = self._calculate_religion_demographics(total_pop, geography)
        if religion_demographics is None and geography.geography_type == "zip" and geography.zip_code:
            county_geography = await self._zip_to_county_geography(geography.zip_code, sources)
            if county_geography is not None:
                religion_demographics = self._calculate_religion_demographics(total_pop, county_geography)

        top_races = self._top_groups(race_demographics, limit=10)
        top_religions = self._top_groups(religion_demographics, limit=10) if religion_demographics else []
        if religion_demographics is not None:
            sources.append(f"arda_file:{self.arda_data_path}")
            if self.arda_group_detail_path.exists():
                sources.append(f"arda_group_detail:{self.arda_group_detail_path}")
        income_tier = self._income_tier(median_income)
        primary_language = self._primary_language_proxy(census_payload)

        return DemographicProfileResponse(
            location=geography.display_name,
            geography_type=cast(Literal["address", "zip"], geography.geography_type),
            total_pop=total_pop,
            household_count=household_count,
            population_density_per_sq_mile=None,
            geography_coverage=self._build_geography_coverage(geography),
            age_groups=cast(dict[str, DemographicProfileResponse.CountShare], age_groups),
            top_age_groups=cast(list[DemographicProfileResponse.TopGroup], top_age_groups),
            race_demographics=cast(dict[str, DemographicProfileResponse.CategoryDemographic], race_demographics),
            religion_demographics=cast(dict[str, DemographicProfileResponse.CategoryDemographic] | None, religion_demographics),
            top_races=cast(list[DemographicProfileResponse.TopGroup], top_races),
            top_religions=cast(list[DemographicProfileResponse.TopGroup], top_religions),
            median_income=median_income,
            income_tier=income_tier,
            primary_language=primary_language,
            sources=sources,
        )

    async def _zip_to_county_geography(self, zip_code: str, sources: list[str]) -> Geography | None:
        payload = await self._get_json(ZIP_LOOKUP_URL.format(zip_code=zip_code), params={}, sources=sources)
        places = payload.get("places") or []
        if not places:
            return None

        lat = places[0].get("latitude")
        lon = places[0].get("longitude")
        if lat is None or lon is None:
            return None

        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "showall": "true",
            "format": "json",
        }
        county_payload = await self._get_json(FCC_COUNTY_LOOKUP_URL, params=params, sources=sources)
        county_fips = str(county_payload.get("County", {}).get("FIPS", ""))
        if len(county_fips) != 5 or not county_fips.isdigit():
            return None

        county_name = str(county_payload.get("County", {}).get("name", "")).strip()
        return Geography(
            display_name=county_name or zip_code,
            geography_type="address",
            state_fips=county_fips[:2],
            county_fips=county_fips[2:],
            zip_code=zip_code,
        )

    def _top_groups(self, demographics: dict[str, Any] | None, limit: int) -> list[dict[str, int | float | str]]:
        if not demographics:
            return []

        rows: list[dict[str, int | float | str]] = []
        for name, entry in demographics.items():
            count = self._to_int(entry.get("count"))
            share_pct = self._to_float(entry.get("share_pct"))
            if count <= 0 or share_pct <= 0:
                continue
            rows.append(
                {
                    "group": name,
                    "count": count,
                    "share_pct": round(share_pct, 2),
                }
            )

        rows.sort(key=lambda row: (cast(float, row["share_pct"]), cast(int, row["count"])), reverse=True)
        return rows[:limit]

    async def _resolve_geography(self, request: DemographicProfileRequest, sources: list[str]) -> Geography:
        if request.address:
            params = {
                "address": request.address,
                "benchmark": "Public_AR_Current",
                "vintage": "Current_Current",
                "format": "json",
            }
            payload = await self._get_json(GEOCODER_URL, params=params, sources=sources)
            matches = payload.get("result", {}).get("addressMatches", [])
            if not matches:
                raise ValueError("Could not geocode the supplied address.")

            geography = matches[0]["geographies"]["Census Tracts"][0]
            display_name = matches[0]["matchedAddress"]
            county_geographies = matches[0]["geographies"].get("Counties", [])
            county_name = geography.get("NAME", "County")
            if county_geographies:
                county_name = county_geographies[0].get("NAME", county_name)
            state = geography.get("STATE", "")
            county = geography.get("COUNTY", "")
            county_display = f"County {county_name}" if county_name else display_name

            return Geography(
                display_name=county_display,
                geography_type="address",
                state_fips=state,
                county_fips=county,
                tract=geography.get("TRACT"),
            )

        if request.zip_code:
            zip_code = request.zip_code.strip()
            if not zip_code:
                raise ValueError("ZIP code cannot be blank.")
            return Geography(display_name=zip_code, geography_type="zip", zip_code=zip_code)

        raise ValueError("Provide either an address or a ZIP code.")

    async def _fetch_census_payload(self, geography: Geography, sources: list[str]) -> dict[str, Any]:
        base_variables = [
            "B01003_001E",
            "B11001_001E",
            "B19013_001E",
            "B02008_001E",
            "B02009_001E",
            "B02010_001E",
            "B02011_001E",
            "B02012_001E",
            "B02013_001E",
            "B03002_010E",
            "B03002_003E",
            "B03002_004E",
            "B03002_005E",
            "B03002_006E",
            "B03002_007E",
            "B03002_008E",
            "B03002_009E",
            "B03002_011E",
            "B03002_012E",
            "B03002_013E",
            "B03002_014E",
            "B03002_015E",
            "B03002_016E",
            "B03002_017E",
            "B02001_002E",
            "B02001_003E",
            "B02001_004E",
            "B02001_005E",
            "B02001_006E",
            "B02001_007E",
            "B02001_008E",
        ]
        base_payload = await self._fetch_census_chunk(geography, base_variables, sources)
        age_payload = await self._fetch_census_chunk(geography, self._age_variables(), sources)
        asian_detail_payload = await self._fetch_group_payload(geography, "B02015", sources)
        nhpi_detail_payload = await self._fetch_group_payload(geography, "B02016", sources)
        asian_combo_payload = await self._fetch_group_payload(geography, "B02018", sources)
        nhpi_combo_payload = await self._fetch_group_payload(geography, "B02019", sources)

        merged = dict(base_payload)
        merged.update(age_payload)
        merged.update(asian_detail_payload)
        merged.update(nhpi_detail_payload)
        merged.update(asian_combo_payload)
        merged.update(nhpi_combo_payload)
        return merged

    async def _fetch_group_payload(self, geography: Geography, group_name: str, sources: list[str]) -> dict[str, Any]:
        labels = await self._get_group_labels(group_name, sources)
        variables = sorted(labels.keys())
        chunk_size = 45
        combined: dict[str, Any] = {}

        for index in range(0, len(variables), chunk_size):
            chunk = variables[index:index + chunk_size]
            payload = await self._fetch_census_chunk(geography, chunk, sources)
            combined.update(payload)

        return combined

    async def _get_group_labels(self, group_name: str, sources: list[str]) -> dict[str, str]:
        if group_name in self._group_labels_cache:
            return self._group_labels_cache[group_name]

        url = f"https://api.census.gov/data/2023/acs/acs5/groups/{group_name}.json"
        payload = await self._get_json(url, params={}, sources=sources)
        variables = payload.get("variables", {})

        labels: dict[str, str] = {}
        for variable, meta in variables.items():
            if not variable.startswith(f"{group_name}_") or not variable.endswith("E"):
                continue

            label = self._format_group_label(meta.get("label", ""), group_name)
            if not label:
                continue
            labels[variable] = label

        self._group_labels_cache[group_name] = labels
        return labels

    def _format_group_label(self, label: str, group_name: str) -> str:
        parts = [segment.strip().rstrip(":") for segment in label.split("!!")]
        filtered = [segment for segment in parts if segment and segment.lower() not in {"estimate", "total"}]
        if not filtered:
            return ""

        prefix_map = {
            "B02015": "Asian subgroup",
            "B02016": "NHPI subgroup",
            "B02018": "Asian subgroup (alone or in any combination)",
            "B02019": "NHPI subgroup (alone or in any combination)",
        }
        prefix = prefix_map.get(group_name, "Race subgroup")

        return f"{prefix}: {' - '.join(filtered)}"

    def _extract_zip_from_text(self, text: str) -> str | None:
        match = re.search(r"\b(\d{5})(?:-\d{4})?\b", text)
        return match.group(1) if match else None

    async def _fetch_census_chunk(
        self,
        geography: Geography,
        variables: list[str],
        sources: list[str],
    ) -> dict[str, Any]:
        params: dict[str, str] = {"get": ",".join(variables)}

        if self.census_api_key and self.census_api_key != "DEMO_KEY":
            params["key"] = self.census_api_key

        if geography.geography_type == "zip":
            params["for"] = f"zip code tabulation area:{geography.zip_code}"
        elif geography.state_fips and geography.county_fips:
            params["for"] = f"county:{geography.county_fips}"
            params["in"] = f"state:{geography.state_fips}"
        else:
            raise ValueError("Unable to determine valid Census geography scope.")

        payload = await self._get_json(ACS_URL, params=params, sources=sources)
        headers = payload[0]
        row = payload[1]
        return dict(zip(headers, row, strict=False))

    async def _get_json(self, url: str, params: dict[str, str], sources: list[str]) -> Any:
        async with httpx.AsyncClient(timeout=20.0) as client:
            await wait_for_outbound_slot()
            response = await client.get(url, params=params, follow_redirects=True)
            request_url = str(response.request.url)
            if request_url not in sources:
                sources.append(request_url)
            try:
                response.raise_for_status()
            except httpx.HTTPStatusError as error:
                raise ValueError(f"Request to {url} failed with status {response.status_code}.") from error

            try:
                return response.json()
            except ValueError as error:
                raise ValueError(f"Request to {url} returned non-JSON content.") from error

    def _age_variables(self) -> list[str]:
        return [
            "B01001_003E",
            "B01001_004E",
            "B01001_005E",
            "B01001_006E",
            "B01001_007E",
            "B01001_008E",
            "B01001_009E",
            "B01001_010E",
            "B01001_011E",
            "B01001_012E",
            "B01001_013E",
            "B01001_014E",
            "B01001_015E",
            "B01001_016E",
            "B01001_017E",
            "B01001_018E",
            "B01001_019E",
            "B01001_020E",
            "B01001_021E",
            "B01001_022E",
            "B01001_023E",
            "B01001_024E",
            "B01001_025E",
            "B01001_027E",
            "B01001_028E",
            "B01001_029E",
            "B01001_030E",
            "B01001_031E",
            "B01001_032E",
            "B01001_033E",
            "B01001_034E",
            "B01001_035E",
            "B01001_036E",
            "B01001_037E",
            "B01001_038E",
            "B01001_039E",
            "B01001_040E",
            "B01001_041E",
            "B01001_042E",
            "B01001_043E",
            "B01001_044E",
            "B01001_045E",
            "B01001_046E",
            "B01001_047E",
            "B01001_048E",
            "B01001_049E",
        ]

    def _calculate_age_buckets(self, payload: dict[str, Any]) -> dict[str, int]:
        raw_buckets = {
            "0-17": sum(self._to_int(payload.get(key)) for key in [
                "B01001_003E", "B01001_004E", "B01001_005E", "B01001_006E",
                "B01001_027E", "B01001_028E", "B01001_029E", "B01001_030E",
            ]),
            "18-34": sum(self._to_int(payload.get(key)) for key in [
                "B01001_007E", "B01001_008E", "B01001_009E", "B01001_010E", "B01001_011E", "B01001_012E",
                "B01001_031E", "B01001_032E", "B01001_033E", "B01001_034E", "B01001_035E", "B01001_036E",
            ]),
            "35-54": sum(self._to_int(payload.get(key)) for key in [
                "B01001_013E", "B01001_014E", "B01001_015E", "B01001_016E",
                "B01001_037E", "B01001_038E", "B01001_039E", "B01001_040E",
            ]),
            "55+": sum(self._to_int(payload.get(key)) for key in [
                "B01001_017E", "B01001_018E", "B01001_019E", "B01001_020E", "B01001_021E", "B01001_022E", "B01001_023E", "B01001_024E", "B01001_025E",
                "B01001_041E", "B01001_042E", "B01001_043E", "B01001_044E", "B01001_045E", "B01001_046E", "B01001_047E", "B01001_048E", "B01001_049E",
            ]),
        }

        total = sum(raw_buckets.values())
        if not total:
            return {bucket: 0 for bucket in raw_buckets}

        scaled = {bucket: (value * 100) / total for bucket, value in raw_buckets.items()}
        rounded = {bucket: int(value) for bucket, value in scaled.items()}
        remainder = 100 - sum(rounded.values())

        if remainder > 0:
            fractions = sorted(
                ((scaled[bucket] - rounded[bucket], bucket) for bucket in raw_buckets),
                reverse=True,
            )
            for _, bucket in fractions[:remainder]:
                rounded[bucket] += 1

        return rounded

    def _calculate_age_groups(self, payload: dict[str, Any]) -> dict[str, dict[str, int | float]]:
        raw_counts = {
            "0-9": sum(self._to_int(payload.get(key)) for key in [
                "B01001_003E", "B01001_004E",
                "B01001_027E", "B01001_028E",
            ]),
            "10-19": sum(self._to_int(payload.get(key)) for key in [
                "B01001_005E", "B01001_006E", "B01001_007E",
                "B01001_029E", "B01001_030E", "B01001_031E",
            ]),
            "20-29": sum(self._to_int(payload.get(key)) for key in [
                "B01001_008E", "B01001_009E", "B01001_010E", "B01001_011E",
                "B01001_032E", "B01001_033E", "B01001_034E", "B01001_035E",
            ]),
            "30-39": sum(self._to_int(payload.get(key)) for key in [
                "B01001_012E", "B01001_013E",
                "B01001_036E", "B01001_037E",
            ]),
            "40-49": sum(self._to_int(payload.get(key)) for key in [
                "B01001_014E", "B01001_015E",
                "B01001_038E", "B01001_039E",
            ]),
            "50-59": sum(self._to_int(payload.get(key)) for key in [
                "B01001_016E", "B01001_017E",
                "B01001_040E", "B01001_041E",
            ]),
            "60-69": sum(self._to_int(payload.get(key)) for key in [
                "B01001_018E", "B01001_019E", "B01001_020E", "B01001_021E",
                "B01001_042E", "B01001_043E", "B01001_044E", "B01001_045E",
            ]),
            "70-79": sum(self._to_int(payload.get(key)) for key in [
                "B01001_022E", "B01001_023E",
                "B01001_046E", "B01001_047E",
            ]),
            "80+": sum(self._to_int(payload.get(key)) for key in [
                "B01001_024E", "B01001_025E",
                "B01001_048E", "B01001_049E",
            ]),
        }

        total = sum(raw_counts.values())
        if not total:
            return {bucket: {"count": 0, "share_pct": 0.0} for bucket in raw_counts}

        return {
            bucket: {
                "count": count,
                "share_pct": round((count * 100) / total, 2),
            }
            for bucket, count in raw_counts.items()
        }

    def _calculate_race_demographics(
        self,
        payload: dict[str, Any],
        total_pop: int,
    ) -> dict[str, dict[str, int | float | dict[str, dict[str, int | float]]]]:
        denominator = total_pop if total_pop > 0 else 1

        def cs(count: int) -> dict[str, int | float]:
            return {"count": count, "share_pct": round((count * 100) / denominator, 2)}

        asian_sub = {
            "Asian alone or in combination": cs(self._to_int(payload.get("B02011_001E"))),
            "Non-Hispanic Asian alone": cs(self._to_int(payload.get("B03002_006E"))),
            "Hispanic Asian alone": cs(self._to_int(payload.get("B03002_014E"))),
        }
        for variable, label in self._group_labels_cache.get("B02015", {}).items():
            asian_sub[label] = cs(self._to_int(payload.get(variable)))
        for variable, label in self._group_labels_cache.get("B02018", {}).items():
            asian_sub[label] = cs(self._to_int(payload.get(variable)))

        nhpi_sub = {
            "NHPI alone or in combination": cs(self._to_int(payload.get("B02012_001E"))),
            "Non-Hispanic NHPI alone": cs(self._to_int(payload.get("B03002_007E"))),
            "Hispanic NHPI alone": cs(self._to_int(payload.get("B03002_015E"))),
        }
        for variable, label in self._group_labels_cache.get("B02016", {}).items():
            nhpi_sub[label] = cs(self._to_int(payload.get(variable)))
        for variable, label in self._group_labels_cache.get("B02019", {}).items():
            nhpi_sub[label] = cs(self._to_int(payload.get(variable)))

        race_output = {
            "White": {
                **cs(self._to_int(payload.get("B02001_002E"))),
                "subcategories": {
                    "White alone or in combination": cs(self._to_int(payload.get("B02008_001E"))),
                    "Non-Hispanic White alone": cs(self._to_int(payload.get("B03002_003E"))),
                    "Hispanic White alone": cs(self._to_int(payload.get("B03002_011E"))),
                },
            },
            "Black or African American": {
                **cs(self._to_int(payload.get("B02001_003E"))),
                "subcategories": {
                    "Black alone or in combination": cs(self._to_int(payload.get("B02009_001E"))),
                    "Non-Hispanic Black alone": cs(self._to_int(payload.get("B03002_004E"))),
                    "Hispanic Black alone": cs(self._to_int(payload.get("B03002_012E"))),
                },
            },
            "American Indian or Alaska Native": {
                **cs(self._to_int(payload.get("B02001_004E"))),
                "subcategories": {
                    "AIAN alone or in combination": cs(self._to_int(payload.get("B02010_001E"))),
                    "Non-Hispanic AIAN alone": cs(self._to_int(payload.get("B03002_005E"))),
                    "Hispanic AIAN alone": cs(self._to_int(payload.get("B03002_013E"))),
                },
            },
            "Asian": {
                **cs(self._to_int(payload.get("B02001_005E"))),
                "subcategories": asian_sub,
            },
            "Native Hawaiian or Other Pacific Islander": {
                **cs(self._to_int(payload.get("B02001_006E"))),
                "subcategories": nhpi_sub,
            },
            "Some other race": {
                **cs(self._to_int(payload.get("B02001_007E"))),
                "subcategories": {
                    "Some other race alone or in combination": cs(self._to_int(payload.get("B02013_001E"))),
                    "Non-Hispanic Some other race alone": cs(self._to_int(payload.get("B03002_008E"))),
                    "Hispanic Some other race alone": cs(self._to_int(payload.get("B03002_016E"))),
                },
            },
            "Two or more races": {
                **cs(self._to_int(payload.get("B02001_008E"))),
                "subcategories": {
                    "Non-Hispanic Two or more races": cs(self._to_int(payload.get("B03002_009E"))),
                    "Hispanic Two or more races": cs(self._to_int(payload.get("B03002_017E"))),
                },
            },
            "Hispanic or Latino (any race)": {
                **cs(self._to_int(payload.get("B03002_010E"))),
                "subcategories": {
                    "Hispanic White": cs(self._to_int(payload.get("B03002_011E"))),
                    "Hispanic Black": cs(self._to_int(payload.get("B03002_012E"))),
                    "Hispanic AIAN": cs(self._to_int(payload.get("B03002_013E"))),
                    "Hispanic Asian": cs(self._to_int(payload.get("B03002_014E"))),
                    "Hispanic NHPI": cs(self._to_int(payload.get("B03002_015E"))),
                    "Hispanic Some other race": cs(self._to_int(payload.get("B03002_016E"))),
                    "Hispanic Two or more races": cs(self._to_int(payload.get("B03002_017E"))),
                },
            },
        }

        return self._prune_zero_categories(race_output)

    def _calculate_religion_demographics(
        self,
        total_pop: int,
        geography: Geography,
    ) -> dict[str, dict[str, int | float | dict[str, dict[str, int | float]]]] | None:
        if not self.arda_data_path.exists() or not geography.county_fips or not geography.state_fips:
            return None

        county_fips = f"{geography.state_fips.zfill(2)}{geography.county_fips.zfill(3)}"

        row = self._get_arda_county_row(county_fips)
        if row is None:
            return None

        total_adh = self._to_int(row.get("TOTADH_2020"))
        denominator = total_adh if total_adh > 0 else (total_pop if total_pop > 0 else 1)

        def cs(count: int) -> dict[str, int | float]:
            return {"count": count, "share_pct": round((count * 100) / denominator, 2)}

        # Load ALL religion denominations dynamically from ARDA data
        religion_output: dict[str, dict[str, int | float | dict[str, dict[str, int | float]]]] = {}

        # Iterate through ALL codes in the row that end with "ADH_2020"
        for code, value in row.items():
            if code in {"FIPS", "TOTADH_2020", "TOTCNG_2020", "TOTRATE_2020"}:
                continue
            if not code.endswith("ADH_2020"):
                continue

            count = self._to_int(value)
            if count <= 0:
                continue

            # Extract short code and resolve to full denomination name
            short_code = code.removesuffix("_2020").removesuffix("ADH")
            full_name = self._arda_code_to_name(short_code)
            if not full_name:
                full_name = short_code

            religion_output[full_name] = {
                **cs(count),
                "subcategories": {},
            }

        return self._prune_zero_categories(religion_output)

    def _get_arda_county_row(self, county_fips: str) -> dict[str, str] | None:
        if self._arda_rows_by_fips is None:
            self._arda_rows_by_fips = self._load_arda_rows()

        return self._arda_rows_by_fips.get(county_fips)

    def _load_arda_rows(self) -> dict[str, dict[str, str]]:
        path = self.arda_data_path
        if not path.exists():
            return {}

        if path.suffix.lower() == ".csv":
            return self._load_arda_rows_from_csv(path)

        if path.suffix.lower() == ".xlsx":
            return self._load_arda_rows_from_xlsx(path)

        return {}

    def _load_arda_rows_from_csv(self, path: Path) -> dict[str, dict[str, str]]:
        rows: dict[str, dict[str, str]] = {}
        try:
            with path.open(newline="", encoding="utf-8") as handle:
                reader = csv.DictReader(handle)
                for row in reader:
                    fips = (row.get("FIPS") or row.get("fips") or "").strip()
                    if not fips:
                        continue
                    rows[fips.zfill(5)] = {k: "" if v is None else str(v) for k, v in row.items() if k is not None}
        except OSError:
            return {}

        return rows

    def _load_arda_rows_from_xlsx(self, path: Path) -> dict[str, dict[str, str]]:
        rows_by_fips: dict[str, dict[str, str]] = {}
        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

        with ZipFile(path) as zip_file:
            shared = self._read_shared_strings(zip_file, ns)
            sheet_root = ET.fromstring(zip_file.read("xl/worksheets/sheet1.xml"))
            data_rows = sheet_root.findall('.//a:sheetData/a:row', ns)
            if not data_rows:
                return {}

            headers = self._read_sheet_row(data_rows[0], shared, ns)
            for row in data_rows[1:]:
                values = self._read_sheet_row(row, shared, ns)
                if not values:
                    continue

                row_data = {headers[col]: value for col, value in values.items() if col in headers}
                fips = row_data.get("FIPS", "").strip()
                if not fips:
                    continue
                rows_by_fips[fips.zfill(5)] = row_data

        return rows_by_fips

    def _get_arda_name_map(self) -> dict[str, str]:
        if self._arda_code_name_map is not None:
            return self._arda_code_name_map

        mapping: dict[str, str] = {}
        path = self.arda_mapping_path

        mapping = self._load_arda_name_map_from_codebook_html(self.arda_codebook_path)

        if path.exists():
            try:
                with path.open(newline="", encoding="utf-8") as handle:
                    reader = csv.DictReader(handle)
                    for row in reader:
                        code = (row.get("code") or "").strip().upper()
                        name = (row.get("name") or "").strip()
                        if code and name:
                            mapping.setdefault(code, name)
            except OSError:
                mapping = {}

        if not mapping:
            mapping = self._load_arda_name_map_from_group_detail_xlsx(self.arda_group_detail_path)
            if mapping:
                try:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with path.open("w", newline="", encoding="utf-8") as handle:
                        writer = csv.DictWriter(handle, fieldnames=["code", "name"])
                        writer.writeheader()
                        for code in sorted(mapping):
                            writer.writerow({"code": code, "name": mapping[code]})
                except OSError:
                    pass

        self._arda_code_name_map = mapping
        return mapping

    def _prune_zero_categories(self, categories: dict[str, Any]) -> dict[str, Any]:
        pruned: dict[str, Any] = {}

        for name, entry in categories.items():
            count = self._to_int(entry.get("count"))
            share_pct_value = entry.get("share_pct", 0.0)
            share_pct = float(share_pct_value) if isinstance(share_pct_value, (int, float, str)) else 0.0
            subcategories = entry.get("subcategories", {})
            cleaned_subcategories = {
                sub_name: sub_entry
                for sub_name, sub_entry in subcategories.items()
                if self._to_int(sub_entry.get("count")) > 0
            }

            if count <= 0 and not cleaned_subcategories:
                continue

            pruned[name] = {
                "count": count,
                "share_pct": share_pct,
                "subcategories": cleaned_subcategories,
            }

        return pruned

    def _load_arda_name_map_from_group_detail_xlsx(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}

        ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        try:
            with ZipFile(path) as zip_file:
                shared = self._read_shared_strings(zip_file, ns)
                sheet_root = ET.fromstring(zip_file.read("xl/worksheets/sheet1.xml"))
                data_rows = sheet_root.findall('.//a:sheetData/a:row', ns)
                if not data_rows:
                    return {}

                header_row = self._read_sheet_row(data_rows[0], shared, ns)
                code_column = next((column for column, value in header_row.items() if value == "Group Code"), None)
                name_column = next((column for column, value in header_row.items() if value == "Group Name"), None)
                if not code_column or not name_column:
                    return {}

                mapping: dict[str, str] = {}
                for row in data_rows[1:]:
                    values = self._read_sheet_row(row, shared, ns)
                    code = values.get(code_column, "").strip().upper()
                    name = values.get(name_column, "").strip()
                    if code and name:
                        mapping[code] = name
                return mapping
        except (OSError, KeyError, ET.ParseError, zipfile.BadZipFile):
            return {}

    def _load_arda_name_map_from_codebook_html(self, path: Path) -> dict[str, str]:
        if not path.exists():
            return {}

        try:
            html = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return {}

        mapping: dict[str, str] = {}
        pattern = re.compile(r"\d+\)\s+([A-Z0-9_]+)\s+(.+?)\s+--\s+Total number of Adherents \(2020\) \(\1\)", re.IGNORECASE | re.DOTALL)

        for match in pattern.finditer(html):
            code = match.group(1).strip().upper()
            name = re.sub(r"\s+", " ", match.group(2)).strip()
            if code.endswith("ADH_2020") and name:
                mapping[code.removesuffix("ADH_2020")] = name

        if mapping:
            try:
                self.arda_mapping_path.parent.mkdir(parents=True, exist_ok=True)
                with self.arda_mapping_path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=["code", "name"])
                    writer.writeheader()
                    for code in sorted(mapping):
                        writer.writerow({"code": code, "name": mapping[code]})
            except OSError:
                pass

        return mapping

    def _arda_code_to_name(self, code: str) -> str | None:
        name_map = self._get_arda_name_map()
        return name_map.get(code.upper())

    def _read_shared_strings(self, zip_file: ZipFile, ns: dict[str, str]) -> list[str]:
        if "xl/sharedStrings.xml" not in zip_file.namelist():
            return []

        shared_root = ET.fromstring(zip_file.read("xl/sharedStrings.xml"))
        strings: list[str] = []
        for item in shared_root.findall("a:si", ns):
            text = "".join(node.text or "" for node in item.findall('.//a:t', ns))
            strings.append(text)

        return strings

    def _read_sheet_row(
        self,
        row_node: ET.Element,
        shared_strings: list[str],
        ns: dict[str, str],
    ) -> dict[str, str]:
        values: dict[str, str] = {}
        for cell in row_node.findall("a:c", ns):
            ref = cell.attrib.get("r", "")
            match = re.match(r"[A-Z]+", ref)
            if not match:
                continue

            col = match.group(0)
            cell_type = cell.attrib.get("t")
            value_node = cell.find("a:v", ns)
            if value_node is None or value_node.text is None:
                values[col] = ""
                continue

            raw = value_node.text
            if cell_type == "s":
                idx = self._to_int(raw)
                values[col] = shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
            else:
                values[col] = raw

        return values

    def _build_geography_coverage(self, geography: Geography) -> DemographicProfileResponse.GeographyCoverage:
        if geography.geography_type == "address":
            return DemographicProfileResponse.GeographyCoverage(
                geography_unit="county",
                coverage_id=geography.coverage_id,
                estimated_radius_miles=None,
                explanation="Data is aggregated at county level for the geocoded address. Counties are boundary polygons, so there is no fixed radius.",
            )

        return DemographicProfileResponse.GeographyCoverage(
            geography_unit="zcta",
            coverage_id=geography.coverage_id,
            estimated_radius_miles=None,
            explanation="Data is aggregated for the full ZIP Code Tabulation Area (ZCTA). This is a boundary polygon, so there is no fixed radius.",
        )

    def _income_tier(self, median_income: int | None) -> str:
        if median_income is None:
            return "unknown"
        if median_income < 35000:
            return "low"
        if median_income < 55000:
            return "lower-middle"
        if median_income < 80000:
            return "middle"
        if median_income < 120000:
            return "upper-middle"
        return "high"

    def _primary_language_proxy(self, payload: dict[str, Any]) -> str:
        total = self._to_int(payload.get("B01003_001E"))
        hispanic = self._to_int(payload.get("B03002_010E"))
        if total and hispanic / total >= 0.2:
            return "Spanish"
        return "English"

    def _to_int(self, value: Any) -> int:
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return 0

    def _to_float(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0