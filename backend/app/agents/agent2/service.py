from __future__ import annotations

import asyncio
import os
import re
from typing import Any, Literal, cast

import httpx

from app.agents.agent1.models import DemographicProfileRequest, DemographicProfileResponse
from app.agents.agent1.service import DemographicProfiler, Geography
from app.rate_limit import (
    set_gemini_cooldown,
    set_outbound_cooldown,
    wait_for_gemini_slot,
    wait_for_outbound_slot,
)

from .models import (
    BuyingBehaviorCategory,
    BuyingBehaviorResponse,
    BuyingBehaviorSignal,
    CoverageStatistics,
    GroupItemSuggestion,
    TopGroupShare,
)

PRIMARY_THRESHOLD = 10.0
SECONDARY_THRESHOLD = 5.0
MAX_CATEGORIES = 6
MAX_SIGNALS = 10
MAX_GROUPS_PER_TYPE = 6
MAX_OFF_QUERIES_PER_GROUP = 2
MAX_QUERY_VARIANTS_PER_QUERY = 1
GEMINI_TIMEOUT_SECONDS = 30.0

ZIP_LOOKUP_URL = "https://api.zippopotam.us/us/{zip_code}"
FCC_COUNTY_LOOKUP_URL = "https://geo.fcc.gov/api/census/block/find"
OPEN_FOOD_FACTS_SEARCH_URL = "https://world.openfoodfacts.org/cgi/search.pl"
OPEN_FOOD_FACTS_LABEL_URL = "https://world.openfoodfacts.org/api/v2/search"
WIKIPEDIA_SUMMARY_URL = "https://en.wikipedia.org/api/rest_v1/page/summary/{title}"
USDA_FOODDATA_URL = "https://api.nal.usda.gov/fdc/v1/foods/search"


class BuyingBehaviorSuggester:
    def _extract_retry_after_seconds(self, message: str) -> float | None:
        retry_in_match = re.search(r"retry in\s+([0-9]+(?:\.[0-9]+)?)s", message, flags=re.IGNORECASE)
        if retry_in_match:
            return float(retry_in_match.group(1))

        retry_delay_match = re.search(r"retry_delay\s*\{\s*seconds:\s*([0-9]+)", message, flags=re.IGNORECASE)
        if retry_delay_match:
            return float(retry_delay_match.group(1))

        return None

    def _is_quota_error(self, message: str) -> bool:
        lowered = message.lower()
        return "resourceexhausted" in lowered or "quota exceeded" in lowered or "429" in lowered

    async def _set_global_cooldown_from_error(self, error: Exception) -> None:
        message = str(error)
        if not self._is_quota_error(message):
            return

        retry_after = self._extract_retry_after_seconds(message)
        wait_seconds = retry_after if retry_after is not None else 60.0
        wait_seconds = max(1.0, wait_seconds) + 1.0
        await set_outbound_cooldown(wait_seconds)
        await set_gemini_cooldown(wait_seconds)

    def _format_gemini_error(self, error: Exception) -> str:
        code = getattr(error, "code", None)
        status = getattr(error, "status", None)
        message = getattr(error, "message", None) or str(error)

        parts: list[str] = []
        if code is not None:
            parts.append(str(code))
        elif isinstance(error, asyncio.TimeoutError):
            parts.append("504")

        if status:
            parts.append(str(status))
        elif isinstance(error, asyncio.TimeoutError):
            parts.append("Gateway Timeout")

        if message:
            parts.append(str(message))
        elif isinstance(error, asyncio.TimeoutError):
            parts.append("Timed out waiting for Gemini API response.")

        return " ".join(parts).strip()

    async def suggest(self, profile: DemographicProfileResponse, progress: Any | None = None) -> BuyingBehaviorResponse:
        async def emit(msg: str) -> None:
            if progress:
                await progress(msg)

        await emit("Analyzing demographic profile...")
        profile = await self._refresh_profile_from_agent1_if_needed(profile)

        religion_data = profile.religion_demographics

        top_races = self._get_top_groups_from_profile_or_demographics(profile.top_races, profile.race_demographics, 10)
        top_religions = self._get_top_groups_from_profile_or_demographics(profile.top_religions, religion_data, 10)
        top_religions = self._dedupe_overlapping_religions(top_religions)

        high_races = [row for row in top_races if row.share_pct >= PRIMARY_THRESHOLD]
        high_religions = [row for row in top_religions if row.share_pct >= SECONDARY_THRESHOLD]

        await emit("Generating search intents...")
        generated_queries = await self._generate_search_intents(high_races, high_religions)
        await emit("Fetching product data...")
        group_item_suggestions, source_links, data_gaps = await self._run_api_loop(
            high_races,
            high_religions,
            generated_queries,
            emit=emit,
        )
        await emit("Synthesizing categories...")
        categories = self._synthesize_categories(group_item_suggestions)
        top_signals = self._build_top_signals(top_races, top_religions)

        if not top_religions:
            data_gaps.append("No religion distribution available from Agent 1 profile.")
        if top_races and not high_races:
            data_gaps.append("No race groups met the primary threshold for item retrieval.")
        if top_religions and not high_religions:
            data_gaps.append("No religion groups met the secondary threshold for item retrieval.")
        if not group_item_suggestions:
            data_gaps.append("No API-backed item results returned for current top groups.")

        # Calculate coverage statistics
        all_groups = high_races + high_religions
        groups_with_data = sum(1 for s in group_item_suggestions if s.all_year_items)
        coverage_stats = CoverageStatistics(
            total_groups_analyzed=len(all_groups),
            groups_with_data=groups_with_data,
            groups_without_data=len(all_groups) - groups_with_data,
            coverage_percentage=round((groups_with_data / len(all_groups) * 100) if all_groups else 0, 1),
        )

        return BuyingBehaviorResponse(
            location=profile.location,
            top_signals=top_signals,
            categories=categories,
            group_item_suggestions=group_item_suggestions,
            data_gaps=data_gaps,
            coverage_statistics=coverage_stats,
        )

    async def _refresh_profile_from_agent1_if_needed(self, profile: DemographicProfileResponse) -> DemographicProfileResponse:
        if profile.top_races and profile.top_religions:
            return profile

        if profile.geography_type != "zip":
            return profile

        zip_code = profile.location.strip()
        if not zip_code.isdigit() or len(zip_code) != 5:
            return profile

        try:
            refreshed = await DemographicProfiler().build_profile(DemographicProfileRequest(zip_code=zip_code))
            return refreshed
        except Exception:
            return profile

    async def _generate_search_intents(
        self,
        high_races: list[TopGroupShare],
        high_religions: list[TopGroupShare],
    ) -> dict[str, list[str]]:
        default_queries: dict[str, list[str]] = {}
        for row in high_races:
            default_queries[row.group] = [f"Top {row.group} grocery staples in USA"]
        for row in high_religions:
            default_queries[row.group] = [f"{row.group} dietary staples USA"]
        return default_queries

    async def _run_api_loop(
        self,
        top_races: list[TopGroupShare],
        top_religions: list[TopGroupShare],
        generated_queries: dict[str, list[str]],
        emit: Any | None = None,
    ) -> tuple[list[GroupItemSuggestion], list[str], list[str]]:
        suggestions: list[GroupItemSuggestion] = []
        source_links: list[str] = []

        # Process religions in parallel
        religion_tasks = []
        for group in top_religions[:MAX_GROUPS_PER_TYPE]:
            task = self._process_religion_group(group, generated_queries)
            religion_tasks.append(task)

        religion_results = await asyncio.gather(*religion_tasks, return_exceptions=True)

        for result in religion_results:
            if isinstance(result, BaseException):
                continue
            suggestion, links, _gap = cast(tuple[GroupItemSuggestion, list[str], str | None], result)
            suggestions.append(suggestion)
            source_links.extend(links)

        # Process races in parallel
        race_tasks = []
        for group in top_races[:MAX_GROUPS_PER_TYPE]:
            task = self._process_race_group(group, generated_queries)
            race_tasks.append(task)

        race_results = await asyncio.gather(*race_tasks, return_exceptions=True)

        for result in race_results:
            if isinstance(result, BaseException):
                continue
            suggestion, links, _gap = cast(tuple[GroupItemSuggestion, list[str], str | None], result)
            suggestions.append(suggestion)
            source_links.extend(links)

        missing_groups: list[tuple[Literal["race", "religion"], str]] = [
            (suggestion.group_type, suggestion.group)
            for suggestion in suggestions
            if not suggestion.all_year_items
        ]

        batch_results: dict[str, list[str]] = {}
        batch_error: str | None = None
        batch_attempted = False
        if missing_groups:
            if emit:
                await emit(f"Generating AI product suggestions for {len(missing_groups)} group(s)...")
            batch_results, batch_error, batch_attempted = await self._gemini_generate_fallback_items_batch(missing_groups)

        finalized_suggestions: list[GroupItemSuggestion] = []
        finalized_gaps: list[str] = []
        for suggestion in suggestions:
            key = f"{suggestion.group_type}:{suggestion.group}".lower()
            fallback_items = self._dedupe(batch_results.get(key, []))[:10]

            if not suggestion.all_year_items and fallback_items:
                finalized_suggestions.append(
                    suggestion.model_copy(
                        update={
                            "all_year_items": fallback_items,
                            "rationale": (
                                f"Built from Gemini fallback for top {suggestion.group_type} share {suggestion.share_pct:.2f}% "
                                "because OpenFoodFacts/USDA/Wikipedia retrieval was empty."
                            ),
                            "source": "Gemini AI fallback",
                        }
                    )
                )
                continue

            finalized_suggestions.append(suggestion)
            if not suggestion.all_year_items:
                if batch_attempted:
                    finalized_gaps.append(
                        f"No items found for {suggestion.group_type} group '{suggestion.group}' from OpenFoodFacts/USDA/Wikipedia. "
                        f"Gemini fallback failed: {batch_error or 'unknown error'}."
                    )
                else:
                    finalized_gaps.append(
                        f"No items found for {suggestion.group_type} group '{suggestion.group}' from OpenFoodFacts/USDA/Wikipedia."
                    )

        return finalized_suggestions, self._dedupe(source_links), finalized_gaps

    async def _process_religion_group(
        self,
        group: TopGroupShare,
        generated_queries: dict[str, list[str]],
    ) -> tuple[GroupItemSuggestion, list[str], str | None]:
        """Process a single religion group with parallelized API calls."""
        group_lower = group.group.lower()
        label_tag: str | None = None
        if "muslim" in group_lower or "islam" in group_lower:
            label_tag = "en:halal"
        elif "jewish" in group_lower:
            label_tag = "en:kosher"

        all_items: list[str] = []
        local_links: list[str] = []

        # Parallelize the API calls for this group
        tasks = []
        task_names = []
        
        if label_tag:
            tasks.append(self._search_open_food_facts_by_label(label_tag))
            task_names.append("label")
        
        tasks.append(self._fetch_religion_dietary_terms(group.group))
        task_names.append("wiki")
        
        query_candidates = self._religion_query_candidates(group.group, generated_queries)
        tasks.append(
            self._fetch_items_with_query_fallbacks(
                query_candidates,
                max_queries=MAX_OFF_QUERIES_PER_GROUP,
                max_variants=MAX_QUERY_VARIANTS_PER_QUERY,
            )
        )
        task_names.append("off_query")
        
        # Run all initial tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        result_map = dict(zip(task_names, results))
        
        if "label" in result_map:
            result = result_map["label"]
            if not isinstance(result, BaseException):
                products, label_link = cast(tuple[list[str], str], result)
                local_links.append(label_link)
                all_items.extend(products)
        
        wiki_result = result_map["wiki"]
        wiki_terms, wiki_link = ([], None) if isinstance(wiki_result, BaseException) else cast(tuple[list[str], str | None], wiki_result)
        if wiki_link:
            local_links.append(wiki_link)
        
        off_result = result_map["off_query"]
        off_items, off_links = ([], []) if isinstance(off_result, BaseException) else cast(tuple[list[str], list[str]], off_result)
        if off_items:
            all_items.extend(off_items)
        local_links.extend(off_links)
        
        # USDA search based on wiki terms
        if wiki_terms:
            usda_items, usda_link = await self._search_usda_foods(" ".join(wiki_terms[:3]))
            if usda_items:
                all_items.extend(usda_items)
            if usda_link:
                local_links.append(usda_link)

        dedup_items = self._dedupe(all_items)[:10]
        gap: str | None = None

        suggestion = GroupItemSuggestion(
            group_type="religion",
            group=group.group,
            share_pct=group.share_pct,
            count=group.count,
            all_year_items=dedup_items,
            rationale=f"Built from OpenFoodFacts and USDA API calls for top religion share {group.share_pct:.2f}%.",
            source=self._summarize_source_label(local_links, default="OpenFoodFacts + USDA FoodData Central + Wikipedia + Agent 1 demographics"),
            source_links=self._dedupe(local_links),
        )
        
        return suggestion, self._dedupe(local_links), gap

    async def _process_race_group(
        self,
        group: TopGroupShare,
        generated_queries: dict[str, list[str]],
    ) -> tuple[GroupItemSuggestion, list[str], str | None]:
        """Process a single race group with parallelized API calls."""
        all_items: list[str] = []
        local_links: list[str] = []

        race_queries = self._race_query_candidates(group.group, generated_queries)
        usda_keyword = " ".join(race_queries[:3]) if race_queries else "rice beans bread"
        
        # Parallelize the API calls for this group
        off_task = self._fetch_items_with_query_fallbacks(
            race_queries,
            max_queries=MAX_OFF_QUERIES_PER_GROUP,
            max_variants=MAX_QUERY_VARIANTS_PER_QUERY,
        )
        usda_task = self._search_usda_foods(usda_keyword)
        
        results = await asyncio.gather(off_task, usda_task, return_exceptions=True)
        
        # Process OpenFoodFacts results
        off_result = results[0]
        if not isinstance(off_result, BaseException):
            off_items, off_links = cast(tuple[list[str], list[str]], off_result)
            if off_items:
                all_items.extend(off_items)
            local_links.extend(off_links)
        
        # Process USDA results
        usda_result = results[1]
        if not isinstance(usda_result, BaseException):
            usda_items, usda_link = cast(tuple[list[str], str | None], usda_result)
            if usda_items:
                all_items.extend(usda_items)
            if usda_link:
                local_links.append(usda_link)

        dedup_items = self._dedupe(all_items)[:10]
        gap: str | None = None

        suggestion = GroupItemSuggestion(
            group_type="race",
            group=group.group,
            share_pct=group.share_pct,
            count=group.count,
            all_year_items=dedup_items,
            rationale=f"Built from OpenFoodFacts and USDA API calls for top race share {group.share_pct:.2f}%.",
            source=self._summarize_source_label(local_links, default="OpenFoodFacts + USDA FoodData Central + Agent 1 demographics"),
            source_links=self._dedupe(local_links),
        )
        
        return suggestion, self._dedupe(local_links), gap

    async def _search_open_food_facts_by_label(self, label_tag: str) -> tuple[list[str], str]:
        params = {
            "labels_tags": label_tag,
            "countries_tags_en": "united-states",
            "fields": "product_name,brands",
            "page_size": "10",
        }
        link = str(httpx.URL(OPEN_FOOD_FACTS_LABEL_URL, params=params))
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await wait_for_outbound_slot()
                response = await client.get(OPEN_FOOD_FACTS_LABEL_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return [], link

        items: list[str] = []
        for product in payload.get("products", []):
            name = str(product.get("product_name") or "").strip()
            brand = str(product.get("brands") or "").strip()
            if not name:
                continue
            items.append(f"{name} ({brand})" if brand else name)
        return self._dedupe(items)[:5], link

    async def _search_open_food_facts_text(self, query_terms: str) -> tuple[list[str], str]:
        params = {
            "search_terms": query_terms,
            "search_simple": "1",
            "action": "process",
            "json": "1",
            "page_size": "20",
            "fields": "product_name,brands",
            "countries_tags_en": "united-states",
        }
        link = str(httpx.URL(OPEN_FOOD_FACTS_SEARCH_URL, params=params))
        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                await wait_for_outbound_slot()
                response = await client.get(OPEN_FOOD_FACTS_SEARCH_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return [], link

        items: list[str] = []
        relaxed_items: list[str] = []
        for product in payload.get("products", []):
            name = str(product.get("product_name") or "").strip()
            brand = str(product.get("brands") or "").strip()
            if not name:
                continue
            # Keep a relaxed candidate list so we can recover when strict keyword
            # matching yields no hits for niche group labels.
            try:
                name.encode("ascii")
            except UnicodeEncodeError:
                continue
            relaxed_items.append(f"{name} ({brand})" if brand else name)
            if not self._is_reasonable_item_match(name, query_terms):
                continue
            items.append(f"{name} ({brand})" if brand else name)

        dedup_items = self._dedupe(items)
        if dedup_items:
            return dedup_items[:8], link
        return self._dedupe(relaxed_items)[:8], link

    async def _fetch_items_with_query_fallbacks(
        self,
        queries: list[str],
        max_queries: int = 2,
        max_variants: int = 2,
    ) -> tuple[list[str], list[str]]:
        items: list[str] = []
        links: list[str] = []

        for query in queries[:max_queries]:
            if len(items) >= 10:
                break
            variants = self._query_variants(query)[:max_variants]
            variant_items: list[str] = []
            variant_links: list[str] = []
            for variant in variants:
                if len(variant_items) >= 10:
                    break
                result_items, link = await self._search_open_food_facts_text(variant)
                variant_links.append(link)
                if result_items:
                    variant_items.extend(result_items)
            result_items = self._dedupe(variant_items)[:10]
            links.extend(self._dedupe(variant_links))
            if result_items:
                items.extend(result_items)

        return self._dedupe(items)[:10], self._dedupe(links)

    def _extract_llm_text_content(self, response: Any) -> str:
        if response is None:
            return ""

        if isinstance(response, str):
            return response.strip()

        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text_part = part.get("text")
                    if isinstance(text_part, str) and text_part.strip():
                        parts.append(text_part.strip())
                    continue

                text_part = getattr(part, "text", None)
                if isinstance(text_part, str) and text_part.strip():
                    parts.append(text_part.strip())

            if parts:
                return "\n".join(parts).strip()

        if content is not None:
            as_text = str(content).strip()
            if as_text and as_text != "None":
                return as_text

        text_attr = getattr(response, "text", None)
        if isinstance(text_attr, str) and text_attr.strip():
            return text_attr.strip()

        as_text = str(response).strip()
        if as_text and as_text != "None":
            return as_text

        return ""

    async def _search_usda_foods(self, keyword: str) -> tuple[list[str], str | None]:
        api_key = os.getenv("USDA_API_KEY")
        if not api_key:
            return [], None

        params = {
            "query": keyword,
            "api_key": api_key,
            "pageSize": "10",
        }
        link = str(httpx.URL(USDA_FOODDATA_URL, params={"query": keyword}))

        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                await wait_for_outbound_slot()
                response = await client.get(USDA_FOODDATA_URL, params=params)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError):
            return [], link

        foods = payload.get("foods", [])
        items: list[str] = []
        for row in foods:
            desc = str(row.get("description") or "").strip()
            brand = str(row.get("brandOwner") or "").strip()
            if desc:
                items.append(f"{desc} ({brand})" if brand else desc)
        return self._dedupe(items)[:8], link

    def _synthesize_categories(self, suggestions: list[GroupItemSuggestion]) -> list[BuyingBehaviorCategory]:
        sorted_suggestions = sorted(
            suggestions,
            key=lambda suggestion: (suggestion.share_pct, suggestion.count),
            reverse=True,
        )
        categories: list[BuyingBehaviorCategory] = []
        for suggestion in sorted_suggestions:
            if not suggestion.all_year_items:
                continue
            categories.append(
                BuyingBehaviorCategory(
                    category=f"{suggestion.group} all-year inventory",
                    rationale=suggestion.rationale,
                    drivers=[f"Top {suggestion.group_type} group: {suggestion.group} ({suggestion.share_pct:.2f}%)"],
                    evidence=suggestion.all_year_items[:8],
                    source=suggestion.source or self._summarize_source_label(suggestion.source_links, default="OpenFoodFacts + USDA FoodData Central"),
                    source_links=suggestion.source_links,
                )
            )

        return categories[:MAX_CATEGORIES]

    def _query_variants(self, query: str) -> list[str]:
        base = query.strip()
        if not base:
            return []

        variants = [base]
        normalized = re.sub(r"[^a-zA-Z0-9\s]", " ", base)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        if normalized and normalized.lower() != base.lower():
            variants.append(normalized)

        tokens = [token for token in normalized.split() if len(token) >= 3]
        if len(tokens) >= 3:
            variants.append(" ".join(tokens[-3:]))

        return self._dedupe(variants)[:3]

    async def _gemini_generate_fallback_items_batch(
        self,
        groups: list[tuple[Literal["race", "religion"], str]],
    ) -> tuple[dict[str, list[str]], str | None, bool]:
        api_key = os.getenv("GOOGLE_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
        if not api_key:
            return {}, "GOOGLE_API_KEY is not set", False

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as error:
            return {}, f"langchain_google_genai import failed: {error}", False

        unique_groups: list[tuple[Literal["race", "religion"], str]] = []
        seen: set[str] = set()
        for group_type, group_name in groups:
            key = f"{group_type}:{group_name}".lower()
            if key in seen:
                continue
            seen.add(key)
            unique_groups.append((group_type, group_name))

        if not unique_groups:
            return {}, None, False

        group_specs = [{"group_type": group_type, "group": group_name} for group_type, group_name in unique_groups]

        prompt = (
            "Return only valid JSON. No markdown, no explanation. "
            "Format exactly: {\"results\":[{\"group_type\":\"race|religion\",\"group\":\"name\",\"items\":[\"item1\",\"item2\",\"item3\",\"item4\",\"item5\",\"item6\",\"item7\",\"item8\"]}]}. "
            "Each input group must appear exactly once in results. "
            "Each group must have a distinct, group-specific items list. Do not reuse one common list across multiple groups. "
            "Items must be common US year-round grocery items. "
            f"Input groups: {group_specs!r}"
        )

        try:
            llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2, api_key=cast(Any, api_key), max_retries=0)
            await wait_for_gemini_slot()
            await wait_for_outbound_slot()
            
            # Invoke the LLM with a reasonable timeout (90 seconds to account for rate limiting)
            try:
                response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=GEMINI_TIMEOUT_SECONDS)
            except asyncio.TimeoutError as timeout_error:
                return {}, self._format_gemini_error(timeout_error), True
            except Exception as api_error:
                await self._set_global_cooldown_from_error(api_error)
                return {}, self._format_gemini_error(api_error), True
            
            content = self._extract_llm_text_content(response)
            if not content:
                return {}, "Gemini returned empty response (no content extracted)", True
            
            payload = self._parse_llm_json_object(content)

            if not isinstance(payload, dict):
                # Log raw content for debugging (up to 150 chars)
                raw_sample = content[:150] if len(content) > 150 else content
                return {}, f"Gemini returned non-JSON content: {raw_sample}", True

            results_payload = payload.get("results", [])
            if not isinstance(results_payload, list):
                return {}, "Gemini response JSON missing 'results' list", True

            expected_keys = {f"{group_type}:{group_name}".lower() for group_type, group_name in unique_groups}
            grouped_items: dict[str, list[str]] = {}
            for row in results_payload:
                if not isinstance(row, dict):
                    continue
                row_group_type = str(row.get("group_type", "")).strip().lower()
                row_group_name = str(row.get("group", "")).strip()
                if row_group_type not in {"race", "religion"} or not row_group_name:
                    continue
                row_key = f"{row_group_type}:{row_group_name}".lower()
                if row_key not in expected_keys:
                    continue
                items = row.get("items", [])
                if not isinstance(items, list):
                    continue
                parsed_items = [str(item).strip() for item in items if str(item).strip()]
                deduped = self._dedupe(parsed_items)[:10]
                if deduped:
                    grouped_items[row_key] = deduped

            # Reject duplicated/common outputs reused across different groups.
            signature_to_keys: dict[tuple[str, ...], list[str]] = {}
            for key, items in grouped_items.items():
                signature = tuple(item.lower() for item in items)
                signature_to_keys.setdefault(signature, []).append(key)

            duplicate_keys: list[str] = []
            for keys in signature_to_keys.values():
                if len(keys) <= 1:
                    continue
                for duplicate_key in keys[1:]:
                    duplicate_keys.append(duplicate_key)
                    grouped_items.pop(duplicate_key, None)

            if duplicate_keys:
                return grouped_items, (
                    "Gemini returned identical/common item lists for multiple groups: "
                    + ", ".join(sorted(duplicate_keys))
                ), True

            return grouped_items, None, True
        except Exception as error:
            await self._set_global_cooldown_from_error(error)
            return {}, self._format_gemini_error(error), True

    def _parse_llm_json_object(self, text: str) -> dict[str, Any] | None:
        import json
        
        cleaned = (text or "").strip()
        if not cleaned:
            return None

        # Step 1: Try direct parse (handles unwrapped JSON)
        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass

        # Step 2: Remove markdown code blocks
        if cleaned.startswith("```"):
            temp = cleaned.strip("`")
            if temp.lower().startswith("json"):
                temp = temp[4:].strip()
            elif temp.startswith("\n"):
                temp = temp[1:].strip()
            try:
                payload = json.loads(temp)
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                pass

        # Step 3: Extract JSON from text (find first { and last })
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = cleaned[start:end + 1]
            try:
                payload = json.loads(snippet)
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                pass

        # Step 4: Try to find "results" array if it's wrapped differently
        results_idx = cleaned.find('"results"')
        if results_idx != -1:
            # Look backwards for opening {
            start = cleaned.rfind("{", 0, results_idx)
            if start != -1:
                end = cleaned.rfind("}")
                if end != -1 and end > start:
                    snippet = cleaned[start:end + 1]
                    try:
                        payload = json.loads(snippet)
                        return payload if isinstance(payload, dict) else None
                    except json.JSONDecodeError:
                        pass

        return None

    def _dedupe_overlapping_religions(self, groups: list[TopGroupShare]) -> list[TopGroupShare]:
        deduped: list[TopGroupShare] = []
        seen: set[tuple[str, int, float]] = set()

        def normalize(label: str) -> str:
            lowered = label.lower().strip()
            lowered = lowered.replace(" church", "")
            lowered = lowered.replace(" in the usa", "")
            lowered = re.sub(r"\s+", " ", lowered)
            return lowered

        for group in groups:
            key = (normalize(group.group), group.count, round(group.share_pct, 2))
            if key in seen:
                continue
            seen.add(key)
            deduped.append(group)

        return deduped[:10]

    def _religion_query_candidates(self, group: str, generated_queries: dict[str, list[str]]) -> list[str]:
        base = generated_queries.get(group, [f"{group} staple foods USA"])
        lower = group.lower()
        candidates = list(base)

        if "muslim" in lower or "islam" in lower:
            candidates.extend(["halal meat", "halal chicken", "basmati rice", "lentils"])
        elif "jewish" in lower:
            candidates.extend(["kosher bread", "kosher dairy", "kosher snacks"])
        elif "catholic" in lower:
            candidates.extend(["pasta", "olive oil", "canned tuna", "bread"])
        elif "baptist" in lower or "protestant" in lower or "methodist" in lower:
            candidates.extend(["rice", "beans", "bread", "milk", "eggs", "chicken"])
        else:
            candidates.extend(["rice", "beans", "bread", "milk", "eggs"])

        return self._dedupe(candidates)

    def _race_query_candidates(self, group: str, generated_queries: dict[str, list[str]]) -> list[str]:
        base = generated_queries.get(group, [f"{group} staple foods USA"])
        lower = group.lower()

        ambiguous_groups = {
            "white",
            "black or african american",
            "some other race",
            "two or more races",
        }
        candidates = [] if lower in ambiguous_groups else list(base)

        if "asian" in lower:
            candidates.extend(["rice", "noodles", "soy sauce", "tofu", "lentils"])
        elif "hispanic" in lower or "latino" in lower:
            candidates.extend(["tortillas", "beans", "rice", "salsa"])
        elif "black" in lower:
            candidates.extend(["rice", "beans", "chicken", "cornmeal", "oats"])
        else:
            candidates.extend(["rice", "beans", "bread", "milk", "eggs", "oats"])

        return self._dedupe(candidates)

    def _get_top_groups_from_profile_or_demographics(
        self,
        top_groups: list[DemographicProfileResponse.TopGroup] | None,
        demographics: dict[str, DemographicProfileResponse.CategoryDemographic] | None,
        limit: int,
    ) -> list[TopGroupShare]:
        _ = demographics
        if top_groups:
            rows = [
                TopGroupShare(group=item.group, share_pct=round(float(item.share_pct), 2), count=int(item.count))
                for item in top_groups
                if int(item.count) > 0 and float(item.share_pct) > 0
            ]
            rows.sort(key=lambda row: (row.share_pct, row.count), reverse=True)
            return rows[:limit]

        return []

    def _top_groups_from_demographics(
        self,
        demographics: dict[str, DemographicProfileResponse.CategoryDemographic] | None,
        limit: int,
    ) -> list[TopGroupShare]:
        if not demographics:
            return []

        rows: list[TopGroupShare] = []
        for name, entry in demographics.items():
            if isinstance(entry, dict):
                count = int(entry.get("count", 0) or 0)
                share_pct = float(entry.get("share_pct", 0) or 0)
            else:
                count = int(entry.count)
                share_pct = float(entry.share_pct)

            if count <= 0 or share_pct <= 0:
                continue

            rows.append(
                TopGroupShare(group=name, share_pct=round(share_pct, 2), count=count)
            )

        rows.sort(key=lambda row: (row.share_pct, row.count), reverse=True)
        return rows[:limit]

    def _build_top_signals(
        self,
        top_races: list[TopGroupShare],
        top_religions: list[TopGroupShare],
    ) -> list[BuyingBehaviorSignal]:
        signal_rows: list[tuple[Literal["race", "religion"], TopGroupShare]] = []
        signal_rows.extend(("race", row) for row in top_races)
        signal_rows.extend(("religion", row) for row in top_religions)
        signal_rows.sort(key=lambda pair: (pair[1].share_pct, pair[1].count), reverse=True)

        signals: list[BuyingBehaviorSignal] = []
        for dimension, row in signal_rows[:MAX_SIGNALS]:
            confidence: Literal["high", "medium"] = "high" if row.share_pct >= PRIMARY_THRESHOLD else "medium"
            signals.append(
                BuyingBehaviorSignal(
                    dimension=dimension,
                    label=row.group,
                    share_pct=row.share_pct,
                    confidence=confidence,
                    rationale=(
                        f"Top {dimension} group from Agent 1 profile with count {row.count} and share {row.share_pct:.2f}%."
                    ),
                    source="Agent 1 demographic profile",
                )
            )

        return signals

    async def _resolve_state_name(self, profile: DemographicProfileResponse) -> str | None:
        zip_code = profile.location.strip() if profile.geography_type == "zip" else ""
        if not zip_code.isdigit() or len(zip_code) != 5:
            return None

        async with httpx.AsyncClient(timeout=15.0) as client:
            await wait_for_outbound_slot()
            response = await client.get(ZIP_LOOKUP_URL.format(zip_code=zip_code))
            response.raise_for_status()
            payload = response.json()

        places = payload.get("places") or []
        if not places:
            return None

        state = places[0].get("state")
        return str(state).strip() if state else None


    async def _religion_from_zip_arda(
        self,
        zip_code: str,
        total_pop: int,
    ) -> dict[str, DemographicProfileResponse.CategoryDemographic] | None:
        if not zip_code.isdigit() or len(zip_code) != 5:
            return None

        async with httpx.AsyncClient(timeout=15.0) as client:
            await wait_for_outbound_slot()
            zip_response = await client.get(ZIP_LOOKUP_URL.format(zip_code=zip_code))
            zip_response.raise_for_status()
            zip_payload = zip_response.json()

        places = zip_payload.get("places") or []
        if not places:
            return None

        lat = places[0].get("latitude")
        lon = places[0].get("longitude")
        if not lat or not lon:
            return None

        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "showall": "true",
            "format": "json",
        }
        async with httpx.AsyncClient(timeout=15.0) as client:
            await wait_for_outbound_slot()
            fcc_response = await client.get(FCC_COUNTY_LOOKUP_URL, params=params)
            fcc_response.raise_for_status()
            fcc_payload = fcc_response.json()

        county_fips = str(fcc_payload.get("County", {}).get("FIPS", ""))
        if len(county_fips) != 5:
            return None

        profiler = DemographicProfiler()
        geography = Geography(
            display_name=zip_code,
            geography_type="zip",
            state_fips=county_fips[:2],
            county_fips=county_fips[2:],
            zip_code=zip_code,
        )
        return cast(dict[str, DemographicProfileResponse.CategoryDemographic] | None, profiler._calculate_religion_demographics(total_pop=total_pop, geography=geography))

    async def _fetch_religion_dietary_terms(self, religion_group: str) -> tuple[list[str], str | None]:
        title = re.sub(r"\s+", "_", religion_group.strip())
        if not title:
            return [], None

        url = WIKIPEDIA_SUMMARY_URL.format(title=title)
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                await wait_for_outbound_slot()
                response = await client.get(url)
            if response.status_code != 200:
                return [], None
            payload = response.json()
            summary = str(payload.get("extract", "")).lower()
        except (httpx.HTTPError, ValueError):
            return [], None

        terms: list[str] = []
        for token in ["halal", "kosher", "vegetarian", "vegan", "pork", "beef", "lentil", "rice"]:
            if token in summary:
                terms.append(token)
        unique_terms = list(dict.fromkeys(terms))
        return unique_terms[:5], url

    def _dedupe(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            normalized = value.strip()
            if not normalized:
                continue
            key = normalized.lower()
            if key in seen:
                continue
            seen.add(key)
            result.append(normalized)
        return result

    def _summarize_source_label(self, links: list[str], default: str) -> str:
        text = " ".join(links).lower()
        labels: list[str] = []

        if "openfoodfacts" in text:
            labels.append("OpenFoodFacts")
        if "api.nal.usda.gov" in text:
            labels.append("USDA FoodData Central")
        if "wikipedia.org" in text:
            labels.append("Wikipedia")
        if "arda" in text:
            labels.append("ARDA")

        if labels:
            return " + ".join(self._dedupe(labels))

        return default

    def _is_reasonable_item_match(self, item_name: str, query_terms: str) -> bool:
        normalized_name = item_name.strip()
        if not normalized_name:
            return False

        # Reduce noisy/non-localized entries that frequently pollute OFF text search.
        try:
            normalized_name.encode("ascii")
        except UnicodeEncodeError:
            return False

        name_lower = normalized_name.lower()
        if len(name_lower) < 3:
            return False

        stop_words = {
            "and",
            "the",
            "for",
            "with",
            "from",
            "top",
            "usa",
            "us",
            "foods",
            "food",
            "staple",
            "staples",
            "grocery",
            "dietary",
        }
        tokens = [
            token
            for token in re.findall(r"[a-z0-9]+", query_terms.lower())
            if len(token) >= 3 and token not in stop_words
        ]
        if not tokens:
            return True

        return any(token in name_lower for token in tokens)
