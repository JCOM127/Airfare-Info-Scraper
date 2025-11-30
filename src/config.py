import json
import os
from dataclasses import dataclass, field
from typing import List
from pathlib import Path
import jsonschema
from src.logger import setup_logger

logger = setup_logger(__name__)

@dataclass
class RouteConfig:
    origin: str
    destination: str
    programs: List[str]
    active: bool = True

@dataclass
class ScrapingSettings:
    headless: bool = True
    timeout_ms: int = 60000
    user_agent: str = ""
    retries: int = 3
    search_window_days: int = 60 # +/- flex window
    departure_date: str = ""      # ISO YYYY-MM-DD; optional
    max_offers_per_route: int = 0 # 0 = no cap

@dataclass
class AppConfig:
    project_name: str
    env: str
    default_programs: List[str]
    scraping_settings: ScrapingSettings
    routes: List[RouteConfig]

class ConfigLoader:
    @staticmethod
    def load_config(config_path: str = "config/config.json") -> AppConfig:
        if not os.path.isabs(config_path):
            base_dir = os.getcwd()
            config_path = os.path.join(base_dir, config_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config missing at: {config_path}")

        with open(config_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        # Validate config against schema
        try:
            schema_path = Path(config_path).resolve().parent / "config_schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=raw, schema=schema)
        except Exception as e:
            raise ValueError(f"Config validation failed: {e}")
        
        defaults = raw.get("default_programs", [])
        s_data = raw.get("scraping_settings", {})
        
        settings = ScrapingSettings(
            headless=s_data.get("headless", True),
            timeout_ms=s_data.get("timeout_ms", 60000),
            user_agent=s_data.get("user_agent", ""),
            retries=s_data.get("retries", 3),
            # Robust .get() to avoid KeyErrors
            search_window_days=s_data.get("search_window_days", 60),
            departure_date=s_data.get("departure_date", ""),
            max_offers_per_route=s_data.get("max_offers_per_route", 0),
        )

        routes = []
        for r in raw.get("routes", []):
            programs = r.get("programs", [])
            if not programs:
                programs = defaults
            routes.append(RouteConfig(r.get("origin"), r.get("destination"), programs))

        return AppConfig(
            project_name=raw.get("project_name", ""),
            env=raw.get("env", "dev"),
            default_programs=defaults,
            scraping_settings=settings,
            routes=routes
        )

def get_config(path: str = "config/config.json") -> AppConfig:
    return ConfigLoader.load_config(path)
