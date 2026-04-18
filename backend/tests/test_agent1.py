from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.agents.agent1.service import DemographicProfiler, Geography
from app.main import app


client = TestClient(app)


def test_agent1_profile_requires_input() -> None:
    response = client.post("/agents/agent-1/profile", json={})
    assert response.status_code == 400


def test_age_bucket_helper_counts_expected_ranges() -> None:
    profiler = DemographicProfiler()
    payload = {"B01003_001E": "100"}
    for key in profiler._age_variables():
        payload[key] = "1"

    buckets = profiler._calculate_age_groups(payload)

    assert abs(sum(float(bucket["share_pct"]) for bucket in buckets.values()) - 100.0) <= 0.1
    assert set(buckets) == {
        "0-9",
        "10-19",
        "20-29",
        "30-39",
        "40-49",
        "50-59",
        "60-69",
        "70-79",
        "80+",
    }
    assert all("count" in bucket and "share_pct" in bucket for bucket in buckets.values())


def test_race_demographics_returns_count_and_share() -> None:
    profiler = DemographicProfiler()
    profiler._group_labels_cache = {
        "B02015": {"B02015_021E": "Asian subgroup: South Asian - Asian Indian"},
        "B02016": {"B02016_003E": "NHPI subgroup: Polynesian - Samoan"},
        "B02018": {"B02018_021E": "Asian subgroup (alone or in any combination): South Asian - Asian Indian"},
        "B02019": {"B02019_003E": "NHPI subgroup (alone or in any combination): Polynesian - Samoan"},
    }
    payload = {
        "B02001_002E": "50",
        "B02001_003E": "20",
        "B02001_004E": "5",
        "B02001_005E": "10",
        "B02001_006E": "0",
        "B02001_007E": "7",
        "B02001_008E": "7",
        "B03002_010E": "22",
        "B03002_003E": "45",
        "B03002_014E": "4",
        "B02015_021E": "6",
        "B02016_003E": "0",
        "B02018_021E": "8",
        "B02019_003E": "0",
    }

    race = profiler._calculate_race_demographics(payload, total_pop=100)

    assert race["White"]["count"] == 50
    assert race["White"]["share_pct"] == 50.0
    assert race["White"]["subcategories"]["Non-Hispanic White alone"]["count"] == 45
    assert race["Hispanic or Latino (any race)"]["count"] == 22
    assert race["Hispanic or Latino (any race)"]["share_pct"] == 22.0
    assert race["Hispanic or Latino (any race)"]["subcategories"]["Hispanic Asian"]["count"] == 4
    assert race["Asian"]["subcategories"]["Asian subgroup: South Asian - Asian Indian"]["count"] == 6
    assert race["Asian"]["subcategories"]["Asian subgroup (alone or in any combination): South Asian - Asian Indian"]["count"] == 8
    assert "Native Hawaiian or Other Pacific Islander" not in race


def test_address_profiles_use_county_scope() -> None:
    geography = Geography(display_name="County Example", geography_type="address", state_fips="01", county_fips="001")
    coverage = DemographicProfiler()._build_geography_coverage(geography)

    assert coverage.geography_unit == "county"
    assert coverage.coverage_id == "01-001"
    assert "county" in coverage.explanation.lower()


def test_religion_demographics_uses_readable_names_and_returns_all_nonzero_groups() -> None:
    profiler = DemographicProfiler()
    profiler._get_arda_name_map = lambda: {
        "AMEZ": "African Methodist Episcopal Zion Church",
        "AME": "African Methodist Episcopal Church",
        "FHJ": "Agape Christian Fellowship",
    }
    profiler._get_arda_county_row = lambda county_fips: {
        "TOTADH_2020": "300",
        "EVANADH_2020": "120",
        "MPRTADH_2020": "90",
        "BPRTADH_2020": "0",
        "CATHADH_2020": "40",
        "ORTHADH_2020": "0",
        "OTHADH_2020": "50",
        "AMEZADH_2020": "15",
        "AMEADH_2020": "12",
        "FHJADH_2020": "5",
    }

    geography = Geography(display_name="County Example", geography_type="address", state_fips="01", county_fips="001")
    religion = profiler._calculate_religion_demographics(total_pop=500, geography=geography)

    assert religion is not None
    assert set(religion) == {
        "Evangelical Protestant",
        "Mainline Protestant",
        "Catholic",
        "Other Religions",
        "African Methodist Episcopal Zion Church",
        "African Methodist Episcopal Church",
        "Agape Christian Fellowship",
    }
    assert religion["Evangelical Protestant"]["share_pct"] == 40.0
    assert religion["African Methodist Episcopal Zion Church"]["count"] == 15
    assert religion["African Methodist Episcopal Church"]["count"] == 12
    assert religion["Agape Christian Fellowship"]["count"] == 5
    assert all(entry["subcategories"] == {} for entry in religion.values())