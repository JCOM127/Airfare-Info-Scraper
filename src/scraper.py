import asyncio
import sys
import time
import json
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

# Playwright
from playwright.async_api import async_playwright, Page, Locator

# Internal
from src.config import AppConfig, RouteConfig, get_config
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
        Scrapes the details from the open modal window.
        """
        try:
            # Wait for modal content to be visible
            # Seats.aero modals usually have a generic container. 
            # We look for the modal header or content wrapper.
            modal = page.locator("div[role='dialog']").first
            await modal.wait_for(state="visible", timeout=5000)

            # --- Extract Text Content for Parsing ---
            # We grab the full text of the modal to ensure we don't miss dynamic class names
            # Then we can use Regex on the full block if specific selectors fail.
            full_modal_text = await modal.inner_text()
            
            # Try specific selectors for pricing (Adjust these based on visual inspection)
            # Usually distinct colors or large fonts imply price.
            # Fallback: We log the raw text to debug if selectors fail.
            logger.debug(f"Modal Text Preview: {full_modal_text[:100]}...")

            # --- Placeholder Selectors (Need validation on live site) ---
            # Assuming standard layout:
            flight_record.update({
                "points_price_raw": "Parsed from Modal (Implement Specific Selector)", 
                "cash_copay_raw": "Parsed from Modal (Implement Specific Selector)"
            })
            
            # Close Modal
            # Click the 'X' button or press Escape
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500) # Animation buffer

        except Exception as e:
            logger.error(f"Error processing modal for {flight_record.get('flight_number')}: {e}")
            await page.keyboard.press("Escape")

    async def run(self):
        logger.info("Starting Active Scraper Run...")
        
        async with async_playwright() as p:
            # Force headless=False if running via __main__ for debugging
            headless_mode = self.config.scraping_settings.headless
            
            browser = await p.chromium.launch(headless=headless_mode)
            context = await browser.new_context(user_agent=self.config.scraping_settings.user_agent)
            page = await context.new_page()

            # Dynamic Date: Today + 60 Days (To ensure we find flights)
            target_date = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%d')

            for route in self.config.routes:
                # Construct Search URL
                # We use the generic search params used by Seats.aero
                search_url = (
                    f"https://seats.aero/search?origin={route.origin}"
                    f"&destination={route.destination}&date={target_date}"
                    "&applicable_cabins=business&applicable_cabins=first"
                )
                
                logger.info(f"Navigating: {route.origin} -> {route.destination} on {target_date}")
                await page.goto(search_url, wait_until="domcontentloaded")
                
                # Wait for the Data Table
                try:
                    await page.wait_for_selector("table", timeout=15000)
                except:
                    logger.warning(f"Timeout waiting for table on {route.origin}-{route.destination}")
                    continue

                # Find all Info Buttons (The 'i' icon)
                # We limit to first 3 for the local test to save time
                info_buttons = await page.locator(".fa-info-circle").all()
                logger.info(f"Found {len(info_buttons)} flights. Processing first 3...")

                count = 0
                for btn in info_buttons:
                    if count >= 3: break # Test Limit
                    
                    try:
                        # Ensure button is interactive
                        if await btn.is_visible():
                            await btn.click()
                            
                            # Initialize Record
                            record = {
                                "inputs_from": route.origin,
                                "inputs_to": route.destination,
                                "departure_date": target_date,
                                "program": "DETECTED_IN_MODAL", # We will refine this
                            }
                            
                            await self._process_modal(page, route, record)
                            self.output_schema["origin_dest_pairs"].append(record)
                            count += 1
                    except Exception as e:
                        logger.warning(f"Interaction failed: {e}")

            await browser.close()
            
            # Save Output
            filename = f"output/run_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(filename, "w") as f:
                json.dump(self.output_schema, f, indent=2)
            
            logger.info(f"Run Complete. Saved to {filename}")
            return self.output_schema

if __name__ == "__main__":
    # Windows Patch
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())

    cfg = get_config()
    # FORCE VISIBLE BROWSER FOR LOCAL TEST
    cfg.scraping_settings.headless = False 
    
    scraper = SeatsAeroScraper(cfg)
    asyncio.run(scraper.run())