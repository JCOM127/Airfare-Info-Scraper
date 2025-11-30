"""
Data transformation and schema validation.

This module normalizes raw scraped data and validates it against
the JSON Schema data contract defined in config/data_contract.json.

Core functionality:
- Normalize field names, types, and values
- Parse complex strings (prices, durations, etc.)
- Validate against data contract
- Log schema violations (warnings don't halt pipeline)
"""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.utils import DataParser
from src.logger import setup_logger

CONTRACT_PATH = Path(__file__).resolve().parents[1] / "config" / "data_contract.json"
logger = setup_logger(__name__)


def _safe_get(d: Dict, key: str, default=None) -> Any:
    """
    Safely get nested dict value with default.
    
    Args:
        d (Dict): Dictionary to get value from
        key (str): Key to retrieve
        default: Value to return if key not found or d is not dict
    
    Returns:
        Any: Value or default
    """
    return d.get(key, default) if isinstance(d, dict) else default


def _normalize_points(pricing: Dict[str, Any]) -> Dict[str, Any]:
    """
    Ensure points fields are filled with sensible defaults.
    
    Parses points_price_raw if points_amount is missing.
    
    Args:
        pricing (Dict[str, Any]): Pricing dict from scraped data
    
    Returns:
        Dict[str, Any]: Normalized points with amount and currency
    """
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
    """
    Normalize cash copay fields with defaults.
    
    Parses cash_copay_raw if cash_copay_amount is missing.
    
    Args:
        pricing (Dict[str, Any]): Pricing dict from scraped data
    
    Returns:
        Dict[str, Any]: Normalized cash with amount and currency
    """
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
    """
    Transform and normalize a single flight record.
    
    Standardizes field names, normalizes data types, and normalizes nested structures.
    
    Args:
        rec (Dict[str, Any]): Raw flight record from scraper
    
    Returns:
        Dict[str, Any]: Normalized record matching data contract schema
    """
    # Extract pricing dict from record
    pricing = _safe_get(rec, "pricing", {}) or {}
    points = _normalize_points(pricing)
    cash = _normalize_cash(pricing)

    def _format_duration(val):
        if val is None:
            return None
        if isinstance(val, (int, float)):
            try:
                minutes_val = int(val)
                hours = minutes_val // 60
                minutes = minutes_val % 60
                return f"{hours}h {minutes}m"
            except Exception:
                return str(val)
        return str(val)

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
        "duration": _format_duration(rec.get("duration")),
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


def _validate_type(val: Any, expected_types: List[str]) -> bool:
    """
    Validate value against list of JSON Schema types.
    
    Args:
        val (Any): Value to validate
        expected_types (List[str]): JSON Schema type names (string, integer, null, etc.)
    
    Returns:
        bool: True if value matches one of the expected types
    """
    py_types = []
    for t in expected_types:
        if t == "string":
            py_types.append(str)
        elif t == "integer":
            py_types.append(int)
        elif t == "number":
            py_types.append((int, float))
        elif t == "null":
            if val is None:
                return True
            continue
    return isinstance(val, tuple(py_types))


def _validate_schema(data: Any, schema: Dict[str, Any], path: str = "root", errors: Optional[List[str]] = None) -> List[str]:
    """
    Recursively validate data against JSON Schema.
    
    Custom implementation (not using jsonschema library) for control and error messages.
    
    Args:
        data (Any): Data to validate
        schema (Dict[str, Any]): JSON Schema
        path (str): Current path in nested structure (for error messages)
        errors (Optional[List[str]]): Accumulated error list
    
    Returns:
        List[str]: List of validation errors (empty if valid)
    """
    if not isinstance(schema, dict):
        return errors

    expected_type = schema.get("type")
    if expected_type:
        types_list = expected_type if isinstance(expected_type, list) else [expected_type]
        if "null" in types_list and data is None:
            pass
        elif "object" in types_list and isinstance(data, dict):
            pass
        elif "array" in types_list and isinstance(data, list):
            pass
        elif any(t in ["string", "number", "integer"] for t in types_list):
            if not _validate_type(data, types_list):
                errors.append(f"{path}: expected {types_list}, got {type(data).__name__}")
                return errors
        elif not isinstance(data, dict) and not isinstance(data, list):
            errors.append(f"{path}: expected {types_list}, got {type(data).__name__}")
            return errors

    if isinstance(data, dict):
        required = schema.get("required", [])
        props = schema.get("properties", {})
        for req in required:
            if req not in data:
                errors.append(f"{path}: missing required key '{req}'")
        for key, subschema in props.items():
            if key in data:
                _validate_schema(data[key], subschema, f"{path}.{key}", errors)
    elif isinstance(data, list):
        item_schema = schema.get("items")
        if item_schema:
            for idx, item in enumerate(data):
                _validate_schema(item, item_schema, f"{path}[{idx}]", errors)
    return errors


def transform_run(input_path: Path, output_path: Optional[Path] = None) -> Path:
    """
    Transform raw scraper output into normalized, validated format.
    
    Reads raw JSON from scraper, normalizes each record, validates against contract,
    and saves transformed output.
    
    Args:
        input_path (Path): Path to raw run_*.json file from scraper
        output_path (Optional[Path]): Output path (auto-generated if None)
    
    Returns:
        Path: Path to transformed output file
    
    Example:
        >>> output = transform_run(Path("output/run_2025-11-30T09-02-51Z.json"))
        >>> print(output)
        Path('output/run_2025-11-30T09-02-51Z_transformed.json')
    """
    # Load raw JSON from input file
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

    # Validate against contract if present
    if contract:
        errors = _validate_schema(cleaned, contract, "root", [])
        if errors:
            logger.warning(f"Schema validation reported {len(errors)} issue(s):")
            for e in errors:
                logger.warning(f" - {e}")

    if output_path is None:
        stem = input_path.stem + "_transformed"
        output_path = input_path.with_name(f"{stem}{input_path.suffix}")
    output_path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
    logger.info(f"Transformed {len(cleaned['flights'])} flight record(s) from {input_path} into {output_path} | validation_errors={len(errors) if contract else 0}")
    return output_path


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python -m src.transform <input_json> [output_json]")
        sys.exit(1)
    inp = Path(sys.argv[1])
    outp = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    result = transform_run(inp, outp)
    print(f"Transformed file written to: {result}")
