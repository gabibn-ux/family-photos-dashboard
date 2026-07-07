"""
Google Drive API helpers for the Family Photos dashboard.
Uses a Service Account for authenticated access — works for any shared folder.
"""
import io
import json
import re
import requests as _requests
import streamlit as st
from PIL import Image

try:
    from pillow_heif import register_heif_opener
    register_heif_opener()
except ImportError:
    pass

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2 import service_account
from google.auth.transport.requests import Request as _GoogleRequest

SCOPES  = ["https://www.googleapis.com/auth/drive.readonly"]
_FIELDS = "id,name,mimeType,size,thumbnailLink"

# MIME type sets
IMG_MIME = frozenset([
    "image/jpeg", "image/png", "image/heic", "image/heif",
    "image/webp", "image/gif", "image/bmp", "image/tiff",
    "image/x-tiff",
])
VID_MIME = frozenset([
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/mpeg", "video/3gpp",
])


@st.cache_resource
def _drive_service():
    """Build and cache the Drive API service using Service Account credentials."""
    info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _svc():
    return _drive_service()


@st.cache_data(ttl=3500)   # refresh slightly before the 1-hour token expiry
def _get_access_token():
    """Return a fresh Bearer token for direct HTTP thumbnail requests."""
    info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
    creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
    creds.refresh(_GoogleRequest())
    return creds.token


# ── Folder / file listing ─────────────────────────────────────────────────────

@st.cache_data(ttl=3600)
def list_folders(parent_id):
    """Return list of subfolder dicts sorted by name.  [] on error."""
    if not parent_id:
        return []
    try:
        res = _svc().files().list(
            q=(f"'{parent_id}' in parents "
               "and mimeType='application/vnd.google-apps.folder' "
               "and trashed=false"),
            fields=f"files({_FIELDS})",
            orderBy="name",
            pageSize=1000,
        ).execute()
        return res.get("files", [])
    except Exception:
        return []


@st.cache_data(ttl=3600)
def list_media(parent_id):
    """Return (images, videos) as lists of file dicts for a folder."""
    if not parent_id:
        return [], []
    try:
        res = _svc().files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            fields=f"files({_FIELDS})",
            orderBy="name",
            pageSize=1000,
        ).execute()
        files = res.get("files", [])
    except Exception:
        return [], []
    imgs = [f for f in files if f.get("mimeType") in IMG_MIME]
    vids = [f for f in files if f.get("mimeType") in VID_MIME]
    return imgs, vids


@st.cache_data(ttl=3600)
def get_folder_id(parent_id, name):
    """Find a direct subfolder by name.  Returns its ID, or None."""
    for f in list_folders(parent_id):
        if f["name"] == name:
            return f["id"]
    return None


def list_media_recursive(parent_id):
    """Recursively collect (images, videos) under parent_id.
    list_media and list_folders are each cached — no need to cache this wrapper."""
    imgs, vids = list_media(parent_id)
    for folder in list_folders(parent_id):
        si, sv = list_media_recursive(folder["id"])
        imgs = imgs + si
        vids = vids + sv
    return imgs, vids


@st.cache_data(ttl=3600)
def search_drive_folders(query, root_id):
    """
    Search for folders whose names contain *query* (case-insensitive).
    Searches 2 levels below each category.
    Returns list of {"id", "name", "path"} sorted by name.
    """
    q = query.lower()
    results = []
    for cat in list_folders(root_id):
        for s1 in list_folders(cat["id"]):
            if q in s1["name"].lower():
                results.append({
                    "id":   s1["id"],
                    "name": s1["name"],
                    "path": f"{cat['name']} / {s1['name']}",
                })
            for s2 in list_folders(s1["id"]):
                if q in s2["name"].lower():
                    results.append({
                        "id":   s2["id"],
                        "name": s2["name"],
                        "path": f"{cat['name']} / {s1['name']} / {s2['name']}",
                    })
    return sorted(results, key=lambda r: r["name"])


# ── Image download ────────────────────────────────────────────────────────────

def _download_bytes(file_id):
    """Download raw bytes for a Drive file via Service Account."""
    buf = io.BytesIO()
    req = _svc().files().get_media(fileId=file_id)
    dl  = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    buf.seek(0)
    return buf.read()


@st.cache_data(ttl=86400)
def get_thumbnail_bytes(file_id, size=120):
    """
    Fetch thumbnail JPEG bytes via Drive CDN + Bearer token.
    Cached 24 hours — fast path for Streamlit Cloud (no local static/thumbs/).
    Returns None if the response is not a valid image.
    """
    try:
        token = _get_access_token()
        url   = f"https://drive.google.com/thumbnail?id={file_id}&sz=w{size}"
        resp  = _requests.get(url,
                               headers={"Authorization": f"Bearer {token}"},
                               timeout=15)
        content = resp.content
        # Validate: must be 200, non-trivial size, and start with JPEG/PNG/GIF magic
        if resp.status_code != 200 or len(content) < 500:
            return None
        if not (content[:2] == b'\xff\xd8' or        # JPEG
                content[:8] == b'\x89PNG\r\n\x1a\n' or  # PNG
                content[:6] in (b'GIF87a', b'GIF89a') or  # GIF
                content[:4] == b'RIFF'):              # WEBP
            return None
        return content
    except Exception:
        pass
    return None


@st.cache_data(ttl=86400)
def fetch_thumb(file_id, thumb_link=None, token=None, size=220):
    """
    Fetch thumbnail JPEG bytes.
    Fast path: Drive CDN thumbnail URL (20-30 KB) — token passed from main thread.
    Slow fallback: download full file and resize with PIL (5-10 MB).
    """
    # ── Fast path via CDN thumbnail ───────────────────────────────────────────
    if thumb_link and token:
        try:
            # Normalise size: strip trailing =sNNN / =wNNN-hNNN and append ours
            url = re.sub(r'=s\d+$', '', thumb_link)
            url = re.sub(r'=w\d+-h\d+.*$', '', url)
            url = url.rstrip('=') + f'=s{size}'
            resp = _requests.get(url,
                                 headers={"Authorization": f"Bearer {token}"},
                                 timeout=15)
            if resp.status_code == 200 and len(resp.content) > 500:
                img = Image.open(io.BytesIO(resp.content))
                img.thumbnail((size, size), Image.LANCZOS)
                if img.mode not in ("RGB", "RGBA"):
                    img = img.convert("RGB")
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=75)
                return buf.getvalue()
        except Exception:
            pass   # fall through to slow path

    # ── Slow fallback: download full file ────────────────────────────────────
    try:
        raw = _download_bytes(file_id)
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((size, size), Image.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=75)
        return buf.getvalue()
    except Exception:
        return None


@st.cache_data(ttl=86400)
def fetch_modal(file_id, max_px=900):
    """Download + resize for modal view. Returns JPEG bytes or None."""
    try:
        raw = _download_bytes(file_id)
        img = Image.open(io.BytesIO(raw))
        w, h  = img.size
        new_w = min(int(w * 0.7), max_px)
        new_h = int(h * new_w / w)
        img   = img.resize((new_w, new_h), Image.LANCZOS)
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=88)
        return buf.getvalue()
    except Exception:
        return None


# ── URL helpers ───────────────────────────────────────────────────────────────

def drive_view_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"
