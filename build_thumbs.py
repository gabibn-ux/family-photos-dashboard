#!/usr/bin/env python3
"""
build_thumbs.py — מוריד thumbnails לכל הקבצים ב-index.json ושומר ב-static/thumbs/

גישה: drive.google.com/thumbnail?id=FILE_ID&sz=w120 + Bearer token
מהיר מאוד — לא צריך thumbnailLink ולא הורדת קובץ מלא.

הרצה:
    cd ~/projects/family-photos-dashboard
    python3 build_thumbs.py
"""

import json, re, time, sys, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import warnings; warnings.filterwarnings("ignore")

# ── auth ──────────────────────────────────────────────────────────────────────
with open(".streamlit/secrets.toml") as f:
    _raw = f.read()
SA_JSON = json.loads(
    re.search(r'GOOGLE_SERVICE_ACCOUNT_JSON\s*=\s*\'(.+?)\'$',
              _raw, re.DOTALL | re.MULTILINE).group(1)
)

from google.oauth2 import service_account
from google.auth.transport.requests import Request as _GReq
import requests as _req

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
_creds = service_account.Credentials.from_service_account_info(SA_JSON, scopes=SCOPES)
_creds.refresh(_GReq())

# Thread-safe token refresh
import threading
_tok_lock = threading.Lock()
_tok_time = [0.0]
_tok_val  = [_creds.token]

def get_token():
    with _tok_lock:
        if time.time() - _tok_time[0] > 3000:
            _creds.refresh(_GReq())
            _tok_val[0]  = _creds.token
            _tok_time[0] = time.time()
        return _tok_val[0]

# ── setup ──────────────────────────────────────────────────────────────────────
with open("static/index.json") as f:
    index = json.load(f)

THUMB_DIR = Path("static/thumbs")
THUMB_DIR.mkdir(parents=True, exist_ok=True)

all_files = list(index["files"].items())
todo = [(fid, fd) for fid, fd in all_files
        if not (THUMB_DIR / f"{fid}.jpg").exists()]

print(f"סה״כ קבצים: {len(all_files)}  |  לא הורדו: {len(todo)}")
if not todo:
    print("הכל כבר הורד! ✓")
    sys.exit(0)

# ── download ──────────────────────────────────────────────────────────────────
VID_MIME = {"video/mp4","video/quicktime","video/x-msvideo",
            "video/x-matroska","video/mpeg","video/3gpp"}

# Pre-built 1x1 grey JPEG for videos (placeholder)
_VID_PLACEHOLDER = (
    b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
    b'\xff\xdb\x00C\x00\x08\x06\x06\x07\x06\x05\x08\x07\x07\x07\t\t\x08\n\x0c'
    b'\x14\r\x0c\x0b\x0b\x0c\x19\x12\x13\x0f\x14\x1d\x1a\x1f\x1e\x1d\x1a\x1c'
    b'\x1c $.\' ",#\x1c\x1c(7),01444\x1f\'9=82<.342\x1e\x1e'
    b'\x1c!(-@1=-@-0\x1e\x1e\x1c\xff\xc0\x00\x0b\x08\x00x\x00x\x01\x01\x11\x00'
    b'\xff\xc4\x00\x1f\x00\x00\x01\x05\x01\x01\x01\x01\x01\x01\x00\x00\x00\x00'
    b'\x00\x00\x00\x00\x01\x02\x03\x04\x05\x06\x07\x08\t\n\x0b\xff\xda\x00\x08'
    b'\x01\x01\x00\x00?\x00\xf5\xd6\xff\xd9'
)

def download_one(file_id, fdata):
    out = THUMB_DIR / f"{file_id}.jpg"
    if out.exists():
        return "skip"
    mime = fdata.get("mime", "")
    if mime in VID_MIME:
        # Use Drive thumbnail which often works for videos too
        pass
    url  = f"https://drive.google.com/thumbnail?id={file_id}&sz=w120"
    resp = _req.get(url, headers={"Authorization": f"Bearer {get_token()}"},
                    timeout=20)
    content = resp.content
    # Validate it's a real image (JPEG/PNG/GIF/WEBP magic bytes)
    is_img = (len(content) >= 500 and (
        content[:2] == b'\xff\xd8' or
        content[:8] == b'\x89PNG\r\n\x1a\n' or
        content[:6] in (b'GIF87a', b'GIF89a') or
        content[:4] == b'RIFF'
    ))
    if resp.status_code == 200 and is_img:
        out.write_bytes(content)
        return "ok"
    # Video or no thumb available — write small placeholder
    if mime in VID_MIME:
        # Save a dark square placeholder using PIL
        try:
            import io
            from PIL import Image, ImageDraw
            img = Image.new("RGB", (120, 120), (30, 30, 30))
            draw = ImageDraw.Draw(img)
            draw.polygon([(40, 36), (40, 84), (88, 60)], fill=(180, 180, 180))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            out.write_bytes(buf.getvalue())
            return "vid"
        except Exception:
            pass
    return "skip"


WORKERS = 12
done = cdn = skip = err = 0
t0 = time.time()

with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(download_one, fid, fd): fid for fid, fd in todo}
    for fut in as_completed(futs):
        done += 1
        try:
            r = fut.result()
            if r in ("ok", "vid"): cdn += 1
            elif r == "skip": skip += 1
        except Exception:
            err += 1
        if done % 200 == 0 or done == len(todo):
            elapsed = time.time() - t0
            rate    = done / elapsed
            remain  = (len(todo) - done) / rate if rate else 0
            pct     = done * 100 // len(todo)
            print(f"  [{pct:3d}%] {done}/{len(todo)}  ✓{cdn} skip:{skip} err:{err}  "
                  f"~{remain:.0f}s נותר  ({rate:.1f}/s)", flush=True)

elapsed = time.time() - t0
total_mb = sum(p.stat().st_size for p in THUMB_DIR.glob("*.jpg")) / 1024 / 1024
total_n  = len(list(THUMB_DIR.glob("*.jpg")))
print(f"\n✓ הסתיים ב-{elapsed:.0f}s | {total_n} thumbnails | {total_mb:.1f} MB")
