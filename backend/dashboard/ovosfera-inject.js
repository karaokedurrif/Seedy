/**
 * OvoSfera Camera + Seedy Widget Injector
 *
 * Inyecta feeds de cámaras en las páginas de gallineros y dashboard de OvoSfera
 * y carga el widget de chat Seedy 🌱.
 *
 * Uso: <script src="https://seedy-api.neofarm.io/dashboard/ovosfera-inject.js"></script>
 */
(function () {
  "use strict";

  const SEEDY_API = "https://seedy-api.neofarm.io";
  const SNAPSHOT_INTERVAL = 5000;
  const YOLO_INTERVAL = 4000;
  const ANNOTATED_INTERVAL = 30000;

  const CAMERA_MAP = {
    2: { name: "Durrif I", stream: "gallinero_durrif_1" },
    3: { name: "Durrif II", stream: "gallinero_durrif_2" },
  };

  // ── Styles ──
  const INJECT_CSS = `
    .seedy-cam-wrap {
      margin-top: 12px;
      border-radius: 10px;
      overflow: hidden;
      position: relative;
      background: #0a0a0a;
      cursor: pointer;
    }
    .seedy-cam-wrap img {
      width: 100%;
      display: block;
      border-radius: 10px;
      transition: opacity 0.3s;
    }
    .seedy-cam-wrap img.loading { opacity: 0.4; }
    .seedy-cam-badge {
      position: absolute;
      top: 8px;
      left: 8px;
      display: flex;
      gap: 6px;
      align-items: center;
    }
    .seedy-cam-badge span {
      background: rgba(0,0,0,0.65);
      color: #fff;
      font-size: 10px;
      font-weight: 600;
      padding: 3px 8px;
      border-radius: 6px;
      backdrop-filter: blur(4px);
    }
    .seedy-cam-badge .live {
      background: rgba(220,38,38,0.85);
      animation: seedy-pulse 2s infinite;
    }
    @keyframes seedy-pulse {
      0%, 100% { opacity: 1; }
      50% { opacity: 0.5; }
    }
    .seedy-cam-toolbar {
      position: absolute;
      bottom: 8px;
      right: 8px;
      display: flex;
      gap: 4px;
    }
    .seedy-cam-toolbar button {
      background: rgba(0,0,0,0.6);
      color: #fff;
      border: none;
      border-radius: 6px;
      padding: 4px 8px;
      font-size: 11px;
      cursor: pointer;
      backdrop-filter: blur(4px);
      transition: background 0.15s;
    }
    .seedy-cam-toolbar button:hover {
      background: rgba(0,0,0,0.85);
    }
    .seedy-cam-error {
      padding: 16px;
      text-align: center;
      color: #999;
      font-size: 12px;
    }
    .seedy-fullscreen {
      position: fixed;
      inset: 0;
      z-index: 10000;
      background: rgba(0,0,0,0.92);
      display: flex;
      align-items: center;
      justify-content: center;
      cursor: zoom-out;
    }
    .seedy-fullscreen img {
      max-width: 95vw;
      max-height: 95vh;
      border-radius: 8px;
    }
    .seedy-fullscreen-close {
      position: absolute;
      top: 16px;
      right: 16px;
      background: rgba(255,255,255,0.15);
      color: #fff;
      border: none;
      border-radius: 50%;
      width: 36px;
      height: 36px;
      font-size: 18px;
      cursor: pointer;
    }
    .seedy-cam-toggle {
      display: flex;
      gap: 0;
      margin-top: 6px;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.08);
    }
    .seedy-cam-toggle button {
      flex: 1;
      padding: 5px 0;
      font-size: 11px;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: all 0.15s;
      background: rgba(0,0,0,0.04);
      color: var(--neutral-500, #888);
    }
    .seedy-cam-toggle button.active {
      background: var(--primary-600, #B07D2B);
      color: #fff;
    }
    /* ── Dashboard dual-camera panel ── */
    .seedy-dashboard-panel {
      padding: 16px;
      max-width: 1400px;
      margin: 0 auto;
    }
    .seedy-dashboard-panel h3 {
      color: var(--neutral-100, #f1f5f9);
      font-size: 1.1em;
      margin-bottom: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
    }
    .seedy-dashboard-grid {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 16px;
    }
    @media (max-width: 768px) {
      .seedy-dashboard-grid { grid-template-columns: 1fr; }
    }
    .seedy-dashboard-cell {
      background: var(--neutral-900, #111827);
      border-radius: 12px;
      border: 1px solid var(--neutral-800, #1f2937);
      overflow: hidden;
    }
    .seedy-dashboard-cell h4 {
      padding: 10px 14px 0;
      font-size: 0.9em;
      color: var(--neutral-300, #d1d5db);
      margin: 0;
    }
    .seedy-dashboard-cell .seedy-cam-wrap { margin: 8px; border-radius: 8px; }
    .seedy-dashboard-cell .seedy-cam-toggle { margin: 0 8px 8px; }
    .seedy-twin-links {
      display: flex;
      gap: 10px;
      margin-top: 14px;
      flex-wrap: wrap;
    }
    .seedy-twin-links a {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 0.85em;
      font-weight: 600;
      text-decoration: none;
      transition: all 0.15s;
    }
    .seedy-twin-links a.twin-3d {
      background: linear-gradient(135deg, #3b82f6, #8b5cf6);
      color: #fff;
    }
    .seedy-twin-links a.twin-3d:hover { opacity: 0.85; }
    .seedy-twin-links a.twin-2d {
      background: var(--neutral-800, #1f2937);
      color: var(--neutral-200, #e5e7eb);
      border: 1px solid var(--neutral-700, #374151);
    }
    .seedy-twin-links a.twin-2d:hover { background: var(--neutral-700, #374151); }
  `;

  // ── Inject CSS ──
  function injectStyles() {
    if (document.getElementById("seedy-inject-css")) return;
    const style = document.createElement("style");
    style.id = "seedy-inject-css";
    style.textContent = INJECT_CSS;
    document.head.appendChild(style);
  }

  // ── Parse gallinero ID from card ──
  function parseGallineroId(card) {
    // The card shows "Zona · #ID" in a span
    const spans = card.querySelectorAll("span");
    for (const span of spans) {
      const m = span.textContent.match(/#(\d+)/);
      if (m) return parseInt(m[1], 10);
    }
    return null;
  }

  // ── Build camera element for a card ──
  function buildCameraElement(gallineroId) {
    const cam = CAMERA_MAP[gallineroId];
    if (!cam) return null;

    const wrap = document.createElement("div");
    wrap.className = "seedy-cam-wrap";
    wrap.dataset.gallineroId = gallineroId;
    wrap.dataset.mode = "live"; // "live" or "annotated"

    const img = document.createElement("img");
    img.alt = `Cámara ${cam.name}`;
    img.loading = "lazy";
    img.className = "loading";
    wrap.appendChild(img);

    // Badge
    const badge = document.createElement("div");
    badge.className = "seedy-cam-badge";
    badge.innerHTML = `<span class="live">● LIVE</span><span>📷 ${cam.name}</span>`;
    wrap.appendChild(badge);

    // Toolbar
    const toolbar = document.createElement("div");
    toolbar.className = "seedy-cam-toolbar";

    const btnAnnotated = document.createElement("button");
    btnAnnotated.textContent = "🐔 IA";
    btnAnnotated.title = "Ver detección IA";
    btnAnnotated.addEventListener("click", (e) => {
      e.stopPropagation();
      const mode = wrap.dataset.mode === "live" ? "annotated" : "live";
      wrap.dataset.mode = mode;
      btnAnnotated.textContent = mode === "live" ? "🐔 IA" : "📷 Live";
      refreshSnapshot(wrap, gallineroId);
      // Update toggle buttons if they exist
      updateToggle(wrap, mode);
    });
    toolbar.appendChild(btnAnnotated);

    const btnFullscreen = document.createElement("button");
    btnFullscreen.textContent = "⛶";
    btnFullscreen.title = "Pantalla completa";
    btnFullscreen.addEventListener("click", (e) => {
      e.stopPropagation();
      openFullscreen(img.src, cam.name);
    });
    toolbar.appendChild(btnFullscreen);

    wrap.appendChild(toolbar);

    // Toggle bar — 3 modes: live MJPEG, YOLO fast, full IA
    const toggle = document.createElement("div");
    toggle.className = "seedy-cam-toggle";
    toggle.innerHTML = `
      <button class="active" data-mode="live">📷 Live</button>
      <button data-mode="yolo">🎯 YOLO</button>
      <button data-mode="annotated">🐔 IA</button>
    `;
    toggle.querySelectorAll("button").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const mode = btn.dataset.mode;
        wrap.dataset.mode = mode;
        btnAnnotated.textContent = mode === "live" ? "🐔 IA" : "📷 Live";
        refreshSnapshot(wrap, gallineroId);
        updateToggle(wrap, mode);
      });
    });

    const container = document.createElement("div");
    container.className = "seedy-cam-container";
    container.dataset.gallineroId = gallineroId;
    container.appendChild(wrap);
    container.appendChild(toggle);

    // Initial load
    refreshSnapshot(wrap, gallineroId);

    return container;
  }

  function updateToggle(wrap, mode) {
    const container = wrap.parentElement;
    if (!container) return;
    container.querySelectorAll(".seedy-cam-toggle button").forEach((btn) => {
      btn.classList.toggle("active", btn.dataset.mode === mode);
    });
  }

  // ── Refresh snapshot ──
  function refreshSnapshot(wrap, gallineroId) {
    const img = wrap.querySelector("img");
    if (!img) return;
    const mode = wrap.dataset.mode || "live";
    const cam = CAMERA_MAP[gallineroId];
    if (!cam) return;
    const ts = Date.now();

    // Stop any MJPEG stream when switching modes
    if (img.src.includes("/mjpeg")) {
      img.src = "";
    }

    if (mode === "live") {
      // Snapshot mode: fast frame refresh (works through Cloudflare tunnel)
      const url = `${SEEDY_API}/ovosfera/camera/${gallineroId}/snapshot?_t=${ts}`;
      const tempImg = new Image();
      tempImg.onload = () => {
        if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
        img.src = tempImg.src;
        img.classList.remove("loading");
      };
      tempImg.onerror = () => img.classList.remove("loading");
      tempImg.src = url;
      // Update badge
      const badge = wrap.querySelector(".seedy-cam-badge");
      if (badge) badge.innerHTML = `<span class="live">● LIVE</span><span>📷 ${cam.name}</span>`;
      return;
    }

    img.classList.add("loading");

    if (mode === "yolo") {
      // YOLO-only: fast GET endpoint (~50ms inference)
      const url = `${SEEDY_API}/vision/identify/snapshot/${cam.stream}/yolo?_t=${ts}`;
      fetch(url)
        .then((r) => {
          if (!r.ok) return Promise.reject("error");
          const birds = r.headers.get("X-Birds-Detected") || "0";
          const ms = r.headers.get("X-Inference-Ms") || "?";
          const badge = wrap.querySelector(".seedy-cam-badge");
          if (badge) badge.innerHTML = `<span style="background:rgba(76,175,80,0.85)">🎯 YOLO ${ms}ms</span><span>🐔 ${birds} aves</span>`;
          return r.blob();
        })
        .then((blob) => {
          if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
          img.src = URL.createObjectURL(blob);
          img.classList.remove("loading");
        })
        .catch(() => img.classList.remove("loading"));
    } else if (mode === "annotated") {
      // Full IA: POST (YOLO + Gemini, slower)
      fetch(`${SEEDY_API}/vision/identify/snapshot/${cam.stream}/annotated?_t=${ts}`, {
        method: "POST",
      })
        .then((r) => {
          if (!r.ok) return Promise.reject("error");
          const birds = r.headers.get("X-Birds-Detected") || "0";
          const engine = r.headers.get("X-Engine") || "?";
          const badge = wrap.querySelector(".seedy-cam-badge");
          if (badge) badge.innerHTML = `<span style="background:rgba(33,150,243,0.85)">🐔 IA</span><span>${engine} · ${birds} aves</span>`;
          return r.blob();
        })
        .then((blob) => {
          if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
          img.src = URL.createObjectURL(blob);
          img.classList.remove("loading");
        })
        .catch(() => img.classList.remove("loading"));
    }
  }

  // ── Fullscreen overlay ──
  function openFullscreen(src, name) {
    const overlay = document.createElement("div");
    overlay.className = "seedy-fullscreen";
    overlay.innerHTML = `
      <img src="${src}" alt="${name}">
      <button class="seedy-fullscreen-close">✕</button>
    `;
    overlay.addEventListener("click", () => overlay.remove());
    overlay.querySelector("button").addEventListener("click", () => overlay.remove());
    document.body.appendChild(overlay);
  }

  // ── Inject cameras into gallinero cards ──
  function injectCameras() {
    const cards = document.querySelectorAll(".nf-card, [class*='card'], [class*='Card']");
    cards.forEach((card) => {
      if (card.querySelector(".seedy-cam-container")) return;

      const gid = parseGallineroId(card);
      if (!gid || !CAMERA_MAP[gid]) return;

      const camEl = buildCameraElement(gid);
      if (!camEl) return;

      // Insert before the status/action bar (last flex row in the card)
      const padDiv = card.querySelector("div[style]");
      if (padDiv) {
        // Find the main content div (first child with padding)
        const contentDiv = card.firstElementChild;
        if (contentDiv) {
          // Insert camera before the last child (status bar)
          const children = contentDiv.children;
          if (children.length > 2) {
            // Insert before the status/actions div
            contentDiv.insertBefore(camEl, children[children.length - 1]);
          } else {
            contentDiv.appendChild(camEl);
          }
        }
      }
    });
  }

  // ── Auto-refresh loop ──
  let refreshTimer = null;
  function startRefreshLoop() {
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(() => {
      document.querySelectorAll(".seedy-cam-wrap").forEach((wrap) => {
        const gid = parseInt(wrap.dataset.gallineroId, 10);
        if (!gid) return;
        const mode = wrap.dataset.mode || "live";
        // Live: refresh every 2s (snapshot), YOLO: every 4s, IA: every 30s
        if (mode === "live" || mode === "yolo") {
          refreshSnapshot(wrap, gid);
        }
      });
    }, 2000); // 2s base interval for live, YOLO checked inside

    // Slower loop for IA annotated
    setInterval(() => {
      document.querySelectorAll(".seedy-cam-wrap").forEach((wrap) => {
        const gid = parseInt(wrap.dataset.gallineroId, 10);
        if (!gid) return;
        if (wrap.dataset.mode === "annotated") refreshSnapshot(wrap, gid);
      });
    }, ANNOTATED_INTERVAL);
  }

  function stopRefreshLoop() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  // ── Load Seedy widget ──
  function loadSeedyWidget() {
    if (document.getElementById("seedy-widget-script")) return;
    const script = document.createElement("script");
    script.id = "seedy-widget-script";
    script.src = `${SEEDY_API}/dashboard/seedy-widget.js`;
    document.body.appendChild(script);
  }

  // ── MutationObserver for SPA navigation ──
  function isGallinerosPage() {
    return window.location.pathname.includes("/gallineros");
  }

  function isDashboardPage() {
    return window.location.pathname.includes("/dashboard");
  }

  function isFarmPage() {
    return window.location.pathname.includes("/farm/");
  }

  // ── Dashboard panel: dual cameras + digital twin links ──
  function injectDashboardPanel() {
    if (document.getElementById("seedy-dashboard-injected")) return;

    // Find a suitable container in the dashboard page
    const main =
      document.querySelector("main") ||
      document.querySelector("[class*='content']") ||
      document.querySelector("[class*='Content']") ||
      document.querySelector("[class*='dashboard']") ||
      document.querySelector("[class*='Dashboard']");

    if (!main) return;

    const panel = document.createElement("div");
    panel.id = "seedy-dashboard-injected";
    panel.className = "seedy-dashboard-panel";

    // Header
    const header = document.createElement("h3");
    header.innerHTML = "📹 Cámaras en directo";
    panel.appendChild(header);

    // Grid with both cameras
    const grid = document.createElement("div");
    grid.className = "seedy-dashboard-grid";

    for (const [gid, cam] of Object.entries(CAMERA_MAP)) {
      const cell = document.createElement("div");
      cell.className = "seedy-dashboard-cell";
      const title = document.createElement("h4");
      title.textContent = cam.name;
      cell.appendChild(title);

      const camEl = buildCameraElement(parseInt(gid));
      if (camEl) cell.appendChild(camEl);
      grid.appendChild(cell);
    }

    panel.appendChild(grid);

    // Digital Twin links
    const links = document.createElement("div");
    links.className = "seedy-twin-links";
    links.innerHTML = `
      <a href="${SEEDY_API}/dashboard/digital_twin_3d.html" target="_blank" class="twin-3d">
        🏗️ Digital Twin 3D
      </a>
      <a href="${SEEDY_API}/dashboard/plano_2d.html" target="_blank" class="twin-2d">
        📐 Plano 2D
      </a>
    `;
    panel.appendChild(links);

    // Insert at the top of main content
    if (main.firstChild) {
      main.insertBefore(panel, main.firstChild);
    } else {
      main.appendChild(panel);
    }
  }

  function onPageChange() {
    if (isDashboardPage()) {
      setTimeout(() => {
        injectDashboardPanel();
        injectCameras();
        startRefreshLoop();
      }, 800);
    } else if (isGallinerosPage()) {
      setTimeout(() => {
        injectCameras();
        startRefreshLoop();
      }, 800);
    } else if (isFarmPage()) {
      // Any farm page — try to inject cameras if cards exist
      setTimeout(() => {
        injectCameras();
      }, 1000);
    } else {
      stopRefreshLoop();
    }
  }

  // ── Init ──
  function init() {
    injectStyles();
    loadSeedyWidget();

    // Initial check
    onPageChange();

    // Watch for SPA navigation and DOM changes
    const observer = new MutationObserver(() => {
      if (isGallinerosPage()) {
        injectCameras();
      } else if (isDashboardPage()) {
        injectDashboardPanel();
        injectCameras();
      }
    });
    observer.observe(document.body, { childList: true, subtree: true });

    // Also watch URL changes (SPA pushState)
    let lastPath = window.location.pathname;
    setInterval(() => {
      if (window.location.pathname !== lastPath) {
        lastPath = window.location.pathname;
        onPageChange();
      }
    }, 500);
  }

  // Start when DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
