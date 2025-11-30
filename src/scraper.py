import asyncio
import sys
import time
from datetime import datetime, timezone
from typing import List, Dict, Any

# Playwright
from playwright.async_api import async_playwright, Page, Locator

# Internal
from src.config import AppConfig, RouteConfig
from src.logger import setup_logger
from src.utils import DataParser

logger = setup_logger(__name__)

class SeatsAeroScraper:
    def __init__(self, config: AppConfig):
        self.config = config
        self.output_schema = {
            "run_timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "origin_dest_pairs": []
        }

    async def _process_modal(self, page: Page, route: RouteConfig, flight_record: Dict):
        """
        Scrapes the details from the open modal window (Req 4.2).
        """
        try:
            # Wait for modal content to be visible
            modal = page.locator(".modal-content").first
            await modal.wait_for(state="visible", timeout=5000)

            # --- 1. Extract Pricing (Req 4.2.1) ---
            # NOTE: Selectors below are hypothetical based on standard Bootstrap/React patterns.
            # We will need to adjust these selectors once we run the visual debug.
            points_raw = await modal.locator(".points-cost").inner_text() # e.g. "57.5k ..."
            cash_raw = await modal.locator(".cash-cost").inner_text()     # e.g. "+ $123"
            
            p_amount, p_curr = DataParser.parse_points_string(points_raw)
            c_amount, c_curr = DataParser.parse_cash_string(cash_raw)

            flight_record.update({
                "points_price_raw": points_raw,
                "points_amount": p_amount,
                "points_program_currency": p_curr,
                "cash_copay_raw": cash_raw,
                "cash_copay_amount": c_amount,
                "cash_copay_currency": c_curr,
            })

            # --- 2. Extract Legs ---
            legs_data = []
            leg_elements = await modal.locator(".flight-leg").all()
            
            for leg in leg_elements:
                legs_data.append({
                    "leg_flight_number": await leg.locator(".flight-num").inner_text(),
                    "leg_airplane": await leg.locator(".aircraft-type").inner_text(),
                    "leg_class": await leg.locator(".cabin-class").inner_text(),
                    # Add timestamps extraction here
                })
            
            flight_record["legs"] = legs_data

            # Close Modal (Press Escape is usually safest)
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500) # Animation buffer

        except Exception as e:
            logger.error(f"Error parsing modal for {flight_record.get('flight_number')}: {e}")
            # Try to force close modal if it's stuck
            await page.keyboard.press("Escape")

    async def run(self):
        logger.info("Starting Active Scraper Run...")
        
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=self.config.scraping_settings.headless)
            context = await browser.new_context(user_agent=self.config.scraping_settings.user_agent)
            page = await context.new_page()

            for route in self.config.routes:
                # 1. Navigation (Req 4.1.1)
                # Note: Seats.aero URL structure usually involves query params.
                # Adjusting to generic search URL based on spec.
                search_url = (
                    f"https://seats.aero/search?origin={route.origin}"
                    f"&destination={route.destination}&date=2025-01-12" # TODO: Dynamic Date Logic
                )
                
                logger.info(f"Navigating: {route.origin} -> {route.destination}")
                await page.goto(search_url, wait_until="networkidle")
                
                # 2. Wait for Results Table (Req 4.1.3)
                # Assuming table rows have class 'search-result-row'
                await page.wait_for_selector("table", timeout=10000)

                # 3. Iterate Rows (Req 4.1.4)
                # We fetch all rows first to avoid stale element handles if DOM updates
                rows = await page.locator("tr:has(.fa-info-circle)").all()
                logger.info(f"Found {len(rows)} potential flights.")

                for row in rows:
                    try:
                        # Extract basic info from the row to see if we should click
                        row_text = await row.inner_text()
                        
                        # Filter by Program (Req 4.1.4)
                        # We assume the program name is visible in the row text
                        found_program = next((prog for prog in route.programs if prog in row_text), None)
                        
                        if not found_program:
                            continue # Skip if program not in our target list

                        # Initialize Record
                        record = {
                            "inputs_from": route.origin,
                            "inputs_to": route.destination,
                            "program": found_program,
                            "flight_number": "PENDING", # Needs extraction
                            "last_updated": datetime.now().isoformat() # Placeholder
                        }

                        # Click Info Button (Req 4.1.4.1)
                        info_btn = row.locator(".fa-info-circle")
                        if await info_btn.count() > 0:
                            await info_btn.click()
                            # Hand off to modal processor
                            await self._process_modal(page, route, record)
                            
                            # Add to global results
                            self.output_schema["origin_dest_pairs"].append(record)
                    
                    except Exception as e:
                        logger.warning(f"Failed to process a row: {e}")
                        continue

            await browser.close()
            
            # Save Local JSON for verification
            import json
            filename = f"output/run_{int(time.time())}.json"
            with open(filename, "w") as f:
                json.dump(self.output_schema, f, indent=2)
            
            logger.info(f"Run Complete. Saved to {filename}")
            return self.output_schema

if __name__ == "__main__":
    from src.config import get_config
    
    # Windows Patch
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    cfg = get_config()
    cfg.scraping_settings.headless = False # Debug mode on
    
    scraper = SeatsAeroScraper(cfg)
    asyncio.run(scraper.run())