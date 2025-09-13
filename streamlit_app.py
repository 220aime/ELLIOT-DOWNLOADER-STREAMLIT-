# streamlit_app.py — Eliot Downloader with Light/Dark theme support
from __future__ import annotations

import uuid
import time
from pathlib import Path
from datetime import datetime

import streamlit as st

from main import (
    list_cookie_files,
    save_uploaded_cookie,
    start_download,
    download_sessions,
)

# ---------- Page Config ----------
st.set_page_config(
    page_title="Eliot Downloader",
    page_icon=None,
    layout="wide"
)

# ---------- Basic SEO ----------
st.markdown(
    """
    <meta name="description" content="Eliot Downloader — fast, reliable video and audio downloader powered by yt-dlp.">
    <meta name="robots" content="index,follow">
    """,
    unsafe_allow_html=True
)

# ---------- Theme Detection ----------
theme = st.get_option("theme.base") or "dark"  # "light" or "dark"

if theme == "light":
    CUSTOM_CSS = """
    <style>
    body, .stApp {
      background-color: #ffffff;
      color: #111827;
    }
    .card {
      background: #f9fafb;
      border: 1px solid #e5e7eb;
      border-radius: 14px;
      padding: 20px;
    }
    .stButton>button {
      background: #2563eb;
      color: white;
      border-radius: 8px;
      border: none;
      padding: 0.6rem 1rem;
    }
    .stButton>button:hover { opacity: 0.92; }
    .footer {
      color: #6b7280;
      font-size: 13px;
      text-align: center;
      padding: 16px 0 6px 0;
      border-top: 1px solid #e5e7eb;
      margin-top: 28px;
    }
    </style>
    """
else:  # dark theme
    CUSTOM_CSS = """
    <style>
    body, .stApp {
      background-color: #0b0c0f;
      color: #e5e7eb;
    }
    .card {
      background: #111317;
      border: 1px solid #1f2937;
      border-radius: 14px;
      padding: 20px;
    }
    .stButton>button {
      background: #2563eb;
      color: white;
      border-radius: 8px;
      border: none;
      padding: 0.6rem 1rem;
    }
    .stButton>button:hover { opacity: 0.92; }
    .footer {
      color: #9ca3af;
      font-size: 13px;
      text-align: center;
      padding: 16px 0 6px 0;
      border-top: 1px solid #1f2937;
      margin-top: 28px;
    }
    </style>
    """

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ---------- Sidebar ----------
with st.sidebar:
    st.markdown("<h2 style='margin-bottom:0'>Eliot Downloader</h2>", unsafe_allow_html=True)
    st.caption("Streamlined video and audio downloads.")
    st.markdown("---")

    st.subheader("Cookies")
    cookies = list_cookie_files()
    if cookies:
        names = ["None"] + [c["name"] for c in cookies]
    else:
        names = ["None"]

    selected_cookie = st.selectbox("Select cookie file", names, index=0, key="cookie_select")

    st.markdown("Upload cookie file (.txt) to access age/region-restricted content.")
    uploaded = st.file_uploader("Upload cookies.txt", type=["txt"], key="cookie_upload")
    if uploaded is not None:
        path = save_uploaded_cookie(uploaded.name, uploaded.getvalue())
        st.success(f"Cookie saved: {path.name}")
        st.experimental_rerun()

# ---------- Main Layout ----------
col_left, col_right = st.columns([7, 5], gap="large")

with col_left:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### Download")
    url = st.text_input("Video URL", placeholder="https://...")

    col_a, col_b = st.columns(2)
    with col_a:
        media = st.selectbox("Format", ["video", "audio"], index=0)
    with col_b:
        quality = st.selectbox("Quality (video)", ["best", "1080p", "720p", "480p", "360p"], index=0)

    start = st.button("Start Download")
    placeholder = st.empty()

    if start:
        if not url.strip():
            st.error("Please provide a valid URL.")
        else:
            session_id = str(uuid.uuid4())
            start_download(url=url.strip(), media=media, quality=quality, session_id=session_id, cookie_name=st.session_state.cookie_select)

            # Live progress polling
            with placeholder.container():
                st.write("Progress")
                prog_bar = st.progress(0)
                status_area = st.empty()

            while True:
                prog = download_sessions.get(session_id)
                if not prog:
                    time.sleep(0.2)
                    continue

                pct = max(0, min(100, int(prog.progress)))
                prog_bar.progress(pct)
                status_area.write(f"Status: {prog.status}")

                if prog.status in ("completed", "error"):
                    break
                time.sleep(0.35)

            prog = download_sessions.get(session_id)
            if prog and prog.status == "completed" and prog.filepath:
                st.success(f"Completed: {prog.filename}")
                try:
                    with open(prog.filepath, "rb") as f:
                        st.download_button("Download file", f, file_name=Path(prog.filepath).name)
                except Exception:
                    st.info("File is saved to your system Downloads folder.")
            elif prog and prog.status == "error":
                st.error(f"Error: {prog.error or 'Download failed'}")

    st.markdown("</div>", unsafe_allow_html=True)

with col_right:
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("### System")
    st.write(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    st.write(f"Downloads folder: {str(Path.home() / 'Downloads')}")
    if cookies := list_cookie_files():
        st.write("Cookie files found:")
        for c in cookies:
            st.write(f"• {c['name']}.txt")
    else:
        st.write("No cookie files detected.")
    st.markdown("</div>", unsafe_allow_html=True)

# ---------- Footer ----------
st.markdown(
    f"<div class='footer'>&copy; {datetime.now().year} Eliot Downloader. All rights reserved.</div>",
    unsafe_allow_html=True
)
