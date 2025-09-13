# main.py — Core logic for Eliot Downloader (Streamlit edition)
from __future__ import annotations

import os
import shutil
import threading
import time
import logging
from pathlib import Path
from typing import Optional, Dict, List

import yt_dlp

# ---------- Logging ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)s  %(message)s"
)
log = logging.getLogger("eliot")

# ---------- Paths ----------
BASE_DIR = Path(__file__).resolve().parent
DOWNLOAD_DIR = Path.home() / "Downloads"         # use system Downloads
COOKIES_DIR = BASE_DIR / "cookies"
FFMPEG_DIR = BASE_DIR / "bin"                    # optional local ffmpeg

DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
COOKIES_DIR.mkdir(parents=True, exist_ok=True)

# ---------- Progress Model ----------
class DownloadProgress:
    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        self.status = "queued"            # queued | starting | downloading | processing | completed | error
        self.progress = 0.0               # 0..100
        self.speed = "N/A"
        self.eta = "N/A"
        self.file_size = "N/A"
        self.downloaded = "0 B"
        self.error: Optional[str] = None
        self.filename = ""
        self.filepath = ""
        self.cookie_file: Optional[Path] = None
        self._lock = threading.Lock()

    def update(self, **kwargs) -> None:
        with self._lock:
            for k, v in kwargs.items():
                setattr(self, k, v)

# All sessions in memory
download_sessions: Dict[str, DownloadProgress] = {}
_sessions_lock = threading.Lock()

# ---------- Utilities ----------
def has_ffmpeg() -> bool:
    return (
        shutil.which("ffmpeg") is not None
        or (FFMPEG_DIR / "ffmpeg").exists()
        or (FFMPEG_DIR / "ffmpeg.exe").exists()
    )

def fmt_bytes(n: Optional[float]) -> str:
    if not n or n <= 0:
        return "N/A"
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    x = float(n)
    for u in units:
        if x < 1024.0:
            return f"{x:.1f} {u}"
        x /= 1024.0
    return f"{x:.1f} EB"

def list_cookie_files() -> List[dict]:
    out: List[dict] = []
    for p in sorted(COOKIES_DIR.glob("*.txt")):
        out.append({"name": p.stem, "path": str(p)})
    return out

def save_uploaded_cookie(filename: str, data: bytes) -> Path:
    safe_name = filename.replace("/", "_").replace("\\", "_")
    if not safe_name.endswith(".txt"):
        safe_name += ".txt"
    path = COOKIES_DIR / safe_name
    with open(path, "wb") as f:
        f.write(data)
    return path

# ---------- yt-dlp Options Builders ----------
def build_video_format(quality: str) -> str:
    if quality == "best":
        return "bv*+ba/b"
    digits = "".join(ch for ch in quality if ch.isdigit())
    if not digits:
        return "bv*+ba/b"
    return f"((bv*[height<={digits}][ext=mp4]/bv*[height<={digits}])+(ba[ext=m4a]/ba))/b[height<={digits}]"

def build_audio_opts() -> dict:
    return {
        "format": "bestaudio/best",
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    }

def ydl_base_opts(cookie_file_path: Optional[str] = None) -> dict:
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "merge_output_format": "mp4",
        "outtmpl": str(DOWNLOAD_DIR / "%(title).120B.%(ext)s"),
        "retries": 15,
        "socket_timeout": 30,
        "concurrent_fragment_downloads": 5,
    }
    if cookie_file_path and os.path.exists(cookie_file_path):
        opts["cookiefile"] = cookie_file_path
    if has_ffmpeg():
        opts["ffmpeg_location"] = str(FFMPEG_DIR)
    return opts

# ---------- Progress Hook ----------
def _progress_hook(d: dict, session_id: str) -> None:
    prog = download_sessions.get(session_id)
    if not prog:
        return
    status = d.get("status", "")
    try:
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            downloaded = d.get("downloaded_bytes") or 0
            pct = (downloaded / total * 100) if total else prog.progress
            prog.update(
                status="downloading",
                filename=os.path.basename(d.get("filename") or prog.filename),
                progress=pct,
                file_size=fmt_bytes(total),
                downloaded=fmt_bytes(downloaded),
                speed=d.get("_speed_str", "N/A"),
                eta=d.get("_eta_str", "N/A"),
            )
        elif status == "finished":
            prog.update(status="processing", progress=100.0, filepath=d.get("filename") or prog.filepath)
    except Exception as e:
        prog.update(status="error", error=str(e))

# ---------- Download Worker ----------
def _download_worker(url: str, media: str, quality: str, session_id: str, cookie_file_path: Optional[str]) -> None:
    prog = download_sessions[session_id]
    prog.update(status="starting")

    opts = ydl_base_opts(cookie_file_path)
    if media == "audio":
        opts.update(build_audio_opts())
    else:
        opts["format"] = build_video_format(quality)

    opts["progress_hooks"] = [lambda d: _progress_hook(d, session_id)]

    # slight jitter helps avoid extractor burst limits
    time.sleep(0.2)

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=True)
            target = ydl.prepare_filename(info)
            if target and os.path.exists(target):
                prog.update(filepath=target, filename=os.path.basename(target))
            prog.update(status="completed", progress=100.0)
    except Exception as e:
        log.exception("Download failed")
        prog.update(status="error", error=str(e))

# ---------- Public API ----------
def start_download(url: str, media: str, quality: str, session_id: str, cookie_name: Optional[str]) -> None:
    cookie_file_path = None
    if cookie_name and cookie_name != "None":
        cookie_path = COOKIES_DIR / f"{cookie_name}.txt"
        if cookie_path.exists():
            cookie_file_path = str(cookie_path)

    with _sessions_lock:
        download_sessions[session_id] = DownloadProgress(session_id)

    t = threading.Thread(
        target=_download_worker,
        args=(url, media, quality, session_id, cookie_file_path),
        daemon=True
    )
    t.start()

