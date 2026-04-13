import json
import os
from pathlib import Path

# Config file lives alongside downloads so it's always on a persisted volume.
# Falls back to next to main.py for local dev.
_DOWNLOAD_PATH_FROM_ENV = os.environ.get("YTDL_DOWNLOAD_PATH", "")

DEFAULT_CONFIG = {
    "download_path": _DOWNLOAD_PATH_FROM_ENV or "/app/downloads",
    "cookies_path": "",
    "potoken": "",
}


def _config_path() -> Path:
    """Config file is stored in the download directory so it survives restarts."""
    dl = _DOWNLOAD_PATH_FROM_ENV or DEFAULT_CONFIG["download_path"]
    p = Path(dl)
    if p.exists():
        return p / "config.json"
    # Fallback for local dev (no volume mounted)
    return Path(__file__).parent / "config.json"


def get_config() -> dict:
    cp = _config_path()
    if cp.exists():
        try:
            data = json.loads(cp.read_text())
            return {**DEFAULT_CONFIG, **data}
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(data: dict):
    merged = {**DEFAULT_CONFIG, **data}
    cp = _config_path()
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps(merged, indent=2))
