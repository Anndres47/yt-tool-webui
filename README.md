# yt-tool-webui

A self-hosted web interface for downloading YouTube videos and trimming them — all from the browser, no command line required. Runs entirely inside Docker.

---

## Features

- **Unified Downloader:**
  - **Multi-Download System** — download up to **5 concurrent** videos, livestreams, or audio files.
  - **Quality Selector** — choose from Best, 1080p, 720p, etc. for videos.
  - **Audio Mode** — download best audio stream, with optional re-encoding to MP3.
  - **Livestream Support** — track catch-up progress and mux segments on completion.
  - **Configurable Proxy** — built-in SOCKS4/5 and HTTP proxy support with credential redaction in logs.
- **Robust YouTube Access:**
  - **Automated PO Tokens & Visitor ID** — integrated with a `pot-provider` sidecar to bypass YouTube's strictest bot-detection.
  - **Toggleable PO Token** — optionally enable PO tokens for standard downloads to balance speed and reliability.
  - **Robust HTML Title Fetching** — a lightweight, secondary title scraper that bypasses bot detection for near-instant metadata retrieval.
  - **JS Challenge Solving** — automatically solves YouTube JS challenges via Node.js and remote components for full-speed downloads.
  - **Session Isolation** — uses per-job cache directories to prevent session clashing and fix HTTP 403 Forbidden errors on concurrent or long downloads.
- **Advanced FFmpeg Cutter:**
  - **Instant Cut** — use stream copy (`-c:v copy`) for near-instant, lossless results.
  - **Full Re-encode** — optional transcoding for maximum device compatibility.
  - **Smart Slider UX** — Start and End sliders automatically push each other to maintain valid selections; sliders reset perfectly on new file load.
  - **High-Precision Mode** — an advanced setting unlocks secondary sliders for centisecond-accurate cuts.
  - **Library & Upload Support** — cut from finished downloads or directly upload a file.
- **Intelligent Job & System Management:**
  - **Smooth Real-time Progress** — track all jobs via independent cards with high-frequency (10 FPS) smooth progress updates.
  - **Dynamic Timeout Watchdog** — a smart timeout kills legitimately stalled jobs but allows long post-processing tasks to finish.
  - **Automatic Recovery & Cleanup** — failed livestreams are automatically recovered. Stale temp files are cleaned up on startup.
  - **Persistent State** — jobs list and UI state are preserved across browser refreshes and server restarts.
- **Clear User Interface:**
  - **Task-based Tabs** for Downloading, Cutting, and Settings.
  - **Configurable Paths & Arguments** from the Settings UI.
  - **Detailed Command Logging** to `data/logs/commands.log`.

---

## Stack

### Backend
| Package | Role |
|---------|------|
| [FastAPI](https://github.com/tiangolo/fastapi) | REST API framework |
| [Uvicorn](https://github.com/encode/uvicorn) | ASGI server |
| [aiofiles](https://github.com/Tinche/aiofiles) | Async file I/O for HTTP range serving |
| [python-multipart](https://github.com/andrew-d/python-multipart) | Multipart form / file upload parsing |

### Frontend
| Package | Role |
|---------|------|
| [Vue 3](https://github.com/vuejs/core) | Reactive UI framework (Composition API) |
| [Vite](https://github.com/vitejs/vite) | Build tool and dev server |
| [@vitejs/plugin-vue](https://github.com/vitejs/vite-plugin-vue) | Vue SFC support for Vite |
| [Axios](https://github.com/axios/axios) | HTTP client |

### CLI tools (bundled in Docker image)
| Tool | Role |
|------|------|
| [yt-dlp](https://github.com/yt-dlp/yt-dlp) | Video and audio downloads from YouTube |
| [ytarchive](https://github.com/dreammu/ytarchive) | Livestream recording (custom fork with `--visitor-data` support) |
| [ffmpeg](https://github.com/FFmpeg/FFmpeg) | Video/audio cutting and audio re-encoding |
| [pot-provider](https://github.com/brainicism/bgutil-ytdlp-pot-provider) | Sidecar service for automated PO Token generation |

---

## Project structure

```
yt-tool-webui/
├── backend/
│   ├── main.py          # FastAPI app — all API endpoints
│   ├── config.py        # Load/save config.json from the data volume
│   ├── jobs.py          # JobManager for persistent state
│   ├── logger.py        # Append timestamped command log entries
│   └── requirements.txt
├── frontend/
│   ├── index.html       # HTML shell
│   ├── main.js          # Vue app entry point
│   └── components/
│       ├── YtDownloader.vue   # Tab 1 — download
│       ├── FfmpegCutter.vue   # Tab 2 — cut
│       └── Settings.vue       # Tab 3 — settings
├── Dockerfile
├── docker-compose.yml
├── data/                # Internal state (config.json, jobs.json, logs/)
├── downloads/           # Temporary working directory for active downloads
└── outputs/             # Finished downloads and recovered livestreams
    └── ffmpeg/          # Edited clips from the Cutter
```

---

## Deployment

### Requirements
- Docker and Docker Compose installed on the host

### First run

```bash
# Clone / copy the project, then:
docker compose up -d --build
```

Open `http://<host-ip>:8047`.

The `data/`, `downloads/`, and `outputs/` directories are created automatically on your host and mapped into the container. 

- **data/**: Your settings and job history.
- **downloads/**: Where temporary files live during the download process.
- **outputs/**: Where your finished files appear once complete.

### Updating

```bash
docker compose down
docker compose up -d --build
```

Your volumes are untouched.

### Changing the port

Edit `docker-compose.yml`:

```yaml
ports:
  - "8080:8047"   # host:container
```

---

## Configuration

All settings are available in the **Settings** tab of the UI.

| Setting | Default | Description |
|---------|---------|-------------|
| Data path | `/app/data` | Where internal state (config, jobs, logs) is stored. |
| Download path | `/app/downloads` | Temporary working directory for active downloads. |
| Output path | `/app/outputs` | Where finished files are moved upon completion. |
| Cookies.txt path | _(empty)_ | Absolute path to a Netscape-format cookies file inside the container. |
| yt-dlp args | _(empty)_ | Additional CLI arguments for all `yt-dlp` commands. |
| ytarchive args | _(empty)_ | Additional CLI arguments for all `ytarchive` commands. |
| FFmpeg args | _(empty)_ | Additional CLI arguments for FFmpeg cut/re-encode. |
| Video format | `mp4` | Default output extension for video cuts (MP4, MKV, MOV, WebM). |
| Audio format | `mp3` | Default output extension for audio cuts (MP3, M4A, WAV, FLAC, Opus). |
| Re-encode Audio Instant | `false` | If true, forces AAC audio re-encoding during Instant Cuts for better compatibility. |
| High Precision Cutter | `false` | If true, enables secondary sliders in the Cutter for centisecond precision. |
| Enable PO Token | `false` | If true, applies PO tokens to standard `yt-dlp` downloads (always used for livestreams). |
| Proxy Support | `false` | Enable/Disable global proxy. Supports SOCKS4, SOCKS5, and HTTP with authentication. |

### Using cookies

Place your `cookies.txt` in the `./data/` folder on your host, then set the path to `/app/data/cookies.txt` in the Settings tab.

---

## How it works

### Download flow

```
Browser  →  POST /api/download  →  FastAPI spawns subprocess  →  yt-dlp or ytarchive
         ←  { job_id }
         →  GET /api/download/progress/{job_id}  (EventSource / SSE)
         ←  data: { percent, speed, eta } or { segments, live }
         ←  data: { done: true }
```

1. The browser POSTs the URL, mode, and quality.
2. The backend creates a **job-specific temp directory** under `downloads/` to isolate files.
3. The backend builds the CLI command (adding `--newline` for real-time log parsing and `--merge` for ytarchive reliability).
4. Subprocess stdout is piped to both the browser (SSE) and the console (`docker logs`) with ANSI error highlighting.
5. Upon completion, `yt-dlp` (via `--paths home`) or the backend move the finished file to `outputs/` and purge the temp directory.

### Job Persistence & Recovery

The backend tracks all jobs in a `JobManager` that persists to `data/jobs.json`. This enables:
- **Resilient State:** If the server restarts, orphaned downloads are identified on startup and marked as "interrupted."
- **Automatic Livestream Recovery:** If a livestream download fails or is terminated unexpectedly, the system will automatically attempt to recover it by locating the largest valid video file in the temporary directory and moving it to `outputs/`. If no single large file is found, it will attempt to mux all downloaded `.ts` segments into a complete video.
- **7-Day Temp File Retention:** Failed livestream temporary files are preserved for 7 days to allow for manual recovery. A cleanup task runs on startup to automatically delete any stale temporary directories older than one week.
- **Smart Cancellation:** 
  - **Livestreams:** Aborting a livestream prompts the user to either **Keep & Mux** (graceful stop with `SIGINT` + `--merge`) or **Delete All** (forced stop with cleanup of the job temp folder).
  - **Regular Downloads:** Users can choose to stop and keep partial files or perform a full cleanup.
- **History:** Completed, cancelled, and interrupted jobs remain in the list until manually cleared from the Settings tab.

### FFmpeg cut flow

```
Browser  →  POST /api/ffmpeg/cut  (library_path or uploaded file)
         ←  { job_id }
         →  GET /api/ffmpeg/progress/{job_id}  (EventSource / SSE)
         ←  data: { percent: 67.1 }
         ←  data: { done: true, output: "/app/outputs/ffmpeg/clip.mp4" }
```

The tool defaults to **Instant Cut** (Stream Copy) for zero quality loss. Enabling **Full Re-encode** uses:
```
ffmpeg -y -ss <start> -i <input> -t <duration> -c:v libx264 -crf 23 -preset superfast -c:a aac -b:a 192k ...
```

Key flags:
- `-ss` and `-to` — The start and end timestamps. The backend passes the user's selection directly to ffmpeg, which handles a variety of formats including seconds (`65.5`) and timestamps (`01:05.50`).
- `-c:v copy` — used by default; video stream is never re-encoded; cut is instantaneous.
- `-progress pipe:1` — ffmpeg writes machine-readable `key=value` progress lines to stdout.
- All edited clips are saved to the `outputs/ffmpeg/` subdirectory.

### Library streaming

Files are scanned from `outputs/` and `outputs/ffmpeg/` and served via `GET /api/library/stream/{folder}/{filename}` with full HTTP `Range` header support (206 Partial Content). The browser's native `<video>` element uses range requests to seek instantly without downloading the whole file.

### Settings persistence

`config.py` stores `config.json` inside the data directory (`/app/data/config.json`), which maps to `./data/config.json` on the host. Because the data directory is a Docker volume, the config survives container restarts and rebuilds automatically.

### Command logging

Every CLI command is timestamped and logged to `data/logs/commands.log` before execution. Progress is also printed to standard output for real-time monitoring via `docker logs`.

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | Return current settings |
| `POST` | `/api/settings` | Save settings (JSON body) |
| `GET` | `/api/jobs` | List all tracked jobs (active/done/interrupted/cancelled) |
| `POST` | `/api/jobs/clear` | Clear completed/cancelled job history |
| `POST` | `/api/jobs/finalize/{id}` | Recover/mux interrupted livestream segments |
| `GET` | `/api/library` | List files in `outputs` and `outputs/ffmpeg` |
| `GET` | `/api/library/stream/{f}/{n}` | Stream file with Range support |
| `POST` | `/api/download` | Start download, return `{job_id}` |
| `GET` | `/api/download/progress/{id}` | SSE progress stream |
| `POST` | `/api/download/cancel/{id}` | Cancel / abort download |
| `POST` | `/api/ffmpeg/cut` | Start ffmpeg cut, return `{job_id}` |
| `GET` | `/api/ffmpeg/progress/{id}` | SSE ffmpeg progress stream |
| `POST` | `/api/ffmpeg/cancel/{id}` | Cancel active FFmpeg process |


---

## Local development (without Docker)

**Backend**

```bash
cd backend
pip install -r requirements.txt
# Also needs yt-dlp, ytarchive, and ffmpeg on your PATH
python main.py
# Runs on http://localhost:8047
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
# /api/* proxied to http://localhost:8047
```

---

## Limitations

- **No authentication** — anyone on the network can access the UI. Run behind a VPN or reverse proxy with auth (e.g. Caddy + basic auth, or Authelia) if exposed beyond localhost.
- **Keyframe-accurate Instant Cuts** — By default, the cutter uses a fast stream-copy mode. This is nearly instantaneous but means the cut starts at the nearest video keyframe, not the exact timestamp. The new high-precision mode helps specify the timestamp more accurately, but for true frame-perfect cuts, you must enable the "Full Re-encode" option.
- **Livestream progress is approximate** — ytarchive does not report a reliable percentage for ongoing streams; the UI shows segment count during catch-up and capture.

---

## License

This project is a personal tool that wraps open-source software. Each dependency carries its own license:

- yt-dlp — [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)
- ytarchive — [MIT](https://github.com/Kethsar/ytarchive/blob/master/LICENSE)
- FFmpeg — [LGPL 2.1 / GPL 2.0](https://www.ffmpeg.org/legal.html)
- FastAPI — [MIT](https://github.com/tiangolo/fastapi/blob/master/LICENSE)
- Vue — [MIT](https://github.com/vuejs/core/blob/main/LICENSE)
