# yt-webui-v3

A self-hosted web interface for downloading YouTube videos and trimming them — all from the browser, no command line required. Runs entirely inside Docker.

---

## Features

- **Download** YouTube videos, livestreams, and audio — powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [ytarchive](https://github.com/Kethsar/ytarchive)
- **Quality selector** for video: Best, 1080p, 720p, 480p, 360p
- **Audio mode** — download best audio stream, optionally re-encode to MP3 320kbps via ffmpeg
- **Livestream support** — tracks catch-up progress, switches to a live indicator when reaching the live edge; Abort & Save stops recording and muxes the file up to that point
- **Real-time progress bars** via Server-Sent Events (SSE) — no polling
- **FFmpeg Cutter** — trim any video or audio file without re-encoding
  - **Library picker** — select a file already in the downloads folder, streamed directly to the browser via HTTP range requests; no upload needed
  - **Upload fallback** — upload an external file (up to 1 GB) for cutting
  - **Native video preview** — seek anywhere in the file inside the browser before setting cut points
  - **Set from playhead** — play to the exact frame you want, click to capture start/end time
  - **Optional audio re-encode** — cut output re-encodes audio to MP3 320kbps via ffmpeg; video is always stream-copied (no quality loss, no re-encode)
- **Settings panel** — configure download path, cookies.txt path, and PO token from the UI; persisted on the server
- **Command log** — every CLI command executed is timestamped and logged to `data/logs/commands.log`

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
| [ytarchive](https://github.com/Kethsar/ytarchive) | Livestream recording (downloads as the stream happens) |
| [ffmpeg](https://github.com/FFmpeg/FFmpeg) | Video/audio cutting and audio re-encoding |

---

## Project structure

```
yt-webui-v3/
├── backend/
│   ├── main.py          # FastAPI app — all API endpoints
│   ├── config.py        # Load/save config.json from the data volume
│   ├── logger.py        # Append timestamped command log entries
│   └── requirements.txt
├── frontend/
│   ├── index.html       # HTML shell, loads Google Fonts
│   ├── main.js          # Vue app entry point
│   ├── App.vue          # Root layout, sidebar nav, global CSS
│   ├── vite.config.js   # Vue plugin + /api proxy for local dev
│   └── components/
│       ├── YtDownloader.vue   # Tab 1 — download
│       ├── FfmpegCutter.vue   # Tab 2 — cut
│       └── Settings.vue       # Tab 3 — config
├── Dockerfile
├── docker-compose.yml
├── .dockerignore
└── data/                # Created on first run (gitignore this)
    ├── *.mp4 / *.mkv …  # Downloaded files
    ├── config.json       # Saved settings
    └── logs/
        └── commands.log
```

---

## Deployment

### Requirements
- Docker and Docker Compose installed on the host

### First run

```bash
# Clone / copy the project, then:
mkdir -p data
docker compose up --build
```

Open `http://<host-ip>:7860`.

The `./data` directory is created automatically and mapped into the container. Everything that needs to persist — downloaded files, settings, logs — lives there.

### Updating

```bash
docker compose down
docker compose up --build
```

Your `./data` directory is untouched.

### Changing the port

Edit `docker-compose.yml`:

```yaml
ports:
  - "8080:7860"   # host:container
```

---

## Configuration

All settings are available in the **Config** tab of the UI and saved to `data/config.json`.

| Setting | Default | Description |
|---------|---------|-------------|
| Download path | `/app/downloads` | Where files are saved inside the container. The default maps to `./data/` on your host. Only change this if you mount a different volume. |
| Cookies.txt path | _(empty)_ | Absolute path to a Netscape-format cookies file inside the container. Required for age-gated or members-only content. |
| PO Token | _(empty)_ | YouTube Proof-of-Origin token. Required for some bot-protected streams. [How to obtain one.](https://github.com/yt-dlp/yt-dlp/wiki/Extractors#po-token-guide) |

### Using cookies

Export your YouTube cookies from the browser (e.g. with the [cookies.txt extension](https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp)), place the file in `./data/`, then set the path to `/app/downloads/cookies.txt` in the Config tab.

---

## How it works

### Download flow

```
Browser  →  POST /api/download  →  FastAPI spawns subprocess  →  yt-dlp or ytarchive
         ←  { job_id }
         →  GET /api/download/progress/{job_id}  (EventSource / SSE)
         ←  data: { percent, speed, eta }  (streaming, line by line from stdout)
         ←  data: { done: true }
```

1. The browser POSTs the URL, mode, and quality as `multipart/form-data`.
2. The backend builds the CLI command, logs it, spawns it with `asyncio.create_subprocess_exec`, stores the process in an in-memory job dict, and returns a `job_id` immediately.
3. The browser opens an `EventSource` connection to the progress endpoint.
4. The backend reads the subprocess stdout line by line. For yt-dlp it parses `[download] 42.3% of 1.23GiB at 3.21MiB/s ETA 00:12`. For ytarchive it parses segment counts and detects the live edge.
5. Parsed events are emitted as SSE frames: `data: {"percent": 42.3, "speed": "3.21MiB/s", "eta": "00:12"}`.
6. Cancel (video/audio) sends `SIGTERM` to yt-dlp, which cleans up its `.part` files. Abort & Save (livestream) sends `SIGINT` to ytarchive, which muxes and saves everything recorded so far.

### FFmpeg cut flow

```
Browser  →  POST /api/ffmpeg/cut  (library_path or uploaded file)
         ←  { job_id }
         →  GET /api/ffmpeg/progress/{job_id}  (EventSource / SSE)
         ←  data: { percent: 67.1 }
         ←  data: { done: true, output: "/app/downloads/clip.mp4" }
```

The ffmpeg command used:

```
ffmpeg -y -ss <start> -i <input> -t <duration> -c:v copy -c:a [copy|libmp3lame -b:a 320k] -progress pipe:1 -nostats <output>
```

Key flags:
- `-ss` **before** `-i` — input-level seek, fast even for large files
- `-t` — duration of the clip (computed as `end - start` on the backend)
- `-c:v copy` — video stream is never re-encoded; cut is keyframe-accurate and instantaneous
- `-c:a copy` or `libmp3lame -b:a 320k` — audio is either copied or re-encoded to MP3 320kbps
- `-progress pipe:1` — ffmpeg writes machine-readable `key=value` progress lines to stdout; the backend parses `out_time_us` and computes `percent = out_time_us / (duration_s × 1,000,000) × 100`
- The original source file is **never modified**

### Library streaming

Files already in the downloads folder are served via `GET /api/library/stream/{filename}` with full HTTP `Range` header support (206 Partial Content). The browser's native `<video>` element uses range requests to seek instantly without downloading the whole file. No upload is needed — the file stays on the server.

### Settings persistence

`config.py` stores `config.json` inside the downloads directory (`/app/downloads/config.json`), which maps to `./data/config.json` on the host. Because the downloads directory is already a Docker volume, the config survives container restarts and rebuilds automatically — no separate volume mount needed.

### Command logging

Every CLI command is appended to `data/logs/commands.log` before execution:

```
2026-04-11T14:32:01Z  [job:a3f91c2e]  yt-dlp https://youtube.com/... -f bestvideo+bestaudio/best -o /app/downloads/%(title)s.%(ext)s
```

---

## API reference

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/settings` | Return current config |
| `POST` | `/api/settings` | Save config (JSON body) |
| `GET` | `/api/library` | List files in download folder |
| `GET` | `/api/library/stream/{filename}` | Stream file with Range support |
| `POST` | `/api/download` | Start download, return `{job_id}` |
| `GET` | `/api/download/progress/{job_id}` | SSE progress stream |
| `POST` | `/api/download/cancel/{job_id}` | Cancel / abort download |
| `POST` | `/api/ffmpeg/cut` | Start ffmpeg cut, return `{job_id}` |
| `GET` | `/api/ffmpeg/progress/{job_id}` | SSE ffmpeg progress stream |

---

## Local development (without Docker)

**Backend**

```bash
cd backend
pip install -r requirements.txt
# Also needs yt-dlp, ytarchive, and ffmpeg on your PATH
python main.py
# Runs on http://localhost:7860
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
# Runs on http://localhost:5173
# /api/* proxied to http://localhost:7860
```

---

## Limitations

- **No authentication** — anyone on the network can access the UI. Run behind a VPN or reverse proxy with auth (e.g. Caddy + basic auth, or Authelia) if exposed beyond localhost.
- **No download queue** — multiple downloads can run in parallel, each with its own job ID, but there is no queue or concurrency limit.
- **Keyframe-accurate cuts only** — because `-c:v copy` is used, the cut start point snaps to the nearest keyframe. For most content (especially livestream recordings) this is a fraction of a second. For frame-exact cuts a full re-encode would be needed.
- **Livestream progress is approximate** — ytarchive does not report a reliable percentage for ongoing streams; the UI shows segment count during catch-up and switches to an indeterminate bar at the live edge.
- **In-memory job store** — active jobs are held in a Python dict. Restarting the container while a download is running orphans the subprocess.

---

## License

This project is a personal tool that wraps open-source software. Each dependency carries its own license:

- yt-dlp — [Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE)
- ytarchive — [MIT](https://github.com/Kethsar/ytarchive/blob/master/LICENSE)
- FFmpeg — [LGPL 2.1 / GPL 2.0](https://www.ffmpeg.org/legal.html)
- FastAPI — [MIT](https://github.com/tiangolo/fastapi/blob/master/LICENSE)
- Vue — [MIT](https://github.com/vuejs/core/blob/main/LICENSE)
