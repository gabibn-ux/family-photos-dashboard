"use strict";

// ── Constants ─────────────────────────────────────────────────────────────────
const IMG_MIME = new Set([
  "image/jpeg", "image/jpg", "image/png", "image/heic", "image/heif",
  "image/webp", "image/gif", "image/bmp", "image/tiff",
]);

const PLACEHOLDER_SVG =
  "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' " +
  "width='120' height='120'%3E%3Crect fill='%23e5e7eb' width='120' height='120'/%3E" +
  "%3Ctext x='50%25' y='55%25' dominant-baseline='middle' text-anchor='middle' " +
  "font-size='36' fill='%239ca3af'%3E%F0%9F%93%B7%3C/text%3E%3C/svg%3E";

// ── State ─────────────────────────────────────────────────────────────────────
let IDX        = null;   // index.json content
let curFolder  = null;   // currently shown folder id
let curFiles   = [];     // current grid file ids (images only)
let modalIdx   = 0;      // index into curFiles for modal

// ── Boot ──────────────────────────────────────────────────────────────────────
async function init() {
  showLoading(true);
  try {
    IDX = await fetch("./static/index.json").then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  } catch (e) {
    document.getElementById("grid").innerHTML =
      `<p class="error">שגיאה בטעינת index.json: ${e.message}</p>`;
    showLoading(false);
    return;
  }

  buildTree(IDX.root, document.getElementById("folder-tree"), 0);
  navigateTo(IDX.root);
  showLoading(false);
  setupSearch();
  setupModal();
  setupKeyboard();
}

// ── Loading ───────────────────────────────────────────────────────────────────
function showLoading(on) {
  document.getElementById("loading").hidden = !on;
}

// ── Folder Tree ───────────────────────────────────────────────────────────────
function buildTree(fid, container, depth) {
  const f = IDX.folders[fid];
  if (!f || depth > 8) return;

  const ul = document.createElement("ul");
  ul.className = "tree-list";

  for (const subId of (f.folders || [])) {
    const sub = IDX.folders[subId];
    if (!sub) continue;

    const li   = document.createElement("li");
    const row  = document.createElement("div");
    row.className = "tree-row";

    // Toggle arrow (only if has subfolders)
    if (sub.folders && sub.folders.length) {
      const tog = document.createElement("button");
      tog.className = "tree-toggle";
      tog.textContent = "▶";
      tog.setAttribute("aria-label", "פתח/סגור");
      row.appendChild(tog);

      const childWrap = document.createElement("div");
      childWrap.className = "tree-children collapsed";
      buildTree(subId, childWrap, depth + 1);

      tog.onclick = (e) => {
        e.stopPropagation();
        const collapsed = childWrap.classList.toggle("collapsed");
        tog.textContent = collapsed ? "▶" : "▼";
      };
      li.appendChild(row);
      li.appendChild(childWrap);
    } else {
      // leaf spacer
      const sp = document.createElement("span");
      sp.className = "tree-spacer";
      row.appendChild(sp);
      li.appendChild(row);
    }

    // Folder name button
    const btn = document.createElement("button");
    btn.className = "tree-btn";
    btn.textContent = sub.name;
    btn.dataset.fid = subId;
    btn.onclick = () => {
      navigateTo(subId);
      setActive(btn);
    };
    row.appendChild(btn);

    ul.appendChild(li);
  }

  container.appendChild(ul);
}

function setActive(btn) {
  document.querySelectorAll(".tree-btn.active")
    .forEach(b => b.classList.remove("active"));
  btn && btn.classList.add("active");
}

// ── Search ────────────────────────────────────────────────────────────────────
function setupSearch() {
  const input = document.getElementById("search");
  input.addEventListener("input", () => {
    const q = input.value.trim().toLowerCase();
    document.querySelectorAll(".tree-btn").forEach(btn => {
      const match = !q || btn.textContent.toLowerCase().includes(q);
      btn.closest("li").style.display = match ? "" : "none";
    });
    // Show all children when searching
    if (q) {
      document.querySelectorAll(".tree-children").forEach(c => c.classList.remove("collapsed"));
    }
  });
}

// ── Navigation ────────────────────────────────────────────────────────────────
function navigateTo(fid) {
  curFolder = fid;
  curFiles  = collectImages(fid);
  renderBreadcrumb(fid);
  renderGrid(curFiles);
  document.getElementById("photo-count").textContent =
    curFiles.length ? `${curFiles.length} תמונות` : "";
  window.scrollTo({ top: 0 });
}

function collectImages(fid, out = []) {
  const f = IDX.folders[fid];
  if (!f) return out;
  for (const fileId of (f.files || [])) {
    const file = IDX.files[fileId];
    if (file && IMG_MIME.has(file.mime)) out.push(fileId);
  }
  for (const subId of (f.folders || [])) collectImages(subId, out);
  return out;
}

// ── Breadcrumb ────────────────────────────────────────────────────────────────
function renderBreadcrumb(fid) {
  const path = [];
  let cur = fid;
  while (cur) {
    const f = IDX.folders[cur];
    if (!f) break;
    path.unshift({ id: cur, name: f.name });
    cur = f.parent;
  }
  // Skip the synthetic "root" entry in breadcrumb display
  const display = path.filter(p => IDX.folders[p.id]?.name !== "root");

  const bc = document.getElementById("breadcrumb");
  bc.innerHTML = display.map((p, i) =>
    i < display.length - 1
      ? `<button class="bc-btn" onclick="navigateTo('${p.id}')">${p.name}</button>
         <span class="bc-sep">›</span>`
      : `<span class="bc-cur">${p.name}</span>`
  ).join("");
}

// ── Grid ──────────────────────────────────────────────────────────────────────
function renderGrid(fileIds) {
  const grid = document.getElementById("grid");
  grid.innerHTML = "";

  if (!fileIds.length) {
    grid.innerHTML = '<p class="empty">אין תמונות בתיקייה זו</p>';
    return;
  }

  const frag = document.createDocumentFragment();
  fileIds.forEach((fid, idx) => {
    const file = IDX.files[fid];
    const wrap = document.createElement("div");
    wrap.className = "thumb-wrap";

    const img = document.createElement("img");
    img.loading  = "lazy";
    img.decoding = "async";
    img.src      = `./static/thumbs/${fid}.jpg`;
    img.alt      = file.name;
    img.title    = file.name;
    img.onerror  = () => { img.src = PLACEHOLDER_SVG; img.style.objectFit = "contain"; };
    img.onclick  = () => openModal(idx);

    wrap.appendChild(img);
    frag.appendChild(wrap);
  });

  grid.appendChild(frag);
}

// ── Modal ─────────────────────────────────────────────────────────────────────
function setupModal() {
  document.getElementById("modal-bg").onclick    = closeModal;
  document.getElementById("modal-close").onclick = closeModal;
  document.getElementById("modal-prev").onclick  = () => stepModal(-1);
  document.getElementById("modal-next").onclick  = () => stepModal(+1);
}

function openModal(idx) {
  modalIdx = idx;
  showModalImage();
  document.getElementById("modal").hidden = false;
}

function showModalImage() {
  const fid    = curFiles[modalIdx];
  const file   = IDX.files[fid];
  const mImg   = document.getElementById("modal-img");
  const spin   = document.getElementById("modal-spinner");

  mImg.style.opacity = "0";
  spin.style.display = "block";

  mImg.onload = () => {
    mImg.style.opacity = "1";
    spin.style.display = "none";
  };
  mImg.onerror = () => {
    // fall back to small thumbnail
    mImg.src = `./static/thumbs/${fid}.jpg`;
    spin.style.display = "none";
    mImg.style.opacity = "1";
  };

  mImg.src = `./static/modal/${fid}.jpg`;
  document.getElementById("modal-name").textContent = file.name;
  document.getElementById("modal-drive-link").href =
    `https://drive.google.com/file/d/${fid}/view`;

  // prev/next visibility
  document.getElementById("modal-prev").disabled = modalIdx === 0;
  document.getElementById("modal-next").disabled = modalIdx === curFiles.length - 1;
}

function stepModal(delta) {
  const next = modalIdx + delta;
  if (next < 0 || next >= curFiles.length) return;
  modalIdx = next;
  showModalImage();
}

function closeModal() {
  document.getElementById("modal").hidden = true;
  document.getElementById("modal-img").src = "";
}

// ── Keyboard ──────────────────────────────────────────────────────────────────
function setupKeyboard() {
  document.addEventListener("keydown", (e) => {
    const modal = document.getElementById("modal");
    if (!modal.hidden) {
      if (e.key === "Escape")     closeModal();
      if (e.key === "ArrowRight") stepModal(-1);  // RTL: right = prev
      if (e.key === "ArrowLeft")  stepModal(+1);  // RTL: left  = next
    }
  });
}

// ── Start ─────────────────────────────────────────────────────────────────────
init();
