# main.py — Full backend for Eliot Downloader (Streamlit Edition)

import os
import shutil
import uuid
import logging
import time
from datetime import datetime, timedelta
from urllib.parse import urlparse
from pathlib import Path

import yt_dlp

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eliot")

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path.home() / "Downloads"
COOKIES_DIR = BASE_DIR / "cookies"
FFMPEG_DIR = BASE_DIR / "bin"

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Platform Config ----------
PLATFORM_CONFIGS = {
    "agasobanuyefilms.com": {
        "requires_cookies": True,
        "description": "Rwandan movie streaming platform",
        "user_agent": "Mozilla/5.0",
        "referer": "https://agasobanuyefilms.com/",
    },
    "youtube.com": {"requires_cookies": False, "description": "YouTube"},
    "vimeo.com": {"requires_cookies": False, "description": "Vimeo"},
    "instagram.com": {"requires_cookies": False, "description": "Instagram (videos, images, reels)"},
    "pinterest.com": {"requires_cookies": False, "description": "Pinterest images"},
}

# ---------- Download Session ----------
class DownloadProgress:
    def __init__(self, sid: str):
        self.session_id = sid
        self.status = "queued"
        self.progress = 0.0
        self.speed = "N/A"
        self.eta = "N/A"
        self.file_size = "N/A"
        self.downloaded = "0 B"
        self.error = None
        self.filename = ""
        self.filepath = ""
        self.cookie_file = None


download_sessions = {}

# ---------- Utilities ----------
def has_ffmpeg() -> bool:
    return shutil.which("ffmpeg") or (FFMPEG_DIR / "ffmpeg").exists()

def fmt_bytes(n: int | float | None) -> str:
    if not n or n <= 0:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB"]
    x = float(n)
    for u in units:
        if x < 1024.0:
            return f"{x:.1f} {u}"
        x /= 1024.0
    return f"{x:.1f} PB"

def get_platform_config(url: str):
    domain = urlparse(url).netloc.lower()
    if domain.startswith("www."):
        domain = domain[4:]
    for k, v in PLATFORM_CONFIGS.items():
        if domain.endswith(k):
            return v
    return None

def list_cookie_files():
    cookies = []
    for f in COOKIES_DIR.glob("*.txt"):
        cookies.append({"name": f.stem, "path": str(f)})
    return cookies

def save_uploaded_cookie(filename: str, data: bytes):
    safe = filename.replace("/", "_").replace("\\", "_")
    if not safe.endswith(".txt"):
        safe += ".txt"
    path = COOKIES_DIR / safe
    with open(path, "wb") as f:
        f.write(data)
    return path

def cleanup_old_cookies():
    for f in COOKIES_DIR.glob("*.txt"):
        age = datetime.now() - datetime.fromtimestamp(f.stat().st_ctime)
        if age > timedelta(hours=24):
            f.unlink()

# ---------- yt-dlp Options ----------
def ydl_base_opts(url: str, cookie_file: str | None = None):
    platform = get_platform_config(url)
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "outtmpl": str(DOWNLOAD_DIR / "%(title).100B-%(id)s.%(ext)s"),
        "retries": 10,
        "socket_timeout": 30,
    }
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
    if has_ffmpeg():
        opts["ffmpeg_location"] = str(FFMPEG_DIR)
    if platform and "user_agent" in platform:
        opts.setdefault("http_headers", {})["User-Agent"] = platform["user_agent"]
    if platform and "referer" in platform:
        opts.setdefault("http_headers", {})["Referer"] = platform["referer"]
    return opts

def build_video_format(quality: str) -> str:
    if quality == "best":
        return "bv*+ba/b"
    digits = "".join(ch for ch in quality if ch.isdigit())
    if not digits:
        return "bv*+ba/b"
    return f"((bv*[height<={digits}][ext=mp4]/bv*[height<={digits}])+(ba[ext=m4a]/ba))/b[height<={digits}]"

def build_audio_opts():
    return {
        "format": "bestaudio/best",
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
    }

def build_photo_opts():
    return {"format": "best", "skip_download": False}

# ---------- Progress Hook ----------
def _progress_hook(d, session_id: str):
    prog = download_sessions.get(session_id)
    if not prog:
        return
    status = d.get("status", "")
    if status == "downloading":
        total = d.get("total_bytes") or d.get("total_bytes_estimate")
        downloaded = d.get("downloaded_bytes") or 0
        prog.status = "downloading"
        prog.progress = (downloaded / total * 100) if total else prog.progress
        prog.file_size = fmt_bytes(total)
        prog.downloaded = fmt_bytes(downloaded)
        prog.speed = d.get("_speed_str", "N/A")
        prog.eta = d.get("_eta_str", "N/A")
        prog.filename = os.path.basename(d.get("filename") or prog.filename)
    elif status == "finished":
        prog.status = "processing"
        prog.progress = 100.0
        prog.filepath = d.get("filename") or prog.filepath
    elif status == "error":
        prog.status = "error"
        prog.error = "Download error"

# ---------- Download Job ----------
def download_job(url: str, media: str, quality: str, session_id: str, cookie_file: str | None = None):
    prog = download_sessions[session_id]
    prog.status = "starting"
    opts = ydl_base_opts(url, cookie_file)
    if media == "audio":
        opts.update(build_audio_opts())
    elif media == "photo":
        opts.update(build_photo_opts())
    else:
        opts["format"] = build_video_format(quality)
    opts["progress_hooks"] = [lambda d: _progress_hook(d, session_id)]
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            target = ydl.prepare_filename(info)
            for cand in [target, target.replace(".webm", ".mp4"), target.replace(".mkv", ".mp4")]:
                if os.path.exists(cand):
                    prog.filepath = cand
                    prog.filename = os.path.basename(cand)
                    break
            prog.status = "completed"
    except Exception as e:
        prog.status = "error"
        prog.error = str(e)
        log.error(f"Download error: {e}")

# ---------- Start Download Wrapper ----------
def start_download(url: str, media: str, quality: str, cookie_file: str | None = None):
    """
    Wrapper to start a download session, mimicking Flask's /start_download.
    Returns the session_id and its progress object.
    """
    session_id = str(uuid.uuid4())
    download_sessions[session_id] = DownloadProgress(session_id)

    # Run synchronously for Streamlit
    download_job(url, media, quality, session_id, cookie_file)

    return session_id, download_sessions[session_id]
