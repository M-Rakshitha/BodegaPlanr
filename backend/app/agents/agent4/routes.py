from fastapi import APIRouter

from app.agents.agent4.models import Agent4Request, Agent4Output
from app.agents.agent4.service import VendorInventoryRecommender

router = APIRouter(prefix="/agent4", tags=["Agent 4"])

@router.post("/recommend", response_model=Agent4Output)
def get_agent4_recommendations(request: Agent4Request) -> Agent4Output:
    """
    Standalone endpoint to manually test Agent 4's Vendor Inventory Recommender.
    """
    service = VendorInventoryRecommender()
    return service.generate_recommendations(request)
