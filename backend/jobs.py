import json
import os
from pathlib import Path
from typing import Dict

class JobManager:
    def __init__(self, data_path: str):
        self.path = Path(data_path) if data_path else Path("/app/data")
        self.jobs_file = self.path / "jobs.json"
        self.jobs: Dict[str, dict] = {}  # All metadata
        self.processes: Dict[str, any] = {}  # Active subprocesses
        
        # Ensure path exists before loading/saving
        try:
            self.path.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass
        self.load()

    def load(self):
        """Load job metadata from disk."""
        if self.jobs_file.exists():
            try:
                self.jobs = json.loads(self.jobs_file.read_text())
            except Exception:
                self.jobs = {}

    def save(self):
        """Save job metadata to disk, excluding process objects."""
        try:
            self.path.mkdir(parents=True, exist_ok=True)
            clean_jobs = {}
            for jid, data in self.jobs.items():
                # Ensure we don't try to serialize non-serializable objects
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
        self.save()

    def update_job(self, job_id: str, updates: dict):
        """Update job metadata."""
        if job_id in self.jobs:
            self.jobs[job_id].update(updates)
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
        """Identify 'running' jobs whose processes are gone and mark them as interrupted."""
        changed = False
        for job_id, job in self.jobs.items():
            if job.get("status") == "running":
                pid = job.get("pid")
                if pid:
                    try:
                        # signal 0 is a safe way to check if a process is still alive
                        os.kill(pid, 0)
                    except (ProcessLookupError, PermissionError):
                        job["status"] = "interrupted"
                        changed = True
                else:
                    job["status"] = "interrupted"
                    changed = True
        if changed:
            self.save()

    def get_all_jobs(self):
        """Return all tracked jobs."""
        return self.jobs
