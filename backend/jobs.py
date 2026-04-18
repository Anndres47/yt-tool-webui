import json
import os
import asyncio
import aiofiles
from pathlib import Path
from typing import Dict

class JobManager:
    def __init__(self, data_path: str):
        self.path = Path(data_path) if data_path else Path("/app/data")
        self.jobs_file = self.path / "jobs.json"
        self.jobs: Dict[str, dict] = {}  # All metadata
        self.processes: Dict[str, any] = {}  # Active subprocesses
        
        # Ensure path exists before loading
        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.load()

    def load(self):
        """Load job metadata from disk synchronously on startup."""
        if self.jobs_file.exists():
            try:
                self.jobs = json.loads(self.jobs_file.read_text())
            except Exception:
                self.jobs = {}

    async def save_async(self):
        """Save job metadata to disk asynchronously."""
        try:
            # Prepare data
            clean_jobs = {}
            for jid, data in self.jobs.items():
                clean_jobs[jid] = {k: v for k, v in data.items() if k not in ["process", "event_source"]}
            
            content = json.dumps(clean_jobs, indent=2)
            
            # Write asynchronously
            async with aiofiles.open(str(self.jobs_file), mode='w') as f:
                await f.write(content)
        except Exception as e:
            print(f"Async save error: {e}")

    def save(self):
        """Legacy synchronous save for non-async contexts."""
        try:
            clean_jobs = {}
            for jid, data in self.jobs.items():
                clean_jobs[jid] = {k: v for k, v in data.items() if k not in ["process", "event_source"]}
            self.jobs_file.write_text(json.dumps(clean_jobs, indent=2))
        except Exception:
            pass

    def add_job(self, job_id: str, data: dict, process=None):
        """Add a new job and track its process if provided."""
        self.jobs[job_id] = data
        if process:
            self.processes[job_id] = process
            self.jobs[job_id]["pid"] = process.pid
            self.jobs[job_id]["status"] = "running"
        else:
            self.jobs[job_id]["status"] = self.jobs[job_id].get("status", "pending")
        # Standard adds/removes still sync save for immediate consistency
        self.save()

    def update_job(self, job_id: str, updates: dict, save_to_disk: bool = True):
        """Update job metadata. Skip disk write if save_to_disk is False."""
        if job_id in self.jobs:
            self.jobs[job_id].update(updates)
            if save_to_disk:
                self.save()

    def get_job(self, job_id: str):
        """Get job metadata, attaching the live process object if active."""
        job = self.jobs.get(job_id)
        if job and job_id in self.processes:
            job["process"] = self.processes[job_id]
        return job

    def remove_job(self, job_id: str):
        """Remove a job from tracking."""
        if job_id in self.jobs:
            del self.jobs[job_id]
        if job_id in self.processes:
            del self.processes[job_id]
        self.save()

    def cleanup_on_startup(self):
        """Identify 'running' jobs whose processes are gone and return livestreams for recovery."""
        changed = False
        to_recover = []
        for job_id, job in self.jobs.items():
            if job.get("status") == "running":
                # On startup, all previously 'running' jobs are considered interrupted
                if job.get("mode") == "livestream":
                    to_recover.append(job_id)
                
                job["status"] = "interrupted"
                job["pid"] = None
                changed = True
        if changed:
            self.save()
        return to_recover

    def get_all_jobs(self):
        """Return all tracked jobs."""
        return self.jobs
