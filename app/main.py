from fastapi import FastAPI, Request, Form, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.responses import RedirectResponse
import shutil, os, subprocess
from pathlib import Path

app = FastAPI()
templates = Jinja2Templates(directory="templates")
storage_dir = "/downloads"
os.makedirs(storage_dir, exist_ok=True)

@app.get("/", response_class=HTMLResponse)
def get_form(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.post("/download")
async def download(request: Request, url: str = Form(...), mode: str = Form(...),
                   potoken: str = Form(""), extra_args: str = Form(""),
                   cookies: UploadFile = None):
    temp_cookie_path = None

    if cookies:
        temp_cookie_path = f"/tmp/{cookies.filename}"
        with open(temp_cookie_path, "wb") as f:
            shutil.copyfileobj(cookies.file, f)

    cmd = []
    if mode == "ytarchive":
        cmd = ["ytarchive", "--add-metadata", "--threads", "2", url, "best"]
        if potoken:
            cmd += ["--potoken", potoken]
        if temp_cookie_path:
            cmd += ["--cookies", temp_cookie_path]
    else:
        cmd = ["yt-dlp", "-f", "bestvideo+bestaudio", "-o", f"{storage_dir}/%(title)s.%(ext)s", url]
        if temp_cookie_path:
            cmd += ["--cookies", temp_cookie_path]

    if extra_args:
        cmd += extra_args.split()

    subprocess.Popen(cmd)
    return RedirectResponse("/", status_code=303)
