#!/usr/bin/env python3
"""
build_thumbs_old_ids.py — מוריד thumbnails לקבצים עם IDs ישנים (0B5-...)
באמצעות files.get?fields=thumbnailLink מה-Drive API.

הרצה:
    cd ~/projects/family-photos-dashboard
    python3 build_thumbs_old_ids.py
"""

import json, re, time, sys
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
MODAL_DIR = Path("static/modal")
THUMB_DIR.mkdir(parents=True, exist_ok=True)
MODAL_DIR.mkdir(parents=True, exist_ok=True)

IMG_MIME = {"image/jpeg","image/jpg","image/png","image/heic","image/heif",
            "image/webp","image/gif","image/bmp","image/tiff"}

# Only files missing from BOTH thumbs AND modal
todo = [(fid, fd) for fid, fd in index["files"].items()
        if fd.get("mime") in IMG_MIME
        and not (THUMB_DIR / f"{fid}.jpg").exists()]

print(f"קבצים חסרים: {len(todo)}")
if not todo:
    print("הכל כבר קיים! ✓")
    sys.exit(0)

# ── download one ───────────────────────────────────────────────────────────────
from PIL import Image
import io

def download_one(file_id, fdata):
    thumb_out = THUMB_DIR / f"{file_id}.jpg"
    modal_out = MODAL_DIR / f"{file_id}.jpg"
    if thumb_out.exists() and modal_out.exists():
        return "skip"

    # Step 1: get thumbnailLink via files.get
    r = _req.get(
        f"https://www.googleapis.com/drive/v3/files/{file_id}",
        params={"fields": "thumbnailLink"},
        headers={"Authorization": f"Bearer {get_token()}"},
        timeout=15
    )
    if r.status_code != 200:
        return "err"

    thumb_link = r.json().get("thumbnailLink", "")
    if not thumb_link:
        return "no_link"

    # Step 2: change =s220 → =s400 for higher resolution
    thumb_link_400 = re.sub(r'=s\d+$', '=s400', thumb_link)

    # Step 3: download the thumbnail image (no auth needed, pre-signed URL)
    r2 = _req.get(thumb_link_400, timeout=15)
    if r2.status_code != 200 or len(r2.content) < 200:
        return "err"

    content = r2.content
    is_img = (
        content[:2] == b'\xff\xd8' or
        content[:8] == b'\x89PNG\r\n\x1a\n' or
        content[:6] in (b'GIF87a', b'GIF89a')
    )
    if not is_img:
        return "not_img"

    # Step 4: create thumb (120px) and modal (400px) via PIL
    try:
        img = Image.open(io.BytesIO(content))
        img = img.convert("RGB")

        # thumb 120px
        if not thumb_out.exists():
            t = img.copy()
            t.thumbnail((120, 120), Image.LANCZOS)
            buf = io.BytesIO()
            t.save(buf, "JPEG", quality=70, optimize=True)
            thumb_out.write_bytes(buf.getvalue())

        # modal 400px
        if not modal_out.exists():
            m = img.copy()
            m.thumbnail((400, 400), Image.LANCZOS)
            buf2 = io.BytesIO()
            m.save(buf2, "JPEG", quality=75, optimize=True)
            modal_out.write_bytes(buf2.getvalue())

        return "ok"
    except Exception as e:
        return f"pil_err:{e}"


# ── run ───────────────────────────────────────────────────────────────────────
WORKERS = 8
done = ok = skip = err = 0
t0 = time.time()

with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(download_one, fid, fd): fid for fid, fd in todo}
    for fut in as_completed(futs):
        done += 1
        try:
            r = fut.result()
            if r == "ok":   ok += 1
            elif r == "skip": skip += 1
            else: err += 1
        except Exception:
            err += 1
        if done % 100 == 0 or done == len(todo):
            elapsed = time.time() - t0
            rate    = done / elapsed if elapsed else 1
            remain  = (len(todo) - done) / rate
            pct     = done * 100 // len(todo)
            print(f"  [{pct:3d}%] {done}/{len(todo)}  ✓{ok} skip:{skip} err:{err}  ~{remain:.0f}s נותר  ({rate:.1f}/s)")

elapsed = time.time() - t0
thumb_mb = sum(p.stat().st_size for p in THUMB_DIR.glob("*.jpg")) / 1024 / 1024
modal_mb = sum(p.stat().st_size for p in MODAL_DIR.glob("*.jpg")) / 1024 / 1024
print(f"\n✓ הסתיים ב-{elapsed:.0f}s | thumbs: {thumb_mb:.1f}MB | modal: {modal_mb:.1f}MB | new:{ok} err:{err}")
