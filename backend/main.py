import asyncio
import json
import os
import re
import shlex
import shutil
import signal
import urllib.request
import uuid
from pathlib import Path
from typing import Optional

import aiofiles
from fastapi import FastAPI, Form, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from config import get_config, save_config
from logger import log_command
from jobs import JobManager

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
                        visitor_id = (
                            res_data.get("visit_identifier") or 
                            res_data.get("visitorData") or 
                            res_data.get("visitor_data") or 
                            res_data.get("visitor_id") or ""
                        )
                        
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


app = FastAPI()

@app.on_event("startup")
async def on_startup():
    asyncio.create_task(check_pot_connectivity())

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize job manager
job_manager = JobManager(get_config()["data_path"])
job_manager.cleanup_on_startup()


QUALITY_MAP = {
    "best": "bestvideo+bestaudio/best",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "720p": "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "480p": "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "360p": "bestvideo[height<=360]+bestaudio/best[height<=360]",
}

ONE_GB = 1 * 1024 * 1024 * 1024


def _write_file(path: str, data: bytes):
    """Synchronous file write, run in a thread to avoid blocking the event loop."""
    with open(path, "wb") as f:
        f.write(data)


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

@app.get("/api/settings")
def api_get_settings():
    return get_config()


@app.post("/api/settings")
async def api_save_settings(request: Request):
    data = await request.json()
    save_config(data)
    # Re-create directories if paths changed
    for key in ["data_path", "download_path", "output_path"]:
        p = data.get(key)
        if p:
            Path(p).mkdir(parents=True, exist_ok=True)
    
    # Ensure ffmpeg output dir exists
    output_dir = data.get("output_path", "/app/outputs")
    Path(output_dir, "ffmpeg").mkdir(parents=True, exist_ok=True)

    # Update job manager path
    data_dir = data.get("data_path", "/app/data")
    job_manager.path = Path(data_dir)
    job_manager.jobs_file = job_manager.path / "jobs.json"
    job_manager.load()
    return {"status": "saved"}


@app.get("/api/jobs")
def api_get_jobs():
    return job_manager.get_all_jobs()


@app.post("/api/jobs/clear")
def api_clear_jobs():
    # Only clear jobs that are NOT running
    to_remove = [jid for jid, j in job_manager.jobs.items() if j.get("status") != "running"]
    for jid in to_remove:
        job_manager.remove_job(jid)
    return {"status": "cleared"}


@app.post("/api/jobs/finalize/{job_id}")
async def api_finalize_job(job_id: str):
    job = job_manager.get_job(job_id)
    if not job or job.get("mode") != "livestream":
        raise HTTPException(status_code=400, detail="Invalid job for finalization")

    dl_path = get_config()["download_path"]
    out_path = get_config()["output_path"]
    # ytarchive typically uses {id}.f*.ts or similar.
    # We look for .ts files in the download directory.
    # This is a bit heuristic but helpful for recovery.
    ts_files = sorted(Path(dl_path).glob("*.ts"))
    if not ts_files:
        raise HTTPException(status_code=404, detail="No segments found to finalize")

    output_file = f"{out_path}/recovered_{job_id[:8]}.mp4"

    # Create a concat file for ffmpeg
    concat_file = Path(dl_path) / f"concat_{job_id}.txt"
    with open(concat_file, "w") as f:
        for ts in ts_files:
            # Use absolute path and escape single quotes for ffmpeg concat demuxer
            safe_path = str(ts.resolve()).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

    cmd = [
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", str(concat_file), "-c", "copy", output_file
    ]

    log_command(job_id, cmd)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    # Update job to track this new process
    job_manager.update_job(job_id, {"status": "running", "pid": process.pid, "type": "finalize"})
    job_manager.processes[job_id] = process

    return {"job_id": job_id, "status": "finalizing"}


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.get("/api/library")
def api_library():
    cfg = get_config()
    out_dir = Path(cfg["output_path"])
    dl_dir = Path(cfg["download_path"])
    
    files = []
    
    def scan_dir(base_path: Path, folder_label: str):
        if not base_path.exists():
            return
        for p in sorted(base_path.iterdir()):
            if p.is_file():
                stat = p.stat()
                # Relative path from the root of outputs or downloads
                # For streaming, we'll need to know which base it's in.
                files.append({
                    "name": p.name,
                    "size": stat.st_size,
                    "modified": stat.st_mtime,
                    "folder": folder_label,
                    "path": f"{folder_label}/{p.name}"
                })

    scan_dir(out_dir, "outputs")
    scan_dir(out_dir / "ffmpeg", "outputs/ffmpeg")
    scan_dir(dl_dir, "downloads")
    
    return files


@app.get("/api/library/stream/{folder:path}/{filename}")
async def api_library_stream(folder: str, filename: str, request: Request):
    cfg = get_config()
    
    # Map label to actual path
    base_map = {
        "outputs": Path(cfg["output_path"]),
        "outputs/ffmpeg": Path(cfg["output_path"]) / "ffmpeg",
        "downloads": Path(cfg["download_path"]),
    }
    
    base_path = base_map.get(folder)
    if not base_path:
        raise HTTPException(status_code=404, detail="Folder not found")
        
    file_path = (base_path / filename).resolve()

    # Security: ensure resolved path is inside the mapped base directory
    if not str(file_path).startswith(str(base_path.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    file_size = file_path.stat().st_size
    range_header = request.headers.get("range")

    # Determine content type
    suffix = file_path.suffix.lower()
    content_types = {
        ".mp4": "video/mp4", ".mkv": "video/x-matroska", ".ts": "video/mp2t",
        ".webm": "video/webm", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
        ".aac": "audio/aac", ".opus": "audio/ogg", ".ogg": "audio/ogg",
    }
    content_type = content_types.get(suffix, "application/octet-stream")

    if range_header:
        match = re.match(r"bytes=(\d+)-(\d*)", range_header)
        if not match:
            raise HTTPException(status_code=416, detail="Invalid Range")
        start = int(match.group(1))
        end = int(match.group(2)) if match.group(2) else file_size - 1
        end = min(end, file_size - 1)
        chunk_size = end - start + 1

        async def range_generator():
            async with aiofiles.open(file_path, "rb") as f:
                await f.seek(start)
                remaining = chunk_size
                while remaining > 0:
                    read_size = min(65536, remaining)
                    data = await f.read(read_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            range_generator(),
            status_code=206,
            media_type=content_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(chunk_size),
            },
        )

    async def full_generator():
        async with aiofiles.open(file_path, "rb") as f:
            while True:
                chunk = await f.read(65536)
                if not chunk:
                    break
                yield chunk

    return StreamingResponse(
        full_generator(),
        media_type=content_type,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        },
    )


# ---------------------------------------------------------------------------
# Download
# ---------------------------------------------------------------------------

@app.post("/api/download")
async def api_download(
    url: str = Form(...),
    mode: str = Form(...),      # video | livestream | audio
    quality: str = Form("best"),
    reencode_audio: str = Form("false"),
):
    cfg = get_config()
    dl_path = cfg["download_path"]
    out_path = cfg["output_path"]
    cookies = cfg.get("cookies_path", "")
    potoken = cfg.get("potoken", "")
    Path(dl_path).mkdir(parents=True, exist_ok=True)
    Path(out_path).mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())

    # Auto-fetch PO Token if not manually set (or if current token looks invalid/short)
    visitor_id = ""
    potoken = potoken.strip()
    if len(potoken) < 20: # Real tokens are very long strings
        print(f"[job:{job_id[:8]}] Auto-fetching PO Token...", flush=True)
        potoken, visitor_id = await get_auto_potoken()
        if potoken:
            print(f"[job:{job_id[:8]}] PO Token fetched (ID: {visitor_id[:10]}...)", flush=True)
        else:
            print(f"\033[93m[job:{job_id[:8]}] WARNING: Auto-fetch returned NO token. YouTube may block this request.\033[0m", flush=True)
    
    potoken = potoken.strip()
    visitor_id = visitor_id.strip()

    # Concurrency Limit Check (Max 5 active download jobs)
    active_downloads = [
        j for j in job_manager.get_all_jobs().values()
        if j.get("type") == "download" and j.get("status") == "running"
    ]
    if len(active_downloads) >= 5:
        raise HTTPException(
            status_code=429, 
            detail="Maximum concurrent downloads (5) reached. Please wait or cancel a download."
        )

    # Create a unique temp folder for this specific job to isolate its files
    job_temp_dir = Path(dl_path) / f"job_{job_id[:8]}"
    job_temp_dir.mkdir(parents=True, exist_ok=True)

    if mode == "livestream":
        # Map UI quality to ytarchive labels
        ytarchive_quality = quality
        if quality == "best":
            ytarchive_quality = "best"
        elif quality.endswith("p"):
            # ytarchive expects just "1080p", "720p", etc.
            pass
        
        # Base options
        cmd = ["ytarchive", "--newline", "--merge", "-td", str(job_temp_dir), "-o", f"{out_path}/{{id}}"]
        
        if cookies:
            cmd += ["--cookies", cookies]
        if potoken:
            cmd += ["--potoken", potoken]
        if visitor_id:
            # ytarchive dev branch uses --visitor for visitorData
            cmd += ["--visitor", visitor_id]
        
        # Append advanced arguments
        if cfg.get("ytarchive_args"):
            cmd.extend(shlex.split(cfg["ytarchive_args"]))

        # POSITIONAL ARGS LAST: [url] [quality]
        cmd.append(url)
        cmd.append(ytarchive_quality)

    elif mode == "audio":
        # --paths temp: is working dir, --paths home: is final dir
        cmd = ["yt-dlp", "--newline", "-f", "bestaudio",
               "--paths", f"temp:{job_temp_dir}", "--paths", f"home:{out_path}",
               "-o", "%(title)s.%(ext)s"]
        if reencode_audio == "true":
            cmd += ["-x", "--audio-format", "mp3",
                    "--postprocessor-args", "ffmpeg:-b:a 320k"]
        if cookies:
            cmd += ["--cookies", cookies]
        
        # Combine PO Token and Visitor ID for yt-dlp
        if potoken:
            token_arg = f"po_token=web+{potoken}"
            if visitor_id:
                token_arg += f";visitor_data={visitor_id}"
            cmd += ["--extractor-args", f"youtube:player-client=web,ios;{token_arg}"]
        
        # Append advanced arguments
        if cfg.get("ytdlp_args"):
            cmd.extend(shlex.split(cfg["ytdlp_args"]))

        cmd.append(url)

    else:  # video
        fmt = QUALITY_MAP.get(quality, QUALITY_MAP["best"])
        cmd = ["yt-dlp", "--newline", "-f", fmt,
               "--paths", f"temp:{job_temp_dir}", "--paths", f"home:{out_path}",
               "-o", "%(title)s.%(ext)s"]
        if cookies:
            cmd += ["--cookies", cookies]
        
        # Combine PO Token and Visitor ID for yt-dlp
        if potoken:
            token_arg = f"po_token=web+{potoken}"
            if visitor_id:
                token_arg += f";visitor_data={visitor_id}"
            cmd += ["--extractor-args", f"youtube:player-client=web,ios;{token_arg}"]
        
        # Append advanced arguments
        if cfg.get("ytdlp_args"):
            cmd.extend(shlex.split(cfg["ytdlp_args"]))

        cmd.append(url)

    # Log full command to console for debugging
    print(f"[job:{job_id[:8]}] EXECUTING: {shlex.join(cmd)}", flush=True)
    log_command(job_id, cmd)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    job_manager.add_job(job_id, {
        "mode": mode, 
        "type": "download", 
        "temp_dir": str(job_temp_dir),
        "url": url
    }, process=process)
    return {"job_id": job_id}


@app.get("/api/download/progress/{job_id}")
async def api_download_progress(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        process = job.get("process")
        mode = job.get("mode")

        if not process:
             yield f"data: {json.dumps({'error': 'Process not found or already finished'})}\n\n"
             return

        try:
            stalled_seconds = 0
            while True:
                try:
                    # Inner timeout: send heartbeats every 15s to keep SSE alive
                    line_bytes = await asyncio.wait_for(process.stdout.readline(), timeout=15.0)
                    stalled_seconds = 0 # Reset watchdog on any output
                except asyncio.TimeoutError:
                    stalled_seconds += 15
                    if stalled_seconds >= 120:
                        print(f"\033[91m[job:{job_id[:8]}] TIMEOUT: No output for 120s. Terminating.\033[0m", flush=True)
                        process.terminate()
                        job_manager.update_job(job_id, {"status": "cancelled", "cleanup_files": True})
                        yield f"data: {json.dumps({'error': 'Download stalled for 120s (Possible YouTube Bot Block). Job terminated.'})}\n\n"
                        return
                    
                    yield ": ping\n\n"
                    continue

                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                
                # Output to console so it appears in docker logs
                print(f"[job:{job_id[:8]}] {line}", flush=True)

                event = None

                if mode == "livestream":
                    # ytarchive progress: "Video Segments: 123 (4.5MB)  /  128"
                    # Handle "Video Segments: 123" or "Audio Segments: 123"
                    seg_match = re.search(r"(?:Video|Audio) Segments:\s*(\d+)", line, re.IGNORECASE)
                    if seg_match:
                        segments = int(seg_match.group(1))
                        # Check if live: ytarchive prints "at the live edge" or similar
                        is_live = any(word in line.lower() for word in ["live", "up to date", "current"])
                        event = json.dumps({
                            "live": is_live, 
                            "segments": segments,
                            "mode": "livestream"
                        })
                else:
                    # yt-dlp: [download]  42.3% of 1.23GiB at  3.21MiB/s ETA 00:12
                    # The regex handles optional ~ and extra spaces
                    dl_match = re.search(
                        r"\[download\]\s+([\d.]+)%\s+of\s+[\d.]+\S+\s+at\s+([~\d.]+\S+)\s+ETA\s+([~\d:]+)",
                        line,
                    )
                    if dl_match:
                        event = json.dumps({
                            "percent": float(dl_match.group(1)),
                            "speed": dl_match.group(2).replace("~", ""),
                            "eta": dl_match.group(3).replace("~", ""),
                        })

                if event:
                    yield f"data: {event}\n\n"

            rc = await process.wait()
            # rc == 0: success
            # rc == -2: SIGINT (handled by python)
            # rc == 2 or 130: SIGINT (handled by ytarchive/shell)
            if rc in [0, -2, 2, 130]:
                yield f"data: {json.dumps({'done': True})}\n\n"
            else:
                err_msg = f"Process exited with code {rc}"
                print(f"\033[91mERROR: {err_msg}\033[0m", flush=True)
                yield f"data: {json.dumps({'error': err_msg})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Check if it was already cancelled before setting to done
            current_job = job_manager.get_job(job_id)
            temp_dir = current_job.get("temp_dir") if current_job else None
            
            # If we have a dedicated temp dir, clean it up
            if temp_dir and os.path.exists(temp_dir):
                # If specifically requested to delete (Abort/Cancel)
                if current_job.get("cleanup_files"):
                    try:
                        shutil.rmtree(temp_dir)
                    except:
                        pass
                # On success, still remove the empty or leftover folder
                else:
                    try:
                        # Clean up if successful (files have been moved to outputs)
                        shutil.rmtree(temp_dir)
                    except:
                        pass

            final_status = "cancelled" if current_job and current_job.get("status") in ["cancelled", "finishing"] else "done"
            job_manager.update_job(job_id, {"status": final_status, "pid": None})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/download/cancel/{job_id}")
async def api_download_cancel(job_id: str, delete: str = Form("false")):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    process = job.get("process")
    mode = job.get("mode")
    is_delete = delete.lower() == "true"

    if not process:
        return {"status": "not_running"}
    try:
        if mode == "livestream":
            if is_delete:
                # Mark for cleanup if they chose to delete
                job_manager.update_job(job_id, {"status": "cancelled", "cleanup_files": True})
                process.terminate()
            else:
                # SIGINT tells ytarchive to mux and save up to current point
                process.send_signal(signal.SIGINT)
                job_manager.update_job(job_id, {"status": "finishing"})
        else:
            if is_delete:
                job_manager.update_job(job_id, {"status": "cancelled", "cleanup_files": True})
            else:
                job_manager.update_job(job_id, {"status": "cancelled"})
            process.terminate()  # SIGTERM — yt-dlp usually cleans up, but we'll double check
    except ProcessLookupError:
        pass
    return {"status": "signal_sent"}


# ---------------------------------------------------------------------------
# FFmpeg cut
# ---------------------------------------------------------------------------

@app.post("/api/ffmpeg/cut")
async def api_ffmpeg_cut(
    start: str = Form(...),
    end: str = Form(...),
    name: str = Form(...),
    reencode_full: str = Form("false"),
    library_path: str = Form(""),
    duration_s: str = Form("0"),
    video: Optional[UploadFile] = None,
):
    cfg = get_config()
    out_path = cfg["output_path"]
    dl_path = cfg["download_path"]
    
    # Ensure cut dir exists
    cut_dir = Path(out_path) / "ffmpeg"
    cut_dir.mkdir(parents=True, exist_ok=True)

    # Concurrency Limit Check (Max 1 active cut job)
    active_cuts = [
        j for j in job_manager.get_all_jobs().values()
        if j.get("type") == "ffmpeg" and j.get("status") == "running"
    ]
    if len(active_cuts) >= 1:
        raise HTTPException(
            status_code=429, 
            detail="Another cut is already in progress. Please wait for it to finish."
        )

    if library_path:
        # library_path is "folder/filename"
        if "/" not in library_path:
             raise HTTPException(status_code=400, detail="Invalid library path")
             
        folder_label, filename = library_path.split("/", 1)
        
        base_map = {
            "outputs": Path(out_path),
            "outputs/ffmpeg": Path(out_path) / "ffmpeg",
            "downloads": Path(dl_path),
        }
        
        base_path = base_map.get(folder_label)
        if not base_path:
             raise HTTPException(status_code=400, detail="Invalid folder in library path")
             
        resolved = (base_path / filename).resolve()
        if not str(resolved).startswith(str(base_path.resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")
        if not resolved.exists():
            raise HTTPException(status_code=404, detail="File not found")
        input_path = str(resolved)
    elif video:
        # Stream to disk to save RAM (64KB chunks)
        safe_upload_name = Path(video.filename).name if video.filename else "upload"
        tmp_job = str(uuid.uuid4())
        input_path = f"/tmp/{tmp_job}_{safe_upload_name}"
        
        total_size = 0
        try:
            async with aiofiles.open(input_path, "wb") as f:
                while True:
                    chunk = await video.read(65536)
                    if not chunk:
                        break
                    total_size += len(chunk)
                    if total_size > ONE_GB:
                        raise HTTPException(status_code=413, detail="File exceeds 1 GB limit")
                    await f.write(chunk)
        except HTTPException:
            if os.path.exists(input_path):
                os.unlink(input_path)
            raise
        except Exception as e:
            if os.path.exists(input_path):
                os.unlink(input_path)
            raise HTTPException(status_code=500, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail="No file provided")

    # Detect if input is audio
    input_suffix = Path(input_path).suffix.lower()
    is_audio_input = input_suffix in [".mp3", ".m4a", ".aac", ".opus", ".ogg", ".flac", ".wav", ".m4b"]

    # Sanitize output name: Replace spaces with underscores, then strip dangerous chars
    safe_output_name = name.replace(" ", "_")
    safe_output_name = re.sub(r'[^a-zA-Z0-9_\-]', '', safe_output_name)
    
    if not safe_output_name:
        safe_output_name = f"clip_{uuid.uuid4().hex[:8]}"
    
    # Extensions from config
    def_video = cfg.get("video_format", "mp4").strip(".")
    def_audio = cfg.get("audio_format", "mp3").strip(".")
    
    output_ext = f".{def_audio}" if is_audio_input else f".{def_video}"
    output_file = f"{cut_dir}/{safe_output_name}{output_ext}"
    job_id = str(uuid.uuid4())

    # Codec Selection
    if is_audio_input:
        video_codec = ["-vn"]  # Strip video for audio outputs
        
        # Decide if we MUST re-encode (extensions differ) or if user WANTs to
        must_reencode = input_suffix != output_ext
        should_reencode = reencode_full == "true" or must_reencode
        
        if should_reencode:
            if def_audio == "mp3":
                audio_codec = ["libmp3lame", "-b:a", "320k"]
            elif def_audio == "m4a":
                audio_codec = ["aac", "-b:a", "192k"]
            elif def_audio == "wav":
                audio_codec = ["pcm_s16le"]
            elif def_audio == "flac":
                audio_codec = ["flac"]
            elif def_audio == "opus":
                audio_codec = ["libopus", "-b:a", "128k"]
            else:
                audio_codec = ["libmp3lame", "-b:a", "320k"] # Default fallback
        else:
            audio_codec = ["copy"]
    else:
        # Video Logic
        if reencode_full == "true":
            # Standard high-compatibility transcode
            video_codec = ["-c:v", "libx264", "-crf", "23", "-preset", "superfast"]
            audio_codec = ["-c:a", "aac", "-b:a", "192k"]
        else:
            # Instant cut
            video_codec = ["-c:v", "copy"]
            if cfg.get("reencode_audio_instant"):
                audio_codec = ["-c:a", "aac", "-b:a", "192k"]
            else:
                audio_codec = ["-c:a", "copy"]

    # With -ss before -i, -to is relative to the seek point (output duration).
    try:
        cut_duration = str(float(end) - float(start))
    except ValueError:
        cut_duration = end

    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-i", input_path,
        "-t", cut_duration,
    ]

    if is_audio_input:
        cmd.extend(video_codec)
        cmd.extend(["-c:a"] + audio_codec)
    else:
        cmd.extend(["-map", "0"])
        cmd.extend(video_codec)
        cmd.extend(audio_codec)
        cmd.extend(["-c:s", "copy"])
        cmd.extend(["-avoid_negative_ts", "make_zero", "-strict", "-2"])

    cmd.extend(["-progress", "pipe:1", "-nostats"])

    # Append advanced arguments
    if cfg.get("ffmpeg_args"):
        cmd.extend(shlex.split(cfg["ffmpeg_args"]))

    # Final output file
    cmd.append(output_file)

    log_command(job_id, cmd)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    job_manager.add_job(job_id, {
        "type": "ffmpeg",
        "duration_s": float(duration_s) if duration_s else 0,
        "output": output_file,
        "tmp_input": input_path if not library_path else None,
    }, process=process)
    return {"job_id": job_id}


@app.get("/api/ffmpeg/progress/{job_id}")
async def api_ffmpeg_progress(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        process = job.get("process")
        duration_s = job.get("duration_s", 0)
        output = job.get("output", "")

        if not process:
            yield f"data: {json.dumps({'error': 'Process not found or already finished'})}\n\n"
            return

        try:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                
                # Output to console so it appears in docker logs
                if line:
                    print(f"[job:{job_id[:8]}] {line}", flush=True)

                # ffmpeg -progress pipe:1 emits key=value lines
                if line.startswith("out_time_us="):
                    try:
                        out_us = int(line.split("=", 1)[1])
                        if duration_s and duration_s > 0:
                            percent = min(100.0, out_us / (duration_s * 1_000_000) * 100)
                        else:
                            percent = 0
                        yield f"data: {json.dumps({'percent': round(percent, 1)})}\n\n"
                    except ValueError:
                        pass
                elif line == "progress=end":
                    break

            rc = await process.wait()
            if rc == 0:
                yield f"data: {json.dumps({'done': True, 'output': output})}\n\n"
            else:
                stderr_bytes = await process.stderr.read()
                stderr_str = stderr_bytes.decode('utf-8', errors='replace').strip()
                # Print the error in red to the console for docker logs
                print(f"\033[91mFFMPEG ERROR:\n{stderr_str}\033[0m", flush=True)
                yield f"data: {json.dumps({'error': stderr_str[-500:]})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            # Clean up uploaded temp file if any
            tmp = job.get("tmp_input")
            if tmp:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            job_manager.update_job(job_id, {"status": "done", "pid": None})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/ffmpeg/cancel/{job_id}")
async def api_ffmpeg_cancel(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    process = job.get("process")
    if not process:
        return {"status": "not_running"}
    
    try:
        process.terminate()
        job_manager.update_job(job_id, {"status": "cancelled"})
        
        # Cleanup unfinished file
        out_path = job.get("output")
        if out_path and os.path.exists(out_path):
            try:
                os.unlink(out_path)
            except:
                pass
                
        # Cleanup temp input if any
        tmp_in = job.get("tmp_input")
        if tmp_in and os.path.exists(tmp_in):
            try:
                os.unlink(tmp_in)
            except:
                pass
                
    except ProcessLookupError:
        pass
    return {"status": "signal_sent"}


# ---------------------------------------------------------------------------
# Serve built frontend (production)
# ---------------------------------------------------------------------------

frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    cfg = get_config()
    # Ensure all configured directories exist on startup
    for key in ["data_path", "download_path", "output_path"]:
        Path(cfg[key]).mkdir(parents=True, exist_ok=True)
    
    # Ensure ffmpeg subfolder exists
    Path(cfg["output_path"], "ffmpeg").mkdir(parents=True, exist_ok=True)
    
    uvicorn.run(app, host="0.0.0.0", port=8047)
