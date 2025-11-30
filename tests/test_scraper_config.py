import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_config


def test_config_loads_defaults():
    cfg = get_config()
    assert cfg.project_name is not None
    assert cfg.scraping_settings.timeout_ms > 0
    assert len(cfg.routes) > 0
