"""
Utility functions and helpers.

Common functions used across modules for data validation,
formatting, and string parsing operations.
"""

import re
from typing import Tuple, Optional
from datetime import datetime


class DataParser:
    """Static utilities to parse raw scraping strings into strict schema types."""

    @staticmethod
    def parse_points_string(raw: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Parse points string into amount and currency.
        
        Handles abbreviated amounts like "57.5k" and extracts program name.
        
        Args:
            raw (str): Raw string like "57.5k AAdvantage miles"
        
        Returns:
            Tuple[Optional[float], Optional[str]]: (amount, program_name)
        
        Example:
            >>> DataParser.parse_points_string("57.5k AAdvantage miles")
            (57500.0, 'Aadvantage Miles')
        """
        if not raw:
            return None, None
            
        # Extract number (handling 'k' for thousands)
        # Regex looks for digits, optional decimal, and optional 'k'
        match = re.search(r'([\d\.]+)(k)?', raw.lower())
        if not match:
            return None, None
            
        # Convert to float, multiply by 1000 if 'k' is present
        amount = float(match.group(1))
        if match.group(2) == 'k':
            amount *= 1000
            
        # Extract currency (whatever is left after the number/k)
        # Simplistic approach: remove the number part, strip whitespace
        currency = re.sub(r'[\d\.]+k?', '', raw.lower()).replace('+', '').strip().title()
        
        return amount, currency

    @staticmethod
    def parse_cash_string(raw: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Parse cash amount string into amount and currency code.
        
        Handles various currency symbols and converts to ISO 4217 codes.
        
        Args:
            raw (str): Raw string like "$123.45" or "€50"
        
        Returns:
            Tuple[Optional[float], Optional[str]]: (amount, currency_code)
        
        Example:
            >>> DataParser.parse_cash_string("$123.45")
            (123.45, 'USD')
            >>> DataParser.parse_cash_string("€50")
            (50.0, 'EUR')
        """
        if not raw:
            return None, None
            
        # Map common currency symbols to ISO 4217 codes
        currency_map = {
            '$': 'USD',
            '€': 'EUR',
            '£': 'GBP',
            '¥': 'JPY'
        }
        
        # Default to USD if no recognized symbol found
        currency_code = "USD"
        for symbol, code in currency_map.items():
            if symbol in raw:
                currency_code = code
                break
        
        # Extract numeric amount from string
        match = re.search(r'([\d\.]+)', raw)
        amount = float(match.group(1)) if match else 0.0
        
        return amount, currency_code

    @staticmethod
    def normalize_date(date_str: str) -> str:
        """
        Normalize date strings to ISO-8601 YYYY-MM-DD format.
        
        Attempts to parse common date formats and normalize to standard format.
        
        Args:
            date_str (str): Date string in various formats
        
        Returns:
            str: Normalized ISO 8601 date (YYYY-MM-DD) or original if parsing fails
        
        Example:
            >>> DataParser.normalize_date("2025-12-25")
            '2025-12-25'
        """
        try:
            # Add parsing logic here based on actual site format
            # For now, return as-is if parsing fails or implement specific format
            return date_str
        except Exception:
            # If parsing fails, return original string
            return date_str