from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys

from fastapi.testclient import TestClient

sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.agents.agent1.models import DemographicProfileResponse
from app.agents.agent2 import routes as agent2_routes
from app.agents.agent2.service import BuyingBehaviorSuggester
from app.main import app


client = TestClient(app)


def _load_agent1_sample() -> dict:
    sample_path = (
        Path(__file__).resolve().parents[1]
        / "app"
        / "agents"
        / "agent2"
        / "sample_data"
        / "agent1_profile_20052.json"
    )
    return json.loads(sample_path.read_text())


def test_agent2_route_returns_thresholded_categories() -> None:
    async def fake_refresh(profile: DemographicProfileResponse) -> DemographicProfileResponse:
        payload = profile.model_dump()
        payload["top_races"] = [{"group": "White", "share_pct": 66.11, "count": 1514}]
        payload["top_religions"] = [{"group": "Catholic", "share_pct": 21.0, "count": 81735}]
        return DemographicProfileResponse.model_validate(payload)

    async def fake_religion_from_zip(_zip_code: str, _total_pop: int):
        return None

    async def fake_generate(_high_races, _high_religions):
        return {"White": ["Top White grocery staples in USA"]}

    async def fake_loop(_top_races, _top_religions, _queries):
        from app.agents.agent2.models import GroupItemSuggestion

        return (
            [
                GroupItemSuggestion(
                    group_type="race",
                    group="White",
                    share_pct=66.11,
                    count=1514,
                    all_year_items=["Milk", "Bread", "Eggs"],
                    rationale="API-backed test suggestion",
                    source="OpenFoodFacts + USDA FoodData Central",
                    source_links=["https://example.test/source"],
                )
            ],
            ["https://example.test/source"],
            [],
        )

    agent2_routes.suggester._refresh_profile_from_agent1_if_needed = fake_refresh  # type: ignore[method-assign]
    agent2_routes.suggester._religion_from_zip_arda = fake_religion_from_zip  # type: ignore[method-assign]
    agent2_routes.suggester._generate_search_intents = fake_generate  # type: ignore[method-assign]
    agent2_routes.suggester._run_api_loop = fake_loop  # type: ignore[method-assign]

    response = client.post("/agents/agent-2/suggest", json={"profile": _load_agent1_sample()})

    assert response.status_code == 200
    payload = response.json()
    categories = payload["categories"]

    assert payload["location"] == "20052"
    assert "thresholds" not in payload
    assert categories[0]["category"] == "White all-year inventory"
    assert categories[0]["source"] == "OpenFoodFacts + USDA FoodData Central"
    assert payload["data_sources"][-1] == "https://example.test/source"
    assert payload["group_item_suggestions"][0]["all_year_items"] == ["Milk", "Bread", "Eggs"]
    assert payload["group_item_suggestions"][0]["source"] == "OpenFoodFacts + USDA FoodData Central"
    assert "coverage_statistics" in payload
    assert payload["coverage_statistics"]["total_groups_analyzed"] >= 0


def test_agent2_route_accepts_raw_agent1_payload() -> None:
    async def fake_refresh(profile: DemographicProfileResponse) -> DemographicProfileResponse:
        payload = profile.model_dump()
        payload["top_races"] = [{"group": "Black or African American", "share_pct": 43.26, "count": 290772}]
        payload["top_religions"] = [{"group": "Catholic", "share_pct": 21.0, "count": 81735}]
        return DemographicProfileResponse.model_validate(payload)

    async def fake_generate(_high_races, _high_religions):
        return {}

    async def fake_loop(_top_races, _top_religions, _queries):
        return ([], [], [])

    agent2_routes.suggester._refresh_profile_from_agent1_if_needed = fake_refresh  # type: ignore[method-assign]
    agent2_routes.suggester._generate_search_intents = fake_generate  # type: ignore[method-assign]
    agent2_routes.suggester._run_api_loop = fake_loop  # type: ignore[method-assign]

    response = client.post("/agents/agent-2/suggest", json=_load_agent1_sample())

    assert response.status_code == 200
    payload = response.json()
    assert payload["location"] == _load_agent1_sample()["location"]
    assert "top_races" not in payload
    assert "top_religions" not in payload
    assert "coverage_statistics" in payload
    assert payload["coverage_statistics"]["total_groups_analyzed"] >= 0


def test_agent2_service_uses_agent1_sample_signal_mix() -> None:
    suggester = BuyingBehaviorSuggester()
    profile = DemographicProfileResponse.model_validate(_load_agent1_sample())

    async def fake_refresh(profile: DemographicProfileResponse) -> DemographicProfileResponse:
        payload = profile.model_dump()
        payload["top_races"] = [{"group": "White", "share_pct": 66.11, "count": 1514}]
        payload["top_religions"] = [{"group": "Catholic", "share_pct": 21.0, "count": 81735}]
        return DemographicProfileResponse.model_validate(payload)

    async def fake_religion_from_zip(_zip_code: str, _total_pop: int):
        return None

    async def fake_generate(_high_races, _high_religions):
        return {"White": ["Top White grocery staples in USA"]}

    async def fake_loop(_top_races, _top_religions, _queries):
        from app.agents.agent2.models import GroupItemSuggestion

        return (
            [
                GroupItemSuggestion(
                    group_type="race",
                    group="White",
                    share_pct=66.11,
                    count=1514,
                    all_year_items=["Milk", "Bread", "Eggs"],
                    rationale="API-backed test suggestion",
                    source_links=["https://example.test/source"],
                )
            ],
            ["https://example.test/source"],
            [],
        )

    suggester._refresh_profile_from_agent1_if_needed = fake_refresh  # type: ignore[method-assign]
    suggester._religion_from_zip_arda = fake_religion_from_zip  # type: ignore[method-assign]
    suggester._generate_search_intents = fake_generate  # type: ignore[method-assign]
    suggester._run_api_loop = fake_loop  # type: ignore[method-assign]

    response = asyncio.run(suggester.suggest(profile))

    assert response.top_signals[0].dimension == "race"
    assert response.top_signals[0].label == "White"
    assert response.categories[0].category == "White all-year inventory"
    assert response.categories[0].evidence == ["Milk", "Bread", "Eggs"]
    assert response.coverage_statistics.total_groups_analyzed > 0