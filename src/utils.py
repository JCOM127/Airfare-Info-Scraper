import re
from typing import Tuple, Optional
from datetime import datetime

class DataParser:
    """
    Static utilities to parse raw scraping strings into strict schema types.
    """

    @staticmethod
    def parse_points_string(raw: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Parses "57.5k AAdvantage miles" -> (57500.0, "AAdvantage")
        """
        if not raw:
            return None, None
            
        # Extract number (handling 'k')
        # Regex looks for digits, optional decimal, and optional 'k'
        match = re.search(r'([\d\.]+)(k)?', raw.lower())
        if not match:
            return None, None
            
        amount = float(match.group(1))
        if match.group(2) == 'k':
            amount *= 1000
            
        # Extract currency (whatever is left after the number/k)
        # simplistic approach: remove the number part, strip whitespace
        currency = re.sub(r'[\d\.]+k?', '', raw.lower()).replace('+', '').strip().title()
        
        return amount, currency

    @staticmethod
    def parse_cash_string(raw: str) -> Tuple[Optional[float], Optional[str]]:
        """
        Parses "$123" -> (123.0, "USD") or "€50" -> (50.0, "EUR")
        """
        if not raw:
            return None, None
            
        # Map common symbols to ISO codes
        currency_map = {'$': 'USD', '€': 'EUR', '£': 'GBP', '¥': 'JPY'}
        
        currency_code = "USD" # Default fallback
        for symbol, code in currency_map.items():
            if symbol in raw:
                currency_code = code
                break
        
        # Extract number
        match = re.search(r'([\d\.]+)', raw)
        amount = float(match.group(1)) if match else 0.0
        
        return amount, currency_code

    @staticmethod
    def normalize_date(date_str: str) -> str:
        """
        Attempts to normalize date strings to ISO-8601 YYYY-MM-DD.
        Assumes input is close to standard formats.
        """
        try:
            # Add parsing logic here based on actual site format (e.g., "Jan 12, 2025")
            # For now, return as-is if parsing fails or implement specific format
            return date_str 
        except:
            return date_str