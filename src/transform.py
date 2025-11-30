import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils import DataParser

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "config" / "data_contract.json"


def _safe_get(d: Dict, key: str, default=None):
    return d.get(key, default) if isinstance(d, dict) else default


def _normalize_points(pricing: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure points fields are filled with sensible defaults."""
    points_raw = _safe_get(pricing, "points_price_raw")
    points_amount = _safe_get(pricing, "points_amount")
    points_curr = _safe_get(pricing, "points_program_currency")
    if points_amount is None and points_raw:
        amt, curr = DataParser.parse_points_string(points_raw)
        points_amount = points_amount or amt
        points_curr = points_curr or curr
    return {
        "points_price_raw": points_raw,
        "points_amount": points_amount,
        "points_program_currency": points_curr,
    }


def _normalize_cash(pricing: Dict[str, Any]) -> Dict[str, Any]:
    cash_raw = _safe_get(pricing, "cash_copay_raw")
    cash_amount = _safe_get(pricing, "cash_copay_amount")
    cash_curr = _safe_get(pricing, "cash_copay_currency")
    if cash_amount is None and cash_raw:
        amt, curr = DataParser.parse_cash_string(cash_raw)
        cash_amount = cash_amount or amt
        cash_curr = cash_curr or curr
    return {
        "cash_copay_raw": cash_raw,
        "cash_copay_amount": cash_amount,
        "cash_copay_currency": cash_curr,
    }


def _transform_record(rec: Dict[str, Any]) -> Dict[str, Any]:
    pricing = _safe_get(rec, "pricing", {}) or {}
    points = _normalize_points(pricing)
    cash = _normalize_cash(pricing)

    legs_out: List[Dict[str, Optional[Any]]] = []
    for leg in _safe_get(rec, "legs", []) or []:
        legs_out.append(
            {
                "leg_departure_datetime": _safe_get(leg, "leg_departure_datetime"),
                "leg_arrival_datetime": _safe_get(leg, "leg_arrival_datetime"),
                "leg_flight_number": _safe_get(leg, "leg_flight_number"),
                "leg_distance": _safe_get(leg, "leg_distance"),
                "leg_airplane": _safe_get(leg, "leg_airplane"),
                "leg_class": _safe_get(leg, "leg_class"),
            }
        )

    return {
        "inputs_from": rec.get("inputs_from"),
        "inputs_to": rec.get("inputs_to"),
        "program": rec.get("program"),
        "departure_date": rec.get("departure_date"),
        "duration": rec.get("duration"),
        "class": rec.get("class"),
        "stops": rec.get("stops"),
        "flight_number": rec.get("flight_number"),
        "last_updated": rec.get("last_updated"),
        "legs": legs_out,
        "pricing": {
            "points_price_raw": points["points_price_raw"],
            "points_amount": points["points_amount"],
            "points_program_currency": points["points_program_currency"],
            "cash_copay_raw": cash["cash_copay_raw"],
            "cash_copay_amount": cash["cash_copay_amount"],
            "cash_copay_currency": cash["cash_copay_currency"],
            "cents_per_point": pricing.get("cents_per_point"),
            "total_value_usd": pricing.get("total_value_usd"),
        },
    }


def transform_run(input_path: Path, output_path: Optional[Path] = None) -> Path:
    raw = json.loads(input_path.read_text(encoding="utf-8"))
    # Load data contract (for reference/validation surfaces later)
    contract = {}
    try:
        contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    except Exception:
        contract = {}

    cleaned = {
        "run_timestamp_utc": raw.get("run_timestamp_utc"),
        "flights": [],
    }
    for rec in raw.get("origin_dest_pairs", []):
        cleaned["flights"].append(_transform_record(rec))

    if output_path is None:
        stem = input_path.stem + "_transformed"
        output_path = input_path.with_name(f"{stem}{input_path.suffix}")
    output_path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.transform <input_json> [output_json]")
        sys.exit(1)
    inp = Path(sys.argv[1])
    outp = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    result = transform_run(inp, outp)
    print(f"Transformed file written to: {result}")
