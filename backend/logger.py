import shlex
from datetime import datetime, timezone
from pathlib import Path
from config import get_config


def log_command(job_id: str, cmd: list[str]):
    download_path = Path(get_config()["download_path"])
    log_dir = download_path.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "commands.log"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cmd_str = shlex.join(cmd)
    line = f"{timestamp}  [job:{job_id[:8]}]  {cmd_str}\n"

    with open(log_file, "a", encoding="utf-8") as f:
        f.write(line)
