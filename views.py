import os, subprocess, json, datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, login_required, logout_user, current_user
from .auth import User

main = Blueprint("main", __name__)
HISTORY_FILE = "download_history.json"

@main.route("/", methods=["GET", "POST"])
@login_required
def index():
    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)
    return render_template("index.html", history=history)

@main.route("/start", methods=["POST"])
@login_required
def start():
    url = request.form["url"]
    mode = request.form["mode"]
    potoken = request.form.get("potoken")
    cookies = request.files.get("cookies")

    cmd = []
    if mode == "ytarchive":
        cmd = ["ytarchive", "--merge", "--threads", "4"]
        if potoken: cmd += ["--potoken", potoken]
        if cookies:
            cookie_path = "/tmp/cookies.txt"
            cookies.save(cookie_path)
            cmd += ["--cookies", cookie_path]
        cmd += [url, "best"]

    elif mode == "ytdlp":
        cmd = ["yt-dlp", url]
        if potoken:
            cmd += ["--potoken", potoken]  # FIXME: validate option
        if cookies:
            cookie_path = "/tmp/cookies.txt"
            cookies.save(cookie_path)
            cmd += ["--cookies", cookie_path]

    subprocess.Popen(cmd, cwd="/downloads")

    history = []
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            history = json.load(f)

    history.insert(0, {
        "url": url,
        "mode": mode,
        "datetime": datetime.datetime.now().isoformat()
    })

    with open(HISTORY_FILE, "w") as f:
        json.dump(history[:100], f, indent=2)

    return redirect(url_for("main.index"))

@main.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if request.form["username"] == "admin" and request.form["password"] == "admin":
            user = User()
            login_user(user)
            return redirect(url_for("main.index"))
        flash("Invalid credentials")
    return render_template("login.html")

@main.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("main.login"))