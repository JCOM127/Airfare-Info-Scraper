import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.transform import transform_run, _validate_schema, CONTRACT_PATH


def test_transform_and_validate(tmp_path):
    raw = {
        "run_timestamp_utc": "2025-12-01T00:00:00Z",
        "origin_dest_pairs": [
            {
                "inputs_from": "LHR",
                "inputs_to": "DFW",
                "program": "American",
                "departure_date": "2025-12-05",
                "duration": "9h 30m",
                "class": "business",
                "stops": 0,
                "flight_number": "AA50",
                "last_updated": "2025-11-30T18:00:00Z",
                "legs": [
                    {
                        "leg_departure_datetime": "2025-12-05T10:00:00Z",
                        "leg_arrival_datetime": "2025-12-05T19:30:00Z",
                        "leg_flight_number": "AA50",
                        "leg_distance": 4744,
                        "leg_airplane": "Boeing 777-300ER",
                        "leg_class": "business",
                    }
                ],
                "pricing": {
                    "points_price_raw": "75,000 pts + $123",
                    "points_amount": 75000,
                    "points_program_currency": "AAdvantage",
                    "cash_copay_raw": "$123",
                    "cash_copay_amount": 123.0,
                    "cash_copay_currency": "USD",
                    "cents_per_point": 0.164,
                    "total_value_usd": None,
                },
            }
        ],
    }
    raw_path = tmp_path / "raw.json"
    raw_path.write_text(json.dumps(raw), encoding="utf-8")

    out_path = transform_run(raw_path)
    assert out_path.exists()
    transformed = json.loads(out_path.read_text(encoding="utf-8"))
    assert transformed["run_timestamp_utc"] == "2025-12-01T00:00:00Z"
    assert len(transformed["flights"]) == 1
    flight = transformed["flights"][0]
    assert flight["inputs_from"] == "LHR"
    assert flight["pricing"]["points_amount"] == 75000

    schema = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    errors = _validate_schema(transformed, schema, "root", [])
    assert errors == []
