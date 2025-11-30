import json
import os
from dataclasses import dataclass, field
from typing import List
from src.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class RouteConfig:
    """Defines a specific search target."""
    origin: str
    destination: str
    programs: List[str] # Specific programs for this route
    active: bool = True

@dataclass
class ScrapingSettings:
    """Technical settings for the browser engine."""
    headless: bool = True
    timeout_ms: int = 60000
    user_agent: str = "Mozilla/5.0..."
    retries: int = 3

@dataclass
class AppConfig:
    """Root configuration object."""
    project_name: str
    env: str
    default_programs: List[str] # Global defaults
    scraping_settings: ScrapingSettings
    routes: List[RouteConfig]

class ConfigLoader:
    @staticmethod
    def load_config(config_path: str = "config/config.json") -> AppConfig:
        # Resolve absolute path
        if not os.path.isabs(config_path):
            base_dir = os.getcwd()
            config_path = os.path.join(base_dir, config_path)

        if not os.path.exists(config_path):
            logger.critical(f"Config missing at: {config_path}")
            raise FileNotFoundError(f"Config missing at: {config_path}")

        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
            
            logger.info(f"Loaded config from {config_path}")
            
            # 1. Load Globals
            defaults = raw.get("default_programs", [])
            
            # 2. Load Settings
            s_data = raw.get("scraping_settings", {})
            settings = ScrapingSettings(
                headless=s_data.get("headless", True),
                timeout_ms=s_data.get("timeout_ms", 60000),
                user_agent=s_data.get("user_agent", ""),
                retries=s_data.get("retries", 3)
            )

            # 3. Load Routes (Applying defaults if specific programs are missing)
            routes = []
            for r in raw.get("routes", []):
                if not r.get("active", True):
                    continue
                
                # Logic: Use route-specific programs if present, else use defaults
                route_programs = r.get("programs")
                if not route_programs:
                    route_programs = defaults

                routes.append(RouteConfig(
                    origin=r.get("origin"),
                    destination=r.get("destination"),
                    programs=route_programs,
                    active=True
                ))

            return AppConfig(
                project_name=raw.get("project_name", "Scraper"),
                env=raw.get("env", "dev"),
                default_programs=defaults,
                scraping_settings=settings,
                routes=routes
            )

        except Exception as e:
            logger.critical(f"Config load failed: {e}")
            raise

def get_config(path: str = "config/config.json") -> AppConfig:
    return ConfigLoader.load_config(path)