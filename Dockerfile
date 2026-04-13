FROM node:18 AS frontend
WORKDIR /app
COPY frontend/package.json ./
RUN npm install
COPY frontend .
RUN npm run build

FROM python:3.11-slim AS backend
WORKDIR /app

# Copy static FFmpeg binaries (tiny, zero dependencies)
COPY --from=mwader/static-ffmpeg:7.1 /ffmpeg /usr/local/bin/
COPY --from=mwader/static-ffmpeg:7.1 /ffprobe /usr/local/bin/

# Install only essential tools for ytarchive
RUN apt-get update && apt-get install -y \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install yt-dlp
RUN pip install --no-cache-dir yt-dlp

# Install ytarchive
RUN curl -L https://github.com/Kethsar/ytarchive/releases/latest/download/ytarchive_linux_amd64.zip \
       -o /tmp/ytarchive.zip \
    && unzip /tmp/ytarchive.zip -d /usr/local/bin \
    && chmod +x /usr/local/bin/ytarchive \
    && rm /tmp/ytarchive.zip

COPY --from=frontend /app/dist ./frontend
COPY backend ./backend

WORKDIR /app/backend
RUN pip install --no-cache-dir -r requirements.txt

EXPOSE 8047
CMD ["python", "main.py"]
