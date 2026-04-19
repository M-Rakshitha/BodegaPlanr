import pytest

from app.agents.agent4.models import Agent4Request, Agent4RequestCategory, Agent4RequestHoliday
import app.agents.agent4.service as service_module


@pytest.fixture(autouse=True)
def mock_llm(monkeypatch):
    async def mock_process_items(items, zip_code, category_context=""):
        results = []
        for item in items:
            results.append({
                "product": f"Processed {item}",
                "suggested_vendor": "Mocked Real Vendor",
                "base_wholesale_cost": 3.00,
                "base_margin_pct": 25.0,
                "base_reorder_trigger": 10
            })
        return results
        
    monkeypatch.setattr(service_module, "_process_requested_items_with_llm", mock_process_items)


def test_agent4_empty_input():
    service = service_module.VendorInventoryRecommender()
    request = Agent4Request(categories=[])
    output = service.generate_recommendations(request)
    
    assert len(output.recommendations) == 0


def test_agent4_normal_input():
    service = service_module.VendorInventoryRecommender()
    request = Agent4Request(
        categories=[
            Agent4RequestCategory(
                category="Asian pantry staples",
                score=0.85,
                rationale="High Asian demographic."
            )
        ]
    )
    output = service.generate_recommendations(request)
    
    assert len(output.recommendations) == 1
    rec = output.recommendations[0]
    assert rec.product == "Processed Asian pantry staples"
    assert rec.suggested_vendor == "Mocked Real Vendor"
    # Base margin is 25.0. No score bump applied to LLM dynamically generated items (we just use base_margin_pct)
    # Wait, the score factor logic was in the deterministic part. In the LLM part we just take what LLM gives.
    assert rec.margin_pct == 25.0
    assert rec.suggested_retail_price == 4.0  # 3.0 / (1 - 0.25)
    assert rec.reorder_trigger_units == 10


def test_agent4_weak_signal_filtered():
    service = service_module.VendorInventoryRecommender()
    request = Agent4Request(
        categories=[
            Agent4RequestCategory(
                category="Snacks & impulse sweets",
                score=0.2, # < 0.3 should be filtered
                rationale="Low demand."
            )
        ]
    )
    output = service.generate_recommendations(request)
    
    assert len(output.recommendations) == 0


def test_agent4_holiday_multiplier():
    service = service_module.VendorInventoryRecommender()
    request = Agent4Request(
        categories=[
            Agent4RequestCategory(
                category="Ready-to-drink beverages",
                score=0.6,
                rationale="Baseline demand."
            )
        ],
        holidays=[
            Agent4RequestHoliday(
                holiday="Summer Heatwave",
                demand_multiplier=1.5
            )
        ]
    )
    output = service.generate_recommendations(request)
    
    assert len(output.recommendations) == 1
    rec = output.recommendations[0]
    
    # reorder trigger should be scaled up
    # Base reorder for mock is 10
    # reorder = 10 * 1.5 = 15
    assert rec.reorder_trigger_units == 15
    assert "Reorder adjusted for seasonal demand" in rec.rationale


def test_agent4_stable_output():
    service = service_module.VendorInventoryRecommender()
    request = Agent4Request(
        categories=[
            Agent4RequestCategory(
                category="Rice & grains",
                score=0.7,
                rationale="Steady demand."
            )
        ]
    )
    output1 = service.generate_recommendations(request)
    output2 = service.generate_recommendations(request)
    
    assert output1.model_dump() == output2.model_dump()


def test_agent4_requested_items():
    service = service_module.VendorInventoryRecommender()
    
    request = Agent4Request(
        categories=[],
        location_zip="11105", 
        requested_items=["milk", "eggs"]
    )
    
    output = service.generate_recommendations(request)
    
    assert len(output.recommendations) == 2
    assert output.recommendations[0].product == "Processed milk"
    assert output.recommendations[0].suggested_vendor == "Mocked Real Vendor"
    
    assert output.recommendations[1].product == "Processed eggs"
    assert output.recommendations[1].suggested_vendor == "Mocked Real Vendor"
