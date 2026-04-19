import json
import os
import random
import time
import urllib.request
import asyncio
from pathlib import Path
import yt_dlp

class ProxyManager:
    def __init__(self, data_path: str):
        self.data_path = Path(data_path)
        self.proxies_file = self.data_path / "proxies.json"
        self.pool = []
        self.last_full_refresh = 0
        self.load()

    def load(self):
        if self.proxies_file.exists():
            try:
                data = json.loads(self.proxies_file.read_text())
                self.last_full_refresh = data.get("last_full_refresh", 0)
                self.pool = data.get("pool", [])
                
                # Check for 48h expiration
                if time.time() - self.last_full_refresh > 48 * 3600:
                    print("[ProxyManager] Pool expired (>48h). Clearing.", flush=True)
                    self.pool = []
            except:
                self.pool = []

    def save(self):
        self.data_path.mkdir(parents=True, exist_ok=True)
        data = {
            "last_full_refresh": self.last_full_refresh,
            "pool": self.pool
        }
        self.proxies_file.write_text(json.dumps(data, indent=2))

    def get_valid_proxies(self) -> list[str]:
        """Returns list of proxy URLs, fastest first."""
        # Sort by speed_ms
        sorted_pool = sorted(self.pool, key=lambda x: x.get("speed_ms", 99999))
        return [p["url"] for p in sorted_pool]

    def flag_proxy(self, url: str):
        """Remove a failed/flagged proxy from the pool."""
        self.pool = [p for p in self.pool if p["url"] != url]
        self.save()
        print(f"[ProxyManager] Flagged and removed proxy: {url}", flush=True)

    def test_proxy(self, proxy_url: str) -> dict:
        """Tests a proxy for bot-detection and speed using yt-dlp API."""
        url = "https://www.youtube.com/watch?v=jNQXAC9IVRw"
        ydl_opts = {
            'proxy': proxy_url,
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,
            'socket_timeout': 10,
        }
        
        start = time.time()
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                # This only fetches metadata, doesn't download video
                info = ydl.extract_info(url, download=False)
                if info and info.get('title'):
                    speed_ms = int((time.time() - start) * 1000)
                    return {"url": proxy_url, "speed_ms": speed_ms, "added_at": int(time.time())}
        except Exception:
            pass
        return None

    async def scavenge(self, stop_event: asyncio.Event):
        """Background worker to find healthy proxies. Can be interrupted."""
        from config import get_config
        cfg = get_config()
        target_count = max(5, int(cfg.get("proxy_pool_size", 15)))

        print(f"[ProxyManager] Starting background scavenger (Target: {target_count})...", flush=True)
        
        # Download fresh list
        try:
            list_url = "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/all/data.txt"
            with urllib.request.urlopen(list_url, timeout=15) as resp:
                raw_list = resp.read().decode('utf-8').splitlines()
        except Exception as e:
            print(f"[ProxyManager] Failed to fetch proxy list: {e}", flush=True)
            return

        random.shuffle(raw_list)
        new_healthy = []
        
        # Keep existing healthy ones if they haven't expired
        self.pool = [p for p in self.pool if time.time() - p["added_at"] < 48 * 3600]

        for proxy_url in raw_list:
            if stop_event.is_set():
                print("[ProxyManager] Scavenger interrupted by user activity.", flush=True)
                break
            
            if len(self.pool) + len(new_healthy) >= target_count:
                break

            # Skip if already in pool
            if any(p["url"] == proxy_url for p in self.pool):
                continue

            # Run test in thread to not block event loop
            res = await asyncio.to_thread(self.test_proxy, proxy_url)
            if res:
                print(f"[ProxyManager] Found healthy proxy: {proxy_url} ({res['speed_ms']}ms)", flush=True)
                new_healthy.append(res)
                # Small sleep to be polite to YouTube
                await asyncio.sleep(1)

        if new_healthy:
            self.pool.extend(new_healthy)
            if len(self.pool) >= target_count:
                self.last_full_refresh = int(time.time())
            self.save()
            print(f"[ProxyManager] Scavenge complete. Pool size: {len(self.pool)}", flush=True)
