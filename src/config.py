"""
Configuration management and validation.

This module loads and validates configuration from JSON files
with support for environment variable overrides.

Core functionality:
- Load configuration from config.json
- Validate against config_schema.json
- Apply environment variable overrides
- Type-safe configuration objects via dataclasses
"""

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
    """Configuration for a single flight route."""
    origin: str  # IATA code of departure airport
    destination: str  # IATA code of arrival airport
    programs: List[str]  # Loyalty programs to search
    active: bool = True  # Whether this route is active


@dataclass
class ScrapingSettings:
    """Configuration for scraper behavior and performance."""
    headless: bool = True  # Run browser in headless mode
    timeout_ms: int = 60000  # Browser navigation timeout in milliseconds
    user_agent: str = ""  # Custom user agent string
    retries: int = 3  # Number of retry attempts for failed API calls
    search_window_days: int = 60  # Days to search ahead/behind (+/- flex window)
    departure_date: str = ""  # ISO YYYY-MM-DD; optional override for specific date
    max_offers_per_route: int = 0  # 0 = no cap; caps API load to avoid 429 errors


@dataclass
class AppConfig:
    """Top-level application configuration."""
    project_name: str  # Project identifier
    env: str  # Environment: dev, staging, production
    default_programs: List[str]  # Default programs if route doesn't specify
    scraping_settings: ScrapingSettings  # Scraper configuration
    routes: List[RouteConfig]  # List of routes to scrape


class ConfigLoader:
    """Load and validate configuration from JSON files."""
    
    @staticmethod
    def load_config(config_path: str = "config/config.json") -> AppConfig:
        """
        Load and validate configuration from JSON file.
        
        Reads config.json, validates against config_schema.json, and returns
        typed configuration object.
        
        Args:
            config_path (str): Path to config.json (relative or absolute)
        
        Returns:
            AppConfig: Validated configuration object
        
        Raises:
            FileNotFoundError: If config file not found
            ValueError: If configuration validation fails
            jsonschema.ValidationError: If schema validation fails
        
        Example:
            >>> config = ConfigLoader.load_config("config/config.json")
            >>> print(f"Found {len(config.routes)} routes")
        """
        if not os.path.isabs(config_path):
            base_dir = os.getcwd()
            config_path = os.path.join(base_dir, config_path)

        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config missing at: {config_path}")

        # Load configuration JSON file
        with open(config_path, 'r', encoding='utf-8') as f:
            raw = json.load(f)

        # Validate config against schema
        try:
            schema_path = Path(config_path).resolve().parent / "config_schema.json"
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            jsonschema.validate(instance=raw, schema=schema)
        except Exception as e:
            raise ValueError(f"Config validation failed: {e}")
        
        # Extract default programs for fallback
        defaults = raw.get("default_programs", [])
        s_data = raw.get("scraping_settings", {})
        
        # Build scraping settings from config
        settings = ScrapingSettings(
            headless=s_data.get("headless", True),
            timeout_ms=s_data.get("timeout_ms", 60000),
            user_agent=s_data.get("user_agent", ""),
            retries=s_data.get("retries", 3),
            # Robust .get() to avoid KeyErrors on optional fields
            search_window_days=s_data.get("search_window_days", 60),
            departure_date=s_data.get("departure_date", ""),
            max_offers_per_route=s_data.get("max_offers_per_route", 0),
        )

        # Build routes from config
        routes = []
        for r in raw.get("routes", []):
            programs = r.get("programs", [])
            if not programs:
                # Use default programs if route doesn't specify
                programs = defaults
            routes.append(RouteConfig(r.get("origin"), r.get("destination"), programs))

        # Create and return typed config object
        return AppConfig(
            project_name=raw.get("project_name", ""),
            env=raw.get("env", "dev"),
            default_programs=defaults,
            scraping_settings=settings,
            routes=routes
        )


def get_config(path: str = "config/config.json") -> AppConfig:
    """
    Convenience function to load configuration.
    
    Args:
        path (str): Path to config.json
    
    Returns:
        AppConfig: Validated configuration object
    
    Example:
        >>> config = get_config()
        >>> print(config.env)
        'dev'
    """
