from __future__ import annotations

import asyncio
import html
import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, TypedDict
from urllib.parse import parse_qs, unquote, urlparse, urlunparse

import httpx
from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app.agents.agent4.models import Agent4Output, Agent4Request, Agent4Recommendation
from app.rate_limit import (
    set_gemini_cooldown,
    set_outbound_cooldown,
    wait_for_gemini_slot,
    wait_for_outbound_slot,
)

OPEN_FOOD_FACTS_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
USDA_FOODDATA_SEARCH_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"
NOMINATIM_SEARCH_URL = "https://nominatim.openstreetmap.org/search"
DUCKDUCKGO_HTML_URL = "https://html.duckduckgo.com/html/"
ZIP_LOOKUP_URL = "https://api.zippopotam.us/us/{zip_code}"

REQUEST_TIMEOUT_SECONDS = 8.0
ZIP_LOOKUP_TIMEOUT_SECONDS = 5.0
GEMINI_TIMEOUT_SECONDS = 20.0

MAX_OPEN_FOOD_FACTS_RESULTS = 6
MAX_USDA_RESULTS = 6
MAX_NOMINATIM_RESULTS = 6
MAX_DUCKDUCKGO_RESULTS = 3
MAX_VENDOR_INSPECTIONS = 4

_GEMINI_GATE = asyncio.Semaphore(1)

_GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")
_BACKEND_ENV_PATH = Path(__file__).resolve().parents[3] / ".env"

_ZIP_REGION_MAP = {
    "0": "northeast",
    "1": "northeast",
    "2": "mid_atlantic",
    "3": "southeast",
    "4": "midwest",
    "5": "midwest",
    "6": "midwest",
    "7": "southwest",
    "8": "mountain",
    "9": "west",
}

_BLOCKED_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "linkedin.com",
    "mapquest.com",
    "tripadvisor.com",
    "twitter.com",
    "x.com",
    "yelp.com",
    "yellowpages.com",
}

_ZIP_CACHE: dict[str, "_ZipContext"] = {}
_OPEN_FOOD_FACTS_CACHE: dict[str, "_ProductProfile | None"] = {}
_USDA_CACHE: dict[str, "_ProductProfile | None"] = {}

class _GeminiVendorRecommendation(BaseModel):
    product: str
    suggested_vendor: str
    vendor_url: str | None = None
    vendor_address: str | None = None
    vendor_unit_price: float | None = None
    vendor_quantity: str | None = None
    rationale: str = Field(default="")
    base_wholesale_cost: float = Field(default=2.0)
    base_margin_pct: float = Field(default=30.0)
    base_reorder_trigger: int = Field(default=10)


class _GeminiVendorResponse(BaseModel):
    recommendations: list[_GeminiVendorRecommendation] = Field(default_factory=list)


@dataclass(slots=True)
class _ZipContext:
    zip_code: str | None
    city: str | None
    state: str | None
    latitude: float | None
    longitude: float | None
    region: str | None
    label: str


@dataclass(slots=True)
class _ProductProfile:
    item_key: str
    product_name: str
    brand: str | None
    category: str | None
    source: str


@dataclass(slots=True)
class _VendorProfile:
    item_key: str
    suggested_vendor: str
    vendor_url: str | None
    vendor_address: str | None
    vendor_unit_price: float | None
    vendor_quantity: str | None
    data_source: str
    rationale: str
    base_wholesale_cost: float | None = None
    base_margin_pct: float | None = None
    base_reorder_trigger: int | None = None


@dataclass(slots=True)
class _SearchQuery:
    query: str
    scope: str


@dataclass(slots=True)
class _SearchHit:
    title: str
    url: str
    snippet: str


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[_SearchHit] = []
        self._capturing_title = False
        self._capturing_snippet = False
        self._href = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "a":
            classes = attr_map.get("class", "")
            if "result__a" not in classes:
                return
            self._capturing_title = True
            self._href = attr_map.get("href", "")
            self._title_parts = []
            return

        if tag == "div":
            classes = attr_map.get("class", "")
            if "result__snippet" in classes:
                self._capturing_snippet = True
                self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing_title:
            self._title_parts.append(data)
        if self._capturing_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._capturing_snippet:
            snippet = html.unescape("".join(self._snippet_parts).strip())
            self._capturing_snippet = False
            if self.results:
                self.results[-1].snippet = snippet
            return

        if tag == "a" and self._capturing_title:
            title = html.unescape("".join(self._title_parts).strip())
            url = _normalize_result_url(self._href)
            if title and url:
                self.results.append(_SearchHit(title=title, url=url, snippet=""))
            self._capturing_title = False
            self._href = ""
            self._title_parts = []


@dataclass(slots=True)
class _VendorCandidate:
    vendor_name: str
    vendor_url: str | None
    vendor_address: str | None
    score: float
    source_query: str
    source_scope: str
    vendor_unit_price: float | None = None
    vendor_quantity: str | None = None
    distance_miles: float | None = None
    page_summary: str = ""


class _DuckDuckGoResultParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.results: list[_SearchHit] = []
        self._capturing_title = False
        self._capturing_snippet = False
        self._href = ""
        self._title_parts: list[str] = []
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {key: value or "" for key, value in attrs}
        if tag == "a":
            classes = attr_map.get("class", "")
            if "result__a" not in classes:
                return
            self._capturing_title = True
            self._href = attr_map.get("href", "")
            self._title_parts = []
            return

        if tag == "div":
            classes = attr_map.get("class", "")
            if "result__snippet" in classes:
                self._capturing_snippet = True
                self._snippet_parts = []

    def handle_data(self, data: str) -> None:
        if self._capturing_title:
            self._title_parts.append(data)
        if self._capturing_snippet:
            self._snippet_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "div" and self._capturing_snippet:
            snippet = html.unescape("".join(self._snippet_parts).strip())
            self._capturing_snippet = False
            if self.results:
                self.results[-1].snippet = snippet
            return

        if tag == "a" and self._capturing_title:
            title = html.unescape("".join(self._title_parts).strip())
            url = _normalize_result_url(self._href)
            if title and url:
                self.results.append(_SearchHit(title=title, url=url, snippet=""))
            self._capturing_title = False
            self._href = ""
            self._title_parts = []


class _VendorGraphState(TypedDict, total=False):
    request: Agent4Request
    items: list[str]
    category_context: str
    zip_context: _ZipContext
    product_profiles: dict[str, _ProductProfile]
    vendor_profiles: dict[str, _VendorProfile]
    recommendations: list[dict[str, Any]]


def _normalize_text(value: str) -> str:
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    return cleaned


def _normalize_item_key(value: str) -> str:
    return _normalize_text(value).lower()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        key = _normalize_item_key(value)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(_normalize_text(value))
    return output


def _normalize_product_name(item: str) -> str:
    cleaned = _normalize_text(item)
    return cleaned[:1].upper() + cleaned[1:] if cleaned else "Unknown Item"


def _normalize_search_phrase(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9\s]+", " ", str(value).strip())
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or "wholesale"


def _extract_retry_after_seconds(message: str) -> float | None:
    retry_in_match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
    if retry_in_match:
        return float(retry_in_match.group(1))

    retry_after_match = re.search(r"retry[-\s]?after[:\s]+([0-9]+(?:\.[0-9]+)?)", message, flags=re.IGNORECASE)
    if retry_after_match:
        return float(retry_after_match.group(1))

    return None


def _is_rate_limit_error(error: Exception) -> bool:
    text = str(error).lower()
    return "429" in text or "too many requests" in text or "quota" in text or "resource_exhausted" in text


async def _set_global_cooldown_from_error(error: Exception) -> None:
    if not _is_rate_limit_error(error):
        return

    retry_after = _extract_retry_after_seconds(str(error))
    wait_seconds = retry_after if retry_after is not None else 60.0
    wait_seconds = max(1.0, wait_seconds) + 1.0
    await set_outbound_cooldown(wait_seconds)
    await set_gemini_cooldown(wait_seconds)


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


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _candidate_domain(url: str) -> str:
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _is_blocked_domain(url: str) -> bool:
    return _candidate_domain(url) in _BLOCKED_DOMAINS


def _normalize_url(value: Any) -> str | None:
    if not value:
        return None
    url = str(value).strip()
    if not url:
        return None
    if url.startswith("//"):
        url = f"https:{url}"
    if re.match(r"^[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}(/.*)?$", url):
        url = f"https://{url}"
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        return None
    if not parsed.netloc:
        return None
    return urlunparse(parsed._replace(fragment=""))


def _normalize_result_url(url: str) -> str | None:
    normalized = _normalize_url(url)
    if not normalized:
        return None

    parsed = urlparse(normalized)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        query = parse_qs(parsed.query)
        uddg = query.get("uddg", [None])[0]
        if uddg:
            normalized = _normalize_url(unquote(uddg))
    return normalized


def _vendor_name_from_result(title: str, url: str) -> str:
    cleaned = html.unescape(re.sub(r"\s+", " ", title).strip())
    if not cleaned:
        return _candidate_domain(url).removeprefix("www.") or "Verified Vendor"
    pieces = re.split(r"\s*[\|—–-]\s*", cleaned)
    cleaned = pieces[0].strip() if pieces else cleaned
    return cleaned or _candidate_domain(url).removeprefix("www.") or "Verified Vendor"


def _extract_page_signals(page_html: str) -> str:
    title_match = re.search(r"<title[^>]*>(.*?)</title>", page_html, flags=re.IGNORECASE | re.DOTALL)
    description_match = re.search(
        r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
        page_html,
        flags=re.IGNORECASE | re.DOTALL,
    )
    heading_matches = re.findall(r"<h[1-2][^>]*>(.*?)</h[1-2]>", page_html, flags=re.IGNORECASE | re.DOTALL)

    parts: list[str] = []
    if title_match:
        parts.append(html.unescape(re.sub(r"<[^>]+>", " ", title_match.group(1)).strip()))
    if description_match:
        parts.append(html.unescape(re.sub(r"<[^>]+>", " ", description_match.group(1)).strip()))
    if heading_matches:
        parts.append(
            " ".join(
                html.unescape(re.sub(r"<[^>]+>", " ", heading).strip())
                for heading in heading_matches
                if heading
            )
        )
    return re.sub(r"\s+", " ", " ".join(part for part in parts if part)).strip()


def _extract_vendor_listing_details(text: str) -> tuple[float | None, str | None]:
    cleaned = re.sub(r"\s+", " ", text)

    price_match = re.search(r"\$\s*([0-9]+(?:\.[0-9]{2})?)", cleaned)
    if not price_match:
        price_match = re.search(r"(?:price|cost)\s*[:\-]?\s*\$\s*([0-9]+(?:\.[0-9]{2})?)", cleaned, flags=re.IGNORECASE)
    unit_price = float(price_match.group(1)) if price_match else None

    quantity_patterns = [
        r"case of\s+([0-9]+(?:\.[0-9]+)?\s?(?:ct|count|lb|oz|pack|case|bag|bottle|gallon|gal|dozen|each|unit)s?)",
        r"pack of\s+([0-9]+(?:\.[0-9]+)?\s?(?:ct|count|lb|oz|pack|case|bag|bottle|gallon|gal|dozen|each|unit)s?)",
        r"([0-9]+(?:\.[0-9]+)?\s?(?:ct|count|lb|oz|pack|case|bag|bottle|gallon|gal|dozen|each|unit)s?)",
        r"([0-9]+\s*x\s*[0-9]+(?:\.[0-9]+)?\s?(?:oz|lb|g|kg|ml|l|fl oz))",
    ]
    quantity = None
    for pattern in quantity_patterns:
        match = re.search(pattern, cleaned, flags=re.IGNORECASE)
        if match:
            quantity = re.sub(r"\s+", " ", match.group(1)).strip()
            break

    return unit_price, quantity


async def _fetch_verified_vendor_page(url: str) -> tuple[str, float | None, str | None, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers, follow_redirects=True) as client:
            await wait_for_outbound_slot()
            response = await client.get(url)
    except Exception:
        return "", None, None, url

    if response.status_code >= 400:
        return "", None, None, str(response.url)

    text = response.text[:120000]
    page_summary = _extract_page_signals(text)
    unit_price, quantity = _extract_vendor_listing_details(f"{page_summary} {text}")
    return page_summary, unit_price, quantity, str(response.url)


def _classify_item(item: str, category_context: str) -> str:
    text = f"{item} {category_context}".lower()
    if any(word in text for word in ("produce", "fruit", "vegetable", "greens", "lettuce", "berries")):
        return "produce"
    if any(word in text for word in ("beverage", "soda", "juice", "water", "drink", "energy")):
        return "beverage"
    if any(word in text for word in ("snack", "candy", "chips", "cracker", "cookies", "packaged", "pantry")):
        return "packaged"
    if any(word in text for word in ("milk", "dairy", "cheese", "yogurt", "butter", "eggs")):
        return "dairy"
    if any(word in text for word in ("meat", "chicken", "beef", "pork", "seafood", "protein")):
        return "meat"
    if any(word in text for word in ("rice", "grain", "grains", "pasta", "flour", "beans", "lentils", "tortilla", "noodle")):
        return "staple"
    return "general"


def _estimate_wholesale_cost(item: str, category_context: str) -> float:
    category = _classify_item(item, category_context)
    mapping = {
        "produce": 4.25,
        "beverage": 2.65,
        "packaged": 1.95,
        "dairy": 3.35,
        "meat": 5.50,
        "staple": 2.85,
        "general": 2.50,
    }
    return mapping[category]


def _estimate_margin_pct(item: str, category_context: str) -> float:
    category = _classify_item(item, category_context)
    mapping = {
        "produce": 48.0,
        "beverage": 58.0,
        "packaged": 34.0,
        "dairy": 32.0,
        "meat": 28.0,
        "staple": 30.0,
        "general": 30.0,
    }
    return mapping[category]


def _estimate_reorder_trigger(item: str, category_context: str) -> int:
    category = _classify_item(item, category_context)
    mapping = {
        "produce": 8,
        "beverage": 12,
        "packaged": 10,
        "dairy": 8,
        "meat": 6,
        "staple": 10,
        "general": 10,
    }
    return mapping[category]


def _calculate_retail_price(wholesale_cost: float, margin_pct: float) -> float:
    if margin_pct >= 100.0:
        return round(wholesale_cost * 2, 2)
    if margin_pct <= 0.0:
        return round(wholesale_cost, 2)
    return round(wholesale_cost / (1 - margin_pct / 100.0), 2)


def _build_product_context(product_profiles: dict[str, _ProductProfile]) -> str:
    payload = [
        {
            "item": profile.item_key,
            "product_name": profile.product_name,
            "brand": profile.brand,
            "category": profile.category,
            "source": profile.source,
        }
        for profile in product_profiles.values()
    ]
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _build_rationale(
    item: str,
    zip_context: _ZipContext,
    product_source: str | None,
    vendor_source: str,
) -> str:
    if vendor_source == "VerifiedVendor":
        vendor_phrase = f"Verified vendor found on an official US wholesaler page for delivery to {zip_context.label}."
    elif vendor_source == "Gemini":
        vendor_phrase = f"Gemini supplied the vendor after verified wholesaler search did not fully resolve {zip_context.label}."
    else:
        vendor_phrase = f"Vendor found via {vendor_source}."

    if product_source == "OpenFoodFacts":
        product_phrase = "Product data from Open Food Facts."
    elif product_source == "USDA":
        product_phrase = "Product data from USDA FoodData Central."
    else:
        product_phrase = "Product data inferred from the requested item."

    return f"{vendor_phrase} {product_phrase}"


def _product_label_for_item(item: str, profile: _ProductProfile | None) -> str:
    if profile is None:
        return _normalize_product_name(item)

    item_tokens = [token for token in re.split(r"[^a-z0-9]+", item.lower()) if len(token) >= 2]
    product_tokens = [token for token in re.split(r"[^a-z0-9]+", profile.product_name.lower()) if len(token) >= 2]

    if any(token in profile.product_name.lower() for token in item_tokens):
        return profile.product_name
    if any(token in item.lower() for token in product_tokens):
        return profile.product_name
    return _normalize_product_name(item)


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


async def _lookup_zip_context(location_zip: str | None) -> _ZipContext:
    if not location_zip:
        return _ZipContext(
            zip_code=None,
            city=None,
            state=None,
            latitude=None,
            longitude=None,
            region=None,
            label="unknown ZIP",
        )

    zip_digits = re.sub(r"\D", "", location_zip)
    if len(zip_digits) != 5:
        region = _ZIP_REGION_MAP.get(zip_digits[:1]) if zip_digits else None
        label = f"ZIP {location_zip}"
        if region:
            label = f"{label} ({region} region)"
        return _ZipContext(zip_code=zip_digits or None, city=None, state=None, latitude=None, longitude=None, region=region, label=label)

    cached = _ZIP_CACHE.get(zip_digits)
    if cached is not None:
        return cached

    try:
        async with httpx.AsyncClient(timeout=ZIP_LOOKUP_TIMEOUT_SECONDS) as client:
            await wait_for_outbound_slot()
            response = await client.get(ZIP_LOOKUP_URL.format(zip_code=zip_digits))
            response.raise_for_status()
            payload = response.json()
    except Exception:
        region = _ZIP_REGION_MAP.get(zip_digits[:1])
        label = f"ZIP {zip_digits}"
        if region:
            label = f"{label} ({region} region)"
        context = _ZipContext(zip_code=zip_digits, city=None, state=None, latitude=None, longitude=None, region=region, label=label)
        _ZIP_CACHE[zip_digits] = context
        return context

    places = payload.get("places", []) if isinstance(payload, dict) else []
    place = places[0] if places else {}
    city = str(place.get("place name") or "").strip() or None
    state = str(place.get("state abbreviation") or "").strip() or None
    latitude = _safe_float(place.get("latitude"))
    longitude = _safe_float(place.get("longitude"))
    region = _ZIP_REGION_MAP.get(zip_digits[:1])

    if city and state:
        label = f"{city}, {state} (ZIP {zip_digits})"
    elif state:
        label = f"{state} (ZIP {zip_digits})"
    elif region:
        label = f"ZIP {zip_digits} ({region} region)"
    else:
        label = f"ZIP {zip_digits}"

    context = _ZipContext(
        zip_code=zip_digits,
        city=city,
        state=state,
        latitude=latitude,
        longitude=longitude,
        region=region,
        label=label,
    )
    _ZIP_CACHE[zip_digits] = context
    return context


def _build_product_queries(item: str) -> list[str]:
    item_text = _normalize_search_phrase(item)
    return [
        item_text,
        f"{item_text} product",
        f"{item_text} brand",
        f"{item_text} categories",
    ]


async def _search_open_food_facts(item: str, category_context: str) -> _ProductProfile | None:
    cache_key = _normalize_item_key(item)
    cached = _OPEN_FOOD_FACTS_CACHE.get(cache_key)
    if cache_key in _OPEN_FOOD_FACTS_CACHE:
        return cached

    params = {
        "search_terms": item,
        "search_simple": "1",
        "action": "process",
        "json": "1",
        "page_size": "10",
        "fields": "product_name,brands,categories",
        "countries_tags_en": "united-states",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await wait_for_outbound_slot()
            response = await client.get(OPEN_FOOD_FACTS_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        _OPEN_FOOD_FACTS_CACHE[cache_key] = None
        return None

    candidates: list[_ProductProfile] = []
    item_tokens = [token for token in re.split(r"[^a-z0-9]+", item.lower()) if len(token) >= 2]
    for product in payload.get("products", [])[:MAX_OPEN_FOOD_FACTS_RESULTS]:
        product_name = _normalize_text(str(product.get("product_name") or product.get("product_name_en") or ""))
        if not product_name:
            continue
        brand = _normalize_text(str(product.get("brands") or "")) or None
        category = _normalize_text(str(product.get("categories") or "")) or None
        haystack = f"{product_name} {brand or ''} {category or ''}".lower()
        score = 0.0
        for token in item_tokens:
            if token in haystack:
                score += 3.0
        if category_context and any(word in category_context.lower() for word in product_name.lower().split()[:4]):
            score += 1.0
        if score <= 0:
            score = 0.5
        candidates.append(
            _ProductProfile(
                item_key=cache_key,
                product_name=product_name,
                brand=brand,
                category=category,
                source="OpenFoodFacts",
            )
        )

    result = candidates[0] if candidates and candidates[0].product_name else None
    if result is not None:
        best_haystack = f"{result.product_name} {result.brand or ''} {result.category or ''}".lower()
        if not any(token in best_haystack for token in item_tokens):
            result = None
    _OPEN_FOOD_FACTS_CACHE[cache_key] = result
    return result


async def _search_usda_fooddata(item: str) -> _ProductProfile | None:
    cache_key = _normalize_item_key(item)
    cached = _USDA_CACHE.get(cache_key)
    if cache_key in _USDA_CACHE:
        return cached

    params = {
        "query": item,
        "pageSize": "10",
        "api_key": "DEMO_KEY",
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            await wait_for_outbound_slot()
            response = await client.get(USDA_FOODDATA_SEARCH_URL, params=params)
            response.raise_for_status()
            payload = response.json()
    except Exception:
        _USDA_CACHE[cache_key] = None
        return None

    foods = payload.get("foods", []) if isinstance(payload, dict) else []
    if not foods:
        _USDA_CACHE[cache_key] = None
        return None

    item_tokens = [token for token in re.split(r"[^a-z0-9]+", item.lower()) if len(token) >= 2]
    best_profile: _ProductProfile | None = None
    best_score = float("-inf")

    for food in foods[:MAX_USDA_RESULTS]:
        product_name = _normalize_text(str(food.get("description") or ""))
        if not product_name:
            continue
        brand = _normalize_text(str(food.get("brandOwner") or food.get("brandName") or "")) or None
        category = _normalize_text(str(food.get("dataType") or food.get("foodCategory") or "")) or None
        haystack = f"{product_name} {brand or ''} {category or ''}".lower()
        score = 0.0
        for token in item_tokens:
            if token in haystack:
                score += 3.0
        if brand:
            score += 1.0
        if category:
            score += 1.0
        if score > best_score:
            best_score = score
            best_profile = _ProductProfile(
                item_key=cache_key,
                product_name=product_name,
                brand=brand,
                category=category,
                source="USDA",
            )

    if best_profile is not None:
        best_haystack = f"{best_profile.product_name} {best_profile.brand or ''} {best_profile.category or ''}".lower()
        if not any(token in best_haystack for token in item_tokens):
            best_profile = None

    _USDA_CACHE[cache_key] = best_profile
    return best_profile


def _verified_vendor_domains_for_item(item: str) -> list[dict[str, str]]:
    category = _classify_item(item, "")
    if category in {"produce", "dairy", "meat"}:
        return [
            {"name": "Sysco", "domain": "sysco.com"},
            {"name": "US Foods", "domain": "usfoods.com"},
            {"name": "Gordon Food Service", "domain": "gfs.com"},
            {"name": "Restaurant Depot", "domain": "restaurantdepot.com"},
            {"name": "McLane Company", "domain": "mclaneco.com"},
        ]
    if category in {"beverage", "packaged"}:
        return [
            {"name": "US Foods", "domain": "usfoods.com"},
            {"name": "Sysco", "domain": "sysco.com"},
            {"name": "McLane Company", "domain": "mclaneco.com"},
            {"name": "Gordon Food Service", "domain": "gfs.com"},
            {"name": "Dot Foods", "domain": "dotfoods.com"},
        ]
    if category == "staple":
        return [
            {"name": "UNFI", "domain": "unfi.com"},
            {"name": "Dot Foods", "domain": "dotfoods.com"},
            {"name": "US Foods", "domain": "usfoods.com"},
            {"name": "WebstaurantStore", "domain": "webstaurantstore.com"},
            {"name": "FoodServiceDirect", "domain": "foodservicedirect.com"},
        ]
    return [
        {"name": "US Foods", "domain": "usfoods.com"},
        {"name": "Sysco", "domain": "sysco.com"},
        {"name": "UNFI", "domain": "unfi.com"},
        {"name": "Gordon Food Service", "domain": "gfs.com"},
        {"name": "Restaurant Depot", "domain": "restaurantdepot.com"},
    ]


def _build_vendor_queries(item: str, zip_context: _ZipContext) -> list[_SearchQuery]:
    item_text = _normalize_search_phrase(item)
    return [
        _SearchQuery(
            query=f"site:{vendor['domain']} {item_text} wholesale price pack",
            scope="national",
        )
        for vendor in _verified_vendor_domains_for_item(item)
    ]


async def _search_duckduckgo(query: str) -> list[_SearchHit]:
    params = {"q": query, "kl": "us-en"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
        await wait_for_outbound_slot()
        response = await client.get("https://html.duckduckgo.com/html/", params=params)

    if response.status_code == 429:
        await _set_global_cooldown_from_error(httpx.HTTPStatusError("429 Too Many Requests", request=response.request, response=response))
        return []

    response.raise_for_status()
    parser = _DuckDuckGoResultParser()
    parser.feed(response.text)
    return parser.results[:MAX_OPEN_FOOD_FACTS_RESULTS]


async def _search_duckduckgo(query: str) -> list[_SearchHit]:
    params = {"q": query, "kl": "us-en"}
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }

    try:
        async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS, headers=headers) as client:
            await wait_for_outbound_slot()
            response = await client.get(DUCKDUCKGO_HTML_URL, params=params)
    except Exception as error:
        await _set_global_cooldown_from_error(error)
        return []

    if response.status_code == 429:
        await _set_global_cooldown_from_error(httpx.HTTPStatusError("429 Too Many Requests", request=response.request, response=response))
        return []

    response.raise_for_status()
    parser = _DuckDuckGoResultParser()
    parser.feed(response.text)
    return parser.results[:MAX_DUCKDUCKGO_RESULTS]


def _score_web_vendor_candidate(
    title: str,
    url: str,
    query: _SearchQuery,
    item: str,
    zip_context: _ZipContext,
    rank: int,
    page_summary: str = "",
    snippet: str = "",
) -> float:
    haystack = f"{title} {url} {query.query} {page_summary} {snippet}".lower()
    item_tokens = [token for token in re.split(r"[^a-z0-9]+", item.lower()) if len(token) >= 2]

    score = 0.0
    score += 20.0

    for token in item_tokens[:5]:
        if token in haystack:
            score += 5.0

    if any(word in haystack for word in ("wholesale", "distributor", "foodservice", "bulk", "cash and carry", "supplier", "catalog")):
        score += 14.0

    if page_summary:
        page_text = page_summary.lower()
        if any(word in page_text for word in ("wholesale", "distributor", "foodservice", "bulk", "catalog", "shop", "order")):
            score += 8.0
        if any(word in page_text for word in ("deliver", "delivery", "ship", "nationwide", "regional", "local pickup")):
            score += 4.0

    if any(word in haystack for word in ("price", "case", "pack", "count", "ct", "oz", "lb")):
        score += 4.0

    if rank == 0:
        score += 8.0
    elif rank < 3:
        score += 4.0

    if _is_blocked_domain(url):
        score -= 100.0

    return score


async def _search_public_wholesale_vendor(item: str, zip_context: _ZipContext) -> _VendorProfile | None:
    best_candidate: _VendorCandidate | None = None

    async def resolve_query(query: _SearchQuery) -> _VendorCandidate | None:
        try:
            hits = await _search_duckduckgo(query.query)
        except Exception as error:
            await _set_global_cooldown_from_error(error)
            return None

        best_for_query: _VendorCandidate | None = None
        for rank, hit in enumerate(hits):
            if _is_blocked_domain(hit.url):
                continue

            page_summary, unit_price, quantity, final_url = await _fetch_verified_vendor_page(hit.url)
            score = _score_web_vendor_candidate(
                hit.title,
                final_url,
                query,
                item,
                zip_context,
                rank,
                page_summary=page_summary,
                snippet=hit.snippet,
            )
            if unit_price is not None:
                score += 18.0
            if quantity:
                score += 8.0

            candidate = _VendorCandidate(
                vendor_name=_vendor_name_from_result(hit.title, final_url),
                vendor_url=final_url,
                vendor_address=None,
                vendor_unit_price=unit_price,
                vendor_quantity=quantity,
                score=score,
                source_query=query.query,
                source_scope=query.scope,
                page_summary=page_summary,
            )
            if best_for_query is None or candidate.score > best_for_query.score:
                best_for_query = candidate

        return best_for_query

    queries = _build_vendor_queries(item, zip_context)
    results = await asyncio.gather(*[resolve_query(query) for query in queries], return_exceptions=True)
    for result in results:
        if isinstance(result, BaseException) or result is None:
            continue
        if best_candidate is None or result.score > best_candidate.score:
            best_candidate = result

    if best_candidate is None or best_candidate.score <= 0:
        return None

    return _VendorProfile(
        item_key=_normalize_item_key(item),
        suggested_vendor=best_candidate.vendor_name,
        vendor_url=best_candidate.vendor_url,
        vendor_address=best_candidate.vendor_address,
        vendor_unit_price=getattr(best_candidate, "vendor_unit_price", None),
        vendor_quantity=getattr(best_candidate, "vendor_quantity", None),
        data_source="VerifiedVendor",
        rationale=(
            "Verified vendor confirmed from an official US wholesaler page. "
            "Price and quantity were extracted from the vendor listing when available."
        ),
    )


def _extract_place_name(result: dict[str, Any]) -> str:
    namedetails = result.get("namedetails")
    if isinstance(namedetails, dict):
        for key in ("name", "brand", "operator", "alt_name"):
            value = namedetails.get(key)
            if value:
                return _normalize_text(str(value))

    for key in ("name", "display_name"):
        value = result.get(key)
        if value:
            text = _normalize_text(str(value))
            if key == "display_name":
                text = text.split(",")[0].strip()
            if text:
                return text

    return "Verified Vendor"


def _extract_vendor_url_from_result(result: dict[str, Any]) -> str | None:
    extratags = result.get("extratags")
    if not isinstance(extratags, dict):
        return None
    for key in ("website", "contact:website", "url", "contact:url"):
        value = extratags.get(key)
        normalized = _normalize_url(value)
        if normalized:
            return normalized
    return None


def _extract_vendor_address(result: dict[str, Any]) -> str | None:
    display_name = str(result.get("display_name") or "").strip()
    if display_name:
        return display_name

    address = result.get("address")
    if isinstance(address, dict):
        parts = [str(address.get(part) or "").strip() for part in ("house_number", "road", "city", "state", "postcode")]
        parts = [part for part in parts if part]
        if parts:
            return ", ".join(parts)
    return None


def _looks_like_vendor_text(value: str) -> bool:
    lowered = value.lower()
    return any(
        word in lowered
        for word in (
            "wholesale",
            "distributor",
            "foodservice",
            "bulk",
            "supplier",
            "market",
            "foods",
            "foods",
            "cash and carry",
            "warehouse",
            "produce",
            "grocery",
        )
    )


def _distance_miles(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> float | None:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return None

    from math import asin, cos, radians, sin, sqrt

    r = 3958.8
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * r * asin(sqrt(a))


def _score_vendor_candidate(
    result: dict[str, Any],
    query: _SearchQuery,
    item: str,
    zip_context: _ZipContext,
    rank: int,
) -> float:
    vendor_name = _extract_place_name(result)
    display_name = str(result.get("display_name") or "").lower()
    name_text = f"{vendor_name} {display_name} {query.query}".lower()
    item_tokens = [token for token in re.split(r"[^a-z0-9]+", item.lower()) if len(token) >= 2]

    score = 0.0
    if query.scope == "local":
        score += 100.0
    elif query.scope == "regional":
        score += 60.0
    else:
        score += 20.0

    if zip_context.city and zip_context.city.lower() in name_text:
        score += 15.0
    if zip_context.state and zip_context.state.lower() in name_text:
        score += 8.0
    if zip_context.region and zip_context.region in name_text:
        score += 4.0

    for token in item_tokens[:5]:
        if token in name_text:
            score += 4.0

    if any(word in name_text for word in ("wholesale", "distributor", "foodservice", "cash and carry", "bulk", "market", "warehouse")):
        score += 14.0

    if any(word in name_text for word in ("vendor", "supplier", "catalog", "order", "warehouse", "center", "center")):
        score += 6.0

    vendor_url = _extract_vendor_url_from_result(result)
    if vendor_url:
        score += 12.0

    lat = _safe_float(result.get("lat"))
    lon = _safe_float(result.get("lon"))
    distance = _distance_miles(zip_context.latitude, zip_context.longitude, lat, lon)
    if distance is not None:
        score += max(0.0, 24.0 - min(distance, 24.0))

    if rank == 0:
        score += 8.0
    elif rank < 3:
        score += 4.0

    if _is_blocked_domain(vendor_url or ""):
        score -= 100.0

    return score


async def _search_nominatim_vendor(item: str, zip_context: _ZipContext) -> _VendorProfile | None:
    return await _search_public_wholesale_vendor(item, zip_context)


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


def _clean_model_json(content: str) -> str:
    cleaned = content.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if match:
        return match.group(0)
    match = re.search(r"\[[\s\S]*\]", cleaned)
    if match:
        return match.group(0)
    return cleaned


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


def _build_gemini_prompt(
    unresolved_items: list[str],
    zip_context: _ZipContext,
    category_context: str,
    product_profiles: dict[str, _ProductProfile],
) -> str:
    products_payload = json.dumps(
        [
            {
                "item": profile.item_key,
                "product_name": profile.product_name,
                "brand": profile.brand,
                "category": profile.category,
                "source": profile.source,
            }
            for profile in product_profiles.values()
        ],
        ensure_ascii=False,
        indent=2,
    )
    return (
        "You are a procurement analyst for a corner store. "
        f"The store is near {zip_context.label}. "
        f"{category_context} "
        "Open Food Facts, USDA FoodData Central, and verified US wholesaler searches were not enough to fully verify a vendor for some items. "
        "For each unresolved item, find a REAL US wholesale vendor or supplier that sells the item in bulk and can deliver to this ZIP area. "
        "Do not return local-only vendors. Prefer official vendor websites or distributor pages. "
        "Return ONLY valid JSON with a top-level key named 'recommendations'. "
        "Each recommendation must contain exactly these keys: "
        '"product", "suggested_vendor", "vendor_url", "vendor_address", "vendor_unit_price", "vendor_quantity", "rationale", "base_wholesale_cost", "base_margin_pct", "base_reorder_trigger". '
        "Use the vendor's exact listed unit price and quantity whenever possible. "
        "If multiple unresolved items are present, resolve them in one batch and return one object per item. "
        f"Resolved product context:\n{products_payload}\n\n"
        f"Unresolved items:\n{json.dumps(unresolved_items, ensure_ascii=False)}"
    )


def _parse_gemini_response(response: Any, unresolved_items: list[str]) -> list[dict[str, Any]]:
    raw_text = getattr(response, "text", None) or _response_text_from_parts(response)
    content = _clean_model_json(str(raw_text))
    parsed_items: list[dict[str, Any]] = []

    try:
        parsed_response = _GeminiVendorResponse.model_validate_json(content)
        parsed_items = [item.model_dump() for item in parsed_response.recommendations]
    except Exception:
        parsed = json.loads(content)
        if isinstance(parsed, dict) and isinstance(parsed.get("recommendations"), list):
            parsed_items = [item for item in parsed["recommendations"] if isinstance(item, dict)]
        elif isinstance(parsed, list):
            parsed_items = [item for item in parsed if isinstance(item, dict)]
        else:
            raise ValueError("Gemini response was not valid JSON.")

    grounding_urls = _extract_grounding_urls(response)
    normalized: list[dict[str, Any]] = []

    for index, item in enumerate(parsed_items):
        product_name = str(item.get("product") or (unresolved_items[index] if index < len(unresolved_items) else "Unknown Item"))
        vendor_name = str(item.get("suggested_vendor") or "Unknown Vendor")
        vendor_url = _normalize_url(item.get("vendor_url"))
        if not vendor_url:
            vendor_url = _infer_vendor_url(grounding_urls, vendor_name)

        normalized.append(
            {
                "product": product_name,
                "suggested_vendor": vendor_name,
                "vendor_url": vendor_url,
                "vendor_address": str(item.get("vendor_address") or "").strip() or None,
                "vendor_unit_price": _coerce_float(item.get("vendor_unit_price"), 0.0) if item.get("vendor_unit_price") is not None else None,
                "vendor_quantity": str(item.get("vendor_quantity") or "").strip() or None,
                "rationale": str(item.get("rationale") or "Vendor selected using Gemini grounded search."),
                "base_wholesale_cost": _coerce_float(item.get("base_wholesale_cost"), 2.0),
                "base_margin_pct": _coerce_float(item.get("base_margin_pct"), 30.0),
                "base_reorder_trigger": _coerce_int(item.get("base_reorder_trigger"), 10),
            }
        )

    return normalized


async def _resolve_unresolved_items_with_gemini(
    unresolved_items: list[str],
    zip_context: _ZipContext,
    category_context: str,
    product_profiles: dict[str, _ProductProfile],
) -> list[dict[str, Any]]:
    api_key = _get_env_value("GOOGLE_API_KEY")
    if not api_key or not unresolved_items:
        return []

    prompt = _build_gemini_prompt(unresolved_items, zip_context, category_context, product_profiles)

    try:
        from google import genai as google_genai
    except ImportError:
        return []

    try:
        async with _GEMINI_GATE:
            await wait_for_gemini_slot()
            await wait_for_outbound_slot()
            client = google_genai.Client(api_key=api_key)
            grounding_tool = types.Tool(googleSearch=types.GoogleSearch())
            config = types.GenerateContentConfig(
                tools=[grounding_tool],
                temperature=0.2,
                responseMimeType="application/json",
                responseSchema=_GeminiVendorResponse,
                maxOutputTokens=2048,
            )
            response = await asyncio.wait_for(
                asyncio.to_thread(
                    client.models.generate_content,
                    model=_GEMINI_MODEL,
                    contents=prompt,
                    config=config,
                ),
                timeout=GEMINI_TIMEOUT_SECONDS,
            )
    except Exception as error:
        await _set_global_cooldown_from_error(error)
        return []

    try:
        return _parse_gemini_response(response, unresolved_items)
    except Exception as error:
        await _set_global_cooldown_from_error(error)
        return []


def _build_graph():
    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as error:  # pragma: no cover - import guard
        raise RuntimeError("LangGraph is not installed. Install langgraph in the backend environment.") from error

    graph = StateGraph(_VendorGraphState)
    graph.add_node("prepare", _graph_prepare)
    graph.add_node("layer_one_open_food_facts", _graph_open_food_facts)
    graph.add_node("layer_two_usda", _graph_usda)
    graph.add_node("layer_three_osm", _graph_nominatim)
    graph.add_node("layer_four_gemini", _graph_gemini)
    graph.add_node("finalize", _graph_finalize)

    graph.add_edge(START, "prepare")
    graph.add_edge("prepare", "layer_one_open_food_facts")
    graph.add_edge("layer_one_open_food_facts", "layer_two_usda")
    graph.add_edge("layer_two_usda", "layer_three_osm")
    graph.add_edge("layer_three_osm", "layer_four_gemini")
    graph.add_edge("layer_four_gemini", "finalize")
    graph.add_edge("finalize", END)
    return graph.compile()


@lru_cache(maxsize=1)
def _compiled_vendor_graph():
    return _build_graph()


async def _graph_prepare(state: _VendorGraphState) -> dict[str, Any]:
    request = state["request"]
    strong_categories = [cat for cat in request.categories if cat.score >= 0.3]
    items = [cat.category for cat in strong_categories]
    items.extend(request.requested_items)
    items = _dedupe_preserve_order(items)
    zip_context = await _lookup_zip_context(request.location_zip)
    category_context = state.get("category_context") or json.dumps(
        [cat.model_dump() for cat in strong_categories],
        indent=2,
        ensure_ascii=False,
    )
    return {
        "items": items,
        "zip_context": zip_context,
        "category_context": category_context,
        "product_profiles": {},
        "vendor_profiles": {},
    }


async def _graph_open_food_facts(state: _VendorGraphState) -> dict[str, Any]:
    product_profiles = dict(state.get("product_profiles", {}))
    category_context = state.get("category_context", "")

    async def fetch_one(item: str) -> tuple[str, _ProductProfile | None]:
        item_key = _normalize_item_key(item)
        if item_key in product_profiles:
            return item_key, None
        profile = await _search_open_food_facts(item, category_context)
        return item_key, profile

    results = await asyncio.gather(*[fetch_one(item) for item in state.get("items", [])])
    for item_key, profile in results:
        if profile is not None:
            product_profiles[item_key] = profile

    return {"product_profiles": product_profiles}


async def _graph_usda(state: _VendorGraphState) -> dict[str, Any]:
    product_profiles = dict(state.get("product_profiles", {}))

    async def fetch_one(item: str) -> tuple[str, _ProductProfile | None]:
        item_key = _normalize_item_key(item)
        if item_key in product_profiles:
            return item_key, None
        profile = await _search_usda_fooddata(item)
        return item_key, profile

    results = await asyncio.gather(*[fetch_one(item) for item in state.get("items", [])])
    for item_key, profile in results:
        if profile is not None:
            product_profiles[item_key] = profile

    return {"product_profiles": product_profiles}


async def _graph_nominatim(state: _VendorGraphState) -> dict[str, Any]:
    vendor_profiles = dict(state.get("vendor_profiles", {}))
    zip_context = state["zip_context"]

    async def fetch_one(item: str) -> tuple[str, _VendorProfile | None]:
        item_key = _normalize_item_key(item)
        if item_key in vendor_profiles:
            return item_key, None
        profile = await _search_nominatim_vendor(item, zip_context)
        return item_key, profile

    results = await asyncio.gather(*[fetch_one(item) for item in state.get("items", [])])
    for item_key, profile in results:
        if profile is not None:
            vendor_profiles[item_key] = profile

    return {"vendor_profiles": vendor_profiles}


async def _graph_gemini(state: _VendorGraphState) -> dict[str, Any]:
    vendor_profiles = dict(state.get("vendor_profiles", {}))
    unresolved_items = []
    for item in state.get("items", []):
        item_key = _normalize_item_key(item)
        vendor_profile = vendor_profiles.get(item_key)
        if vendor_profile is None:
            unresolved_items.append(item)
            continue
        if vendor_profile.vendor_unit_price is None or not vendor_profile.vendor_quantity:
            unresolved_items.append(item)
    if not unresolved_items:
        return {"vendor_profiles": vendor_profiles}

    gemini_results = await _resolve_unresolved_items_with_gemini(
        unresolved_items,
        state["zip_context"],
        state.get("category_context", ""),
        state.get("product_profiles", {}),
    )

    for item, result in zip(unresolved_items, gemini_results):
        item_key = _normalize_item_key(item)
        vendor_profiles[item_key] = _VendorProfile(
            item_key=item_key,
            suggested_vendor=str(result.get("suggested_vendor") or "Unknown Vendor"),
            vendor_url=_normalize_url(result.get("vendor_url")),
            vendor_address=str(result.get("vendor_address") or "").strip() or None,
            vendor_unit_price=_coerce_float(result.get("vendor_unit_price"), 0.0) if result.get("vendor_unit_price") is not None else None,
            vendor_quantity=str(result.get("vendor_quantity") or "").strip() or None,
            data_source="Gemini",
            rationale=str(result.get("rationale") or "Vendor selected using Gemini grounded search."),
            base_wholesale_cost=_coerce_float(result.get("base_wholesale_cost"), 2.0),
            base_margin_pct=_coerce_float(result.get("base_margin_pct"), 30.0),
            base_reorder_trigger=_coerce_int(result.get("base_reorder_trigger"), 10),
        )

    return {"vendor_profiles": vendor_profiles}


async def _graph_finalize(state: _VendorGraphState) -> dict[str, Any]:
    items = state.get("items", [])
    product_profiles = state.get("product_profiles", {})
    vendor_profiles = state.get("vendor_profiles", {})
    zip_context = state["zip_context"]
    category_context = state.get("category_context", "")

    recommendations: list[dict[str, Any]] = []
    for item in items:
        item_key = _normalize_item_key(item)
        product_profile = product_profiles.get(item_key)
        vendor_profile = vendor_profiles.get(item_key)

        product_name = _product_label_for_item(item, product_profile)
        product_source = product_profile.source if product_profile else None
        vendor_source = vendor_profile.data_source if vendor_profile else "Gemini"

        wholesale_cost = _estimate_wholesale_cost(product_name, category_context)
        margin_pct = _estimate_margin_pct(product_name, category_context)
        reorder_trigger = _estimate_reorder_trigger(product_name, category_context)

        if vendor_profile is not None and vendor_profile.vendor_unit_price is not None:
            wholesale_cost = vendor_profile.vendor_unit_price

        if vendor_profile is not None and vendor_profile.data_source == "Gemini":
            # Gemini already returned estimated pricing, so prefer it when available.
            gemini_cost = vendor_profile.base_wholesale_cost if vendor_profile.base_wholesale_cost is not None else wholesale_cost
            gemini_margin = vendor_profile.base_margin_pct if vendor_profile.base_margin_pct is not None else margin_pct
            gemini_reorder = (
                vendor_profile.base_reorder_trigger if vendor_profile.base_reorder_trigger is not None else reorder_trigger
            )
            wholesale_cost = gemini_cost
            margin_pct = gemini_margin
            reorder_trigger = gemini_reorder

        suggested_retail_price = _calculate_retail_price(wholesale_cost, margin_pct)
        vendor_name = vendor_profile.suggested_vendor if vendor_profile else "Gemini unresolved"
        vendor_url = vendor_profile.vendor_url if vendor_profile else None
        vendor_address = vendor_profile.vendor_address if vendor_profile else None
        vendor_unit_price = vendor_profile.vendor_unit_price if vendor_profile else None
        vendor_quantity = vendor_profile.vendor_quantity if vendor_profile else None
        data_source = vendor_profile.data_source if vendor_profile else "Gemini"

        rationale = _build_rationale(product_name, zip_context, product_source, data_source)
        if vendor_profile is not None and vendor_profile.rationale:
            rationale = f"{vendor_profile.rationale} {rationale}"

        recommendations.append(
            {
                "product": product_name,
                "suggested_vendor": vendor_name,
                "vendor_url": vendor_url,
                "vendor_address": vendor_address,
                "vendor_unit_price": round(wholesale_cost, 2) if wholesale_cost is not None else None,
                "vendor_quantity": vendor_quantity,
                "wholesale_cost_estimate": round(wholesale_cost, 2),
                "suggested_retail_price": suggested_retail_price,
                "margin_pct": round(margin_pct, 2),
                "reorder_trigger_units": reorder_trigger,
                "rationale": rationale,
                "data_source": data_source,
            }
        )

    return {"recommendations": recommendations}


async def _process_requested_items_with_llm(
    items: list[str],
    location_zip: str | None,
    category_context: str = "",
) -> list[dict[str, Any]]:
    deduped_items = [str(item).strip() for item in items if str(item).strip()]
    if not deduped_items:
        return []

    compiled = _compiled_vendor_graph()
    final_state = await compiled.ainvoke(
        {
            "request": Agent4Request(
                categories=[],
                holidays=[],
                location_zip=location_zip,
                requested_items=deduped_items,
            ),
            "category_context": category_context,
        }
    )

    recommendations = final_state.get("recommendations", [])
    if isinstance(recommendations, list):
        return [rec for rec in recommendations if isinstance(rec, dict)]
    return []


class VendorInventoryRecommender:
    """Agent 4 service that turns items and location into grounded vendor recommendations."""

    def generate_recommendations(self, request: Agent4Request) -> Agent4Output:
        return asyncio.run(self.generate_recommendations_async(request))

    async def generate_recommendations_async(self, request: Agent4Request) -> Agent4Output:
        max_demand_multiplier = 1.0
        for holiday in request.holidays:
            if holiday.demand_multiplier > max_demand_multiplier:
                max_demand_multiplier = holiday.demand_multiplier

        strong_categories = [cat for cat in request.categories if cat.score >= 0.3]
        all_items = [cat.category for cat in strong_categories]
        all_items.extend(request.requested_items)
        all_items = _dedupe_preserve_order(all_items)

        if not all_items:
            return Agent4Output(recommendations=[])

        category_context = json.dumps([cat.model_dump() for cat in strong_categories], indent=2, ensure_ascii=False)
        grounded_products = await _process_requested_items_with_llm(all_items, request.location_zip, category_context)

        recommendations: list[Agent4Recommendation] = []
        for prod in grounded_products:
            margin_pct = max(0.0, float(prod.get("margin_pct", prod.get("base_margin_pct", 30.0))))
            wholesale_cost = float(prod.get("wholesale_cost_estimate", prod.get("base_wholesale_cost", 2.0)))
            reorder_trigger = max(
                0,
                int(prod.get("reorder_trigger_units", prod.get("base_reorder_trigger", 10)) * max_demand_multiplier),
            )
            vendor_name = str(prod.get("suggested_vendor", "National wholesale vendor"))
            vendor_url = prod.get("vendor_url")
            vendor_address = prod.get("vendor_address")
            vendor_unit_price = prod.get("vendor_unit_price")
            if vendor_unit_price is not None:
                vendor_unit_price = _coerce_float(vendor_unit_price, wholesale_cost)
            vendor_quantity = prod.get("vendor_quantity")
            data_source = str(prod.get("data_source", "Gemini"))
            base_rationale = str(
                prod.get(
                    "rationale",
                    f"Selected using public vendor discovery for ZIP code {request.location_zip}.",
                )
            )

            if max_demand_multiplier > 1.0:
                base_rationale += f" Reorder adjusted for seasonal demand (x{max_demand_multiplier:.2f})."

            recommendations.append(
                Agent4Recommendation(
                    product=str(prod.get("product", "Unknown Item")),
                    suggested_vendor=vendor_name,
                    vendor_url=vendor_url,
                    vendor_address=vendor_address,
                    vendor_unit_price=round(vendor_unit_price, 2) if vendor_unit_price is not None else None,
                    vendor_quantity=vendor_quantity,
                    wholesale_cost_estimate=round(wholesale_cost, 2),
                    suggested_retail_price=_calculate_retail_price(wholesale_cost, margin_pct),
                    margin_pct=round(margin_pct, 2),
                    reorder_trigger_units=reorder_trigger,
                    rationale=base_rationale,
                    data_source=data_source,
                )
            )

        return Agent4Output(recommendations=recommendations)
