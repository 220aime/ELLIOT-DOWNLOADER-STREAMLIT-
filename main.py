# main.py — Cloud-compatible backend for Eliot Downloader

import os
import uuid
import logging
import tempfile
from datetime import datetime, timedelta
from urllib.parse import urlparse
from pathlib import Path
from typing import Union, Optional

import yt_dlp

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("eliot")

# ---------- Cloud-compatible Paths ----------
# Use temp directory for cloud deployment
TEMP_DIR = Path(tempfile.gettempdir()) / "eliot_downloader"
DOWNLOAD_DIR = TEMP_DIR / "downloads"
COOKIES_DIR = TEMP_DIR / "cookies"

# Create directories safely
try:
    DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    COOKIES_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    log.warning(f"Could not create directories: {e}")
    # Fall back to current directory
    DOWNLOAD_DIR = Path(".")
    COOKIES_DIR = Path(".")

# ---------- Platform Config ----------
PLATFORM_CONFIGS = {
    "agasobanuyefilms.com": {
        "requires_cookies": True,
        "description": "Rwandan movie streaming platform",
        "user_agent": "Mozilla/5.0",
        "referer": "https://agasobanuyefilms.com/",
    },
    "youtube.com": {"requires_cookies": False, "description": "YouTube"},
    "youtu.be": {"requires_cookies": False, "description": "YouTube"},
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
    """Check if FFmpeg is available (usually not on cloud platforms)"""
    try:
        import shutil
        return shutil.which("ffmpeg") is not None
    except:
        return False

def fmt_bytes(n: Union[int, float, None]) -> str:
    """Format bytes to human readable format"""
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
    """Get platform-specific configuration"""
    if not url:
        return None
    
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        
        for k, v in PLATFORM_CONFIGS.items():
            if domain.endswith(k):
                return v
    except Exception as e:
        log.warning(f"Error parsing URL: {e}")
    
    return None

def list_cookie_files():
    """List available cookie files"""
    cookies = []
    try:
        for f in COOKIES_DIR.glob("*.txt"):
            if f.is_file():
                cookies.append({"name": f.stem, "path": str(f)})
    except Exception as e:
        log.warning(f"Error listing cookies: {e}")
    return cookies

def save_uploaded_cookie(filename: str, data: bytes):
    """Save uploaded cookie file"""
    try:
        safe = filename.replace("/", "_").replace("\\", "_")
        if not safe.endswith(".txt"):
            safe += ".txt"
        path = COOKIES_DIR / safe
        with open(path, "wb") as f:
            f.write(data)
        return path
    except Exception as e:
        log.error(f"Error saving cookie: {e}")
        raise

def cleanup_old_cookies():
    """Clean up old cookie files"""
    try:
        for f in COOKIES_DIR.glob("*.txt"):
            age = datetime.now() - datetime.fromtimestamp(f.stat().st_ctime)
            if age > timedelta(hours=24):
                f.unlink()
                log.info(f"Removed old cookie: {f.name}")
    except Exception as e:
        log.warning(f"Error cleaning cookies: {e}")

# ---------- yt-dlp Options ----------
def ydl_base_opts(url: str, cookie_file: Optional[str] = None):
    """Build base yt-dlp options"""
    platform = get_platform_config(url)
    
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "outtmpl": str(DOWNLOAD_DIR / "%(title).100s-%(id)s.%(ext)s"),
        "retries": 10,
        "socket_timeout": 30,
        # Don't merge formats if no FFmpeg
        "merge_output_format": "mp4" if has_ffmpeg() else None,
    }
    
    # Add cookie file if available
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
        log.info(f"Using cookie file: {cookie_file}")
    
    # Add platform-specific headers
    if platform:
        if "user_agent" in platform:
            opts.setdefault("http_headers", {})["User-Agent"] = platform["user_agent"]
        if "referer" in platform:
            opts.setdefault("http_headers", {})["Referer"] = platform["referer"]
    
    return opts

def build_video_format(quality: str) -> str:
    """Build video format string"""
    if quality == "best":
        return "best"
    
    # Extract height from quality (e.g., "720p" -> "720")
    digits = "".join(ch for ch in quality if ch.isdigit())
    if not digits:
        return "best"
    
    # If no FFmpeg, just get best single file
    if not has_ffmpeg():
        return f"best[height<={digits}]"
    
    # With FFmpeg, can merge video+audio
    return f"best[height<={digits}]"

def build_audio_opts():
    """Build audio extraction options"""
    opts = {"format": "bestaudio/best"}
    
    # Only add post-processing if FFmpeg is available
    if has_ffmpeg():
        opts["postprocessors"] = [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192"
        }]
    
    return opts

def build_photo_opts():
    """Build photo download options"""
    return {
        "format": "best",
        "skip_download": False
    }

# ---------- Progress Hook ----------
def _progress_hook(d, session_id: str):
    """Progress callback for yt-dlp"""
    prog = download_sessions.get(session_id)
    if not prog:
        return
    
    try:
        status = d.get("status", "")
        
        if status == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate")
            downloaded = d.get("downloaded_bytes") or 0
            
            prog.status = "downloading"
            if total and total > 0:
                prog.progress = (downloaded / total * 100)
            
            prog.file_size = fmt_bytes(total)
            prog.downloaded = fmt_bytes(downloaded)
            prog.speed = d.get("_speed_str", "N/A")
            prog.eta = d.get("_eta_str", "N/A")
            
            filename = d.get("filename", "")
            if filename:
                prog.filename = os.path.basename(filename)
                
        elif status == "finished":
            prog.status = "processing"
            prog.progress = 100.0
            filename = d.get("filename", "")
            if filename:
                prog.filepath = filename
                prog.filename = os.path.basename(filename)
                
        elif status == "error":
            prog.status = "error"
            prog.error = "Download error"
            
    except Exception as e:
        log.warning(f"Progress hook error: {e}")

# ---------- Download Job ----------
def download_job(url: str, media: str, quality: str, session_id: str, cookie_file: Optional[str] = None):
    """Main download function"""
    prog = download_sessions.get(session_id)
    if not prog:
        log.error(f"Session {session_id} not found")
        return
    
    prog.status = "starting"
    
    try:
        # Build options
        opts = ydl_base_opts(url, cookie_file)
        
        if media == "audio":
            opts.update(build_audio_opts())
        elif media == "photo":
            opts.update(build_photo_opts())
        else:
            opts["format"] = build_video_format(quality)
        
        # Add progress hook
        opts["progress_hooks"] = [lambda d: _progress_hook(d, session_id)]
        
        # Download
        with yt_dlp.YoutubeDL(opts) as ydl:
            log.info(f"Starting download: {url}")
            info = ydl.extract_info(url, download=True)
            
            # Find downloaded file
            target = ydl.prepare_filename(info)
            candidates = [
                target,
                target.replace(".webm", ".mp4"),
                target.replace(".mkv", ".mp4"),
                target.replace(".m4a", ".mp3")
            ]
            
            for candidate in candidates:
                if os.path.exists(candidate):
                    prog.filepath = candidate
                    prog.filename = os.path.basename(candidate)
                    break
            
            if not prog.filepath:
                # Look for any file in download directory with similar name
                title = info.get("title", "download")[:50]
                for file in DOWNLOAD_DIR.glob("*"):
                    if title.lower() in file.name.lower() or info.get("id", "") in file.name:
                        prog.filepath = str(file)
                        prog.filename = file.name
                        break
            
            if prog.filepath:
                prog.status = "completed"
                log.info(f"Download completed: {prog.filename}")
            else:
                raise Exception("Downloaded file not found")
                
    except Exception as e:
        prog.status = "error"
        error_msg = str(e)
        
        # Enhanced error messages
        if "age-restricted" in error_msg.lower() or "sign in" in error_msg.lower():
            prog.error = "Age-restricted content. Cookie file may be required."
        elif "private" in error_msg.lower():
            prog.error = "Private content - check URL and permissions."
        elif "unavailable" in error_msg.lower():
            prog.error = "Content unavailable or region-blocked."
        elif "format" in error_msg.lower():
            prog.error = "No suitable format found. Try different quality setting."
        else:
            prog.error = f"Download failed: {error_msg}"
        
        log.error(f"Download error for {session_id}: {prog.error}")

# ---------- Start Download Wrapper ----------
def start_download(url: str, media: str, quality: str, cookie_file: Optional[str] = None):
    """Start a download session"""
    session_id = str(uuid.uuid4())
    download_sessions[session_id] = DownloadProgress(session_id)
    
    log.info(f"Created download session {session_id} for {url}")
    
    # Run download
    download_job(url, media, quality, session_id, cookie_file)
    
    return session_id, download_sessions[session_id]
