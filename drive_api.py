"""
Google Drive API helpers for the Family Photos dashboard.
All functions use an API Key (no OAuth) — works for 'Anyone with link' folders.
"""
import requests
import streamlit as st

DRIVE_API = "https://www.googleapis.com/drive/v3/files"
_FIELDS    = "id,name,mimeType,size"

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


def _key():
    return st.secrets["GOOGLE_DRIVE_API_KEY"]


@st.cache_data(ttl=3600)
def list_folders(parent_id):
    """Return list of subfolder dicts sorted by name.  [] on error."""
    if not parent_id:
        return []
    params = {
        "q": (f"'{parent_id}' in parents "
              "and mimeType='application/vnd.google-apps.folder' "
              "and trashed=false"),
        "fields": f"files({_FIELDS})",
        "orderBy": "name",
        "pageSize": 1000,
        "key": _key(),
    }
    try:
        resp = requests.get(DRIVE_API, params=params, timeout=15)
        resp.raise_for_status()
        return resp.json().get("files", [])
    except Exception:
        return []


@st.cache_data(ttl=3600)
def list_media(parent_id):
    """Return (images, videos) as lists of file dicts for a folder."""
    if not parent_id:
        return [], []
    params = {
        "q": f"'{parent_id}' in parents and trashed=false",
        "fields": f"files({_FIELDS})",
        "orderBy": "name",
        "pageSize": 1000,
        "key": _key(),
    }
    try:
        resp = requests.get(DRIVE_API, params=params, timeout=15)
        resp.raise_for_status()
        files = resp.json().get("files", [])
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


@st.cache_data(ttl=86400)
def list_media_recursive(parent_id):
    """Recursively collect (images, videos) under parent_id (cached 24 h)."""
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
    Searches 2 levels below each category (cat → year → event).
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


# ── URL helpers ───────────────────────────────────────────────────────────────

def thumb_url(file_id, size=240):
    """CDN thumbnail URL — no auth required for 'Anyone with link' files."""
    return f"https://lh3.googleusercontent.com/d/{file_id}=s{size}"


def modal_url(file_id):
    return thumb_url(file_id, size=1200)


def drive_view_url(file_id):
    return f"https://drive.google.com/file/d/{file_id}/view"
