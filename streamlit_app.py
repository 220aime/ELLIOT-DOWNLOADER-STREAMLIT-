# streamlit_app.py — Cloud-compatible Eliot Downloader

import streamlit as st
import uuid
import time
import threading
import os
from datetime import datetime
from pathlib import Path

# Import our backend functions
try:
    from main import (
        list_cookie_files,
        save_uploaded_cookie,
        download_sessions,
        download_job,
        cleanup_old_cookies,
        DownloadProgress,
        has_ffmpeg,
        DOWNLOAD_DIR
    )
except ImportError as e:
    st.error(f"Import error: {e}")
    st.error("Make sure main.py is in the same directory as streamlit_app.py")
    st.stop()

# ---------- Page Config ----------
st.set_page_config(
    page_title="Eliot Downloader",
    page_icon="🎬",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- Initialize Session State ----------
if "download_sessions" not in st.session_state:
    st.session_state.download_sessions = {}

# ---------- Custom CSS ----------
st.markdown("""
<style>
.main-header {
    text-align: center;
    padding: 20px 0;
    margin-bottom: 30px;
    border-bottom: 2px solid #f0f0f0;
}

.download-card {
    padding: 25px;
    border-radius: 15px;
    border: 1px solid #e0e0e0;
    background-color: #f9f9f9;
    margin-bottom: 20px;
}

.info-card {
    padding: 20px;
    border-radius: 10px;
    border: 1px solid #d0d0d0;
    background-color: #f5f5f5;
}

.stButton > button {
    width: 100%;
    border-radius: 8px;
    height: 3em;
    background-color: #FF6B6B;
    color: white;
    border: none;
}

.stButton > button:hover {
    background-color: #FF5252;
    border: none;
}

.progress-container {
    padding: 15px;
    border-radius: 10px;
    background-color: #f0f8ff;
    border: 1px solid #b0d4f1;
    margin: 10px 0;
}
</style>
""", unsafe_allow_html=True)

# ---------- Helper Functions ----------
def start_download_session(url: str, media: str, quality: str, cookie_name: str = None):
    """Start a download session with threading"""
    
    # Resolve cookie file path
    cookie_file_path = None
    if cookie_name and cookie_name != "None":
        cookies = list_cookie_files()
        for cookie in cookies:
            if cookie["name"] == cookie_name:
                cookie_file_path = cookie["path"]
                break
    
    # Create session
    session_id = str(uuid.uuid4())
    download_sessions[session_id] = DownloadProgress(session_id)
    st.session_state.download_sessions[session_id] = download_sessions[session_id]
    
    # Start download in background thread
    thread = threading.Thread(
        target=download_job,
        args=(url, media, quality, session_id, cookie_file_path),
        daemon=True
    )
    thread.start()
    
    return session_id

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("### Cookie Management")
    
    # Cleanup old cookies
    cleanup_old_cookies()
    
    # List available cookies
    cookies = list_cookie_files()
    cookie_names = ["None"] + [c["name"] for c in cookies]
    
    selected_cookie = st.selectbox(
        "Select cookie file", 
        cookie_names, 
        help="Cookie files help access private or age-restricted content"
    )
    
    # Upload new cookie file
    uploaded_file = st.file_uploader(
        "Upload cookies.txt", 
        type=["txt"],
        help="Export cookies from your browser to access private content"
    )
    
    if uploaded_file is not None:
        try:
            path = save_uploaded_cookie(uploaded_file.name, uploaded_file.getvalue())
            st.success(f"Cookie saved: {path.name}")
            st.rerun()
        except Exception as e:
            st.error(f"Failed to save cookie: {e}")
    
    st.markdown("---")
    st.markdown("### System Info")
    st.write(f"**FFmpeg Available:** {'✅' if has_ffmpeg() else '❌'}")
    st.write(f"**Cookie Files:** {len(cookies)}")
    st.write(f"**Download Dir:** {DOWNLOAD_DIR}")

# ---------- Main Interface ----------
st.markdown("""
<div class='main-header'>
    <h1>🎬 Eliot Downloader</h1>
    <p>Download videos and audio from various platforms</p>
</div>
""", unsafe_allow_html=True)

# Create main columns
col1, col2 = st.columns([2, 1], gap="large")

with col1:
    st.markdown("<div class='download-card'>", unsafe_allow_html=True)
    st.subheader("Download Content")
    
    # URL input
    url = st.text_input(
        "Video/Audio URL", 
        placeholder="https://www.youtube.com/watch?v=...",
        help="Paste URL from YouTube, Vimeo, Instagram, and other supported platforms"
    )
    
    # Format and quality selection
    col_format, col_quality = st.columns(2)
    
    with col_format:
        media_type = st.selectbox(
            "Format", 
            ["video", "audio", "photo"],
            help="Choose the type of content to download"
        )
    
    with col_quality:
        if media_type == "video":
            quality = st.selectbox(
                "Video Quality", 
                ["best", "1080p", "720p", "480p", "360p"],
                help="Higher quality = larger file size"
            )
        else:
            quality = "best"
            st.selectbox("Quality", ["best"], disabled=True)
    
    # Download button
    if st.button("🚀 Start Download", type="primary"):
        if not url.strip():
            st.error("Please enter a valid URL")
        else:
            # Start download
            session_id = start_download_session(
                url.strip(), 
                media_type, 
                quality, 
                selected_cookie
            )
            
            st.success(f"Download started! Session ID: {session_id[:8]}...")
            
            # Create progress tracking area
            progress_placeholder = st.empty()
            
            # Track progress
            max_wait_time = 300  # 5 minutes max
            start_time = time.time()
            
            while time.time() - start_time < max_wait_time:
                # Get current progress
                prog = download_sessions.get(session_id)
                
                if not prog:
                    st.error("Download session lost")
                    break
                
                # Update progress display
                with progress_placeholder.container():
                    st.markdown("<div class='progress-container'>", unsafe_allow_html=True)
                    
                    # Progress bar
                    progress_value = max(0, min(100, prog.progress)) / 100
                    st.progress(progress_value)
                    
                    # Status information
                    col_status1, col_status2 = st.columns(2)
                    
                    with col_status1:
                        st.write(f"**Status:** {prog.status.title()}")
                        if prog.filename:
                            st.write(f"**File:** {prog.filename}")
                    
                    with col_status2:
                        if prog.speed != "N/A":
                            st.write(f"**Speed:** {prog.speed}")
                        if prog.eta != "N/A":
                            st.write(f"**ETA:** {prog.eta}")
                    
                    st.markdown("</div>", unsafe_allow_html=True)
                
                # Check if completed
                if prog.status == "completed":
                    st.success(f"✅ Download completed: {prog.filename}")
                    
                    # Offer download button if file exists
                    if prog.filepath and os.path.exists(prog.filepath):
                        try:
                            with open(prog.filepath, "rb") as f:
                                st.download_button(
                                    "📥 Download File",
                                    f,
                                    file_name=prog.filename,
                                    mime="application/octet-stream"
                                )
                        except Exception as e:
                            st.warning(f"File ready but couldn't create download button: {e}")
                            st.info(f"File saved to: {prog.filepath}")
                    break
                
                elif prog.status == "error":
                    st.error(f"❌ Download failed: {prog.error}")
                    
                    # Suggest solutions based on error type
                    if "age-restricted" in (prog.error or "").lower():
                        st.info("💡 Try uploading cookies from your browser to access age-restricted content")
                    elif "private" in (prog.error or "").lower():
                        st.info("💡 Make sure the content is public or upload cookies if you have access")
                    elif "unavailable" in (prog.error or "").lower():
                        st.info("💡 The content might be region-blocked or removed")
                    
                    break
                
                # Wait before next check
                time.sleep(2)
                
            else:
                st.warning("⏰ Download is taking longer than expected. Check back later.")
    
    st.markdown("</div>", unsafe_allow_html=True)

with col2:
    st.markdown("<div class='info-card'>", unsafe_allow_html=True)
    
    st.subheader("ℹ️ Information")
    
    st.markdown("**Supported Platforms:**")
    st.write("• YouTube (videos, shorts, live)")
    st.write("• Vimeo")
    st.write("• Instagram (posts, reels)")
    st.write("• Pinterest")
    st.write("• And many more...")
    
    st.markdown("**Features:**")
    st.write("• Multiple quality options")
    st.write("• Audio extraction")
    st.write("• Cookie support for private content")
    st.write("• Batch processing")
    
    st.markdown("**Tips:**")
    st.write("🔸 Use cookies for private/restricted content")
    st.write("🔸 Lower quality = faster download")
    st.write("🔸 Audio format works for music")
    
    if has_ffmpeg():
        st.success("✅ Full format support available")
    else:
        st.warning("⚠️ Limited format support (no FFmpeg)")
    
    st.markdown("</div>", unsafe_allow_html=True)
    
    # Active downloads section
    if download_sessions:
        st.markdown("### 📊 Active Downloads")
        for sid, prog in list(download_sessions.items()):
            status_color = {
                "completed": "🟢",
                "downloading": "🔵", 
                "processing": "🟡",
                "error": "🔴",
                "queued": "⚪"
            }.get(prog.status, "⚪")
            
            st.write(f"{status_color} {sid[:8]}... - {prog.status}")

# ---------- Footer ----------
st.markdown("---")
st.markdown(
    f"<div style='text-align: center; color: #666; font-size: 14px;'>"
    f"Eliot Downloader © {datetime.now().year} | "
    f"<a href='https://github.com/yt-dlp/yt-dlp' target='_blank'>Powered by yt-dlp</a>"
    f"</div>", 
    unsafe_allow_html=True
)
