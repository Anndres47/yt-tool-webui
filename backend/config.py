import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "download_path": "/app/downloads",
    "cookies_path": "",
    "potoken": "",
}


def get_config() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text())
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(data: dict):
    merged = {**DEFAULT_CONFIG, **data}
    CONFIG_PATH.write_text(json.dumps(merged, indent=2))
