import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.utils import DataParser


def test_parse_points_string_basic():
    amount, currency = DataParser.parse_points_string("57.5k AAdvantage miles")
    assert amount == 57500.0
    assert "Aadvantage" in currency


def test_parse_cash_string_basic():
    amount, currency = DataParser.parse_cash_string("$123")
    assert amount == 123.0
    assert currency == "USD"


def test_parse_cash_string_eur():
    amount, currency = DataParser.parse_cash_string("€52")
    assert amount == 52.0
    assert currency == "EUR"
