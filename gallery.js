"use strict";

// ── Constants ─────────────────────────────────────────────────────────────────
const IMG_MIME = new Set([
  "image/jpeg","image/jpg","image/png","image/heic","image/heif",
  "image/webp","image/gif","image/bmp","image/tiff",
]);
const VID_MIME = new Set([
  "video/mp4","video/quicktime","video/x-msvideo",
  "video/x-matroska","video/mpeg","video/3gpp",
]);
const AUD_MIME = new Set([
  "audio/mpeg","audio/mp3","audio/mp4","audio/m4a","audio/x-m4a",
  "audio/wav","audio/wave","audio/ogg","audio/aac","audio/flac",
  "audio/x-flac","audio/webm","audio/3gpp",
]);
const PAGE_SIZE = 40;
const COLS      = 4;

const CATEGORIES = [
  { name: "משפחה - לפי שנים",  icon: "👨‍👩‍👧‍👦" },
  { name: "אירועים משפחתיים",  icon: "🎉"  },
  { name: "משפחה בן עזרא",     icon: "🌳"  },
  { name: "תמונות סרוקות",      icon: "🗃️"  },
  { name: "ג׳וי",               icon: "🐕"  },
];

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' " +
  "width='120' height='120'%3E%3Crect fill='%23e5e7eb' width='120' height='120'/%3E" +
  "%3Ctext x='50%25' y='55%25' dominant-baseline='middle' text-anchor='middle' " +
  "font-size='36' fill='%239ca3af'%3E%F0%9F%93%B7%3C/text%3E%3C/svg%3E";

// ── State ─────────────────────────────────────────────────────────────────────
let IDX = null;

const S = {
  catIdx:       0,        // CATEGORIES index
  period:       null,     // { label, yearIds: [id,...] } — 5-year group, or null="all"
  eventId:      null,     // folder id of chosen event/sub-folder, or null="all"
  subFolderId:  null,     // 2nd-level sub-folder id for non-year cats
  page:         0,
  search:       "",
  searchChosen: null,
  modalFiles:   [],       // flat list of file ids currently in grid
  modalIdx:     0,
};

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  showLoading(true);
  try {
    IDX = await fetch("./static/index.json?v=21").then(r => r.json());
  } catch (e) {
    document.getElementById("grid").innerHTML =
      `<p class="empty-msg">שגיאה בטעינת index.json: ${e.message}</p>`;
    showLoading(false);
    return;
  }

  // Wire up static controls
  document.getElementById("btn-home").onclick = goHome;
  document.getElementById("search").addEventListener("input", onSearch);
  setupModal();
  setupKeyboard();

  selectCat(0, true);
  showLoading(false);
}

function showLoading(on) {
  document.getElementById("loading").hidden = !on;
}

// ── Index helpers ─────────────────────────────────────────────────────────────
function subfolders(fid) {
  const f = IDX.folders[fid];
  return (f?.folders || [])
    .map(id => ({ id, name: IDX.folders[id]?.name || "" }))
    .filter(x => x.name && collectMedia(x.id).length > 0);  // מסנן תיקיות ריקות
}

function collectMedia(fid, out = []) {
  const f = IDX.folders[fid];
  if (!f) return out;
  for (const fileId of (f.files || [])) {
    const file = IDX.files[fileId];
    if (file && (IMG_MIME.has(file.mime) || VID_MIME.has(file.mime) || AUD_MIME.has(file.mime))) out.push(fileId);
  }
  for (const subId of (f.folders || [])) collectMedia(subId, out);
  return out;
}
// Keep alias for callers
const collectImages = collectMedia;

function isVideo(fid) {
  return VID_MIME.has(IDX.files[fid]?.mime);
}
function isAudio(fid) {
  return AUD_MIME.has(IDX.files[fid]?.mime);
}

function hasYearStructure(subs) {
  if (!subs.length) return false;
  const yearLike = subs.filter(s => /^\d{4}$/.test(s.name)).length;
  return yearLike / subs.length >= 0.5;
}

// Custom year ranges — tailored to where the family content actually lives
const YEAR_GROUPS = [
  { label: "98–2004",   start: 1998, end: 2004 },
  { label: "2005–2006", start: 2005, end: 2006 },
  { label: "2007–2008", start: 2007, end: 2008 },
  { label: "2009–2010", start: 2009, end: 2010 },
  { label: "2011–2016", start: 2011, end: 2016 },
  { label: "2017–2026", start: 2017, end: 2026 },
];

function groupBy5Years(subs) {
  const real = subs.filter(s => /^\d{4}$/.test(s.name));
  real.sort((a, b) => +a.name - +b.name);
  const result = [];
  for (const g of YEAR_GROUPS) {
    const items = real.filter(s => +s.name >= g.start && +s.name <= g.end);
    if (items.length) result.push({ label: g.label, yearFolders: items });
  }
  return result;
}

function findCatId(catName) {
  const root = IDX.folders[IDX.root];
  for (const cid of (root?.folders || [])) {
    if (IDX.folders[cid]?.name === catName) return cid;
  }
  return null;
}

// ── Navigation ────────────────────────────────────────────────────────────────
function goHome() {
  S.search        = "";
  S.searchChosen  = null;
  document.getElementById("search").value = "";
  selectCat(S.catIdx, true);
}

function selectCat(idx, reset = false) {
  S.catIdx = idx;
  if (reset) {
    S.period      = null;
    S.eventId     = null;
    S.subFolderId = null;
    S.page        = 0;
    S.search      = "";
    S.searchChosen= null;
    document.getElementById("search").value = "";
  }

  const catId = findCatId(CATEGORIES[idx].name);
  if (!catId) { render(); return; }

  const subs = subfolders(catId);
  if (hasYearStructure(subs) && reset) {
    // Auto-select most-recent period
    const groups = groupBy5Years(subs);
    if (groups.length) {
      S.period  = groups[groups.length - 1];
      S.eventId = null;
    }
  }
  render();
}

// ── Search ────────────────────────────────────────────────────────────────────
function onSearch() {
  S.search = document.getElementById("search").value.trim();
  S.searchChosen = null;
  S.page = 0;
  render();
}

function searchFolders(q) {
  const ql = q.toLowerCase();
  const results = [];
  const root = IDX.folders[IDX.root];
  for (const catId of (root?.folders || [])) {
    const catName = IDX.folders[catId]?.name || "";
    for (const s1Id of (IDX.folders[catId]?.folders || [])) {
      const s1Name = IDX.folders[s1Id]?.name || "";
      if (ql && s1Name.toLowerCase().includes(ql))
        results.push({ id: s1Id, path: `${catName} › ${s1Name}` });
      for (const s2Id of (IDX.folders[s1Id]?.folders || [])) {
        const s2Name = IDX.folders[s2Id]?.name || "";
        if (ql && s2Name.toLowerCase().includes(ql))
          results.push({ id: s2Id, path: `${catName} › ${s1Name} › ${s2Name}` });
      }
    }
  }
  return results.sort((a, b) => a.path.localeCompare(b.path, "he"));
}

// ── Main render ───────────────────────────────────────────────────────────────
function render() {
  renderCatNav();

  if (S.search) {
    renderSearch();
    return;
  }

  const catId = findCatId(CATEGORIES[S.catIdx].name);
  if (!catId) {
    document.getElementById("sub-nav").innerHTML = "";
    renderHint("לא נמצאה קטגוריה");
    return;
  }

  const subs = subfolders(catId);
  const isYear = hasYearStructure(subs);

  renderSubNav(catId, subs, isYear);
  renderContent(catId, subs, isYear);
}

// ── Category pills ────────────────────────────────────────────────────────────
function renderCatNav() {
  const nav  = document.getElementById("cat-nav");
  const row1 = document.createElement("div"); row1.className = "pill-row";
  const row2 = document.createElement("div"); row2.className = "pill-row";

  CATEGORIES.forEach((cat, i) => {
    const btn = document.createElement("button");
    btn.className = (i === S.catIdx ? "btn btn-primary" : "btn btn-secondary") + " cat-btn";
    btn.innerHTML = `<span class="cat-icon">${cat.icon}</span><span class="cat-label">${cat.name}</span>`;
    btn.onclick = () => { selectCat(i, true); };
    (i < 4 ? row1 : row2).appendChild(btn);
  });

  nav.innerHTML = "";
  nav.appendChild(row1);
  nav.appendChild(row2);
}

// ── Sub-nav ───────────────────────────────────────────────────────────────────
function renderSubNav(catId, subs, isYear) {
  const nav = document.getElementById("sub-nav");
  nav.innerHTML = "";

  if (isYear) {
    const groups = groupBy5Years(subs);

    // Period row
    const pLabel = document.createElement("div"); pLabel.className = "sub-nav-label";
    pLabel.textContent = "תקופה";
    const pRow = document.createElement("div"); pRow.className = "pill-row";

    // "הכל" pill
    const allBtn = mkBtn("הכל", S.period === null);
    allBtn.onclick = () => { S.period = null; S.eventId = null; S.page = 0; render(); };
    pRow.appendChild(allBtn);

    for (const g of groups) {
      const active = S.period?.label === g.label;
      const btn = mkBtn(g.label, active);
      btn.onclick = () => {
        S.period  = g;
        S.eventId = null;
        S.page    = 0;
        render();
      };
      pRow.appendChild(btn);
    }
    nav.appendChild(pLabel);
    nav.appendChild(pRow);

    // Event row (when period chosen)
    if (S.period) {
      // Collect all sub-events from all year-folders in this period
      const events = [];
      for (const yf of S.period.yearFolders) {
        const evSubs = subfolders(yf.id);
        if (evSubs.length) {
          for (const ev of evSubs)
            events.push({ id: ev.id, display: `${yf.name} | ${ev.name}`, year: yf.name });
        } else {
          // Year folder has no sub-events → treat the year itself as clickable
          events.push({ id: yf.id, display: yf.name, year: yf.name });
        }
      }

      if (events.length) {
        const eLabel = document.createElement("div"); eLabel.className = "sub-nav-label";
        eLabel.textContent = "אירוע";
        const eRow = document.createElement("div"); eRow.className = "pill-row";

        const allEv = mkBtn("כל האירועים", S.eventId === null);
        allEv.onclick = () => { S.eventId = null; S.page = 0; render(); };
        eRow.appendChild(allEv);

        for (const ev of events) {
          const active = S.eventId === ev.id;
          const btn = mkBtn(ev.display, active);
          btn.onclick = () => { S.eventId = ev.id; S.page = 0; render(); };
          eRow.appendChild(btn);
        }
        nav.appendChild(eLabel);
        nav.appendChild(eRow);
      }
    }

  } else {
    // Non-year cat — level 1 folders
    if (subs.length) {
      const lbl = document.createElement("div"); lbl.className = "sub-nav-label";
      lbl.textContent = "תיקייה";
      const row = document.createElement("div"); row.className = "pill-row";

      const allBtn = mkBtn("הכל", S.eventId === null);
      allBtn.onclick = () => { S.eventId = null; S.subFolderId = null; S.page = 0; render(); };
      row.appendChild(allBtn);

      for (const s of subs) {
        const active = S.eventId === s.id;
        const btn = mkBtn(s.name, active);
        btn.onclick = () => { S.eventId = s.id; S.subFolderId = null; S.page = 0; render(); };
        row.appendChild(btn);
      }
      nav.appendChild(lbl);
      nav.appendChild(row);
    }

    // Level 2 sub-folders (when folder chosen)
    if (S.eventId) {
      const sub2 = subfolders(S.eventId);
      if (sub2.length) {
        const lbl2 = document.createElement("div"); lbl2.className = "sub-nav-label";
        lbl2.textContent = "תת-תיקייה";
        const row2 = document.createElement("div"); row2.className = "pill-row";

        const allBtn2 = mkBtn("הכל", S.subFolderId === null);
        allBtn2.onclick = () => { S.subFolderId = null; S.page = 0; render(); };
        row2.appendChild(allBtn2);

        for (const s of sub2) {
          const active = S.subFolderId === s.id;
          const btn = mkBtn(s.name, active);
          btn.onclick = () => { S.subFolderId = s.id; S.page = 0; render(); };
          row2.appendChild(btn);
        }
        nav.appendChild(lbl2);
        nav.appendChild(row2);
      }
    }
  }
}

// ── Content area ──────────────────────────────────────────────────────────────
function renderContent(catId, subs, isYear) {
  let breadParts = [CATEGORIES[S.catIdx].name];
  let fileIds    = [];
  let showHint   = false;
  let groupedByYear = null;  // [{year, ids}] when showing multiple years

  if (isYear) {
    if (!S.period) {
      // No period chosen → collect everything (or show hint for large cats)
      const total = collectImages(catId).length;
      if (total > 500) { showHint = true; }
      else { fileIds = collectImages(catId); }
    } else {
      breadParts.push(S.period.label);
      if (S.eventId) {
        // Specific event chosen
        const evName = IDX.folders[S.eventId]?.name || "";
        breadParts.push(evName);
        fileIds = collectImages(S.eventId);
      } else {
        // All events in period — group by year for display
        groupedByYear = [];
        for (const yf of S.period.yearFolders) {
          const ids = collectImages(yf.id);
          if (ids.length) groupedByYear.push({ year: yf.name, ids });
        }
        fileIds = groupedByYear.flatMap(g => g.ids);
      }
    }
  } else {
    const targetId = S.subFolderId || S.eventId || catId;
    if (S.eventId) {
      breadParts.push(IDX.folders[S.eventId]?.name || "");
      if (S.subFolderId) breadParts.push(IDX.folders[S.subFolderId]?.name || "");
    }
    fileIds = collectImages(targetId);
  }

  renderBreadcrumb(breadParts);

  if (showHint) {
    document.getElementById("photo-count").textContent = "";
    renderHint("👆 בחר תקופה כדי לראות תמונות");
    renderPagination(0, 0);
    return;
  }

  // Sort: images first, then videos, then audio — within each year group
  const mediaRank = fid => isAudio(fid) ? 2 : isVideo(fid) ? 1 : 0;
  if (groupedByYear) {
    // Sort within each year (keeps year order intact, moves media to end of each year)
    groupedByYear.forEach(g => g.ids.sort((a, b) => mediaRank(a) - mediaRank(b)));
    fileIds = groupedByYear.flatMap(g => g.ids);   // rebuild flat list from sorted groups
  } else {
    fileIds.sort((a, b) => mediaRank(a) - mediaRank(b));
  }

  const mediaCount = fileIds.length;
  const audCount   = fileIds.filter(isAudio).length;
  const vidCount   = fileIds.filter(isVideo).length;
  const imgCount   = mediaCount - vidCount - audCount;
  let countParts   = [];
  if (imgCount)  countParts.push(`${imgCount} תמונות`);
  if (vidCount)  countParts.push(`${vidCount} סרטונים`);
  if (audCount)  countParts.push(`${audCount} הקלטות`);
  document.getElementById("photo-count").textContent = countParts.join(" · ") || "";

  // Paginate
  const nPages = Math.max(1, Math.ceil(fileIds.length / PAGE_SIZE));
  if (S.page >= nPages) S.page = nPages - 1;
  const start   = S.page * PAGE_SIZE;
  const pageIds = fileIds.slice(start, start + PAGE_SIZE);

  // Build modal file list
  S.modalFiles = fileIds;

  renderGrid(pageIds, groupedByYear, start);
  renderPagination(S.page, nPages);
}

// ── Search results ────────────────────────────────────────────────────────────
function renderSearch() {
  document.getElementById("sub-nav").innerHTML = "";
  document.getElementById("breadcrumb").innerHTML = "";

  const results = searchFolders(S.search);
  if (!results.length) {
    document.getElementById("photo-count").textContent = "";
    renderHint("לא נמצאו תיקיות");
    renderPagination(0, 0);
    return;
  }

  if (!S.searchChosen) S.searchChosen = results[0].id;

  // Render result pills
  const nav = document.getElementById("sub-nav");
  nav.innerHTML = "";
  const lbl = document.createElement("div"); lbl.className = "sub-nav-label";
  lbl.textContent = `${results.length} תוצאות עבור "${S.search}"`;
  const row = document.createElement("div"); row.className = "pill-row";
  for (const r of results) {
    const btn = mkBtn(r.path, S.searchChosen === r.id);
    btn.onclick = () => { S.searchChosen = r.id; S.page = 0; render(); };
    row.appendChild(btn);
  }
  nav.appendChild(lbl);
  nav.appendChild(row);

  const chosen = results.find(r => r.id === S.searchChosen) || results[0];
  S.searchChosen = chosen.id;
  renderBreadcrumb([chosen.path.replace(/ › /g, " › ")]);

  const fileIds = collectImages(chosen.id);
  document.getElementById("photo-count").textContent =
    fileIds.length ? `${fileIds.length} תמונות` : "";

  S.modalFiles = fileIds;
  const nPages  = Math.max(1, Math.ceil(fileIds.length / PAGE_SIZE));
  if (S.page >= nPages) S.page = nPages - 1;
  const pageIds = fileIds.slice(S.page * PAGE_SIZE, (S.page + 1) * PAGE_SIZE);

  renderGrid(pageIds, null, S.page * PAGE_SIZE);
  renderPagination(S.page, nPages);
}

// ── Breadcrumb ────────────────────────────────────────────────────────────────
function renderBreadcrumb(parts) {
  const bc = document.getElementById("breadcrumb");
  bc.innerHTML = "📁 " + parts.map((p, i) =>
    i < parts.length - 1
      ? `<span class="bc-cur">${p}</span><span class="bc-sep">›</span>`
      : `<span class="bc-cur">${p}</span>`
  ).join("");
}

// ── Grid ──────────────────────────────────────────────────────────────────────
function renderGrid(pageIds, groupedByYear, globalStart) {
  const grid = document.getElementById("grid");
  grid.innerHTML = "";

  if (!pageIds.length) {
    grid.innerHTML = '<p class="empty-msg">אין תמונות בתיקייה זו</p>';
    return;
  }

  const frag = document.createDocumentFragment();

  if (groupedByYear && !S.eventId) {
    // Show year dividers — but only for years that appear on this page
    const pageSet = new Set(pageIds);
    let renderedYearHeaders = new Set();

    // Find which year each file belongs to
    const fileYear = {};
    for (const { year, ids } of groupedByYear)
      for (const id of ids) fileYear[id] = year;

    for (let i = 0; i < pageIds.length; i++) {
      const fid  = pageIds[i];
      const year = fileYear[fid];
      if (year && !renderedYearHeaders.has(year)) {
        renderedYearHeaders.add(year);
        const hdr = document.createElement("div");
        hdr.className   = "year-header";
        hdr.textContent = year;
        frag.appendChild(hdr);
      }
      frag.appendChild(makeThumb(fid, globalStart + i));
    }
  } else {
    for (let i = 0; i < pageIds.length; i++)
      frag.appendChild(makeThumb(pageIds[i], globalStart + i));
  }

  grid.appendChild(frag);
}

function makeThumb(fid, globalIdx) {
  const file = IDX.files[fid];
  const vid  = isVideo(fid);
  const aud  = isAudio(fid);
  const wrap = document.createElement("div");
  wrap.className = "thumb-wrap";

  if (aud) {
    // Audio: show a styled card with music icon instead of image
    wrap.classList.add("thumb-audio");
    const icon = document.createElement("div");
    icon.className = "audio-card";
    icon.innerHTML = `<span class="audio-big-icon">🎵</span><span class="audio-name">${file?.name || ""}</span>`;
    wrap.appendChild(icon);
  } else {
    const img      = document.createElement("img");
    img.loading    = "lazy";
    img.decoding   = "async";
    img.src        = `https://drive.google.com/thumbnail?id=${fid}&sz=w400`;
    img.alt        = file?.name || "";
    img.title      = file?.name || "";
    img.onerror    = () => {
      if (!img.dataset.triedThumb) {
        img.dataset.triedThumb = "1";
        img.src = `./static/thumbs/${fid}.jpg`;  // fallback: local 120px
      } else {
        img.src = PLACEHOLDER_SVG;
        img.style.objectFit = "contain";
      }
    };
    wrap.appendChild(img);

    if (vid) {
      const icon = document.createElement("div");
      icon.className = "play-icon";
      icon.innerHTML = "▶";
      wrap.appendChild(icon);
    }
  }

  wrap.onclick = () => openModal(globalIdx);
  return wrap;
}

// ── Pagination ────────────────────────────────────────────────────────────────
function renderPagination(page, nPages) {
  const el = document.getElementById("pagination");
  if (nPages <= 1) { el.innerHTML = ""; return; }

  el.innerHTML = "";
  const prev = mkBtn("← הקודם", false);
  prev.disabled = page === 0;
  prev.onclick  = () => { S.page--; render(); window.scrollTo(0,0); };

  const info = document.createElement("span");
  info.id          = "pager-label";
  info.textContent = `עמוד ${page + 1} מתוך ${nPages}`;

  const next = mkBtn("הבא →", false);
  next.disabled = page >= nPages - 1;
  next.onclick  = () => { S.page++; render(); window.scrollTo(0,0); };

  el.appendChild(prev);
  el.appendChild(info);
  el.appendChild(next);
}

function renderHint(msg) {
  const grid = document.getElementById("grid");
  grid.innerHTML = `<p class="hint-msg">${msg}</p>`;
  document.getElementById("pagination").innerHTML = "";
}

// ── Button factory ─────────────────────────────────────────────────────────────
function mkBtn(label, active) {
  const btn = document.createElement("button");
  btn.className   = active ? "btn btn-primary" : "btn btn-secondary";
  btn.textContent = label;
  return btn;
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function setupModal() {
  document.getElementById("modal-bg").onclick    = closeModal;
  document.getElementById("modal-close").onclick = closeModal;
  document.getElementById("modal-prev").onclick  = () => stepModal(-1);
  document.getElementById("modal-next").onclick  = () => stepModal(+1);
}

function openModal(globalIdx) {
  S.modalIdx = globalIdx;
  showModalImage();
  document.getElementById("modal").hidden = false;
}

function showModalImage() {
  const fid  = S.modalFiles[S.modalIdx];
  if (!fid) return;
  const file = IDX.files[fid];
  const vid  = isVideo(fid);
  const aud  = isAudio(fid);

  const wrap = document.getElementById("modal-img-wrap");
  const mImg = document.getElementById("modal-img");
  const spin = document.getElementById("modal-spinner");

  // Clean up any previous media
  const oldIframe = wrap.querySelector("iframe");
  if (oldIframe) oldIframe.remove();
  const oldAudio = wrap.querySelector(".modal-audio-wrap");
  if (oldAudio) oldAudio.remove();
  mImg.style.display = "";
  spin.style.display = "none";

  if (vid || aud) {
    mImg.style.display = "none";
    const driveUrl  = `https://drive.google.com/file/d/${fid}/view`;
    const isIOS     = /iPhone|iPad|iPod/.test(navigator.userAgent);

    if (aud && isIOS) {
      // אודיו ב-iOS — כפתור פתיחה ב-Drive (iframe לא עובד ב-Safari PWA)
      const btn = document.createElement("a");
      btn.href      = driveUrl;
      btn.target    = "_blank";
      btn.rel       = "noopener";
      btn.className = "ios-audio-btn";
      btn.innerHTML = `<span style="font-size:48px">🎵</span><br>${file?.name || ""}<br><span style="font-size:14px;opacity:.8">הקש להאזנה ב-Drive ↗</span>`;
      wrap.appendChild(btn);
    } else {
      // וידאו / אודיו ב-desktop+Android — iframe של Drive
      const iframe = document.createElement("iframe");
      iframe.src             = `https://drive.google.com/file/d/${fid}/preview`;
      iframe.className       = aud ? "modal-audio-iframe" : "modal-video";
      iframe.allow           = "autoplay";
      iframe.allowFullscreen = true;
      iframe.setAttribute("allowfullscreen", "");
      const hint = document.createElement("div");
      hint.className = "media-fallback-hint";
      hint.innerHTML = `לא מתנגן? <a href="${driveUrl}" target="_blank" rel="noopener">פתח ב-Drive ↗</a>`;
      wrap.appendChild(iframe);
      wrap.appendChild(hint);
    }
  } else {
    // Show image
    mImg.style.opacity = "0";
    spin.style.display = "block";

    mImg.onload  = () => { mImg.style.opacity = "1"; spin.style.display = "none"; };
    mImg.onerror = () => {
      mImg.src = `./static/thumbs/${fid}.jpg`;  // fallback to local thumb
      spin.style.display = "none";
      mImg.style.opacity = "1";
    };
    mImg.src = `https://drive.google.com/thumbnail?id=${fid}&sz=w1200`;
  }

  document.getElementById("modal-name").textContent = file?.name || "";
  document.getElementById("modal-drive-link").href  =
    `https://drive.google.com/file/d/${fid}/view`;

  document.getElementById("modal-prev").disabled = S.modalIdx === 0;
  document.getElementById("modal-next").disabled = S.modalIdx >= S.modalFiles.length - 1;
}

function stepModal(delta) {
  const next = S.modalIdx + delta;
  if (next < 0 || next >= S.modalFiles.length) return;
  S.modalIdx = next;
  showModalImage();
}

function closeModal() {
  document.getElementById("modal").hidden = true;
  document.getElementById("modal-img").src = "";
  const wrap = document.getElementById("modal-img-wrap");
  wrap.querySelectorAll("iframe, .modal-audio-wrap, .media-fallback-hint").forEach(el => el.remove());
  document.getElementById("modal-img").style.display = "";
}

// ── Keyboard ──────────────────────────────────────────────────────────────────
function setupKeyboard() {
  document.addEventListener("keydown", e => {
    if (!document.getElementById("modal").hidden) {
      if (e.key === "Escape")      closeModal();
      if (e.key === "ArrowRight")  stepModal(-1);
      if (e.key === "ArrowLeft")   stepModal(+1);
    }
  });
}

// ── Start ─────────────────────────────────────────────────────────────────────
init();
