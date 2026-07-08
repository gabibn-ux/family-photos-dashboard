#!/usr/bin/env python3
"""
resize_thumbs.py — מקטין thumbnails ומייצר גרסאות modal

מקור:  static/thumbs/*.jpg  (קיים מקומית, ~424MB)
פלט:
  static/thumbs/*.jpg   ← מוחלף בגרסה קטנה (w120 q70, ~19MB)
  static/modal/*.jpg    ← גרסה למודל (w400 q75, ~25MB)

הרצה:
    cd ~/projects/family-photos-dashboard
    python3 resize_thumbs.py
"""

import io
import pathlib
import sys
import time
import concurrent.futures
from PIL import Image

SRC   = pathlib.Path("static/thumbs")
MODAL = pathlib.Path("static/modal")
MODAL.mkdir(exist_ok=True)

files = sorted(SRC.glob("*.jpg"))
if not files:
    print("לא נמצאו קבצים ב-static/thumbs/ — הרץ build_thumbs.py קודם")
    sys.exit(1)

print(f"מעבד {len(files)} קבצים...")
t0 = time.time()

done = 0
errors = 0

def process(jpg):
    try:
        raw = jpg.read_bytes()

        # ── Grid thumbnail: w120 q70 (דורס במקום) ──────────────────
        img = Image.open(io.BytesIO(raw))
        img.thumbnail((120, 120), Image.LANCZOS)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=70, optimize=True)
        jpg.write_bytes(buf.getvalue())

        # ── Modal: w400 q75 (נוצר רק אם חסר) ──────────────────────
        out_m = MODAL / jpg.name
        if not out_m.exists():
            # פתח שוב מהמקור המקורי (לפני הקטנה)
            img2 = Image.open(io.BytesIO(raw))
            img2.thumbnail((400, 400), Image.LANCZOS)
            if img2.mode not in ("RGB", "L"):
                img2 = img2.convert("RGB")
            buf2 = io.BytesIO()
            img2.save(buf2, "JPEG", quality=75, optimize=True)
            out_m.write_bytes(buf2.getvalue())

        return "ok"
    except Exception as e:
        return f"err:{e}"


with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
    futs = {ex.submit(process, f): f for f in files}
    for fut in concurrent.futures.as_completed(futs):
        done += 1
        r = fut.result()
        if r.startswith("err"):
            errors += 1
        if done % 500 == 0 or done == len(files):
            elapsed = time.time() - t0
            rate    = done / elapsed
            remain  = (len(files) - done) / rate if rate else 0
            print(f"  [{done*100//len(files):3d}%] {done}/{len(files)}  "
                  f"err:{errors}  ~{remain:.0f}s נותר  ({rate:.1f}/s)",
                  flush=True)

thumbs_mb = sum(p.stat().st_size for p in SRC.glob("*.jpg"))  / 1024 / 1024
modal_mb  = sum(p.stat().st_size for p in MODAL.glob("*.jpg")) / 1024 / 1024
print(f"\n✓ הסתיים ב-{time.time()-t0:.0f}s")
print(f"  static/thumbs/ → {thumbs_mb:.1f} MB")
print(f"  static/modal/  → {modal_mb:.1f} MB")
print(f"  סה\"כ: {thumbs_mb + modal_mb:.1f} MB")
