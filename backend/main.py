import asyncio
import json
import os
import re
import signal
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

app = FastAPI()
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

    if mode == "livestream":
        # -td is temporary dir, -o is final output
        cmd = ["ytarchive", "-td", dl_path, url, "best", "-o", f"{out_path}/{{id}}"]
        if cookies:
            cmd += ["--cookies", cookies]
        if potoken:
            cmd += ["--potoken", potoken]
    elif mode == "audio":
        # --paths temp: is working dir, --paths home: is final dir
        cmd = ["yt-dlp", url, "-f", "bestaudio",
               "--paths", f"temp:{dl_path}", "--paths", f"home:{out_path}",
               "-o", "%(title)s.%(ext)s"]
        if reencode_audio == "true":
            cmd += ["-x", "--audio-format", "mp3",
                    "--postprocessor-args", "ffmpeg:-b:a 320k"]
        if cookies:
            cmd += ["--cookies", cookies]
        if potoken:
            cmd += ["--extractor-args", f"youtube:player_client=web;po_token=web+{potoken}"]
    else:  # video
        fmt = QUALITY_MAP.get(quality, QUALITY_MAP["best"])
        cmd = ["yt-dlp", url, "-f", fmt,
               "--paths", f"temp:{dl_path}", "--paths", f"home:{out_path}",
               "-o", "%(title)s.%(ext)s"]
        if cookies:
            cmd += ["--cookies", cookies]
        if potoken:
            cmd += ["--extractor-args", f"youtube:player_client=web;po_token=web+{potoken}"]

    log_command(job_id, cmd)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    job_manager.add_job(job_id, {"mode": mode, "type": "download"}, process=process)
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
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                
                # Output to console so it appears in docker logs
                print(line, flush=True)

                event = None

                if mode == "livestream":
                    # ytarchive progress: "Video Segments: 123 (4.5MB)  /  128"
                    seg_match = re.search(r"Video Segments:\s*(\d+)", line)
                    if seg_match:
                        segments = int(seg_match.group(1))
                        # Check if live: ytarchive prints "at the live edge" or similar
                        is_live = "live" in line.lower() or "up to date" in line.lower()
                        if is_live:
                            event = json.dumps({"live": True, "segments": segments})
                        else:
                            event = json.dumps({"segments": segments})
                else:
                    # yt-dlp: [download]  42.3% of 1.23GiB at  3.21MiB/s ETA 00:12
                    dl_match = re.search(
                        r"\[download\]\s+([\d.]+)%\s+of\s+[\d.]+\S+\s+at\s+([\d.]+\S+)\s+ETA\s+(\S+)",
                        line,
                    )
                    if dl_match:
                        event = json.dumps({
                            "percent": float(dl_match.group(1)),
                            "speed": dl_match.group(2),
                            "eta": dl_match.group(3),
                        })

                if event:
                    yield f"data: {event}\n\n"

            rc = await process.wait()
            if rc == 0 or rc == -2:  # -2 = SIGINT (ytarchive abort-and-save)
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
            if current_job and current_job.get("cleanup_ts") and mode == "livestream":
                # Delete all .ts segments in dl_path (best effort)
                dl_path = get_config()["download_path"]
                for ts in Path(dl_path).glob("*.ts"):
                    try:
                        os.unlink(ts)
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
                job_manager.update_job(job_id, {"status": "cancelled", "cleanup_ts": True})
                process.terminate()
            else:
                # SIGINT tells ytarchive to mux and save up to current point
                process.send_signal(signal.SIGINT)
                job_manager.update_job(job_id, {"status": "finishing"})
        else:
            process.terminate()  # SIGTERM — yt-dlp cleans up .part files
            job_manager.update_job(job_id, {"status": "cancelled"})
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
    reencode_audio: str = Form("false"),
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

    # Sanitize output name to prevent path traversal
    safe_output_name = re.sub(r'[^a-zA-Z0-9_\-]', '', name)
    if not safe_output_name:
        safe_output_name = f"clip_{uuid.uuid4().hex[:8]}"
    output_file = f"{cut_dir}/{safe_output_name}.mp4"
    job_id = str(uuid.uuid4())

    audio_codec = ["libmp3lame", "-b:a", "320k"] if reencode_audio == "true" else ["copy"]

    # With -ss before -i, -to is relative to the seek point (output duration).
    # Compute duration = end - start on the backend.
    try:
        cut_duration = str(float(end) - float(start))
    except ValueError:
        cut_duration = end

    cmd = [
        "ffmpeg", "-y",
        "-ss", start,
        "-i", input_path,
        "-t", cut_duration,
        "-c:v", "copy",
        "-c:a", *audio_codec,
        "-progress", "pipe:1",
        "-nostats",
        output_file,
    ]

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
                    print(line, flush=True)

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
