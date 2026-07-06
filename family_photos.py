#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Family Photos Dashboard — Google Drive edition
Run locally:  streamlit run ~/projects/family_photos.py
Deployed at:  https://share.streamlit.io
"""

import streamlit as st
from drive_api import (
    list_folders,
    list_media,
    list_media_recursive,
    get_folder_id,
    search_drive_folders,
    thumb_url,
    modal_url,
    drive_view_url,
    IMG_MIME,
    VID_MIME,
)

# ── Config ────────────────────────────────────────────────────────────────────

ROOT_ID = st.secrets["DRIVE_ROOT_FOLDER_ID"]

CATEGORIES = [
    ("משפחה - חיי יום יום", "👨‍👩‍👧‍👦"),
    ("אירועים משפחתיים", "🎉"),
    ("טיולים", "✈️"),
    ("תמונות סרוקות", "🗃️"),
    ("תמונות לא ממויינות", "📋"),
    ("אוכל", "🍽️"),
    ("ג׳וי", "🐕"),
]
CAT_NAMES  = [c[0] for c in CATEGORIES]

PAGE_SIZE = 48


# ── Helpers ───────────────────────────────────────────────────────────────────

def has_year_structure(folders):
    """True if ≥50% of folder names are 4-digit years."""
    if not folders:
        return False
    year_like = sum(1 for f in folders if f["name"].isdigit() and len(f["name"]) == 4)
    return year_like / len(folders) >= 0.5


# ── Page setup ────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="תמונות משפחה",
    page_icon="📸",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  /* RTL */
  html, body, [class*="css"]  { direction: rtl; }
  /* push content below Streamlit toolbar */
  .block-container             { padding-top: 3.5rem; padding-bottom: 2rem; }
  /* hide Streamlit's own header/toolbar */
  header[data-testid="stHeader"] { display: none; }

  /* Header bar */
  .nav-bar {
    display: flex;
    align-items: center;
    gap: 12px;
    flex-wrap: wrap;
    background: #ffffff;
    border-bottom: 2px solid #e5e7eb;
    padding: 10px 0 12px 0;
    margin-bottom: 16px;
  }
  .nav-title {
    font-size: 22px;
    font-weight: 700;
    color: #1f2937;
    white-space: nowrap;
    margin-left: 8px;
  }

  /* Breadcrumb */
  .breadcrumb {
    font-size: 13px;
    color: #6b7280;
    margin-bottom: 4px;
  }

  /* Stat pills */
  .pill {
    display: inline-block;
    background: #f3f4f6;
    border-radius: 999px;
    padding: 2px 12px;
    font-size: 13px;
    color: #374151;
    margin-left: 6px;
  }

  /* All buttons base */
  div[data-testid="stButton"] > button {
    border-radius: 20px;
    font-size: 13px;
    padding: 5px 14px;
    width: 100%;
    transition: all 0.15s ease;
  }
  /* Sub-folder buttons (secondary style) */
  div[data-testid="stButton"] > button[kind="secondary"] {
    background: #f9fafb;
    border: 1px solid #e5e7eb;
    color: #374151;
    text-align: right;
    border-radius: 8px;
  }
  div[data-testid="stButton"] > button[kind="secondary"]:hover {
    background: #eff6ff;
    border-color: #93c5fd;
    color: #1d4ed8;
  }
  /* Category pill active (primary) */
  div[data-testid="stButton"] > button[kind="primary"] {
    background: #2563eb;
    border: none;
    color: white;
    font-weight: 600;
  }
  /* Category pill inactive */
  div[data-testid="stButton"] > button[kind="secondaryFormSubmit"],
  div[data-testid="stButton"] > button:not([kind="primary"]):not([kind="secondary"]) {
    background: #f3f4f6;
    border: 1px solid #e5e7eb;
    color: #374151;
  }

  /* Image captions */
  .stImage p { font-size: 11px; color: #9ca3af; text-align: center; }

  /* Pagination */
  .pager { text-align: center; color: #6b7280; font-size: 13px; padding-top: 4px; }

  /* Hide default sidebar toggle in collapsed state */
  section[data-testid="stSidebar"] { display: none; }

  /* Hide built-in X on dialog — we use our own close button */
  [data-testid="stDialog"] button[data-testid="stBaseButton-headerNoPadding"] { display: none !important; }
</style>
""", unsafe_allow_html=True)


# ── Session state defaults ────────────────────────────────────────────────────

def ss(key, default):
    if key not in st.session_state:
        st.session_state[key] = default

ss("cat_idx",      0)
ss("search_q",     "")
ss("page",         0)
# nav_stack: list of {"id": str, "name": str} — full path from category root
ss("nav_stack",    [])
ss("modal_img",    None)   # Drive file_id string
ss("media_filter", "all")  # "all" | "images" | "videos"


# ── Image modal (defined here, called at end of script) ───────────────────────

@st.dialog("📷 תמונה", width="large")
def image_modal(file_id):
    st.image(modal_url(file_id))
    if st.button("✕ סגור", use_container_width=True):
        st.session_state.modal_img = None
        st.rerun()


# ── Navigation header ─────────────────────────────────────────────────────────

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

# Search bar — own row, clearly visible
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

# Category pills — row of 4, then row of 3 (centered with spacers)
ROW1 = CATEGORIES[:4]
ROW2 = CATEGORIES[4:]

cols1 = st.columns(4)
for col, (name, icon) in zip(cols1, ROW1):
    idx = CAT_NAMES.index(name)
    is_active = (idx == st.session_state.cat_idx)
    with col:
        if st.button(f"{icon}  {name}", key=f"cat_{idx}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            if not is_active:
                st.session_state.cat_idx  = idx
                st.session_state.nav_stack = []
                st.session_state.page     = 0
                st.rerun()

_, c1, c2, c3, _ = st.columns([1, 2, 2, 2, 1])
for col, (name, icon) in zip((c1, c2, c3), ROW2):
    idx = CAT_NAMES.index(name)
    is_active = (idx == st.session_state.cat_idx)
    with col:
        if st.button(f"{icon}  {name}", key=f"cat_{idx}",
                     type="primary" if is_active else "secondary",
                     use_container_width=True):
            if not is_active:
                st.session_state.cat_idx  = idx
                st.session_state.nav_stack = []
                st.session_state.page     = 0
                st.rerun()

st.markdown('<hr style="margin:8px 0 12px 0;border:none;border-top:2px solid #e5e7eb;">', unsafe_allow_html=True)


# ── Pill selector helper ──────────────────────────────────────────────────────

def pill_row(options, selected, key_prefix, n_cols, all_label="הכל"):
    """
    Render options as pill buttons.
    selected: currently selected value, or None for "all".
    Returns the newly selected value (None = all), or sentinel 'NO_CHANGE'.
    """
    all_options = [all_label] + options
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
                if st.button(
                    opt,
                    key=f"{key_prefix}_{opt}",
                    type="primary" if is_active else "secondary",
                    use_container_width=True,
                ):
                    result = None if opt == all_label else opt
    return result


# ── Fetch category data ───────────────────────────────────────────────────────

selected_cat  = CAT_NAMES[st.session_state.cat_idx]
cat_folder_id = get_folder_id(ROOT_ID, selected_cat)
cat_folders   = list_folders(cat_folder_id) if cat_folder_id else []
with_years    = has_year_structure(cat_folders)

nav = st.session_state.nav_stack  # shorthand (list of {"id", "name"})


# ── Year / Event pill navigation (always visible unless in search mode) ───────

if not st.session_state.search_q:
    if with_years:
        year_names   = [f["name"] for f in cat_folders]
        year_display = ["📦" if y == "9999" else y for y in year_names]
        active_year  = nav[0]["name"] if nav else None

        st.markdown("**שנה**")
        yr_result = pill_row(year_display, active_year, "yr", n_cols=10, all_label="כל השנים")
        if yr_result != "NO_CHANGE":
            if yr_result == "כל השנים":
                st.session_state.nav_stack = []
            else:
                actual = year_names[year_display.index(yr_result)]
                yid    = get_folder_id(cat_folder_id, actual)
                st.session_state.nav_stack = [{"id": yid, "name": actual}] if yid else []
            st.session_state.page = 0
            st.rerun()

        # Event pills — shown only when a year is selected
        if nav:
            year_folder_id = nav[0]["id"]
            event_folders  = list_folders(year_folder_id)
            if event_folders:
                event_names  = [f["name"] for f in event_folders]
                active_event = nav[1]["name"] if len(nav) >= 2 else None
                st.markdown("**אירוע**")
                ev_result = pill_row(event_names, active_event, "ev", n_cols=4, all_label="כל האירועים")
                if ev_result != "NO_CHANGE":
                    if ev_result == "כל האירועים":
                        st.session_state.nav_stack = [nav[0]]
                    else:
                        eid = get_folder_id(year_folder_id, ev_result)
                        if eid:
                            st.session_state.nav_stack = [nav[0], {"id": eid, "name": ev_result}]
                    st.session_state.page = 0
                    st.rerun()

    else:
        active_folder = nav[0]["name"] if nav else None
        if cat_folders:
            folder_names = [f["name"] for f in cat_folders]
            st.markdown("**תיקייה**")
            ev_result = pill_row(folder_names, active_folder, "ev", n_cols=4, all_label="הכל")
            if ev_result != "NO_CHANGE":
                if ev_result == "הכל":
                    st.session_state.nav_stack = []
                else:
                    fid = get_folder_id(cat_folder_id, ev_result)
                    st.session_state.nav_stack = [{"id": fid, "name": ev_result}] if fid else []
                st.session_state.page = 0
                st.rerun()

    # Re-read nav after possible rerun
    nav = st.session_state.nav_stack


# ── Resolve display folder ────────────────────────────────────────────────────

if st.session_state.search_q:
    results = search_drive_folders(st.session_state.search_q, ROOT_ID)
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
    display_folder_id = nav[-1]["id"] if nav else cat_folder_id
    breadcrumb_parts  = [selected_cat] + [n["name"] for n in nav]
    breadcrumb        = " › ".join(breadcrumb_parts)

# Guard: if the category folder couldn't be found in Drive
if not display_folder_id:
    st.warning(f"לא נמצאה תיקייה בגוגל דרייב: **{selected_cat}**")
    st.stop()

# Breadcrumb + back button
bc_col, back_col = st.columns([8, 1])
with bc_col:
    st.markdown(f'<div class="breadcrumb">📁 {breadcrumb}</div>', unsafe_allow_html=True)
with back_col:
    if nav:
        if st.button("⬆️ חזור"):
            st.session_state.nav_stack = nav[:-1]
            st.session_state.page = 0
            st.rerun()


# ── Sub-folder navigation ─────────────────────────────────────────────────────

sub_folders = list_folders(display_folder_id)
if sub_folders:
    with st.expander(f"📂 תת-תיקיות ({len(sub_folders)})", expanded=len(sub_folders) <= 10):
        cols = st.columns(min(5, len(sub_folders)))
        for i, folder in enumerate(sub_folders):
            imgs_sub, vids_sub = list_media(folder["id"])
            count = len(imgs_sub) + len(vids_sub)
            with cols[i % 5]:
                if st.button(f"📁 {folder['name']}  ({count})", key=f"sub_{folder['id']}"):
                    st.session_state.nav_stack = nav + [{"id": folder["id"], "name": folder["name"]}]
                    st.session_state.page = 0
                    st.rerun()


# ── Load media ────────────────────────────────────────────────────────────────

images, videos = list_media_recursive(display_folder_id)
total = len(images) + len(videos)

if total == 0:
    st.info("אין קבצי מדיה בתיקייה זו")
    st.stop()

# Filter buttons (act as stat pills + toggle)
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

# Apply filter
cur_filter = st.session_state.media_filter
if cur_filter == "images":
    filtered = images
elif cur_filter == "videos":
    filtered = videos
else:
    filtered = images + videos

# Reset page + clear modal when folder or filter changes
nav_key = display_folder_id + cur_filter
if st.session_state.get("_last_path") != nav_key:
    st.session_state.page      = 0
    st.session_state.modal_img = None
    st.session_state["_last_path"] = nav_key

page    = st.session_state.page
start   = page * PAGE_SIZE
n_pages = max(1, (len(filtered) + PAGE_SIZE - 1) // PAGE_SIZE)

page_media  = filtered[start : start + PAGE_SIZE]
page_images = [f for f in page_media if f.get("mimeType") in IMG_MIME]
page_videos = [f for f in page_media if f.get("mimeType") in VID_MIME]


# ── Thumbnail grid ────────────────────────────────────────────────────────────

COLS = 5
if page_images:
    rows = [page_images[i : i + COLS] for i in range(0, len(page_images), COLS)]
    for row in rows:
        cols = st.columns(COLS)
        for col, file in zip(cols, row):
            with col:
                st.image(thumb_url(file["id"], 240))
                if st.button("🔍", key=f"zoom_{file['id']}", help=file["name"],
                             use_container_width=True):
                    st.session_state.modal_img = file["id"]

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


# ── Image modal — called last so first click suffices ─────────────────────────

if st.session_state.modal_img:
    image_modal(st.session_state.modal_img)
