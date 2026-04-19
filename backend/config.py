import json
import os
from pathlib import Path

# Config file lives alongside downloads so it's always on a persisted volume.
# Falls back to next to main.py for local dev.
_DATA_PATH_FROM_ENV = os.environ.get("YTDL_DATA_PATH", "")
_DOWNLOAD_PATH_FROM_ENV = os.environ.get("YTDL_DOWNLOAD_PATH", "")
_OUTPUT_PATH_FROM_ENV = os.environ.get("YTDL_OUTPUT_PATH", "")

DEFAULT_CONFIG = {
    "data_path": _DATA_PATH_FROM_ENV or "/app/data",
    "download_path": _DOWNLOAD_PATH_FROM_ENV or "/app/downloads",
    "output_path": _OUTPUT_PATH_FROM_ENV or "/app/outputs",
    "cookies_path": "",
    "potoken": "",
    "ytdlp_args": "",
    "ytarchive_args": "",
    "ffmpeg_args": "",
    "video_format": "mp4",
    "audio_format": "mp3",
    "reencode_audio_instant": False,
    "enable_ytdlp_potoken": False,
    "show_advanced_livestream": False,
    "auto_proxy_enabled": False,
    "high_precision_cutter": False,
    "proxy_enabled": False,
    "proxy_type": "socks5",
    "proxy_host": "",
    "proxy_port": "",
    "proxy_auth_enabled": False,
    "proxy_username": "",
    "proxy_password": "",
}


def _config_path() -> Path:
    """Config file is stored in the data directory so it survives restarts."""
    data_dir = _DATA_PATH_FROM_ENV or DEFAULT_CONFIG["data_path"]
    p = Path(data_dir)
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
