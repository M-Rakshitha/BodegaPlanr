from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from collections import deque
from typing import Any
from urllib.parse import urlparse

from fastapi import HTTPException
from pydantic import BaseModel, Field

from app.agents.agent4.models import Agent4Output, Agent4Request, Agent4Recommendation

_JSON_ARRAY_RE = re.compile(r"\[[\s\S]*\]")
_CODE_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)
_BACKEND_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"
_GEMINI_MODEL = "gemini-3.1-flash-lite-preview"
_GEMINI_RATE_LIMIT_PER_MINUTE = 13
_GEMINI_CALL_TIMES: deque[float] = deque()
_GEMINI_RATE_LOCK = threading.Lock()


def _get_env_value(name: str) -> str | None:
    value = os.getenv(name)
    if value:
        return value

    try:
        from dotenv import load_dotenv
    except ImportError:
        return None

    if _BACKEND_ENV_PATH.exists():
        load_dotenv(_BACKEND_ENV_PATH, override=False)
        return os.getenv(name)

    load_dotenv(override=False)
    return os.getenv(name)


class _VendorLookupItem(BaseModel):
    product: str = Field(..., description="Formal product name.")
    suggested_vendor: str = Field(..., description="Real vendor or wholesaler name.")
    vendor_url: str | None = Field(default=None, description="Official vendor website URL.")
    rationale: str = Field(..., description="Why the vendor fits the ZIP code and product.")
    base_wholesale_cost: float = Field(..., description="Estimated wholesale cost in USD.")
    base_margin_pct: float = Field(..., description="Retail margin percentage.")
    base_reorder_trigger: int = Field(..., description="Base reorder trigger quantity.")


class _VendorLookupResponse(BaseModel):
    recommendations: list[_VendorLookupItem]


def _process_requested_items_with_llm(items: list[str], location_zip: str | None) -> list[dict]:
    api_key = _get_env_value("GOOGLE_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=500,
            detail="GOOGLE_API_KEY is required for real vendor lookup in Agent 4.",
        )

    zip_context = (
        f"The store is located near ZIP code {location_zip} in the United States."
        if location_zip
        else "The store location is unknown, so prefer national vendors that clearly deliver to US addresses."
    )

    prompt = _build_vendor_lookup_prompt(
        items=items,
        location_zip=location_zip,
        zip_context=zip_context,
        search_scope="local and nearby vendors first, then regional vendors that can deliver to the ZIP code",
    )

    try:
        from google import genai
        from google.genai import types
    except ImportError as error:
        raise HTTPException(
            status_code=500,
            detail="google-genai is required for grounded vendor lookup.",
        ) from error

    try:
        client = genai.Client(api_key=api_key)
        grounding_tool = types.Tool(googleSearch=types.GoogleSearch())
        config = types.GenerateContentConfig(
            tools=[grounding_tool],
            temperature=0.2,
            responseMimeType="application/json",
            responseSchema=_VendorLookupResponse,
        )
        _acquire_gemini_slot()
        response = client.models.generate_content(
            model=_GEMINI_MODEL,
            contents=prompt,
            config=config,
        )
        parsed = _parse_vendor_response(response, items)
        if parsed:
            return parsed
        raise ValueError("Gemini returned no usable vendor recommendations.")
    except HTTPException:
        raise
    except Exception as error:
        if _is_quota_error(error):
            raise HTTPException(
                status_code=503,
                detail=(
                    "Gemini quota is exhausted for the configured model. "
                    "Wait for quota reset or reduce request volume."
                ),
            ) from error
        raise HTTPException(status_code=500, detail=f"LLM Error: {str(error)}") from error


def _is_quota_error(error: Exception) -> bool:
    text = str(error).lower()
    return "resource_exhausted" in text or "quota exceeded" in text or "429" in text


def _acquire_gemini_slot() -> None:
    now = time.monotonic()
    with _GEMINI_RATE_LOCK:
        while _GEMINI_CALL_TIMES and now - _GEMINI_CALL_TIMES[0] >= 60:
            _GEMINI_CALL_TIMES.popleft()

        if len(_GEMINI_CALL_TIMES) >= _GEMINI_RATE_LIMIT_PER_MINUTE:
            retry_after = max(1, int(60 - (now - _GEMINI_CALL_TIMES[0])))
            raise HTTPException(
                status_code=429,
                detail=(
                    f"Agent 4 Gemini rate limit reached ({_GEMINI_RATE_LIMIT_PER_MINUTE}/minute). "
                    f"Try again in about {retry_after} seconds."
                ),
            )

        _GEMINI_CALL_TIMES.append(now)


def _build_vendor_lookup_prompt(
    items: list[str],
    location_zip: str | None,
    zip_context: str,
    search_scope: str,
) -> str:
    items_payload = json.dumps(items)

    return (
        "You are a procurement analyst for a corner store. "
        f"{zip_context} "
        "For every requested item, find a REAL vendor or wholesaler using grounded web search. "
        f"Search scope: {search_scope}. "
        "Prioritize vendors that are near the ZIP code; if no nearby vendor is found, expand outward and use a farther U.S. vendor that explicitly delivers to that ZIP code. "
        "Do not invent businesses, do not use placeholder names, and do not repeat the same generic wholesaler unless it is the best verified match. "
        "Return ONLY valid JSON with a top-level key named 'recommendations' containing an array of objects. "
        "Each object must have exactly these keys: "
        '"product", "suggested_vendor", "vendor_url", "rationale", "base_wholesale_cost", "base_margin_pct", "base_reorder_trigger". '
        '"vendor_url" must be the official website URL for the vendor whenever possible. '
        '"rationale" must explain why the vendor is a fit for the ZIP code and item, including the delivery or coverage logic. '
        '"base_wholesale_cost" must be a realistic wholesale estimate in USD, "base_margin_pct" must be a sensible retail margin percentage, and '
        '"base_reorder_trigger" must be a whole number. '
        "Use one vendor per requested item. If a closer vendor is unavailable, select a farther vendor only if delivery to the ZIP code is verified.\n\n"
        f"Requested items: {items_payload}\n"
        f"ZIP code: {location_zip or 'unknown'}"
    )


def _parse_vendor_response(response: Any, requested_items: list[str]) -> list[dict]:
    raw_text = getattr(response, "text", None)
    if not raw_text:
        raw_text = _response_text_from_parts(response)

    parsed_items: list[dict[str, Any]] = []
    content = _clean_model_json(str(raw_text))

    try:
        parsed_response = _VendorLookupResponse.model_validate_json(content)
        parsed_items = [item.model_dump() for item in parsed_response.recommendations]
    except Exception:
        parsed = _load_json_value(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("recommendations"), list):
            parsed_items = [item for item in parsed["recommendations"] if isinstance(item, dict)]
        elif isinstance(parsed, list):
            parsed_items = [item for item in parsed if isinstance(item, dict)]
        else:
            raise ValueError("Gemini response was not a JSON object or array.")

    grounding_urls = _extract_grounding_urls(response)
    normalized: list[dict] = []

    for index, item in enumerate(parsed_items):
        product_name = str(item.get("product") or _safe_requested_item(requested_items, index) or "Unknown Item")
        vendor_name = str(item.get("suggested_vendor") or "Unknown Vendor")
        vendor_url = _normalize_url(item.get("vendor_url"))
        if not vendor_url:
            vendor_url = _infer_vendor_url(grounding_urls, vendor_name)

        normalized.append(
            {
                "product": product_name,
                "suggested_vendor": vendor_name,
                "vendor_url": vendor_url,
                "rationale": str(item.get("rationale") or "Real vendor selected using grounded web search."),
                "base_wholesale_cost": _coerce_float(item.get("base_wholesale_cost"), default=2.0),
                "base_margin_pct": _coerce_float(item.get("base_margin_pct"), default=30.0),
                "base_reorder_trigger": _coerce_int(item.get("base_reorder_trigger"), default=10),
            }
        )

    return normalized


def _response_text_from_parts(response: Any) -> str:
    candidates = getattr(response, "candidates", []) or []
    if not candidates:
        return ""

    content = getattr(candidates[0], "content", None)
    parts = getattr(content, "parts", []) or []
    text_parts: list[str] = []

    for part in parts:
        text = getattr(part, "text", None)
        if text:
            text_parts.append(text)

    return "".join(text_parts)


def _clean_model_json(content: str) -> str:
    stripped = _CODE_FENCE_RE.sub("", content.strip())
    match = _JSON_ARRAY_RE.search(stripped)
    if match:
        return match.group(0)
    return stripped


def _load_json_value(content: str) -> Any:
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        match = _JSON_ARRAY_RE.search(content)
        if match:
            return json.loads(match.group(0))
        raise


def _extract_grounding_urls(response: Any) -> list[tuple[str, str]]:
    urls: list[tuple[str, str]] = []
    candidates = getattr(response, "candidates", []) or []
    if not candidates:
        return urls

    metadata = getattr(candidates[0], "grounding_metadata", None)
    chunks = getattr(metadata, "grounding_chunks", []) or []

    for chunk in chunks:
        web = getattr(chunk, "web", None)
        uri = getattr(web, "uri", None)
        title = getattr(web, "title", None)
        normalized = _normalize_url(uri)
        if normalized:
            urls.append((str(title or ""), normalized))

    return urls


def _infer_vendor_url(grounding_urls: list[tuple[str, str]], vendor_name: str) -> str | None:
    vendor_tokens = [token for token in re.split(r"[^a-z0-9]+", vendor_name.lower()) if len(token) >= 3]
    if not vendor_tokens:
        return None

    for title, url in grounding_urls:
        haystack = f"{title} {url}".lower()
        if all(token in haystack for token in vendor_tokens[:2]):
            return url

    for title, url in grounding_urls:
        haystack = f"{title} {url}".lower()
        if any(token in haystack for token in vendor_tokens):
            return url

    return None


def _normalize_url(value: Any) -> str | None:
    if not value:
        return None
    url = str(value).strip()
    if not url:
        return None

    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None

    host = parsed.netloc.lower()
    if not host:
        return None

    return url


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _safe_requested_item(items: list[str], index: int) -> str | None:
    if 0 <= index < len(items):
        return items[index]
    return None


class VendorInventoryRecommender:
    """Agent 4 service that turns demand signals into grounded vendor recommendations."""

    def generate_recommendations(self, request: Agent4Request) -> Agent4Output:
        recommendations = []

        max_demand_multiplier = 1.0
        for holiday in request.holidays:
            if holiday.demand_multiplier > max_demand_multiplier:
                max_demand_multiplier = holiday.demand_multiplier

        strong_categories = [cat for cat in request.categories if cat.score >= 0.3]
        all_items = [cat.category for cat in strong_categories]
        all_items.extend(request.requested_items)
        all_items = list(dict.fromkeys(all_items))

        if not all_items:
            return Agent4Output(recommendations=[])

        grounded_products = _process_requested_items_with_llm(all_items, request.location_zip)
        for prod in grounded_products:
            margin_pct = max(0.0, float(prod.get("base_margin_pct", 30.0)))
            wholesale_cost = float(prod.get("base_wholesale_cost", 2.0))

            if margin_pct >= 100.0:
                suggested_retail_price = round(wholesale_cost * 2, 2)
            else:
                suggested_retail_price = round(wholesale_cost / (1 - margin_pct / 100.0), 2)

            reorder_trigger = max(0, int(prod.get("base_reorder_trigger", 10) * max_demand_multiplier))
            vendor_name = prod.get("suggested_vendor", "National wholesale vendor")
            vendor_url = prod.get("vendor_url", None)
            base_rationale = prod.get(
                "rationale",
                f"Selected using grounded vendor search for ZIP code {request.location_zip}.",
            )

            if max_demand_multiplier > 1.0:
                base_rationale += f" Reorder adjusted for seasonal demand (x{max_demand_multiplier:.2f})."

            recommendations.append(
                Agent4Recommendation(
                    product=prod.get("product", "Unknown Item"),
                    suggested_vendor=vendor_name,
                    vendor_url=vendor_url,
                    wholesale_cost_estimate=wholesale_cost,
                    suggested_retail_price=suggested_retail_price,
                    margin_pct=round(margin_pct, 2),
                    reorder_trigger_units=reorder_trigger,
                    rationale=base_rationale,
                )
            )

        return Agent4Output(recommendations=recommendations)
