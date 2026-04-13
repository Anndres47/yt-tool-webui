# yt-tool-webui

A self-hosted web interface for downloading YouTube videos and trimming them — all from the browser, no command line required. Runs entirely inside Docker.

---

## Features

- **Multi-Download System** — download up to **5 concurrent** videos, livestreams, or audio files simultaneously.
- **Task Cards** — each download is managed via an independent card showing real-time progress, speed, and ETA.
- **Auto-Hide** — successful downloads automatically disappear from the list after 3 seconds to keep your UI clean.
- **Concurrency Protection** — the UI proactively blocks new downloads and shows a disclaimer when the 5-job limit is reached.
- **Quality selector** for video: Best, 1080p, 720p, 480p, 360p
- **Audio mode** — download best audio stream, optionally re-encode to MP3 320kbps via ffmpeg
- **Livestream support** — tracks catch-up progress, shows segment count, and pulses when live; Abort & Save automatically muxes segments using the `--merge` flag.
- **Real-time progress bars** — SSE progress for downloads and real-time segment tracking for streams.
- **FFmpeg Cutter** — trim any video or audio file.
  - **Instant Cut** — use stream copy (`-c:v copy`) for near-instant results with zero quality loss.
  - **Full Re-encode (Slow)** — optional transcoding to H.264/AAC for maximum compatibility across all devices.
  - **Configurable Defaults** — set your preferred video (MP4, MKV, etc.) and audio (MP3, M4A, FLAC, etc.) formats in the Settings tab.
  - **Smart Codec Selection** — the cutter automatically selects the best encoder if the source format differs from your configured default.
  - **Optional Audio Re-encode** — a toggle in Advanced Settings allows forcing AAC audio re-encoding during Instant Cuts to ensure maximum player compatibility (fixes Windows Media Player silence) without slowing down the video slicing.
  - **Library picker** — select files from `outputs/` or `outputs/ffmpeg/`, streamed via HTTP range requests.
  - **Native video preview** — seek and set cut points from the playhead.
- **Surgical Cleanup** — each download runs in a unique temp directory; cancelling a video download wipes only that specific job's leftovers.
- **Filename Sanitization** — output names are automatically cleaned; spaces are replaced with underscores (`_`) for better filesystem compatibility.
- **Settings panel** — configure Data, Download (temp), and Output paths directly from the UI.
- **Advanced Settings** — pass custom CLI arguments to `yt-dlp`, `ytarchive`, and `ffmpeg` for specialized workflows.
- **Automated PO Tokens** — an integrated `pot-provider` sidecar automatically generates Proof-of-Origin tokens. The tool intelligently binds these tokens with matching **Visitor IDs** (extracted via exhaustive key detection and URL decoding) and passes them to both `yt-dlp` and our `ytarchive` fork to bypass YouTube's strictest security challenges.
- **Universal Provider Discovery** — the backend automatically detects and connects to various PO Token provider versions by trying multiple endpoints (`/get_pot`, `/token`) and request methods.
- **Forward Progress Watchdog** — the backend monitors all downloads; if a process stalls for 60 seconds (potentially due to a 403 bot block), it is automatically killed and cleaned up.
- **Cancel Cut** — instantly stop slow re-encodes with automatic cleanup of unfinished files.
- **Persistent UI State** — navigate between tabs without losing progress or input data thanks to Vue's `KeepAlive`.
- **Command log** — every CLI command executed is timestamped and logged to `data/logs/commands.log`. Progress is prefixed with the job ID in `docker logs` for easy debugging.

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
- **Smart Cancellation:** 
  - **Livestreams:** Aborting a livestream prompts the user to either **Keep & Mux** (graceful stop with `SIGINT` + `--merge`) or **Delete All** (forced stop with cleanup of the job temp folder).
  - **Regular Downloads:** Users can choose to stop and keep partial files or perform a full cleanup.
- **Livestream Finalization:** Interrupted livestreams can be manually muxed from remaining `.ts` segments via a dedicated recovery endpoint.
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
- `-ss` **before** `-i` — input-level seek, fast even for large files.
- `-t` — duration of the clip (computed as `end - start` on the backend).
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
- **Keyframe-accurate cuts only** — when using Instant Cut, the start point snaps to the nearest keyframe. Use Full Re-encode for exact frame accuracy.
- **Livestream progress is approximate** — ytarchive does not report a reliable percentage for ongoing streams; the UI shows segment count during catch-up and capture.
- **Persistent job store** — active and past jobs are saved to `data/jobs.json`. While this survives container restarts, active subprocesses are still orphaned if the container is killed.

---

## License

This project is a personal tool that wraps open-source software. Each dependency carries its own license:

- yt-dlp — [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)
- ytarchive — [MIT](https://github.com/Kethsar/ytarchive/blob/master/LICENSE)
- FFmpeg — [LGPL 2.1 / GPL 2.0](https://www.ffmpeg.org/legal.html)
- FastAPI — [MIT](https://github.com/tiangolo/fastapi/blob/master/LICENSE)
- Vue — [MIT](https://github.com/vuejs/core/blob/main/LICENSE)
