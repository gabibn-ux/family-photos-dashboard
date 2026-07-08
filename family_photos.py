#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Family Photos Dashboard — Static Index edition
Navigation reads from static/index.json (no Drive API).
Thumbnails fetched from Drive API (cached per session).
"""

import json
import os
import streamlit as st
from drive_api import fetch_modal, get_thumbnail_bytes, drive_view_url, IMG_MIME, VID_MIME

ROOT_ID   = st.secrets["DRIVE_ROOT_FOLDER_ID"]
THUMB_DIR = "static/thumbs"

CATEGORIES = [
    ("משפחה - לפי שנים",    "👨‍👩‍👧‍👦"),
    ("אירועים משפחתיים",    "🎉"),
    ("טיולים",               "✈️"),
    ("תמונות סרוקות",        "🗃️"),
    ("תמונות לא ממויינות",   "📋"),
    ("אוכל",                 "🍽️"),
    ("ג׳וי",                  "🐕"),
]
CAT_NAMES = [c[0] for c in CATEGORIES]
PAGE_SIZE = 24


# ── Load static index ─────────────────────────────────────────────────────────

@st.cache_resource
def load_index():
    with open("static/index.json", encoding="utf-8") as f:
        return json.load(f)


# ── Index navigation helpers (instant — no Drive API) ────────────────────────

def idx_subfolders(folder_id, idx):
    """Return list of {id, name} for direct sub-folders."""
    fdata = idx["folders"].get(folder_id, {})
    out = []
    for cid in fdata.get("folders", []):
        if cid in idx["folders"]:
            out.append({"id": cid, "name": idx["folders"][cid]["name"]})
    return out


def idx_media(folder_id, idx):
    """Return (images, videos) for direct files in folder."""
    fdata = idx["folders"].get(folder_id, {})
    imgs, vids = [], []
    for fid in fdata.get("files", []):
        f = idx["files"].get(fid)
        if not f:
            continue
        item = {"id": fid, "name": f["name"], "mimeType": f["mime"]}
        if f["mime"] in IMG_MIME:
            imgs.append(item)
        elif f["mime"] in VID_MIME:
            vids.append(item)
    return imgs, vids


def idx_media_recursive(folder_id, idx):
    """Recursively collect (images, videos) under folder_id."""
    imgs, vids = idx_media(folder_id, idx)
    for sub in idx_subfolders(folder_id, idx):
        si, sv = idx_media_recursive(sub["id"], idx)
        imgs = imgs + si
        vids = vids + sv
    return imgs, vids


def idx_find_folder(parent_id, name, idx):
    """Find a direct sub-folder by name. Returns id or None."""
    for cid in idx["folders"].get(parent_id, {}).get("folders", []):
        if idx["folders"].get(cid, {}).get("name") == name:
            return cid
    return None


def idx_search(query, root_id, idx):
    """Search folder names up to 2 levels deep. Returns [{id, name, path}]."""
    q = query.lower()
    results = []
    for cat_id in idx["folders"].get(root_id, {}).get("folders", []):
        cat_name = idx["folders"][cat_id]["name"]
        for s1_id in idx["folders"].get(cat_id, {}).get("folders", []):
            s1_name = idx["folders"][s1_id]["name"]
            if q in s1_name.lower():
                results.append({"id": s1_id, "name": s1_name,
                                "path": f"{cat_name} / {s1_name}"})
            for s2_id in idx["folders"].get(s1_id, {}).get("folders", []):
                s2_name = idx["folders"][s2_id]["name"]
                if q in s2_name.lower():
                    results.append({"id": s2_id, "name": s2_name,
                                    "path": f"{cat_name} / {s1_name} / {s2_name}"})
    return sorted(results, key=lambda r: r["name"])


def has_year_structure(folders):
    """True if ≥50% of folder names are 4-digit years."""
    if not folders:
        return False
    year_like = sum(1 for f in folders
                    if f["name"].isdigit() and len(f["name"]) == 4)
    return year_like / len(folders) >= 0.5


def group_by_5years(year_folders):
    """
    Group year folders into 5-year ranges.
    Returns [(label, [folder_dict, ...]), ...]  sorted ascending.
    9999 (unsorted) appended at end as '📦 לא ממויין'.
    """
    real, unsorted = [], []
    for f in year_folders:
        (unsorted if f["name"] == "9999" else real).append(f)

    real.sort(key=lambda f: int(f["name"]) if f["name"].isdigit() else 9998)

    if not real:
        return [("📦 לא ממויין", unsorted)] if unsorted else []

    nums = [int(f["name"]) for f in real if f["name"].isdigit()]
    lo   = (min(nums) // 5) * 5
    hi   = max(nums)

    groups = []
    y = lo
    while y <= hi:
        end     = y + 4
        label   = f"{y}–{end}"
        members = [f for f in real if f["name"].isdigit() and y <= int(f["name"]) <= end]
        if members:
            groups.append((label, members))
        y += 5

    if unsorted:
        groups.append(("📦 לא ממויין", unsorted))
    return groups


# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="תמונות משפחה",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  html, body, [class*="css"]  { direction: rtl; }
  .block-container             { padding-top: 3.5rem; padding-bottom: 2rem; }
  header[data-testid="stHeader"] { display: none; }
  .nav-title { font-size: 22px; font-weight: 700; color: #1f2937; white-space: nowrap; }
  .breadcrumb { font-size: 13px; color: #6b7280; margin-bottom: 4px; }
  .pager { text-align: center; color: #6b7280; font-size: 13px; padding-top: 4px; }
  div[data-testid="stButton"] > button {
    border-radius: 20px; font-size: 13px; padding: 5px 14px;
    width: 100%; transition: all 0.15s ease;
  }
  div[data-testid="stButton"] > button[kind="secondary"] {
    background: #f9fafb; border: 1px solid #e5e7eb; color: #374151;
    text-align: right; border-radius: 8px;
  }
  div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: #eff6ff; border-color: #93c5fd; color: #1d4ed8;
  }
  div[data-testid="stButton"] > button[kind="primary"] {
    background: #2563eb; border: none; color: white; font-weight: 600;
  }
  .stImage p { font-size: 11px; color: #9ca3af; text-align: center; }
  section[data-testid="stSidebar"] { display: none; }
  [data-testid="stDialog"] button[data-testid="stBaseButton-headerNoPadding"] { display: none !important; }

  /* ── Clickable thumbnails: transparent zoom button overlays the image ── */
  div[data-testid="stVerticalBlock"]:has(div[data-testid="stImage"]) {
    position: relative;
  }
  div[data-testid="stVerticalBlock"]:has(div[data-testid="stImage"]) > div:has(div[data-testid="stButton"]) {
    position: absolute !important;
    inset: 0;
    z-index: 5;
  }
  div[data-testid="stVerticalBlock"]:has(div[data-testid="stImage"]) > div:has(div[data-testid="stButton"]) button {
    width: 100% !important;
    height: 100% !important;
    background: transparent !important;
    border: none !important;
    box-shadow: none !important;
    color: transparent !important;
    cursor: zoom-in !important;
    border-radius: 6px !important;
    font-size: 0 !important;
    padding: 0 !important;
    margin: 0 !important;
  }
  div[data-testid="stVerticalBlock"]:has(div[data-testid="stImage"]) > div:has(div[data-testid="stButton"]) button:hover {
    background: rgba(0,0,0,0.07) !important;
    box-shadow: inset 0 0 0 3px rgba(255,255,255,0.8) !important;
  }
</style>
""", unsafe_allow_html=True)


# ── Session state ─────────────────────────────────────────────────────────────

def ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

ss("cat_idx",      0)
ss("search_q",     "")
ss("page",         0)
ss("nav_stack",    [])
ss("modal_img",    None)
ss("media_filter", "all")

idx = load_index()


# ── Modal ─────────────────────────────────────────────────────────────────────

@st.dialog("📷 תמונה", width="large")
def image_modal(file):
    data = fetch_modal(file["id"])
    if data:
        st.image(data, width="stretch")
    else:
        st.warning("לא ניתן לטעון תמונה זו")
    st.caption(file.get("name", ""))
    if st.button("✕ סגור", use_container_width=True):
        st.session_state.modal_img = None
        st.rerun()


# ── Header ────────────────────────────────────────────────────────────────────

title_col, home_col = st.columns([5, 1])
with title_col:
    st.markdown('<span class="nav-title">📸 תמונות משפחה</span>', unsafe_allow_html=True)
with home_col:
    if st.button("🏠 ראשי", type="secondary", use_container_width=True):
        st.session_state.cat_idx       = 0
        st.session_state.nav_stack     = []
        st.session_state.page          = 0
        st.session_state.search_q      = ""
        st.session_state.search_chosen = ""
        st.rerun()

search_q = st.text_input(
    "🔍 חיפוש תיקייה",
    value=st.session_state.search_q,
    placeholder="הקלד שם אירוע, שנה או מקום...",
)
if search_q != st.session_state.search_q:
    st.session_state.search_q      = search_q
    st.session_state.page          = 0
    st.session_state.nav_stack     = []
    st.session_state.search_chosen = ""
    st.rerun()

# Category pills
ROW1 = CATEGORIES[:4]
ROW2 = CATEGORIES[4:]

cols1 = st.columns(4)
for col, (name, icon) in zip(cols1, ROW1):
    idx_cat = CAT_NAMES.index(name)
    is_active = (idx_cat == st.session_state.cat_idx)
    with col:
        if st.button(f"{icon}  {name}", key=f"cat_{idx_cat}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            if not is_active:
                st.session_state.cat_idx   = idx_cat
                st.session_state.nav_stack = []
                st.session_state.page      = 0
                st.rerun()

_, c1, c2, c3, _ = st.columns([1, 2, 2, 2, 1])
for col, (name, icon) in zip((c1, c2, c3), ROW2):
    idx_cat = CAT_NAMES.index(name)
    is_active = (idx_cat == st.session_state.cat_idx)
    with col:
        if st.button(f"{icon}  {name}", key=f"cat_{idx_cat}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            if not is_active:
                st.session_state.cat_idx   = idx_cat
                st.session_state.nav_stack = []
                st.session_state.page      = 0
                st.rerun()

st.markdown('<hr style="margin:8px 0 12px 0;border:none;border-top:2px solid #e5e7eb;">',
            unsafe_allow_html=True)


# ── Pill helper ───────────────────────────────────────────────────────────────

def pill_row(options, selected, key_prefix, n_cols, all_label="הכל", all_at_end=False):
    all_options = options + [all_label] if all_at_end else [all_label] + options
    result = "NO_CHANGE"
    rows = [all_options[i:i+n_cols] for i in range(0, len(all_options), n_cols)]
    for row in rows:
        padded = row + [""] * (n_cols - len(row))
        cols = st.columns(n_cols)
        for col, opt in zip(cols, padded):
            if not opt:
                continue
            is_active = (opt == all_label and selected is None) or (opt == selected)
            with col:
                if st.button(opt, key=f"{key_prefix}_{opt}",
                             type="primary" if is_active else "secondary",
                             use_container_width=True):
                    result = None if opt == all_label else opt
    return result


# ── Resolve category folder (from index) ──────────────────────────────────────

selected_cat  = CAT_NAMES[st.session_state.cat_idx]
cat_folder_id = idx_find_folder(ROOT_ID, selected_cat, idx)

nav       = st.session_state.nav_stack
nav_depth = len(nav)

if not st.session_state.search_q:
    if not cat_folder_id:
        st.warning(f"לא נמצאה קטגוריה: **{selected_cat}**")
        st.stop()

    cat_folders  = idx_subfolders(cat_folder_id, idx)
    with_years   = has_year_structure(cat_folders)

    if with_years:
        year_groups   = group_by_5years(cat_folders)
        group_labels  = [g[0] for g in year_groups]

        # Auto-select most recent group on first entry
        if not nav and year_groups:
            last_label, last_members = year_groups[-1]
            st.session_state.nav_stack = [{"id": "__group__", "name": last_label,
                                            "folders": last_members}]
            nav       = st.session_state.nav_stack
            nav_depth = 1

        active_group = nav[0]["name"] if nav else None
        st.markdown("**תקופה**")
        gr_result = pill_row(group_labels, active_group, "grp", n_cols=7,
                             all_label="הכל", all_at_end=True)
        if gr_result != "NO_CHANGE":
            if gr_result is None:
                st.session_state.nav_stack = []
            else:
                matched = next((g for g in year_groups if g[0] == gr_result), None)
                if matched:
                    st.session_state.nav_stack = [{"id": "__group__", "name": matched[0],
                                                    "folders": matched[1]}]
            st.session_state.page = 0
            st.rerun()

        if nav and nav[0].get("id") == "__group__":
            # Collect events from ALL years in the group; prefix with year
            all_events = []
            for yf in nav[0]["folders"]:
                for ev in idx_subfolders(yf["id"], idx):
                    display_name = f"{yf['name']} | {ev['name']}"
                    all_events.append({"id": ev["id"], "name": ev["name"],
                                       "display": display_name, "year": yf["name"]})

            if all_events:
                disp_names   = [e["display"] for e in all_events]
                active_event = nav[1].get("display") if len(nav) >= 2 else None
                st.markdown("**אירוע**")
                ev_result = pill_row(disp_names, active_event, "ev", n_cols=4,
                                     all_label="כל האירועים")
                if ev_result != "NO_CHANGE":
                    if ev_result is None:
                        st.session_state.nav_stack = [nav[0]]
                    else:
                        matched_ev = next((e for e in all_events
                                           if e["display"] == ev_result), None)
                        if matched_ev:
                            st.session_state.nav_stack = [
                                nav[0],
                                {"id": matched_ev["id"], "name": matched_ev["name"],
                                 "display": matched_ev["display"], "year": matched_ev["year"]},
                            ]
                    st.session_state.page = 0
                    st.rerun()
    else:
        # Level 1 — folders directly under category
        active_l1 = nav[0]["name"] if nav else None
        if cat_folders:
            folder_names = [f["name"] for f in cat_folders]
            st.markdown("**תיקייה**")
            ev_result = pill_row(folder_names, active_l1, "ev", n_cols=4, all_label="הכל")
            if ev_result != "NO_CHANGE":
                if ev_result is None:
                    st.session_state.nav_stack = []
                else:
                    fid = idx_find_folder(cat_folder_id, ev_result, idx)
                    st.session_state.nav_stack = [{"id": fid, "name": ev_result}] if fid else []
                st.session_state.page = 0
                st.rerun()

        # Level 2 — sub-folders inside selected folder (e.g. "צבא אייל" → "גיוס אייל")
        if nav:
            l2_folders = idx_subfolders(nav[0]["id"], idx)
            if l2_folders:
                l2_names   = [f["name"] for f in l2_folders]
                active_l2  = nav[1]["name"] if len(nav) >= 2 else None
                st.markdown("**תת-תיקייה**")
                l2_result = pill_row(l2_names, active_l2, "l2", n_cols=4, all_label="הכל")
                if l2_result != "NO_CHANGE":
                    if l2_result is None:
                        st.session_state.nav_stack = [nav[0]]
                    else:
                        l2id = idx_find_folder(nav[0]["id"], l2_result, idx)
                        if l2id:
                            st.session_state.nav_stack = [nav[0], {"id": l2id, "name": l2_result}]
                    st.session_state.page = 0
                    st.rerun()

    nav       = st.session_state.nav_stack
    nav_depth = len(nav)


# ── Resolve display folder ────────────────────────────────────────────────────

if st.session_state.search_q:
    results = idx_search(st.session_state.search_q, ROOT_ID, idx)
    if not results:
        st.info("לא נמצאו תיקיות")
        st.stop()

    back_col, title_col = st.columns([1, 5])
    with back_col:
        if st.button("← חזרה לניווט", type="secondary"):
            st.session_state.search_q      = ""
            st.session_state.search_chosen = ""
            st.rerun()
    with title_col:
        st.markdown(f"**{len(results)} תוצאות עבור \"{st.session_state.search_q}\"**")

    result_ids = [r["id"] for r in results]
    chosen_id  = st.session_state.get("search_chosen") or result_ids[0]
    if chosen_id not in result_ids:
        chosen_id = result_ids[0]

    cols = st.columns(4)
    for i, r in enumerate(results):
        is_active = (r["id"] == chosen_id)
        with cols[i % 4]:
            if st.button(r["path"], key=f"sr_{i}",
                         type="primary" if is_active else "secondary",
                         use_container_width=True):
                st.session_state["search_chosen"] = r["id"]
                st.rerun()

    display_folder_id = chosen_id
    chosen_result     = next((r for r in results if r["id"] == chosen_id), results[0])
    breadcrumb        = chosen_result["path"].replace(" / ", " › ")

else:
    # When a group is selected but no specific event — display_folder_id is virtual
    if nav and nav[-1].get("id") == "__group__":
        display_folder_id = "__group__"
    else:
        display_folder_id = nav[-1]["id"] if nav else cat_folder_id

    # Breadcrumb: use "display" name if available (includes year prefix)
    breadcrumb_parts = [selected_cat] + [n.get("display", n["name"]) for n in nav]
    breadcrumb       = " › ".join(breadcrumb_parts)

if not display_folder_id:
    st.warning(f"לא נמצאה תיקייה: **{selected_cat}**")
    st.stop()

st.markdown(f'<div class="breadcrumb">📁 {breadcrumb}</div>', unsafe_allow_html=True)


# ── Load media (from index — instant) ────────────────────────────────────────

# Group selected but no event chosen → show hint
if display_folder_id == "__group__":
    st.info("👆 בחר אירוע כדי לראות תמונות")
    st.stop()

sub_folders = idx_subfolders(display_folder_id, idx)

# at_intermediate: show hint instead of media when sub-folders exist but none selected
if not st.session_state.search_q:
    if with_years:
        # year categories: intermediate at cat root OR year selected (no event yet)
        at_intermediate = bool(sub_folders) and (
            nav_depth == 0 or (nav_depth == 1 and nav[0].get("id") != "__group__")
        )
    else:
        # non-year categories: intermediate at cat root OR event selected (no sub-folder yet)
        at_intermediate = bool(sub_folders) and nav_depth <= 1
else:
    at_intermediate = False

if at_intermediate:
    images, videos = idx_media(display_folder_id, idx)
else:
    images, videos = idx_media_recursive(display_folder_id, idx)

total = len(images) + len(videos)

if total == 0:
    if at_intermediate:
        st.info("👆 בחר אירוע כדי לראות תמונות")
    else:
        st.info("אין קבצי מדיה בתיקייה זו")
    st.stop()


# ── Filter buttons ────────────────────────────────────────────────────────────

f = st.session_state.media_filter
fc1, fc2, fc3, _ = st.columns([1, 1, 1, 5])
with fc1:
    if st.button(f"🖼️ {len(images)} תמונות",
                 type="primary" if f == "images" else "secondary",
                 use_container_width=True):
        st.session_state.media_filter = "all" if f == "images" else "images"
        st.session_state.page = 0
        st.rerun()
with fc2:
    if videos:
        if st.button(f"🎬 {len(videos)} סרטונים",
                     type="primary" if f == "videos" else "secondary",
                     use_container_width=True):
            st.session_state.media_filter = "all" if f == "videos" else "videos"
            st.session_state.page = 0
            st.rerun()
with fc3:
    if f != "all":
        if st.button("✕ הצג הכל", type="secondary"):
            st.session_state.media_filter = "all"
            st.session_state.page = 0
            st.rerun()

st.divider()

cur_filter = st.session_state.media_filter
if cur_filter == "images":
    filtered = images
elif cur_filter == "videos":
    filtered = videos
else:
    filtered = images + videos

# Reset page when folder changes
nav_key = display_folder_id + cur_filter
if st.session_state.get("_last_path") != nav_key:
    st.session_state.page      = 0
    st.session_state.modal_img = None
    st.session_state.media_filter = "all"
    st.session_state["_last_path"] = nav_key
    cur_filter = "all"
    filtered   = images + videos

page    = st.session_state.page
n_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)
start   = page * PAGE_SIZE
page_media  = filtered[start : start + PAGE_SIZE]
page_images = [f for f in page_media if f.get("mimeType") in IMG_MIME]
page_videos = [f for f in page_media if f.get("mimeType") in VID_MIME]


COLS = 5
if page_images:
    rows = [page_images[i : i + COLS] for i in range(0, len(page_images), COLS)]
    for row_i, row in enumerate(rows):
        cols = st.columns(COLS)
        for col_i, (col, file) in enumerate(zip(cols, row)):
            with col:
                thumb_path = os.path.join(THUMB_DIR, f"{file['id']}.jpg")
                shown = False
                if os.path.exists(thumb_path):
                    try:
                        with open(thumb_path, "rb") as tf:
                            st.image(tf.read(), use_container_width=True)
                        shown = True
                    except Exception:
                        pass   # fall through to API
                if not shown:
                    try:
                        data = get_thumbnail_bytes(file["id"])
                        if data:
                            st.image(data, use_container_width=True)
                            shown = True
                    except Exception:
                        pass
                if not shown:
                    st.markdown(
                        '<div style="width:100%;aspect-ratio:1;background:#f3f4f6;'
                        'border-radius:6px;display:flex;align-items:center;'
                        'justify-content:center;font-size:28px;color:#9ca3af;">📷</div>',
                        unsafe_allow_html=True,
                    )
                if st.button("​", key=f"zoom_{file['id']}", help=file["name"],
                             use_container_width=True):
                    st.session_state.modal_img = file

if page_videos:
    st.markdown("#### 🎬 סרטונים")
    vcols = st.columns(min(3, len(page_videos)))
    for i, vid in enumerate(page_videos):
        with vcols[i % 3]:
            st.markdown(
                f'<a href="{drive_view_url(vid["id"])}" target="_blank" '
                f'style="display:block;background:#f3f4f6;padding:20px 8px;'
                f'border-radius:8px;text-decoration:none;color:#374151;'
                f'text-align:center;font-size:13px;">'
                f'▶️<br><small>{vid["name"]}</small></a>',
                unsafe_allow_html=True,
            )


# ── Pagination ────────────────────────────────────────────────────────────────

st.divider()
p1, p2, p3 = st.columns([1, 3, 1])
with p1:
    if page > 0:
        if st.button("→ הקודם"):
            st.session_state.page -= 1
            st.rerun()
with p2:
    st.markdown(
        f'<div class="pager">עמוד {page + 1} מתוך {n_pages} &nbsp;|&nbsp; {total} קבצים</div>',
        unsafe_allow_html=True,
    )
with p3:
    if page < n_pages - 1:
        if st.button("הבא ←"):
            st.session_state.page += 1
            st.rerun()


# ── Modal ─────────────────────────────────────────────────────────────────────

if st.session_state.modal_img:
    image_modal(st.session_state.modal_img)
