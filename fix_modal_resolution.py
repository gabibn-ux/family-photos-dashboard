#!/usr/bin/env python3
"""
fix_modal_resolution.py — מוריד מחדש ב-w400 את כל תמונות ה-modal שנותרו ב-120px.
(הסט הישן שהורד ב-sz=w120 ואז resize_thumbs לא הגדיל אותן)

הרצה:
    cd ~/projects/family-photos-dashboard
    python3 fix_modal_resolution.py
"""

import json, re, time, sys, io
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import warnings; warnings.filterwarnings("ignore")
from PIL import Image

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

# ── find 120px modal images ────────────────────────────────────────────────────
THUMB_DIR = Path("static/thumbs")
MODAL_DIR = Path("static/modal")

print("סורק modal images...")
todo = []
for p in MODAL_DIR.glob("*.jpg"):
    try:
        img = Image.open(p)
        if img.size[0] <= 120:
            todo.append(p.stem)   # file_id
    except Exception:
        todo.append(p.stem)

print(f"תמונות שצריכות הורדה מחדש ב-400px: {len(todo)}")
if not todo:
    print("הכל כבר בסדר! ✓")
    sys.exit(0)

# ── download at w400 ──────────────────────────────────────────────────────────
def fix_one(file_id):
    url  = f"https://drive.google.com/thumbnail?id={file_id}&sz=w400"
    resp = _req.get(url, headers={"Authorization": f"Bearer {get_token()}"},
                    timeout=20)
    content = resp.content

    is_img = (len(content) >= 500 and (
        content[:2] == b'\xff\xd8' or
        content[:8] == b'\x89PNG\r\n\x1a\n' or
        content[:6] in (b'GIF87a', b'GIF89a')
    ))
    if resp.status_code != 200 or not is_img:
        return "err"

    img = Image.open(io.BytesIO(content)).convert("RGB")

    # modal: 400px
    m = img.copy()
    m.thumbnail((400, 400), Image.LANCZOS)
    buf = io.BytesIO()
    m.save(buf, "JPEG", quality=80, optimize=True)
    (MODAL_DIR / f"{file_id}.jpg").write_bytes(buf.getvalue())

    # thumb: 120px (overwrite with clean resize from 400px source)
    t = img.copy()
    t.thumbnail((120, 120), Image.LANCZOS)
    buf2 = io.BytesIO()
    t.save(buf2, "JPEG", quality=75, optimize=True)
    (THUMB_DIR / f"{file_id}.jpg").write_bytes(buf2.getvalue())

    return "ok"

WORKERS = 12
done = ok = err = 0
t0 = time.time()

with ThreadPoolExecutor(max_workers=WORKERS) as ex:
    futs = {ex.submit(fix_one, fid): fid for fid in todo}
    for fut in as_completed(futs):
        done += 1
        try:
            r = fut.result()
            if r == "ok": ok += 1
            else: err += 1
        except Exception:
            err += 1
        if done % 200 == 0 or done == len(todo):
            elapsed = time.time() - t0
            rate    = done / elapsed if elapsed else 1
            remain  = (len(todo) - done) / rate
            pct     = done * 100 // len(todo)
            print(f"  [{pct:3d}%] {done}/{len(todo)}  ✓{ok} err:{err}  ~{remain:.0f}s נותר  ({rate:.1f}/s)")

elapsed = time.time() - t0
modal_mb = sum(p.stat().st_size for p in MODAL_DIR.glob("*.jpg")) / 1024 / 1024
print(f"\n✓ הסתיים ב-{elapsed:.0f}s | modal: {modal_mb:.1f}MB | חדשים:{ok} שגיאות:{err}")
