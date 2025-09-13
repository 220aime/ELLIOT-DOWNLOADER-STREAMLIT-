# streamlit_app.py — Eliot Downloader (Streamlit Edition)

import os
import streamlit as st
from main import (
    list_cookie_files,
    save_uploaded_cookie,
    cleanup_old_cookies,
    start_download,
    download_sessions,
)

# ---------- Page Config ----------
st.set_page_config(
    page_title="Eliot Downloader",
    page_icon="⬇️",
    layout="wide"
)

# ---------- Theme Toggle ----------
if "theme" not in st.session_state:
    st.session_state.theme = "light"

def toggle_theme():
    st.session_state.theme = "dark" if st.session_state.theme == "light" else "light"

if st.button("Toggle Light/Dark Mode"):
    toggle_theme()

if st.session_state.theme == "light":
    st.markdown(
        """
        <style>
        body, .stApp { background-color: #ffffff; color: #000000; }
        .stButton>button { background-color: #ec4899; color: #ffffff; border-radius: 8px; }
        .stTextInput>div>div>input { border: 1px solid #ec4899; }
        </style>
        """,
        unsafe_allow_html=True,
    )
else:
    st.markdown(
        """
        <style>
        body, .stApp { background-color: #0b0c0f; color: #e5e7eb; }
        .stButton>button { background-color: #2563eb; color: #ffffff; border-radius: 8px; }
        .stTextInput>div>div>input { border: 1px solid #2563eb; }
        </style>
        """,
        unsafe_allow_html=True,
    )

# ---------- Header ----------
st.title("Eliot Downloader")
st.write("Download videos, audio, and images from supported platforms (YouTube, Vimeo, Instagram, Pinterest, Agasobanuyefilms, etc.)")

# ---------- Input ----------
url = st.text_input("Enter media URL", placeholder="https://youtube.com/watch?v=...")
media_type = st.selectbox("Select type", ["video", "audio", "photo"])
quality = st.selectbox("Quality", ["best", "1080p", "720p", "480p", "360p"])

# ---------- Cookies ----------
st.subheader("Cookie Management")
uploaded_cookie = st.file_uploader("Upload cookie file (.txt)", type=["txt"])

if uploaded_cookie:
    path = save_uploaded_cookie(uploaded_cookie.name, uploaded_cookie.read())
    st.success(f"Cookie saved: {path.name}")
    st.rerun()

cleanup_old_cookies()
cookies = list_cookie_files()
if cookies:
    cookie_choice = st.selectbox("Select a cookie file", [None] + [c["name"] for c in cookies])
    cookie_file_path = next((c["path"] for c in cookies if c["name"] == cookie_choice), None)
else:
    cookie_file_path = None

# ---------- Download ----------
if st.button("Start Download"):
    if not url:
        st.error("Please enter a valid URL.")
    else:
        session_id, prog = start_download(url, media_type, quality, cookie_file_path)
        st.info(f"Started download with session ID: {session_id}")

        # Show progress
        if prog.status == "completed":
            st.success(f"Download complete: {prog.filename}")
            with open(prog.filepath, "rb") as f:
                st.download_button("Download File", f, file_name=prog.filename)
        elif prog.status == "error":
            st.error(f"Download failed: {prog.error}")
        else:
            st.warning(f"Status: {prog.status}")
