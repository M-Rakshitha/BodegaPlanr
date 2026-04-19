from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import os
import re
from typing import Literal
from typing import Any, cast

import httpx

from app.agents.agent1.models import DemographicProfileResponse
from app.rate_limit import (
    set_gemini_cooldown,
    set_outbound_cooldown,
    wait_for_gemini_slot,
    wait_for_outbound_slot,
)

from .models import DemographicsSummary, HolidayCalendarResponse, HolidayDemandEvent

HEBCAL_API_URL = "https://www.hebcal.com/hebcal"
ALADHAN_GREGORIAN_TO_HIJRI_CALENDAR_URL = "https://api.aladhan.com/v1/gToHCalendar/{month}/{year}"
NAGER_PUBLIC_HOLIDAYS_URL = "https://date.nager.at/api/v3/PublicHolidays/{year}/{country_code}"
GEMINI_TIMEOUT_SECONDS = 30.0


@dataclass
class RawHoliday:
    name: str
    tradition: Literal["jewish", "islamic", "christian", "hindu", "sikh", "community"]
    start_date: date
    end_date: date
    source: str
    source_links: list[str]
    demand_categories: list[str] | None = None
    lead_days_override: int | None = None
    base_multiplier_override: float | None = None
    target_religions: list[str] | None = None
    target_races: list[str] | None = None


class ReligiousHolidayCalendarBuilder:
    def __init__(self) -> None:
        self._holiday_duration_days = {
            "Passover": 8,
            "Rosh Hashana": 2,
            "Yom Kippur": 1,
            "Hanukkah": 8,
            "Purim": 2,
            "Ramadan": 30,
            "Eid al-Fitr": 3,
            "Eid al-Adha": 4,
            "Christmas Day": 1,
            "Good Friday": 1,
            "Memorial Day": 1,
            "Juneteenth": 1,
            "Independence Day": 1,
            "Diwali": 5,
            "Holi": 2,
            "Navratri": 9,
            "Vaisakhi": 1,
            "Gurpurab": 1,
            "Labor Day": 1,
            "Thanksgiving": 1,
            "New Year": 1,
            "Easter": 1,
        }

    async def build_calendar(self, profile: DemographicProfileResponse, horizon_days: int = 90) -> HolidayCalendarResponse:
        today = datetime.now(timezone.utc).date()
        window_start = today
        window_end = today + timedelta(days=horizon_days)

        top_religions = self._get_top_religion_rows(profile)
        top_races = self._get_top_race_rows(profile)
        religion_labels_by_tradition = self._build_religion_labels_by_tradition(top_religions)
        race_share_map = {row.group: max(0.0, row.share_pct) for row in top_races}
        country_context = self._country_context(profile)

        tradition_shares = self._infer_tradition_shares(profile)
        candidate_traditions = {
            tradition
            for tradition, share in tradition_shares.items()
            if share > 0 and tradition in {"jewish", "islamic", "christian", "hindu", "sikh"}
        }
        data_gaps: list[str] = []
        sources_used: list[str] = []

        raw_events: list[RawHoliday] = []

        if "jewish" in candidate_traditions:
            hebcal_events, hebcal_error = await self._fetch_hebcal_holidays(window_start, window_end)
            if hebcal_error:
                data_gaps.append(hebcal_error)
            else:
                sources_used.append("Hebcal API")
                raw_events.extend(hebcal_events)

        if "islamic" in candidate_traditions:
            islamic_events, islamic_error = await self._fetch_aladhan_holidays(window_start, window_end)
            if islamic_error:
                data_gaps.append(islamic_error)
            else:
                sources_used.append("Aladhan API")
                raw_events.extend(islamic_events)

        if "christian" in candidate_traditions or bool(top_races):
            public_events, public_error = await self._fetch_nager_holidays(window_start, window_end)
            if public_error:
                data_gaps.append(public_error)
            else:
                sources_used.append("Nager Public Holidays API")
                raw_events.extend(public_events)

        covered_traditions = {event.tradition for event in raw_events}
        gemini_supported_traditions = {"hindu", "sikh", "community"}
        missing_traditions = sorted((candidate_traditions - covered_traditions) & gemini_supported_traditions)
        if missing_traditions:
            ai_events, ai_error, ai_attempted = await self._gemini_generate_holiday_events_batch(
                start=window_start,
                end=window_end,
                traditions=missing_traditions,
                tradition_shares=tradition_shares,
                top_religions=[row.group for row in top_religions],
                top_races=[row.group for row in top_races],
                country_context=country_context,
            )
            if ai_events:
                raw_events.extend(ai_events)
                sources_used.append("Gemini AI fallback")
            elif ai_attempted:
                data_gaps.append(
                    "Gemini holiday fallback failed for missing traditions "
                    + f"{missing_traditions}: {ai_error or 'unknown error'}"
                )

        # If religion data is absent but race data exists, use race-grounded community holiday fallback.
        if not candidate_traditions and top_races:
            community_events, community_error, community_attempted = await self._gemini_generate_holiday_events_batch(
                start=window_start,
                end=window_end,
                traditions=["community"],
                tradition_shares=tradition_shares,
                top_religions=[row.group for row in top_religions],
                top_races=[row.group for row in top_races],
                country_context=country_context,
            )
            if community_events:
                raw_events.extend(community_events)
                sources_used.append("Gemini AI fallback")
            elif community_attempted:
                data_gaps.append(
                    "Gemini community holiday fallback failed for race demographics: "
                    f"{community_error or 'unknown error'}"
                )

        if not tradition_shares:
            data_gaps.append(
                "No religion distribution available from Agent 1 profile; using race-based community holiday fallback when possible."
            )

        raw_events, enrichment_error, enrichment_attempted = await self._enrich_demand_signals_batch(
            events=raw_events,
            top_religions=[row.group for row in top_religions],
            top_races=[row.group for row in top_races],
            country_context=country_context,
        )
        if enrichment_attempted:
            if enrichment_error:
                data_gaps.append(f"Runtime demand enrichment fallback issue: {enrichment_error}")
            else:
                sources_used.append("Gemini demand enrichment API")

        events = self._build_demand_events(
            raw_events=raw_events,
            tradition_shares=tradition_shares,
            religion_labels_by_tradition=religion_labels_by_tradition,
            race_share_map=race_share_map,
            country_context=country_context,
            today=today,
        )
        if not events:
            data_gaps.append(
                "No upcoming holiday events found in the requested horizon for the provided top religion/race demographics."
            )

        return HolidayCalendarResponse(
            location=profile.location,
            generated_at=datetime.now(timezone.utc).isoformat(),
            horizon_days=horizon_days,
            window_start=window_start,
            window_end=window_end,
            demographics_used=DemographicsSummary(
                top_religions_used=[f"{row.group} ({row.share_pct:.2f}%)" for row in top_religions],
                top_races_used=[f"{row.group} ({row.share_pct:.2f}%)" for row in top_races],
                country_context=country_context,
            ),
            events=events,
            data_gaps=data_gaps,
            sources_used=sorted(set(sources_used)),
        )

    def _infer_tradition_shares(self, profile: DemographicProfileResponse) -> dict[str, float]:
        tradition_shares: dict[str, float] = {}

        rows = self._get_top_religion_rows(profile)

        for row in rows:
            tradition = self._classify_tradition(row.group)
            if tradition is None:
                continue
            tradition_shares[tradition] = tradition_shares.get(tradition, 0.0) + max(0.0, row.share_pct)

        return tradition_shares

    def _get_top_religion_rows(self, profile: DemographicProfileResponse) -> list[DemographicProfileResponse.TopGroup]:
        rows = list(profile.top_religions)
        if rows:
            return rows

        if profile.religion_demographics:
            return [
                DemographicProfileResponse.TopGroup(group=group, count=row.count, share_pct=row.share_pct)
                for group, row in profile.religion_demographics.items()
            ]
        return []

    def _get_top_race_rows(self, profile: DemographicProfileResponse) -> list[DemographicProfileResponse.TopGroup]:
        rows = list(profile.top_races)
        if rows:
            return rows

        return [
            DemographicProfileResponse.TopGroup(group=group, count=row.count, share_pct=row.share_pct)
            for group, row in profile.race_demographics.items()
        ]

    def _build_religion_labels_by_tradition(
        self,
        rows: list[DemographicProfileResponse.TopGroup],
    ) -> dict[str, list[str]]:
        by_tradition: dict[str, list[str]] = {
            "jewish": [],
            "islamic": [],
            "christian": [],
            "hindu": [],
            "sikh": [],
            "community": [],
        }

        for row in rows:
            tradition = self._classify_tradition(row.group)
            if tradition is None:
                continue
            by_tradition.setdefault(tradition, []).append(row.group)

        return by_tradition

    def _country_context(self, profile: DemographicProfileResponse) -> str:
        if profile.geography_type == "zip":
            return "United States (ZIP-level context)"
        return "United States (address/county context)"

    def _classify_tradition(self, group_name: str) -> Literal["jewish", "islamic", "christian", "hindu", "sikh", "community"] | None:
        lowered = group_name.lower().strip()

        if any(token in lowered for token in ["jew", "judai"]):
            return "jewish"
        if any(token in lowered for token in ["muslim", "islam", "sunni", "shia"]):
            return "islamic"
        if any(token in lowered for token in ["christ", "catholic", "protestant", "orthodox", "evangelical"]):
            return "christian"
        if "hindu" in lowered:
            return "hindu"
        if "sikh" in lowered:
            return "sikh"
        return None

    async def _fetch_hebcal_holidays(self, start: date, end: date) -> tuple[list[RawHoliday], str | None]:
        years = sorted({start.year, end.year})
        events: list[RawHoliday] = []

        async with httpx.AsyncClient(timeout=12.0) as client:
            for year in years:
                try:
                    await wait_for_outbound_slot()
                    response = await client.get(
                        HEBCAL_API_URL,
                        params={"cfg": "json", "year": year, "maj": "on", "i": "off", "ss": "off", "mf": "off"},
                    )
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    return [], f"Hebcal API error for {year}: {str(error).strip() or 'unknown error'}"

                items = payload.get("items", []) if isinstance(payload, dict) else []
                if not isinstance(items, list):
                    continue

                for item in items:
                    if not isinstance(item, dict):
                        continue
                    title = str(item.get("title", "")).strip()
                    date_str = str(item.get("date", "")).strip()
                    if not title or not date_str:
                        continue

                    holiday_date = self._parse_date(date_str)
                    if holiday_date is None or holiday_date < start or holiday_date > end:
                        continue

                    canonical_name = self._normalize_hebcal_title(title)
                    if canonical_name is None:
                        continue

                    duration = self._holiday_duration_days.get(canonical_name, 1)
                    events.append(
                        RawHoliday(
                            name=canonical_name,
                            tradition="jewish",
                            start_date=holiday_date,
                            end_date=holiday_date + timedelta(days=max(1, int(duration)) - 1),
                            source="Hebcal API",
                            source_links=["https://www.hebcal.com/home/developer-apis"],
                        )
                    )

        return self._dedupe_events(events), None

    async def _fetch_aladhan_holidays(self, start: date, end: date) -> tuple[list[RawHoliday], str | None]:
        months = self._month_year_sequence(start, end)
        events: list[RawHoliday] = []

        async with httpx.AsyncClient(timeout=12.0) as client:
            for year, month in months:
                url = ALADHAN_GREGORIAN_TO_HIJRI_CALENDAR_URL.format(month=month, year=year)
                try:
                    await wait_for_outbound_slot()
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    return [], f"Aladhan API error for {month}/{year}: {str(error).strip() or 'unknown error'}"

                rows = payload.get("data", []) if isinstance(payload, dict) else []
                if not isinstance(rows, list):
                    continue

                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    greg = row.get("gregorian", {})
                    hijri = row.get("hijri", {})
                    if not isinstance(greg, dict) or not isinstance(hijri, dict):
                        continue

                    greg_date = self._parse_date(str(greg.get("date", "")))
                    if greg_date is None or greg_date < start or greg_date > end:
                        continue

                    hijri_day = str(hijri.get("day", "")).strip()
                    hijri_month = hijri.get("month", {}) if isinstance(hijri.get("month", {}), dict) else {}
                    hijri_month_number = str(hijri_month.get("number", "")).strip()

                    event_name: str | None = None
                    duration = 1
                    if hijri_month_number == "9" and hijri_day == "1":
                        event_name = "Ramadan"
                        duration = int(self._holiday_duration_days.get("Ramadan", 30))
                    elif hijri_month_number == "10" and hijri_day == "1":
                        event_name = "Eid al-Fitr"
                        duration = int(self._holiday_duration_days.get("Eid al-Fitr", 3))
                    elif hijri_month_number == "12" and hijri_day == "10":
                        event_name = "Eid al-Adha"
                        duration = int(self._holiday_duration_days.get("Eid al-Adha", 4))

                    if not event_name:
                        continue

                    events.append(
                        RawHoliday(
                            name=event_name,
                            tradition="islamic",
                            start_date=greg_date,
                            end_date=greg_date + timedelta(days=max(1, duration) - 1),
                            source="Aladhan API",
                            source_links=["https://aladhan.com/prayer-times-api"],
                        )
                    )

        return self._dedupe_events(events), None

    async def _fetch_nager_holidays(self, start: date, end: date, country_code: str = "US") -> tuple[list[RawHoliday], str | None]:
        years = sorted({start.year, end.year})
        events: list[RawHoliday] = []

        async with httpx.AsyncClient(timeout=12.0) as client:
            for year in years:
                url = NAGER_PUBLIC_HOLIDAYS_URL.format(year=year, country_code=country_code)
                try:
                    await wait_for_outbound_slot()
                    response = await client.get(url)
                    response.raise_for_status()
                    payload = response.json()
                except Exception as error:
                    return [], f"Nager holiday API error for {year}: {str(error).strip() or 'unknown error'}"

                if not isinstance(payload, list):
                    continue

                for row in payload:
                    if not isinstance(row, dict):
                        continue
                    local_name = str(row.get("localName", "")).strip()
                    holiday_name = str(row.get("name", "")).strip() or local_name
                    holiday_date = self._parse_date(str(row.get("date", "")))
                    if holiday_date is None or holiday_date < start or holiday_date > end:
                        continue

                    mapped = self._normalize_public_holiday_name(holiday_name)
                    if mapped is None:
                        continue
                    canonical_name, mapped_tradition = mapped

                    duration = int(self._holiday_duration_days.get(canonical_name, 1))
                    events.append(
                        RawHoliday(
                            name=canonical_name,
                            tradition=mapped_tradition,
                            start_date=holiday_date,
                            end_date=holiday_date + timedelta(days=max(1, duration) - 1),
                            source="Nager Public Holidays API",
                            source_links=["https://date.nager.at"],
                        )
                    )

        return self._dedupe_events(events), None

    async def _gemini_generate_holiday_events_batch(
        self,
        start: date,
        end: date,
        traditions: list[str],
        tradition_shares: dict[str, float],
        top_religions: list[str],
        top_races: list[str],
        country_context: str,
    ) -> tuple[list[RawHoliday], str | None, bool]:
        api_key = os.getenv("GOOGLE_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
        if not api_key:
            return [], "GOOGLE_API_KEY is not set", False

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as error:
            return [], f"langchain_google_genai import failed: {error}", False

        requested = sorted({tradition.lower().strip() for tradition in traditions if tradition.strip()})
        if not requested:
            return [], None, False

        prompt = (
            "Return only valid JSON. No markdown, no explanations. "
            "Generate upcoming religious/community holidays ONLY within the provided date window. "
            "Format exactly: "
            "{\"results\":[{\"holiday\":\"name\",\"tradition\":\"jewish|islamic|christian|hindu|sikh|community\","
            "\"start_date\":\"YYYY-MM-DD\",\"end_date\":\"YYYY-MM-DD\","
            "\"categories\":[\"item1\",\"item2\"],\"lead_days\":14,\"base_multiplier\":1.6,"
            "\"target_religions\":[\"Demographic label\"],\"target_races\":[\"Demographic label\"]}]}. "
            "Only include traditions from the requested list and make each result relevant to provided demographics. "
            "Do not invent impossible dates outside the window. "
            f"Window start: {start.isoformat()}, window end: {end.isoformat()}. "
            f"Requested traditions: {requested!r}. "
            f"Local tradition shares: {tradition_shares!r}. "
            f"Top religions from Agent 1: {top_religions!r}. "
            f"Top races from Agent 1: {top_races!r}. "
            f"Country context: {country_context}."
        )

        try:
            llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2, api_key=cast(Any, api_key), max_retries=0)
            await wait_for_gemini_slot()
            await wait_for_outbound_slot()

            try:
                response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=GEMINI_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                return [], (
                    "Gemini API timeout: "
                    f"type=TimeoutError, waited={GEMINI_TIMEOUT_SECONDS}s, "
                    "message=no response received before timeout"
                ), True
            except Exception as api_error:
                await self._set_global_cooldown_from_error(api_error)
                return [], f"Gemini API error: {self._format_gemini_error_details(api_error)}", True

            content = self._extract_llm_text_content(response)
            if not content:
                return [], "Gemini returned empty response (no content extracted)", True

            payload = self._parse_llm_json_object(content)
            if not isinstance(payload, dict):
                sample = content[:160] if len(content) > 160 else content
                return [], f"Gemini returned non-JSON content: {sample}", True

            rows = payload.get("results", [])
            if not isinstance(rows, list):
                return [], "Gemini response JSON missing 'results' list", True

            allowed_traditions = {"jewish", "islamic", "christian", "hindu", "sikh", "community"}
            requested_set = set(requested)
            events: list[RawHoliday] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue

                holiday_name = str(row.get("holiday", "")).strip()
                tradition = str(row.get("tradition", "")).strip().lower()
                start_date = self._parse_date(str(row.get("start_date", "")).strip())
                end_date = self._parse_date(str(row.get("end_date", "")).strip())
                categories = row.get("categories", [])
                lead_days_raw = row.get("lead_days", None)
                base_multiplier_raw = row.get("base_multiplier", None)
                target_religions_raw = row.get("target_religions", [])
                target_races_raw = row.get("target_races", [])

                if not holiday_name or tradition not in allowed_traditions or tradition not in requested_set:
                    continue
                if start_date is None or end_date is None:
                    continue
                if start_date > end_date:
                    continue
                if start_date < start or start_date > end:
                    continue

                parsed_categories = []
                if isinstance(categories, list):
                    parsed_categories = [str(item).strip() for item in categories if str(item).strip()][:8]

                parsed_target_religions = []
                if isinstance(target_religions_raw, list):
                    parsed_target_religions = [str(item).strip() for item in target_religions_raw if str(item).strip()][:8]

                parsed_target_races = []
                if isinstance(target_races_raw, list):
                    parsed_target_races = [str(item).strip() for item in target_races_raw if str(item).strip()][:8]

                lead_days: int | None = None
                if isinstance(lead_days_raw, int):
                    lead_days = max(3, min(42, lead_days_raw))

                base_multiplier: float | None = None
                if isinstance(base_multiplier_raw, (int, float)):
                    base_multiplier = max(1.0, min(3.5, float(base_multiplier_raw)))

                events.append(
                    RawHoliday(
                        name=holiday_name,
                        tradition=cast(Literal["jewish", "islamic", "christian", "hindu", "sikh", "community"], tradition),
                        start_date=start_date,
                        end_date=end_date,
                        source="Gemini AI fallback",
                        source_links=[],
                        demand_categories=parsed_categories or None,
                        lead_days_override=lead_days,
                        base_multiplier_override=base_multiplier,
                        target_religions=parsed_target_religions or None,
                        target_races=parsed_target_races or None,
                    )
                )

            return self._dedupe_events(events), None, True
        except Exception as error:
            await self._set_global_cooldown_from_error(error)
            return [], f"Gemini request failed: {self._format_gemini_error_details(error)}", True

    async def _enrich_demand_signals_batch(
        self,
        events: list[RawHoliday],
        top_religions: list[str],
        top_races: list[str],
        country_context: str,
    ) -> tuple[list[RawHoliday], str | None, bool]:
        if not events:
            return events, None, False

        api_key = os.getenv("GOOGLE_API_KEY")
        model_name = os.getenv("GEMINI_MODEL", "gemini-3.1-flash-lite-preview")
        if not api_key:
            return events, "GOOGLE_API_KEY is not set", False

        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
        except ImportError as error:
            return events, f"langchain_google_genai import failed: {error}", False

        event_specs = [
            {
                "holiday": event.name,
                "tradition": event.tradition,
                "start_date": event.start_date.isoformat(),
                "end_date": event.end_date.isoformat(),
            }
            for event in events
        ]

        prompt = (
            "Return only valid JSON. No markdown. "
            "Given these holiday events, provide demand metadata per event. "
            "Format exactly: "
            "{\"results\":[{\"holiday\":\"name\",\"tradition\":\"jewish|islamic|christian|hindu|sikh|community\","
            "\"start_date\":\"YYYY-MM-DD\",\"categories\":[\"item1\",\"item2\",\"item3\"],"
            "\"lead_days\":10,\"base_multiplier\":1.4}]}. "
            "Do not invent new holidays; enrich only input rows. "
            f"Input events: {event_specs!r}. "
            f"Top religions: {top_religions!r}. Top races: {top_races!r}. Country context: {country_context}."
        )

        try:
            llm = ChatGoogleGenerativeAI(model=model_name, temperature=0.2, api_key=cast(Any, api_key), max_retries=0)
            await wait_for_gemini_slot()
            await wait_for_outbound_slot()

            try:
                response = await asyncio.wait_for(llm.ainvoke(prompt), timeout=GEMINI_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                return events, (
                    "Gemini demand enrichment timeout: "
                    f"type=TimeoutError, waited={GEMINI_TIMEOUT_SECONDS}s, "
                    "message=no response received before timeout"
                ), True
            except Exception as api_error:
                await self._set_global_cooldown_from_error(api_error)
                return events, f"Gemini API error: {self._format_gemini_error_details(api_error)}", True

            content = self._extract_llm_text_content(response)
            if not content:
                return events, "Gemini returned empty response (no content extracted)", True

            payload = self._parse_llm_json_object(content)
            if not isinstance(payload, dict):
                sample = content[:160] if len(content) > 160 else content
                return events, f"Gemini returned non-JSON content: {sample}", True

            rows = payload.get("results", [])
            if not isinstance(rows, list):
                return events, "Gemini response JSON missing 'results' list", True

            enrichment_map: dict[tuple[str, str, str], dict[str, Any]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                name = str(row.get("holiday", "")).strip()
                tradition = str(row.get("tradition", "")).strip().lower()
                start_date = str(row.get("start_date", "")).strip()
                if not name or not tradition or not start_date:
                    continue
                enrichment_map[(name.lower(), tradition, start_date)] = row

            enriched_events: list[RawHoliday] = []
            for event in events:
                key = (event.name.lower(), event.tradition, event.start_date.isoformat())
                row = enrichment_map.get(key)
                if not row:
                    enriched_events.append(event)
                    continue

                categories_raw = row.get("categories", [])
                categories = event.demand_categories
                if isinstance(categories_raw, list):
                    parsed = [str(item).strip() for item in categories_raw if str(item).strip()][:8]
                    if parsed:
                        categories = parsed

                lead_days = event.lead_days_override
                lead_raw = row.get("lead_days")
                if isinstance(lead_raw, int):
                    lead_days = max(3, min(42, lead_raw))

                multiplier = event.base_multiplier_override
                mult_raw = row.get("base_multiplier")
                if isinstance(mult_raw, (int, float)):
                    multiplier = max(1.0, min(3.5, float(mult_raw)))

                enriched_events.append(
                    RawHoliday(
                        name=event.name,
                        tradition=event.tradition,
                        start_date=event.start_date,
                        end_date=event.end_date,
                        source=event.source,
                        source_links=event.source_links,
                        demand_categories=categories,
                        lead_days_override=lead_days,
                        base_multiplier_override=multiplier,
                        target_religions=event.target_religions,
                        target_races=event.target_races,
                    )
                )

            return enriched_events, None, True
        except Exception as error:
            await self._set_global_cooldown_from_error(error)
            return events, f"Gemini request failed: {self._format_gemini_error_details(error)}", True

    def _build_demand_events(
        self,
        raw_events: list[RawHoliday],
        tradition_shares: dict[str, float],
        religion_labels_by_tradition: dict[str, list[str]],
        race_share_map: dict[str, float],
        country_context: str,
        today: date,
    ) -> list[HolidayDemandEvent]:
        output: list[HolidayDemandEvent] = []

        top_race_labels = list(race_share_map.keys())

        for event in sorted(raw_events, key=lambda item: (item.start_date, item.name)):
            categories = event.demand_categories or []

            event_duration_days = max(1, (event.end_date - event.start_date).days + 1)
            lead_days = event.lead_days_override if event.lead_days_override is not None else max(3, min(21, event_duration_days * 2))
            base_multiplier = event.base_multiplier_override

            if event.target_religions:
                matched_religions = self._match_demographic_labels(
                    candidates=religion_labels_by_tradition.get(event.tradition, []),
                    hints=event.target_religions,
                )
            else:
                matched_religions = list(religion_labels_by_tradition.get(event.tradition, []))

            if event.target_races:
                matched_races = self._match_demographic_labels(
                    candidates=top_race_labels,
                    hints=event.target_races,
                )
            else:
                # Keep top race context visible even for religion-first events.
                matched_races = top_race_labels[:3]

            if not matched_religions and not matched_races:
                continue

            religion_share = max(0.0, tradition_shares.get(event.tradition, 0.0))
            race_share = sum(max(0.0, race_share_map.get(race, 0.0)) for race in matched_races)
            relevant_share = round(max(religion_share, min(race_share, 100.0)), 2)
            if base_multiplier is None:
                base_multiplier = 1.0 + min(1.2, relevant_share / 50.0)
            estimated_multiplier = self._population_adjusted_multiplier(base_multiplier, relevant_share)
            stock_start = event.start_date - timedelta(days=lead_days)

            demographic_rationale = (
                f"Aligned to religion groups {matched_religions or ['none']} and race groups {matched_races or ['none']} "
                "from Agent 1 top demographics."
            )

            output.append(
                HolidayDemandEvent(
                    holiday=event.name,
                    tradition=event.tradition,
                    start_date=event.start_date,
                    end_date=event.end_date,
                    days_until=(event.start_date - today).days,
                    relevant_population_pct=relevant_share,
                    expected_demand_categories=categories,
                    stock_up_window=(
                        f"Start ordering {lead_days} days prior ({stock_start.isoformat()}); "
                        f"hold elevated stock through {event.end_date.isoformat()}."
                    ),
                    estimated_demand_multiplier=estimated_multiplier,
                    matched_religion_demographics=matched_religions,
                    matched_race_demographics=matched_races,
                    geography_context=country_context,
                    demographic_rationale=demographic_rationale,
                    source=event.source,
                    source_links=event.source_links,
                )
            )

        return output

    def _match_demographic_labels(self, candidates: list[str], hints: list[str]) -> list[str]:
        if not candidates or not hints:
            return []

        matched: list[str] = []
        for candidate in candidates:
            candidate_lower = candidate.lower()
            for hint in hints:
                hint_lower = hint.lower()
                if hint_lower in candidate_lower or candidate_lower in hint_lower:
                    matched.append(candidate)
                    break
        return list(dict.fromkeys(matched))

    def _population_adjusted_multiplier(self, base_multiplier: float, population_pct: float) -> float:
        # Scale holiday intensity by local relevant population share.
        normalized = min(max(population_pct, 0.0), 40.0) / 40.0
        adjusted = 1.0 + (base_multiplier - 1.0) * normalized
        return round(max(1.0, adjusted), 2)

    def _normalize_hebcal_title(self, title: str) -> str | None:
        lowered = title.lower()
        if "passover" in lowered or "pesach" in lowered:
            return "Passover"
        if "rosh hashana" in lowered or "rosh hashanah" in lowered:
            return "Rosh Hashana"
        if "yom kippur" in lowered:
            return "Yom Kippur"
        if "hanukk" in lowered:
            return "Hanukkah"
        if "purim" in lowered:
            return "Purim"
        return None

    def _normalize_public_holiday_name(self, name: str) -> tuple[str, Literal["jewish", "islamic", "christian", "hindu", "sikh", "community"]] | None:
        lowered = name.lower().strip()

        if "good friday" in lowered:
            return "Good Friday", "christian"
        if "christmas" in lowered:
            return "Christmas Day", "christian"
        if "easter" in lowered:
            return "Easter", "christian"

        if "memorial day" in lowered:
            return "Memorial Day", "community"
        if "juneteenth" in lowered:
            return "Juneteenth", "community"
        if "independence day" in lowered:
            return "Independence Day", "community"
        if "labor day" in lowered:
            return "Labor Day", "community"
        if "thanksgiving" in lowered:
            return "Thanksgiving", "community"
        if "new year" in lowered:
            return "New Year", "community"
        return None

    def _month_year_sequence(self, start: date, end: date) -> list[tuple[int, int]]:
        months: list[tuple[int, int]] = []
        current = date(start.year, start.month, 1)
        end_month = date(end.year, end.month, 1)

        while current <= end_month:
            months.append((current.year, current.month))
            if current.month == 12:
                current = date(current.year + 1, 1, 1)
            else:
                current = date(current.year, current.month + 1, 1)

        return months

    def _parse_date(self, raw_date: str) -> date | None:
        text = raw_date.strip()
        if not text:
            return None

        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                continue
        return None

    def _dedupe_events(self, events: list[RawHoliday]) -> list[RawHoliday]:
        deduped: list[RawHoliday] = []
        seen: set[tuple[str, str, date]] = set()

        for event in events:
            key = (event.name.lower(), event.tradition, event.start_date)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(event)

        return deduped

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

    def _format_gemini_error_details(self, error: Exception) -> str:
        details: list[str] = []

        status_code = getattr(error, "status_code", None)
        if status_code is not None:
            details.append(f"status_code={status_code}")

        code_attr = getattr(error, "code", None)
        if callable(code_attr):
            try:
                code_attr = code_attr()
            except Exception:
                code_attr = None
        if code_attr is not None:
            code_name = getattr(code_attr, "name", None)
            details.append(f"code={code_name or str(code_attr)}")

        reason = getattr(error, "reason", None)
        if reason:
            details.append(f"reason={reason}")

        message = str(error).strip() or repr(error)
        if details:
            return f"{', '.join(details)} | message={message}"
        return f"message={message}"

    def _extract_llm_text_content(self, response: Any) -> str:
        content = getattr(response, "content", None)
        if isinstance(content, str):
            return content.strip()

        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text") or part.get("content")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif hasattr(part, "text"):
                    text = getattr(part, "text")
                    if isinstance(text, str) and text.strip():
                        parts.append(text.strip())
                elif isinstance(part, str) and part.strip():
                    parts.append(part.strip())

            if parts:
                return "\n".join(parts)

        if isinstance(response, str):
            return response.strip()

        return str(response).strip()

    def _parse_llm_json_object(self, text: str) -> dict[str, Any] | None:
        import json

        cleaned = (text or "").strip()
        if not cleaned:
            return None

        try:
            payload = json.loads(cleaned)
            return payload if isinstance(payload, dict) else None
        except json.JSONDecodeError:
            pass

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

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            snippet = cleaned[start:end + 1]
            try:
                payload = json.loads(snippet)
                return payload if isinstance(payload, dict) else None
            except json.JSONDecodeError:
                pass

        return None