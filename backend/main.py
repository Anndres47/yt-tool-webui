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

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory job store: job_id -> {process, mode, type, duration_s}
jobs: dict = {}

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
    # Re-create downloads dir if path changed
    dl = data.get("download_path", "/app/downloads")
    Path(dl).mkdir(parents=True, exist_ok=True)
    return {"status": "saved"}


# ---------------------------------------------------------------------------
# Library
# ---------------------------------------------------------------------------

@app.get("/api/library")
def api_library():
    dl = Path(get_config()["download_path"])
    if not dl.exists():
        return []
    files = []
    for p in sorted(dl.iterdir()):
        if p.is_file():
            stat = p.stat()
            files.append({
                "name": p.name,
                "size": stat.st_size,
                "modified": stat.st_mtime,
            })
    return files


@app.get("/api/library/stream/{filename}")
async def api_library_stream(filename: str, request: Request):
    dl = Path(get_config()["download_path"])
    file_path = (dl / filename).resolve()

    # Security: ensure resolved path is inside download dir
    if not str(file_path).startswith(str(dl.resolve())):
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
    cookies = cfg.get("cookies_path", "")
    potoken = cfg.get("potoken", "")
    Path(dl_path).mkdir(parents=True, exist_ok=True)

    job_id = str(uuid.uuid4())

    if mode == "livestream":
        cmd = ["ytarchive", url, "best", "-o", f"{dl_path}/{{id}}"]
        if cookies:
            cmd += ["--cookies", cookies]
        if potoken:
            cmd += ["--potoken", potoken]
    elif mode == "audio":
        cmd = ["yt-dlp", url, "-f", "bestaudio",
               "-o", f"{dl_path}/%(title)s.%(ext)s"]
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
               "-o", f"{dl_path}/%(title)s.%(ext)s"]
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
    jobs[job_id] = {"process": process, "mode": mode, "type": "download"}
    return {"job_id": job_id}


@app.get("/api/download/progress/{job_id}")
async def api_download_progress(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        process = job["process"]
        mode = job["mode"]

        try:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()
                if not line:
                    continue

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
                yield f"data: {json.dumps({'error': f'Process exited with code {rc}'})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
        finally:
            jobs.pop(job_id, None)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.post("/api/download/cancel/{job_id}")
async def api_download_cancel(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    process = job["process"]
    mode = job["mode"]
    try:
        if mode == "livestream":
            # SIGINT tells ytarchive to mux and save up to current point
            process.send_signal(signal.SIGINT)
        else:
            process.terminate()  # SIGTERM — yt-dlp cleans up .part files
    except ProcessLookupError:
        pass
    return {"status": "cancelled"}


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
    dl_path = cfg["download_path"]
    Path(dl_path).mkdir(parents=True, exist_ok=True)

    if library_path:
        resolved = (Path(dl_path) / library_path).resolve()
        if not str(resolved).startswith(str(Path(dl_path).resolve())):
            raise HTTPException(status_code=403, detail="Forbidden")
        if not resolved.exists():
            raise HTTPException(status_code=404, detail="File not found")
        input_path = str(resolved)
    elif video:
        # Enforce 1 GB limit
        contents = await video.read()
        if len(contents) > ONE_GB:
            raise HTTPException(status_code=413, detail="File exceeds 1 GB limit")
        # Sanitize filename — strip any path components, use uuid to avoid collisions
        safe_name = Path(video.filename).name if video.filename else "upload"
        tmp_job = str(uuid.uuid4())
        input_path = f"/tmp/{tmp_job}_{safe_name}"
        await asyncio.to_thread(_write_file, input_path, contents)
    else:
        raise HTTPException(status_code=400, detail="No file provided")

    output_path = f"{dl_path}/{name}.mp4"
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
        output_path,
    ]

    log_command(job_id, cmd)

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    jobs[job_id] = {
        "process": process,
        "type": "ffmpeg",
        "duration_s": float(duration_s) if duration_s else 0,
        "output": output_path,
        "tmp_input": input_path if not library_path else None,
    }
    return {"job_id": job_id}


@app.get("/api/ffmpeg/progress/{job_id}")
async def api_ffmpeg_progress(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_stream():
        process = job["process"]
        duration_s = job.get("duration_s", 0)
        output = job.get("output", "")

        try:
            while True:
                line_bytes = await process.stdout.readline()
                if not line_bytes:
                    break
                line = line_bytes.decode("utf-8", errors="replace").strip()

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
                stderr = await process.stderr.read()
                yield f"data: {json.dumps({'error': stderr.decode('utf-8', errors='replace')[-500:]})}\n\n"
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
            jobs.pop(job_id, None)

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
    Path(cfg["download_path"]).mkdir(parents=True, exist_ok=True)
    uvicorn.run(app, host="0.0.0.0", port=7860)
