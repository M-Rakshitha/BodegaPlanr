from __future__ import annotations

from fastapi import APIRouter

from .models import BuyingBehaviorRequest, BuyingBehaviorResponse
from .service import BuyingBehaviorSuggester

router = APIRouter(prefix="/agents/agent-2", tags=["agent-2"])
suggester = BuyingBehaviorSuggester()


@router.post("/suggest", response_model=BuyingBehaviorResponse)
async def suggest_buying_behavior(request: BuyingBehaviorRequest) -> BuyingBehaviorResponse:
    return await suggester.suggest(request.profile)