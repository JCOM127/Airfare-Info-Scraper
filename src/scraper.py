import asyncio
import sys
import json
from datetime import datetime, timezone, timedelta
from typing import Dict, List

from playwright.async_api import async_playwright

from src.config import AppConfig, RouteConfig, get_config
from src.logger import setup_logger

logger = setup_logger(__name__)


class SeatsAeroScraper:
    def __init__(self, config: AppConfig):
        self.config = config
        self.run_timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.output_schema = {
            "run_timestamp_utc": self.run_timestamp,
            "origin_dest_pairs": [],
        }

    def _program_matches(self, source: str, configured: List[str]) -> bool:
        src = (source or "").lower()
        for p in configured:
            if p.lower() in src or src in p.lower():
                return True
        return False

    def _format_duration(self, minutes_val):
        if minutes_val is None:
            return None
        try:
            minutes_val = int(minutes_val)
            hours = minutes_val // 60
            minutes = minutes_val % 60
            return f"{hours}h {minutes}m"
        except Exception:
            return None

    def _last_updated_ts(self, minutes_ago: int):
        try:
            dt = datetime.now(timezone.utc) - timedelta(minutes=int(minutes_ago))
            return dt.isoformat()
        except Exception:
            return self.run_timestamp

    async def _page_fetch_json(self, page, url: str, params: Dict):
        payload = {
            "url": url,
            "params": params,
            "timeout": self.config.scraping_settings.timeout_ms,
        }
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
                  headers: {
                    'accept': 'application/json',
                  },
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
        if not result["ok"]:
            raise Exception(f"fetch {url} returned {result['status']}")
        return json.loads(result["text"])

    async def _fetch_search(self, page, route: RouteConfig, target_date: str):
        params = {
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

    async def _fetch_enrichment(self, page, availability_id: str, route: RouteConfig, target_date: str):
        params = {
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
        program = detail.get("source") or meta.get("source")
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

    async def run(self):
        logger.info(f"Starting Scraper Run ({self.run_timestamp})")
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
                for attempt in range(self.config.scraping_settings.retries):
                    try:
                        metadata = await self._fetch_search(page, route, target_date)
                        logger.info(f"{route.origin}-{route.destination}: fetched {len(metadata)} offers")
                        fetched = True
                        added = 0
                        for meta in metadata:
                            if not self._program_matches(meta.get("source", ""), route.programs):
                                continue
                            for attempt_enrich in range(self.config.scraping_settings.retries):
                                try:
                                    detail = await self._fetch_enrichment(page, meta["id"], route, target_date)
                                    for record in self._build_records(meta, detail):
                                        self.output_schema["origin_dest_pairs"].append(record)
                                        added += 1
                                    break
                                except Exception as e:
                                    if attempt_enrich == self.config.scraping_settings.retries - 1:
                                        logger.warning(f"Enrichment failed for {meta.get('id')}: {e}")
                                    await asyncio.sleep(0.5)
                        logger.info(f"{route.origin}-{route.destination}: appended {added} records")
                        break
                    except Exception as e:
                        if attempt == self.config.scraping_settings.retries - 1:
                            logger.error(f"Route fetch failed for {route.origin}-{route.destination}: {e}")
                        await asyncio.sleep(0.5)

        safe_ts = self.run_timestamp.replace(":", "-")
        filename = f"output/run_{safe_ts}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(self.output_schema, f, indent=2)

        logger.info(f"Run Complete. Saved to {filename}")
        await browser.close()
        return self.output_schema


if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    cfg = get_config()
    scraper = SeatsAeroScraper(cfg)
    asyncio.run(scraper.run())
