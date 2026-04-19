import asyncio
import json
import os
import re
import shlex
import shutil
import signal
import urllib.request
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import unquote
from pathlib import Path
from typing import Optional
from html import unescape

import aiofiles
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import get_config, save_config
from logger import log_command, redact_cmd
from jobs import JobManager
from proxies import ProxyManager

# Initialize managers once
job_manager = JobManager(get_config()["data_path"])
proxy_manager = ProxyManager(get_config()["data_path"])
proxy_stop_event = asyncio.Event()

# Global Constants
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
QUALITY_MAP = {
    "best": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
}

# Global state for broadcasting progress
# job_id -> list of asyncio.Queue
subscribers: dict[str, list[asyncio.Queue]] = {}


async def proxy_worker():
    """Background task that scavenges for healthy proxies every hour if idle."""
    while True:
        # Check every 10 mins if we need to start a scavenge
        await asyncio.sleep(600) 
        
        cfg = get_config()
        if not cfg.get("auto_proxy_enabled"):
            continue

        # Check for 1h cycle since last success
        if time.time() - proxy_manager.last_full_refresh < 3600:
            continue

        # Strictly only if idle
        running_jobs = [j for j in job_manager.get_all_jobs().values() if j.get("status") == "running"]
        if len(running_jobs) == 0:
            proxy_stop_event.clear()
            await proxy_manager.scavenge(proxy_stop_event)


def build_proxy_url(cfg: dict) -> Optional[str]:
    """Helper to build a standard proxy URL from granular config."""
    if not cfg.get("proxy_enabled") or not cfg.get("proxy_host"):
        return None
    
    p_type = cfg.get("proxy_type", "socks5")
    host = cfg.get("proxy_host")
    port = cfg.get("proxy_port")
    
    if cfg.get("proxy_auth_enabled"):
        user = cfg.get("proxy_username", "")
        pw = cfg.get("proxy_password", "")
        auth = f"{user}:{pw}@" if user or pw else ""
        return f"{p_type}://{auth}{host}:{port}" if port else f"{p_type}://{auth}{host}"
    
    return f"{p_type}://{host}:{port}" if port else f"{p_type}://{host}"

# Helper to fetch PO Token and Visitor Data from local sidecar
async def get_auto_potoken() -> tuple[str, str]:
    def fetch():
        # List of endpoints/methods to try
        strategies = [
            {"path": "/get_pot", "method": "POST", "data": b"{}"},
            {"path": "/token", "method": "POST", "data": b"{}"},
            {"path": "/get_pot", "method": "GET", "data": None},
        ]
        
        max_attempts = 2
        for attempt in range(max_attempts):
            for strategy in strategies:
                try:
                    url = f"http://pot-provider:4416{strategy['path']}"
                    req = urllib.request.Request(url, data=strategy["data"])
                    if strategy["method"] == "POST":
                        req.add_header('Content-Type', 'application/json')
                    
                    with urllib.request.urlopen(req, timeout=15) as response:
                        raw_data = response.read()
                        res_data = json.loads(raw_data)
                        print(f"[PO Token] Raw Response from {strategy['path']}: {raw_data.decode()}", flush=True)
                        
                        token = res_data.get("po_token") or res_data.get("poToken") or res_data.get("token") or ""
                        # Check multiple common keys for the visitor id
                        v_id_raw = (
                            res_data.get("visit_identifier") or 
                            res_data.get("visitorData") or 
                            res_data.get("visitor_data") or 
                            res_data.get("contentBinding") or
                            res_data.get("visitor_id") or ""
                        )
                        
                        # URL Decode if present
                        visitor_id = unquote(v_id_raw) if v_id_raw else ""
                        
                        if token:
                            return token, visitor_id
                except Exception:
                    continue
        return "", ""
    return await asyncio.to_thread(fetch)


# Startup Check for PO Token Provider
async def check_pot_connectivity():
    # Wait 5 seconds for the sidecar container to finish booting
    await asyncio.sleep(5)
    print("[System] Checking connectivity to PO Token provider...", flush=True)
    token, _ = await get_auto_potoken()
    if token:
        print("\033[92m[System] PO Token Provider is REACHABLE and functional.\033[0m", flush=True)
    else:
        print("\033[93m[System] WARNING: PO Token Provider is unreachable. Auto-token may fail.\033[0m", flush=True)


# Periodic state saver to prevent data loss without thrashing the disk
async def checkpoint_saver():
    while True:
        await asyncio.sleep(60)
        try:
            await job_manager.save_async()
        except:
            pass


async def get_video_title(url: str, potoken: str, visitor_id: str, proxy_url: str = None) -> str:
    """Fetch video title. Tries a lightweight HTML fetch first, falls back to yt-dlp."""
    # 1. Lightweight HTML fetch (Fastest, often bypasses bot walls)
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0 Safari/537.36'}
        # Simple urllib opener (supports HTTP proxies, SOCKS5 skipped for this light fetch)
        if proxy_url and proxy_url.startswith("http"):
            proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
            opener = urllib.request.build_opener(proxy_handler)
        else:
            opener = urllib.request.build_opener()
        
        def fetch():
            req = urllib.request.Request(url, headers=headers)
            with opener.open(req, timeout=5) as response:
                html = response.read().decode('utf-8', errors='ignore')
                m = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
                if m:
                    t = m.group(1).replace(' - YouTube', '').strip()
                    if t and t.lower() != "youtube":
                        return t
                return None
        
        simple_title = await asyncio.to_thread(fetch)
        if simple_title:
            from html import unescape
            final_t = unescape(simple_title)
            print(f"[get_video_title] Simple fetch success: {final_t}", flush=True)
            return final_t
    except Exception as e:
        print(f"[get_video_title] Simple fetch failed: {e}", flush=True)

    # 2. yt-dlp Fallback (Full extraction)
    try:
        # SAFE MODE: complex arguments to bypass bot detection on bad IPs
        # cmd = ["yt-dlp", url, "--get-title", "--js-runtimes", "node"]
        # cmd += ["--extractor-args", "youtubetab:skip=webpage"]
        # y_args = ["player_client=default,-web,-web_safari", "player_skip=webpage,configs"]
        # if potoken:
        #     y_args.append(f"po_token=web+{potoken}")
        # if visitor_id:
        #     y_args.append(f"visitor_data={visitor_id}")
        # cmd += ["--extractor-args", f"youtube:{';'.join(y_args)}"]
        # if visitor_id:
        #     cmd += ["--add-header", f"X-Goog-Visitor-Id:{visitor_id}"]

        # Create a temp cache for the title fetcher to keep it isolated
        t_cache = Path(os.environ.get("YTDL_DATA_PATH", "/app/data")) / "tmp" / f"cache_{uuid.uuid4().hex[:8]}"
        cmd = ["yt-dlp", url, "--get-title", "--cache-dir", str(t_cache), "--js-runtimes", "node", "--remote-components", "ejs:github"]
        if potoken:
            cmd += ["--extractor-args", f"youtube:po_token=web+{potoken}"]
        if visitor_id:
            cmd += ["--add-header", f"X-Goog-Visitor-Id:{visitor_id}"]
        if proxy_url:
            cmd += ["--proxy", proxy_url]
        
        print(f"[get_video_title] EXECUTING: {redact_cmd(cmd)}", flush=True)

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=15.0)
        
        if process.returncode != 0:
            print(f"[get_video_title] ERROR: {stderr.decode()}", flush=True)
            return "Unknown Title"
            
        return stdout.decode().strip() or "Unknown Title"
    except Exception as e:
        print(f"[get_video_title] EXCEPTION: {e}", flush=True)
        return "Unknown Title"


# Global state for broadcasting progress
# job_id -> list of asyncio.Queue
subscribers: dict[str, list[asyncio.Queue]] = {}

# ANSI escape sequence stripper for cleaner regex matching
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

async def broadcast_output(job_id: str, process: asyncio.subprocess.Process, mode: str):
    """Single reader task that broadcasts subprocess output to all subscribers."""
    buffer = ""
    stalled_seconds = 0
    has_progressed = False
    last_broadcast = 0
    
    try:
        # Smaller chunks for standard downloads for faster feedback
        chunk_size = 1024 if mode == "livestream" else 128

        while process.returncode is None:
            try:
                chunk_bytes = await asyncio.wait_for(process.stdout.read(chunk_size), timeout=15.0)
                if not chunk_bytes:
                    break
                
                stalled_seconds = 0 # Reset watchdog
                buffer += chunk_bytes.decode("utf-8", errors="replace")
                lines = re.split(r"[\r\n]+", buffer)
                buffer = lines.pop() if lines else ""
                
                latest_event_data = None
                for line in lines:
                    # Strip ANSI codes and whitespace for robust matching
                    clean_line = ANSI_ESCAPE.sub('', line).strip()
                    if not clean_line: continue
                    
                    print(f"[job:{job_id[:8]}] {clean_line}", flush=True)
                    
                    if mode == "livestream":
                        # Improved regex: specifically look for Video Fragments as the primary progress indicator
                        # Also handles the generic "Segments: X" format
                        if "Video Fragments" in clean_line or "Segments" in clean_line:
                            has_progressed = True
                            # Find all fragment/segment numbers in the line
                            all_nums = re.findall(r"(?:Fragments|Segments|frags):\s*(\d+)", clean_line, re.IGNORECASE)
                            if all_nums:
                                # If both V and A are present, sum them for "Total chunks"
                                # but if just one is present, use that.
                                segments = sum(int(n) for n in all_nums)
                                is_live = any(word in clean_line.lower() for word in ["live", "up to date", "current"])
                                job_manager.update_job(job_id, {"segments": segments, "is_live": is_live}, save_to_disk=False)
                                latest_event_data = {"live": is_live, "segments": segments, "mode": "livestream"}
                                
                                # Always broadcast livestream updates immediately to keep UI active
                                if job_id in subscribers:
                                    msg = f"data: {json.dumps(latest_event_data)}\n\n"
                                    for q in subscribers[job_id]:
                                        await q.put(msg)
                                    last_broadcast = time.time()
                                    latest_event_data = None # Prevent double-broadcast below
                    elif mode == "ffmpeg":
                        # FFmpeg progress: frame= 123 ... time=00:00:05.12 ...
                        time_match = re.search(r"time=(\d+:\d+:\d+\.\d+)", clean_line)
                        if time_match:
                            has_progressed = True
                            cur_time_str = time_match.group(1)
                            # Convert HH:MM:SS.ms to seconds
                            h, m, s = cur_time_str.split(':')
                            cur_sec = int(h)*3600 + int(m)*60 + float(s)
                            
                            duration = job_manager.get_job(job_id).get("duration_s", 0)
                            if duration > 0:
                                percent = min(100.0, round((cur_sec / duration) * 100, 1))
                                job_manager.update_job(job_id, {"percent": percent}, save_to_disk=False)
                                latest_event_data = {"percent": percent}
                    else:
                        # Robust regex: handles varying spaces, tildes, and missing ETA/Speed
                        dl_match = re.search(r"\[download\]\s+([\d.]+)%\s+of\s+([~\d.]+\S+)(?:\s+at\s+([~\d.]+\S+))?(?:\s+ETA\s+([~\d:]+))?", clean_line)
                        if dl_match:
                            has_progressed = True
                            percent = float(dl_match.group(1))
                            job_manager.update_job(job_id, {"percent": percent}, save_to_disk=False)
                            latest_event_data = {
                                "percent": percent, 
                                "speed": (dl_match.group(3) or "").replace("~", ""), 
                                "eta": (dl_match.group(4) or "").replace("~", "")
                            }

                # Send the most recent progress update from this chunk
                now = time.time()
                if latest_event_data and job_id in subscribers:
                    if now - last_broadcast > 0.1 or mode == "livestream":
                        msg = f"data: {json.dumps(latest_event_data)}\n\n"
                        for q in subscribers[job_id]:
                            await q.put(msg)
                        last_broadcast = now
                elif job_id in subscribers:
                    if now - last_broadcast > 10:
                        for q in subscribers[job_id]:
                            await q.put('data: {"ping": true}\n\n')
                        last_broadcast = now

            except asyncio.TimeoutError:
                # 1. Heartbeat: Keep UI connection alive regardless of progress
                if job_id in subscribers:
                    for q in subscribers[job_id]:
                        await q.put('data: {"ping": true}\n\n')
                last_broadcast = time.time()

                # 2. Safety Shield: If we've seen progress, don't time out (livestreams/merges)
                if has_progressed:
                    continue

                # 3. Watchdog: Kill jobs that never start (bot block/stuck proxy)
                stalled_seconds += 15
                if stalled_seconds >= 120:
                    print(f"\033[91m[job:{job_id[:8]}] TIMEOUT: No output for 120s. Terminating.\033[0m", flush=True)
                    process.terminate()
                    is_livestream = (mode == "livestream")
                    job_manager.update_job(job_id, {"status": "cancelled", "cleanup_files": not is_livestream}, save_to_disk=True)
                    if job_id in subscribers:
                        timeout_msg = f"data: {json.dumps({'error': 'Download stalled for 120s (Bot Block). Job terminated.'})}\n\n"
                        for q in subscribers[job_id]:
                            await q.put(timeout_msg)
                    return
                continue
    except Exception as e:
        print(f"Broadcaster error for {job_id}: {e}")
    finally:
        # Final Signal: Wait a moment for the watcher task to set 'done'
        await asyncio.sleep(0.5)
        if job_id in subscribers:
            job = job_manager.get_job(job_id)
            # Include output/title in the final signal so the UI can display it
            final_data = {"done": True}
            if job:
                if job.get("output"): final_data["output"] = job.get("output")
                if job.get("title"): final_data["title"] = job.get("title")

            msg = f"data: {json.dumps(final_data)}\n\n"
            for q in subscribers[job_id]:
                await q.put(msg)
            del subscribers[job_id]


async def watch_job(job_id: str, process: asyncio.subprocess.Process):
    """Background task that waits for a process to finish and handles cleanup."""
    rc = await process.wait()
    
    current_job = job_manager.get_job(job_id)
    if not current_job:
        return

    is_success = rc in [0, -2, 2, 130]
    temp_dir = current_job.get("temp_dir")
    is_livestream = current_job.get("mode") == "livestream"

    # Determine final status
    final_status = "cancelled" if current_job.get("status") == "cancelled" else "done"
    if not is_success and final_status != "cancelled":
        final_status = "error"
        print(f"\033[91m[job:{job_id[:8]}] Process failed with code {rc}\033[0m", flush=True)
    elif is_success and final_status == "done":
        print(f"\033[92m[job:{job_id[:8]}] Job completed successfully.\033[0m", flush=True)

    # Cleanup logic
    if temp_dir and os.path.exists(temp_dir):
        cleanup_requested = current_job.get("cleanup_files")

        # If it's a livestream that did NOT succeed, preserve files and try to recover.
        if is_livestream and not is_success and final_status != "cancelled":
            print(f"[job:{job_id[:8]}] Livestream process ended unsuccessfully. Preserving temp files and attempting recovery.", flush=True)
            asyncio.create_task(auto_recover_livestreams([job_id]))
        # Otherwise, cleanup if success or if explicitly requested.
        elif is_success or cleanup_requested:
            try:
                shutil.rmtree(temp_dir)
            except Exception as e:
                print(f"[job:{job_id[:8]}] Error during temp dir cleanup: {e}", flush=True)


    job_manager.update_job(job_id, {"status": final_status, "pid": None}, save_to_disk=True)
    if job_id in job_manager.processes:
        del job_manager.processes[job_id]


async def auto_recover_livestreams(job_ids: list[str]):
    """
    Automatically recover interrupted livestreams.
    First, it checks for a large, pre-merged file to move. If not found, it
    falls back to concatenating all .ts fragments using FFmpeg.
    """
    for jid in job_ids:
        job = job_manager.get_job(jid)
        if not job: continue

        if job.get("mode") != "livestream":
            url = job.get("url", "Unknown URL")
            print(f"\033[93m[System] WARNING: Non-livestream download was aborted: {jid[:8]} (URL: {url})\033[0m", flush=True)
            temp_dir = job.get("temp_dir")
            if temp_dir and os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    print(f"[System] Cleaned up temp files for aborted job: {jid[:8]}", flush=True)
                except: pass
            continue

        print(f"[System] Attempting auto-recovery for interrupted livestream: {jid[:8]}", flush=True)
        try:
            cfg = get_config()
            out_path = Path(cfg["output_path"])
            target_dir = Path(job.get("temp_dir") or cfg["download_path"])
            
            # 1. Fast path: Look for an already-merged file from ytarchive
            possible_merged_files = list(target_dir.glob("*.mp4")) + list(target_dir.glob("*.ts"))
            large_files = [f for f in possible_merged_files if f.stat().st_size > 5_000_000] # > 5MB

            if large_files:
                merged_file = max(large_files, key=lambda f: f.stat().st_size)
                output_file = out_path / f"[RECOVERED]_{merged_file.name}"
                print(f"[System] Found pre-merged file: {merged_file.name}. Moving to outputs.", flush=True)
                shutil.move(str(merged_file), str(output_file))
                job_manager.update_job(jid, {"status": "done"}, save_to_disk=True)
                # Cleanup the rest of the temp dir
                shutil.rmtree(target_dir)
                continue

            # 2. Slow path: Concatenate fragments with ffmpeg
            ts_files = sorted(target_dir.glob("*.ts"))
            if not ts_files:
                print(f"[System] No segments found for recovery: {jid[:8]}", flush=True)
                job_manager.update_job(jid, {"status": "error"}, save_to_disk=True)
                continue

            output_file = out_path / f"[RECOVERED]_{jid[:8]}.mp4"
            concat_file = target_dir / f"concat_recovery_{jid}.txt"
            
            with open(concat_file, "w") as f:
                for ts in ts_files:
                    safe_path = str(ts.resolve()).replace("'", "'\\''")
                    f.write(f"file '{safe_path}'\n")

            cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(output_file)]
            log_command(jid, cmd)
            process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            job_manager.update_job(jid, {"status": "running", "type": "finalize", "pid": process.pid}, save_to_disk=True)
            job_manager.processes[jid] = process
            asyncio.create_task(watch_job(jid, process))
            asyncio.create_task(broadcast_output(jid, process, "ffmpeg"))

        except Exception as e:
            print(f"\033[91m[System] Recovery failed for {jid[:8]}: {e}\033[0m", flush=True)
            job_manager.update_job(jid, {"status": "error"}, save_to_disk=True)


async def cleanup_stale_temp_dirs():
    """On startup, cleans up old, abandoned temporary job directories."""
    print("[System] Running stale temp directory cleanup...", flush=True)
    cfg = get_config()
    download_path = Path(cfg.get("download_path"))
    if not download_path.exists():
        return

    seven_days_ago = time.time() - (7 * 24 * 60 * 60)
    active_job_dirs = {job.get("temp_dir") for job in job_manager.get_all_jobs().values() if job.get("temp_dir")}

    for p in download_path.iterdir():
        if p.is_dir() and p.name.startswith("job_"):
            try:
                if str(p) in active_job_dirs:
                    continue
                
                if p.stat().st_mtime < seven_days_ago:
                    print(f"[System] Deleting stale temp directory: {p.name}", flush=True)
                    shutil.rmtree(p)
            except Exception as e:
                print(f"[System] Error cleaning up stale directory {p.name}: {e}", flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    asyncio.create_task(check_pot_connectivity())
    asyncio.create_task(checkpoint_saver())
    asyncio.create_task(cleanup_stale_temp_dirs())
    asyncio.create_task(proxy_worker())
    to_recover = job_manager.cleanup_on_startup()
    if to_recover:
        asyncio.create_task(auto_recover_livestreams(to_recover))
    yield
    job_manager.save()


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/settings")
def api_get_settings():
    return get_config()


@app.post("/api/settings")
async def api_save_settings(request: Request):
    data = await request.json()
    save_config(data)
    for key in ["data_path", "download_path", "output_path"]:
        p = data.get(key)
        if p: Path(p).mkdir(parents=True, exist_ok=True)
    output_dir = data.get("output_path", "/app/outputs")
    Path(output_dir, "ffmpeg").mkdir(parents=True, exist_ok=True)
    job_manager.path = Path(data.get("data_path", "/app/data"))
    job_manager.jobs_file = job_manager.path / "jobs.json"
    job_manager.load()
    return {"status": "saved"}


@app.get("/api/jobs")
def api_get_jobs():
    all_jobs = job_manager.get_all_jobs()
    return {jid: {k: v for k, v in j.items() if k != "process"} for jid, j in all_jobs.items()}


@app.post("/api/jobs/clear")
def api_clear_jobs():
    to_remove = [jid for jid, j in job_manager.jobs.items() if j.get("status") != "running"]
    for jid in to_remove: job_manager.remove_job(jid)
    return {"status": "cleared"}


@app.post("/api/jobs/finalize/{job_id}")
async def api_finalize_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job or job.get("mode") != "livestream":
        raise HTTPException(status_code=400, detail="Invalid job for finalization")
    dl_path = get_config()["download_path"]
    out_path = get_config()["output_path"]
    target_dir = job.get("temp_dir") or dl_path
    ts_files = sorted(Path(target_dir).glob("*.ts"))
    if not ts_files: raise HTTPException(status_code=404, detail="No segments found")
    output_file = f"{out_path}/recovered_{job_id[:8]}.mp4"
    concat_file = Path(target_dir) / f"concat_{job_id}.txt"
    with open(concat_file, "w") as f:
        for ts in ts_files:
            # Pre-process path outside f-string to avoid SyntaxError
            safe_path = str(ts.resolve()).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd = ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", output_file]
    log_command(job_id, cmd)
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    job_manager.update_job(job_id, {"status": "running", "pid": process.pid, "type": "finalize"}, save_to_disk=True)
    job_manager.processes[job_id] = process
    return {"job_id": job_id, "status": "finalizing"}


@app.get("/api/library")
def api_library():
    cfg = get_config()
    files = []
    def scan_dir(base_path: Path, label: str):
        if not base_path.exists(): return
        for p in sorted(base_path.iterdir()):
            if p.is_file():
                s = p.stat()
                files.append({"name": p.name, "size": s.st_size, "modified": s.st_mtime, "folder": label, "path": f"{label}/{p.name}"})
    scan_dir(Path(cfg["output_path"]), "outputs")
    scan_dir(Path(cfg["output_path"]) / "ffmpeg", "outputs/ffmpeg")
    scan_dir(Path(cfg["download_path"]), "downloads")
    return files


@app.get("/api/library/stream/{folder:path}/{filename}")
async def api_library_stream(folder: str, filename: str, request: Request):
    cfg = get_config()
    base_map = {"outputs": Path(cfg["output_path"]), "outputs/ffmpeg": Path(cfg["output_path"]) / "ffmpeg", "downloads": Path(cfg["download_path"])}
    base_path = base_map.get(folder)
    if not base_path: raise HTTPException(status_code=404)
    file_path = (base_path / filename).resolve()
    if not str(file_path).startswith(str(base_path.resolve())) or not file_path.exists(): raise HTTPException(status_code=403)
    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")
    content_type = {"mp4": "video/mp4", "mkv": "video/x-matroska", "ts": "video/mp2t", "webm": "video/webm", "mp3": "audio/mpeg", "m4a": "audio/mp4"}.get(file_path.suffix.lower()[1:], "application/octet-stream")
    if range_header:
        m = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not m: raise HTTPException(status_code=416)
        start, end = int(m.group(1)), int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        async def gen():
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)
                rem = end - start + 1
                while rem > 0:
                    data = await f.read(min(65536, rem))
                    if not data: break
                    rem -= len(data); yield data
        return StreamingResponse(gen(), status_code=206, media_type=content_type, headers={"Content-Range": f"bytes {start}-{end}/{file_size}", "Accept-Ranges": "bytes", "Content-Length": str(end - start + 1)})
    async def full_gen():
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                data = await f.read(65536)
                if not data: break
                yield data
    return StreamingResponse(full_gen(), media_type=content_type, headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)})


@app.post("/api/download")
async def api_download(url: str = Form(...), mode: str = Form(...), quality: str = Form("best"), reencode_audio: str = Form("false"), live_from: Optional[str] = Form(None), capture_duration: Optional[str] = Form(None)):
    cfg = get_config()
    job_id = str(uuid.uuid4())

    # 1. Stop background scavenger
    proxy_stop_event.set()

    # 2. Resolve all potential proxies
    manual_proxy = build_proxy_url(cfg)
    potential_proxies = [manual_proxy] if manual_proxy else []
    if cfg.get("auto_proxy_enabled"):
        potential_proxies.extend(proxy_manager.get_valid_proxies())

    # Fallback to direct if no proxies selected/available
    if not potential_proxies:
        potential_proxies = [None]

    # 3. Rotate through proxies (up to 5) to find one that works
    working_proxy = None
    title = "Unknown Title"
    potoken, visitor_id = "", ""

    for attempt, current_proxy in enumerate(potential_proxies[:5]):
        try:
            print(f"[job:{job_id[:8]}] Attempt {attempt+1}: Testing proxy {redact_cmd([current_proxy]) if current_proxy else 'DIRECT'}", flush=True)

            # Reset tokens for each new proxy attempt
            potoken, visitor_id = "", ""
            should_fetch_token = mode == "livestream" or cfg.get("enable_ytdlp_potoken")
            if should_fetch_token:
                if len(cfg.get("potoken", "").strip()) < 20:
                    potoken, visitor_id = await get_auto_potoken()
                else:
                    potoken = cfg["potoken"].strip()

            title = await get_video_title(url, potoken, visitor_id, current_proxy)

            if title and title != "Unknown Title":
                working_proxy = current_proxy
                print(f"[job:{job_id[:8]}] Found working connection with proxy: {working_proxy or 'DIRECT'}", flush=True)
                break
            else:
                # If title fetch failed, flag the proxy and try next
                if current_proxy and cfg.get("auto_proxy_enabled"):
                    proxy_manager.flag_proxy(current_proxy)
                print(f"[job:{job_id[:8]}] Proxy failed or flagged. Retrying...", flush=True)

        except Exception as e:
            print(f"[job:{job_id[:8]}] Proxy attempt error: {e}", flush=True)

    if len([j for j in job_manager.get_all_jobs().values() if j.get("type") == "download" and j.get("status") == "running"]) >= 5:
        raise HTTPException(status_code=429, detail="Limit reached")

    job_temp_dir = Path(cfg["download_path"]) / f"job_{job_id[:8]}"
    job_temp_dir.mkdir(parents=True, exist_ok=True)

    if mode == "livestream":
        safe_title = re.sub(r'[^\w\-\. ]', '_', title).strip() if title and title != "Unknown Title" else job_id[:8]
        cmd = ["ytarchive", "--newline", "--merge", "-td", str(job_temp_dir), "-o", f"{cfg['output_path']}/{safe_title}"]
        if cfg.get("cookies_path"): cmd += ["--cookies", cfg["cookies_path"]]
        if potoken: cmd += ["--potoken", potoken]
        if visitor_id: cmd += ["--visitor-data", visitor_id]
        # Proxy is disabled for livestreams as ytarchive is currently more trusted by YouTube
        # if working_proxy: cmd += ["--proxy", working_proxy]
        if live_from: cmd += ["--live-from", live_from]
        if capture_duration: cmd += ["--capture-duration", capture_duration]
        if cfg.get("ytarchive_args"): cmd.extend(shlex.split(cfg["ytarchive_args"]))
        cmd += [url, quality]
    else:
        # Standard download logic (Video/Audio)
        fmt = "bestaudio/best" if mode == "audio" else QUALITY_MAP.get(quality, QUALITY_MAP["best"])
        # Use a per-job cache directory to allow session persistence (fixing 403s) without clashing
        cmd = ["yt-dlp", "--newline", "--cache-dir", f"{job_temp_dir}/cache", "--js-runtimes", "node", "--remote-components", "ejs:github", "-f", fmt, "--paths", f"temp:{job_temp_dir}", "--paths", f"home:{cfg['output_path']}", "-o", "%(title)s.%(ext)s"]

        if mode == "audio":
            cmd += ["-x"]
            if reencode_audio == "true": 
                cmd += ["--audio-format", "mp3", "--postprocessor-args", "ffmpeg:-b:a 320k"]

        if cfg.get("cookies_path"): cmd += ["--cookies", cfg["cookies_path"]]

        # Inject tokens if available (governed by settings toggle)
        if potoken:
            y_args = [f"po_token=web+{potoken}"]
            if visitor_id: y_args.append(f"visitor_data={visitor_id}")
            cmd += ["--extractor-args", f"youtube:{';'.join(y_args)}"]

        if working_proxy:
            cmd += ["--proxy", working_proxy]

        if cfg.get("ytdlp_args"): cmd.extend(shlex.split(cfg["ytdlp_args"]))
        cmd.append(url)

    print(f"[job:{job_id[:8]}] EXECUTING: {redact_cmd(cmd)}", flush=True)
    log_command(job_id, cmd)
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
    job_manager.add_job(job_id, {
        "mode": mode, 
        "type": "download", 
        "temp_dir": str(job_temp_dir),
        "url": url,
        "title": title,
        "status": "running"
    }, process=process)

    asyncio.create_task(watch_job(job_id, process))
    asyncio.create_task(broadcast_output(job_id, process, mode))
    return {"job_id": job_id, "title": title}


@app.get("/api/download/progress/{job_id}")
async def api_download_progress(job_id: str):
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(status_code=404)
    async def stream():
        status = job.get("status")
        if status == "done": yield f"data: {json.dumps({'done': True})}\n\n"; return
        if status in ["error", "cancelled"]: yield f"data: {json.dumps({'error': 'Terminated'})}\n\n"; return
        
        # Subscribe to broadcast
        q = asyncio.Queue()
        if job_id not in subscribers: subscribers[job_id] = []
        subscribers[job_id].append(q)
        
        # Yield current progress immediately to prevent UI from waiting for next update
        initial_data = {"percent": job.get("percent", 0), "title": job.get("title")}
        if job.get("mode") == "livestream":
            initial_data.update({"segments": job.get("segments", 0), "live": job.get("is_live", False), "mode": "livestream"})
        yield f"data: {json.dumps(initial_data)}\n\n"
        
        try:
            while True:
                msg = await q.get()
                yield msg
                updated = job_manager.get_job(job_id)
                if not updated or updated.get("status") != "running":
                    if updated and updated.get("status") == "done": yield f"data: {json.dumps({'done': True})}\n\n"
                    break
        except Exception: pass
        finally:
            if job_id in subscribers and q in subscribers[job_id]: subscribers[job_id].remove(q)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/download/cancel/{job_id}")
async def api_download_cancel(job_id: str, delete: str = Form("false")):
    job = job_manager.get_job(job_id)
    if not job or "process" not in job: raise HTTPException(status_code=404)
    is_del = delete.lower() == "true"
    try:
        if job.get("mode") == "livestream":
            if is_del: job_manager.update_job(job_id, {"status": "cancelled", "cleanup_files": True}, save_to_disk=True); job["process"].terminate()
            else: job["process"].send_signal(signal.SIGINT); job_manager.update_job(job_id, {"status": "finishing"}, save_to_disk=True)
        else:
            job_manager.update_job(job_id, {"status": "cancelled", "cleanup_files": is_del}, save_to_disk=True); job["process"].terminate()
    except Exception: pass
    return {"status": "sent"}


@app.post("/api/ffmpeg/cut")
async def api_ffmpeg_cut(start: str = Form(...), end: str = Form(...), name: str = Form(...), reencode_full: str = Form("false"), library_path: str = Form(""), duration_s: str = Form("0"), video: Optional[UploadFile] = None):
    cfg = get_config()
    if len([j for j in job_manager.get_all_jobs().values() if j.get("type") == "ffmpeg" and j.get("status") == "running"]) >= 1:
        raise HTTPException(status_code=429, detail="Cut in progress")
    
    if library_path:
        parts = library_path.split("/", 1)
        if len(parts) < 2: raise HTTPException(status_code=400)
        base = {"outputs": Path(cfg["output_path"]), "outputs/ffmpeg": Path(cfg["output_path"]) / "ffmpeg", "downloads": Path(cfg["download_path"])}.get(parts[0])
        if not base: raise HTTPException(status_code=400)
        input_path = str((base / parts[1]).resolve())
    elif video:
        input_path = f"/tmp/{uuid.uuid4()}_{video.filename}"
        async with aiofiles.open(input_path, "wb") as f:
            while chunk := await video.read(65536): await f.write(chunk)
    else: raise HTTPException(status_code=400)

    is_audio = Path(input_path).suffix.lower() in [".mp3", ".m4a", ".aac", ".opus", ".ogg", ".flac", ".wav"]
    safe_name = re.sub(r'[^a-zA-Z0-9_\-]', '', name.replace(" ", "_"))
    ext = f".{cfg.get('audio_format', 'mp3')}" if is_audio else f".{cfg.get('video_format', 'mp4')}"
    output_file = f"{cfg['output_path']}/ffmpeg/{safe_name}{ext}"
    
    if is_audio:
        v_codec, a_codec = ["-vn"], ["libmp3lame", "-b:a", "320k"] if reencode_full == "true" or Path(input_path).suffix != ext else ["copy"]
    else:
        v_codec, a_codec = (["-c:v", "libx264", "-crf", "23", "-preset", "superfast"], ["-c:a", "aac", "-b:a", "192k"]) if reencode_full == "true" else (["-c:v", "copy"], ["-c:a", "aac", "-b:a", "192k"] if cfg.get("reencode_audio_instant") else ["-c:a", "copy"])

    cmd = ["ffmpeg", "-y", "-ss", start, "-to", end, "-i", input_path, "-copyts"]
    if is_audio: cmd += v_codec + ["-c:a"] + a_codec
    else: cmd += ["-map", "0"] + v_codec + a_codec + ["-c:s", "copy", "-avoid_negative_ts", "make_zero", "-strict", "-2"]
    if cfg.get("ffmpeg_args"): cmd.extend(shlex.split(cfg["ffmpeg_args"]))
    cmd.append(output_file)
    
    log_command(str(uuid.uuid4()), cmd)
    process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    jid = str(uuid.uuid4())
    job_manager.add_job(jid, {"type": "ffmpeg", "duration_s": float(duration_s), "output": output_file, "name": name, "status": "running"}, process=process)
    # Start the watcher and broadcaster
    asyncio.create_task(watch_job(jid, process))
    asyncio.create_task(broadcast_output(jid, process, "ffmpeg"))
    return {"job_id": jid}


@app.get("/api/ffmpeg/progress/{job_id}")
async def api_ffmpeg_progress(job_id: str):
    job = job_manager.get_job(job_id)
    if not job: raise HTTPException(status_code=404)
    async def stream():
        status = job.get("status")
        if status == "done": yield f"data: {json.dumps({'done': True, 'output': job.get('output')})}\n\n"; return
        
        q = asyncio.Queue()
        if job_id not in subscribers: subscribers[job_id] = []
        subscribers[job_id].append(q)
        
        # Yield current progress immediately
        yield f"data: {json.dumps({'percent': job.get('percent', 0), 'output': job.get('output')})}\n\n"
        
        try:
            while True:
                msg = await q.get()
                yield msg
                updated = job_manager.get_job(job_id)
                if not updated or updated.get("status") != "running":
                    if updated and updated.get("status") == "done": yield f"data: {json.dumps({'done': True, 'output': updated.get('output')})}\n\n"
                    break
        except Exception: pass
        finally:
            if job_id in subscribers and q in subscribers[job_id]: subscribers[job_id].remove(q)
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/ffmpeg/cancel/{job_id}")
async def api_ffmpeg_cancel(job_id: str):
    job = job_manager.get_job(job_id)
    if job and "process" in job:
        job["process"].terminate()
        job_manager.update_job(job_id, {"status": "cancelled"}, save_to_disk=True)
        for p in [job.get("output"), job.get("tmp_input")]:
            if p and os.path.exists(p): os.unlink(p)
    return {"status": "sent"}


app.mount("/", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "..", "frontend"), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    cfg = get_config()
    for k in ["data_path", "download_path", "output_path"]: Path(cfg[k]).mkdir(parents=True, exist_ok=True)
    Path(cfg["output_path"], "ffmpeg").mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=8047)
