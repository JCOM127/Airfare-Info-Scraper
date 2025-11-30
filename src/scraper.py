"""
Flight availability scraper for Seats.aero.

This module handles extraction of flight rewards data from Seats.aero using
Playwright browser automation and network request interception.

Core functionality:
- Browser automation with Playwright (Chromium)
- API request interception and JSON parsing
- Retry logic with exponential backoff for transient failures
- Rate limit handling (429 errors)
- Comprehensive logging with route-level statistics
"""

import asyncio
import sys
import json
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Optional

from playwright.async_api import async_playwright

from src.config import AppConfig, RouteConfig, get_config
from src.logger import setup_logger

logger = setup_logger(__name__)


class SeatsAeroScraper:
    """
    Scrapes flight availability from Seats.aero.
    
    Uses Playwright to launch a headless browser and intercepts API requests
    to extract flight rewards data. Handles rate limiting, retries, and errors.
    """
    
    def __init__(self, config: AppConfig) -> None:
        """
        Initialize scraper with configuration.
        
        Args:
            config (AppConfig): Configuration with routes, programs, settings
        
        Attributes:
            config (AppConfig): Application configuration
            run_timestamp (str): ISO 8601 timestamp of this scraping run
            output_schema (Dict): Output data structure with metadata
        """
        self.config = config
        self.run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.output_schema: Dict[str, any] = {
            "run_timestamp_utc": self.run_timestamp,
            "origin_dest_pairs": [],
        }

    def _program_matches(self, source: str, configured: List[str]) -> bool:
        """
        Check if program source matches any configured programs.
        
        Case-insensitive matching. Allows partial matches to handle variations.
        
        Args:
            source (str): Program name from Seats.aero API
            configured (List[str]): List of configured program names
        
        Returns:
            bool: True if program matches configuration
        
        Example:
            >>> self._program_matches("AAdvantage", ["AAC", "AAdvantage"])
            True
        """
        src = (source or "").lower()
        for p in configured:
            if p.lower() in src or src in p.lower():
                return True
        return False

    def _format_duration(self, minutes_val: Optional[int]) -> Optional[str]:
        """
        Convert minutes to human-readable duration format.
        
        Args:
            minutes_val (Optional[int]): Duration in minutes
        
        Returns:
            Optional[str]: Formatted as "Xh Ym" or None if invalid
        
        Example:
            >>> self._format_duration(90)
            '1h 30m'
        """
        if minutes_val is None:
            return None
        try:
            minutes_val = int(minutes_val)
            hours = minutes_val // 60
            minutes = minutes_val % 60
            return f"{hours}h {minutes}m"
        except Exception:
            return None

    def _last_updated_ts(self, minutes_ago: int) -> str:
        """
        Calculate timestamp for last update based on minutes ago.
        
        Args:
            minutes_ago (int): Number of minutes in the past
        
        Returns:
            str: ISO 8601 formatted datetime string
        """
        try:
            dt = datetime.now(timezone.utc) - timedelta(minutes=int(minutes_ago))
            return dt.isoformat()
        except Exception:
            return self.run_timestamp

    def _build_minimal_record(self, meta: Dict, target_date: str) -> Dict:
        """
        Build minimal fallback record when enrichment fails.
        
        Captures top-level fields only when detailed enrichment API fails.
        Used to prevent data loss during rate limiting or API errors.
        
        Args:
            meta (Dict): Metadata from search response
            target_date (str): Target departure date
        
        Returns:
            Dict: Minimal flight record with basic fields
        """
        return {
            "inputs_from": meta.get("oa"),
            "inputs_to": meta.get("da"),
            "program": meta.get("source"),
            "departure_date": meta.get("date") or target_date,
            "duration": None,
            "class": None,
            "stops": meta.get("stops"),
            "flight_number": None,
            "last_updated": self.run_timestamp,
            "legs": [],
            "pricing": {
                "points_price_raw": None,
                "points_amount": None,
                "points_program_currency": meta.get("source"),
                "cash_copay_raw": None,
                "cash_copay_amount": None,
                "cash_copay_currency": None,
                "cents_per_point": None,
                "total_value_usd": None,
            },
        }

    async def _page_fetch_json(self, page, url: str, params: Dict) -> Dict:
        """
        Execute fetch request via browser and return parsed JSON.
        
        Implements retry logic with exponential backoff.
        Handles rate limiting (429 errors) specially.
        
        Args:
            page: Playwright page object
            url (str): API endpoint URL
            params (Dict): Query parameters
        
        Returns:
            Dict: Parsed JSON response
        
        Raises:
            Exception: If fetch fails after all retries
        """
            "url": url,
            "params": params,
            "timeout": self.config.scraping_settings.timeout_ms,
        }

        attempts = self.config.scraping_settings.retries
        for attempt in range(attempts):
            result = await page.evaluate(
                """
                async ({url, params, timeout}) => {
                  const q = new URL(url);
                  Object.entries(params).forEach(([k,v]) => q.searchParams.set(k, String(v)));
                  const ctrl = new AbortController();
                  const t = setTimeout(() => ctrl.abort(), timeout);
                  try {
                    const res = await fetch(q.toString(), {
                      method: 'GET',
                      headers: { 'accept': 'application/json' },
                      signal: ctrl.signal,
                    });
                    const text = await res.text();
                    return { ok: res.ok, status: res.status, text };
                  } finally {
                    clearTimeout(t);
                  }
                }
                """,
                payload,
            )
            if result["ok"]:
                return json.loads(result["text"])
            if result["status"] == 429 and attempt < attempts - 1:
                # Back off more aggressively on rate limits
                await asyncio.sleep((1.0 + random.uniform(0, 1.0)) * (attempt + 1))
                continue
            raise Exception(f"fetch {url} returned {result['status']}")

    async def _fetch_search(self, page, route: RouteConfig, target_date: str) -> List[Dict]:
        """
        Fetch search results from Seats.aero API.
        
        Retrieves available flight offers for a given route and date.
        
        Args:
            page: Playwright page object
            route (RouteConfig): Route configuration with origin, destination, programs
            target_date (str): Target departure date (YYYY-MM-DD)
        
        Returns:
            List[Dict]: Metadata array of available offers
        """
            "min_seats": 1,
            "applicable_cabin": "any",
            "additional_days": "true",
            "additional_days_num": str(self.config.scraping_settings.search_window_days),
            "max_fees": 40000,
            "disable_live_filtering": "false",
            "date": target_date,
            "origins": route.origin,
            "destinations": route.destination,
            "seamless": "true",
            "c": datetime.now().timestamp(),  # cache buster similar to UI
        }
        url = "https://seats.aero/_api/search_partial"
        data = await self._page_fetch_json(page, url, params)
        return data.get("metadata", [])

    async def _fetch_enrichment(self, page, availability_id: str, route: RouteConfig, target_date: str) -> Dict:
        """
        Fetch detailed enrichment data for a specific offer.
        
        Gets full flight details including legs, pricing, and cabin information.
        
        Args:
            page: Playwright page object
            availability_id (str): Unique ID of the offer to enrich
            route (RouteConfig): Route configuration
            target_date (str): Target departure date
        
        Returns:
            Dict: Enriched offer details with trip information
        """
            "m": 1,
            "min_seats": 1,
            "applicable_cabin": "any",
            "additional_days": "true",
            "additional_days_num": str(self.config.scraping_settings.search_window_days),
            "max_fees": 40000,
            "disable_live_filtering": "false",
            "date": target_date,
            "origins": route.origin,
            "destinations": route.destination,
        }
        url = f"https://seats.aero/_api/enrichment_modern/{availability_id}"
        return await self._page_fetch_json(page, url, params)

    def _build_records(self, meta: Dict, detail: Dict) -> List[Dict]:
        """
        Build complete flight records from search metadata and enriched details.
        
        Transforms raw API response into normalized flight records.
        Handles pricing, duration, and leg information.
        
        Args:
            meta (Dict): Metadata from search response
            detail (Dict): Enriched detail from enrichment API
        
        Returns:
            List[Dict]: List of flight records with full information
        """
        date = meta.get("date") or detail.get("departureDate")
        dep_air = detail.get("originAirport") or meta.get("oa")
        arr_air = detail.get("destinationAirport") or meta.get("da")
        trips = detail.get("trips", [])
        records = []
        last_updated_minutes = detail.get("lastUpdatedMinutes")
        last_updated = self._last_updated_ts(last_updated_minutes) if last_updated_minutes is not None else self.run_timestamp

        for trip in trips:
            legs = []
            for seg in trip.get("AvailabilitySegments", []):
                legs.append({
                    "leg_departure_datetime": seg.get("DepartsAt"),
                    "leg_arrival_datetime": seg.get("ArrivesAt"),
                    "leg_flight_number": seg.get("FlightNumber"),
                    "leg_distance": seg.get("Distance"),
                    "leg_airplane": seg.get("AircraftName"),
                    "leg_class": seg.get("Cabin"),
                })

            mileage_cost = trip.get("MileageCost")
            taxes = trip.get("TotalTaxes")
            taxes_currency = trip.get("TaxesCurrency")
            taxes_symbol = trip.get("TaxesCurrencySymbol")
            cpp = None
            if mileage_cost and taxes is not None:
                try:
                    cpp = round((taxes / mileage_cost) * 100, 4)
                except Exception:
                    cpp = None

            # taxes appear to be in minor units (e.g., cents)
            cash_amount = None
            if taxes is not None:
                try:
                    cash_amount = round(taxes / 100, 2)
                except Exception:
                    cash_amount = None

            points_price_raw = None
            if mileage_cost is not None:
                if cash_amount is not None:
                    symbol = taxes_symbol or ""
                    curr = taxes_currency or ""
                    points_price_raw = f"{mileage_cost} pts + {symbol}{cash_amount:.2f} {curr}".strip()
                else:
                    points_price_raw = f"{mileage_cost} pts"

            record = {
                "inputs_from": dep_air,
                "inputs_to": arr_air,
                "program": program,
                "departure_date": date,
                "duration": self._format_duration(trip.get("TotalDuration")),
                "class": trip.get("Cabin"),
                "stops": trip.get("Stops"),
                "flight_number": trip.get("FlightNumbers"),
                "last_updated": last_updated,
                "legs": legs,
                "pricing": {
                    "points_price_raw": points_price_raw,
                    "points_amount": mileage_cost,
                    "points_program_currency": program,
                    "cash_copay_raw": f"{taxes_symbol or ''}{cash_amount:.2f} {taxes_currency}".strip() if cash_amount is not None else None,
                    "cash_copay_amount": cash_amount,
                    "cash_copay_currency": taxes_currency,
                    "cents_per_point": cpp,
                    "total_value_usd": None,
                },
            }
            records.append(record)
        return records

    async def run(self) -> Dict:
        """
        Execute the main scraping pipeline.
        
        Launches browser, iterates through configured routes, fetches search results,
        enriches each offer with details, and saves output.
        
        Returns:
            Dict: Complete output schema with all scraped records
        
        Process:
            1. Launch Playwright browser
            2. For each configured route:
               a. Fetch search results (metadata)
               b. Filter by configured programs
               c. Enrich each result with details
               d. Build complete records
            3. Save timestamped JSON output
            4. Log summary statistics
        """
        timeout_ms = self.config.scraping_settings.timeout_ms

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config.scraping_settings.headless)
            context = await browser.new_context(
                user_agent=self.config.scraping_settings.user_agent,
                extra_http_headers={
                    "referer": "https://seats.aero/search",
                    "accept": "application/json",
                },
            )
            page = await context.new_page()
            try:
                await page.goto("https://seats.aero/search", wait_until="networkidle", timeout=self.config.scraping_settings.timeout_ms)
            except Exception as e:
                logger.warning(f"Warmup page load failed: {e}")

            if self.config.scraping_settings.departure_date:
                target_date = self.config.scraping_settings.departure_date
            else:
                target_date = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")

            for route in self.config.routes:
                fetched = False
                route_429_hits = 0
                skip_rest = False
                for attempt in range(self.config.scraping_settings.retries):
                    try:
                        metadata = await self._fetch_search(page, route, target_date)
                        max_offers = self.config.scraping_settings.max_offers_per_route
                        if max_offers and max_offers > 0:
                            metadata = metadata[:max_offers]
                        logger.info(f"{route.origin}-{route.destination}: fetched {len(metadata)} offers")
                        fetched = True
                        added = 0
                        for meta in metadata:
                            if skip_rest:
                                # If we've hit too many 429s, just append minimal records for the remaining offers
                                fallback = self._build_minimal_record(meta, target_date)
                                self.output_schema["origin_dest_pairs"].append(fallback)
                                added += 1
                                continue

                            if not self._program_matches(meta.get("source", ""), route.programs):
                                continue
                            for attempt_enrich in range(self.config.scraping_settings.retries):
                                try:
                                    detail = await self._fetch_enrichment(page, meta["id"], route, target_date)
                                    for record in self._build_records(meta, detail):
                                        self.output_schema["origin_dest_pairs"].append(record)
                                        added += 1
                                    # Small delay between enrichments to avoid 429
                                    await asyncio.sleep(1.0 + random.uniform(0.5, 1.0))
                                    break
                                except Exception as e:
                                    if attempt_enrich == self.config.scraping_settings.retries - 1:
                                        logger.warning(f"Enrichment failed for {meta.get('id')}: {e}")
                                        if "429" in str(e):
                                            route_429_hits += 1
                                            if route_429_hits >= 2:
                                                logger.warning(f"{route.origin}-{route.destination}: 429 threshold hit; skipping remaining enrichments with minimal records")
                                                skip_rest = True
                                        # Fallback: append minimal record when enrichment fails
                                        fallback = self._build_minimal_record(meta, target_date)
                                        self.output_schema["origin_dest_pairs"].append(fallback)
                                        added += 1
                                    await asyncio.sleep((0.75 + random.uniform(0, 0.75)) * (attempt_enrich + 1))
                        logger.info(f"{route.origin}-{route.destination}: appended {added} records")
                        break
                    except Exception as e:
                        if attempt == self.config.scraping_settings.retries - 1:
                            logger.error(f"Route fetch failed for {route.origin}-{route.destination}: {e}")
                        await asyncio.sleep(0.5 + random.uniform(0, 0.5))
                # Pause between routes to reduce rate hits
                await asyncio.sleep(2.0 + random.uniform(0, 1.0))

        safe_ts = self.run_timestamp.replace(":", "-")
        filename = f"output/run_{safe_ts}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.output_schema, f, indent=2)

        logger.info(f"Run Complete. Saved to {filename} | total_records={len(self.output_schema['origin_dest_pairs'])}")
        await browser.close()
        return self.output_schema


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    cfg = get_config()
    scraper = SeatsAeroScraper(cfg)
    asyncio.run(scraper.run())
