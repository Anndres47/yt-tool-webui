from fastapi import FastAPI, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn, os, subprocess

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.post("/api/download")
async def download(url: str = Form(...), mode: str = Form(...), cookies: str = Form(""), potoken: str = Form("")):
    cmd = ["ytarchive" if mode == "livestream" else "yt-dlp", url]
    if cookies:
        cmd += ["--cookies", cookies]
    if potoken:
        cmd += ["--potoken", potoken]  # FIXME: check yt-dlp syntax
    try:
        subprocess.Popen(cmd)
        return {"status": "started"}
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.post("/api/ffmpeg/cut")
async def cut_video(video: UploadFile, start: str = Form(...), end: str = Form(...), name: str = Form(...)):
    input_path = f"/tmp/{video.filename}"
    output_path = f"/app/downloads/{name}.mp4"
    with open(input_path, "wb") as f:
        f.write(await video.read())
    cmd = ["ffmpeg", "-i", input_path, "-ss", start, "-to", end, "-c", "copy", output_path]
    subprocess.run(cmd)
    return {"output": output_path}
