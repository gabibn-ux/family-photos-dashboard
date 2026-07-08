#!/usr/bin/env python3
"""
build_index.py — בונה static/index.json מכל עץ Google Drive.

הרצה:
    python3 build_index.py

פלט:
    static/index.json   — מבנה תיקיות + metadata קבצים (ללא thumbnails)
"""

import json, os, re, sys, time
from pathlib import Path

# ── אתחול Drive API ──────────────────────────────────────────────────────────

with open(".streamlit/secrets.toml") as f:
    _raw = f.read()

ROOT_ID = re.search(r'DRIVE_ROOT_FOLDER_ID\s*=\s*"([^"]+)"', _raw).group(1)
SA_JSON = json.loads(
    re.search(r'GOOGLE_SERVICE_ACCOUNT_JSON\s*=\s*\'(.+?)\'$',
              _raw, re.DOTALL | re.MULTILINE).group(1)
)

import warnings; warnings.filterwarnings("ignore")
from googleapiclient.discovery import build
from google.oauth2 import service_account

creds = service_account.Credentials.from_service_account_info(
    SA_JSON, scopes=["https://www.googleapis.com/auth/drive.readonly"])
svc = build("drive", "v3", credentials=creds, cache_discovery=False)

# ── MIME types ───────────────────────────────────────────────────────────────

IMG_MIME = {
    "image/jpeg", "image/png", "image/heic", "image/heif",
    "image/webp", "image/gif", "image/bmp", "image/tiff", "image/x-tiff",
}
VID_MIME = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/mpeg", "video/3gpp",
}
AUD_MIME = {
    "audio/mpeg", "audio/mp3", "audio/mp4", "audio/m4a", "audio/x-m4a",
    "audio/wav", "audio/wave", "audio/ogg", "audio/aac", "audio/flac",
    "audio/x-flac", "audio/webm", "audio/3gpp", "audio/x-wav",
    "audio/vnd.dlna.adts",
}
FOLDER_MIME = "application/vnd.google-apps.folder"
SKIP_NAMES  = {".claude"}

# ── סריקה ────────────────────────────────────────────────────────────────────

folders: dict = {}
files:   dict = {}
total_files = 0
t0 = time.time()

def list_all(parent_id: str):
    """Return all children (one API call per page)."""
    items, token = [], None
    while True:
        res = svc.files().list(
            q=f"'{parent_id}' in parents and trashed=false",
            fields="nextPageToken,files(id,name,mimeType,size)",
            pageSize=1000,
            pageToken=token,
        ).execute()
        items.extend(res.get("files", []))
        token = res.get("nextPageToken")
        if not token:
            break
    return items


def walk(folder_id: str, parent_id=None, depth=0):
    global total_files
    children_folders = []
    children_files   = []

    for item in list_all(folder_id):
        if item["name"] in SKIP_NAMES:
            continue

        if item["mimeType"] == FOLDER_MIME:
            children_folders.append(item["id"])
            folders[item["id"]] = {
                "name":    item["name"],
                "parent":  folder_id,
                "folders": [],
                "files":   [],
            }
            walk(item["id"], folder_id, depth + 1)

        elif item["mimeType"] in IMG_MIME or item["mimeType"] in VID_MIME or item["mimeType"] in AUD_MIME:
            children_files.append(item["id"])
            files[item["id"]] = {
                "name":   item["name"],
                "mime":   item["mimeType"],
                "parent": folder_id,
            }
            total_files += 1
            if total_files % 100 == 0:
                elapsed = time.time() - t0
                print(f"  {total_files} קבצים... ({elapsed:.0f}s)", end="\r", flush=True)

    # Update parent record
    if folder_id in folders:
        folders[folder_id]["folders"] = children_folders
        folders[folder_id]["files"]   = children_files


print(f"סורק מ-root: {ROOT_ID}")
print("מחכה...")

# Root entry
folders[ROOT_ID] = {"name": "root", "parent": None, "folders": [], "files": []}
walk(ROOT_ID)

elapsed = time.time() - t0
print(f"\nסיום סריקה: {total_files} קבצים, {len(folders)} תיקיות ({elapsed:.0f}s)")

# ── שמירה ────────────────────────────────────────────────────────────────────

Path("static").mkdir(exist_ok=True)

index = {
    "root":    ROOT_ID,
    "folders": folders,
    "files":   files,
}

out = Path("static/index.json")
out.write_text(json.dumps(index, ensure_ascii=False, separators=(",", ":")))
size_kb = out.stat().st_size / 1024
print(f"נשמר: {out}  ({size_kb:.0f} KB)")
