FROM node:18 AS frontend
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend .
RUN npm run build

# Build latest ytarchive from dev branch to support modern PO Tokens
FROM golang:alpine AS ytarchive-builder
RUN apk add --no-cache git
RUN go install github.com/Kethsar/ytarchive@dev

FROM python:3.11-slim AS backend
WORKDIR /app

# Copy static FFmpeg binaries
COPY --from=mwader/static-ffmpeg:7.1 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:7.1 /ffprobe /usr/local/bin/

# Copy compiled ytarchive from dev branch
COPY --from=ytarchive-builder /go/bin/ytarchive /usr/local/bin/ytarchive

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

COPY --from=frontend /app/dist ./frontend
COPY backend ./backend

WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8047
CMD ["python", "main.py"]
