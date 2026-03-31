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
  const OVOSFERA_API = "https://hub.ovosfera.com/api/ovosfera";
  const SEEDY_FARM = "palacio";  // Solo activar en este tenant
  const SNAPSHOT_INTERVAL = 5000;
  const YOLO_INTERVAL = 4000;
  const ANNOTATED_INTERVAL = 30000;

  const CAMERA_MAP = {
    2: {
      name: "Durrif I",
      stream: "gallinero_durrif_1",
      cameras: [
        { id: "nueva", label: "Cám. Nueva (VIGI)", stream: "gallinero_durrif_1", active: true },
        { id: "sauna", label: "Cám. Sauna (Dahua)", stream: "sauna_durrif_1", active: true },
      ],
    },
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
    .seedy-cam-selector {
      display: flex;
      gap: 0;
      margin-top: 8px;
      margin-bottom: 2px;
      border-radius: 8px;
      overflow: hidden;
      border: 1px solid rgba(255,255,255,0.1);
    }
    .seedy-cam-selector button {
      flex: 1;
      padding: 6px 4px;
      font-size: 10px;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: all 0.15s;
      background: rgba(0,0,0,0.06);
      color: var(--neutral-500, #888);
    }
    .seedy-cam-selector button.active {
      background: var(--primary-700, #8a6220);
      color: #fff;
    }
    .seedy-cam-selector button.offline {
      color: var(--neutral-600, #666);
      font-style: italic;
    }
    .seedy-cam-offline {
      padding: 32px 16px;
      text-align: center;
      color: #888;
      font-size: 12px;
      background: #0a0a0a;
      border-radius: 10px;
      margin-top: 12px;
    }
    .seedy-cam-offline strong {
      display: block;
      color: #f59e0b;
      font-size: 14px;
      margin-bottom: 6px;
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
    /* ── Bird monitoring button ── */
    .seedy-bird-monitor-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 0.85em;
      font-weight: 600;
      background: linear-gradient(135deg, #10b981, #059669);
      color: #fff;
      border: none;
      cursor: pointer;
      transition: all 0.15s;
      margin: 8px 0;
    }
    .seedy-bird-monitor-btn:hover { opacity: 0.85; }
    .seedy-bird-monitor-info {
      position: absolute;
      bottom: 16px;
      left: 50%;
      transform: translateX(-50%);
      color: #fff;
      font-size: 13px;
      background: rgba(0,0,0,0.6);
      padding: 6px 16px;
      border-radius: 8px;
      backdrop-filter: blur(4px);
      white-space: nowrap;
    }
    /* ── Ave detail modal ── */
    .seedy-ave-modal-overlay {
      position: fixed;
      inset: 0;
      z-index: 9999;
      background: rgba(0,0,0,0.6);
      display: flex;
      align-items: center;
      justify-content: center;
      backdrop-filter: blur(3px);
    }
    .seedy-ave-modal {
      background: var(--neutral-900, #1a1a2e);
      border: 1px solid var(--neutral-700, #374151);
      border-radius: 16px;
      max-width: 520px;
      width: 92vw;
      max-height: 90vh;
      overflow-y: auto;
      box-shadow: 0 20px 60px rgba(0,0,0,0.5);
      color: var(--neutral-100, #f1f5f9);
      position: relative;
    }
    .seedy-ave-modal-close {
      position: absolute;
      top: 12px;
      right: 12px;
      background: rgba(255,255,255,0.1);
      color: #fff;
      border: none;
      border-radius: 50%;
      width: 32px;
      height: 32px;
      font-size: 16px;
      cursor: pointer;
      z-index: 1;
      transition: background 0.15s;
    }
    .seedy-ave-modal-close:hover { background: rgba(255,255,255,0.2); }
    .seedy-ave-modal-header {
      padding: 20px 20px 0;
      display: flex;
      gap: 16px;
      align-items: flex-start;
    }
    .seedy-ave-modal-photo {
      width: 100px;
      height: 100px;
      border-radius: 12px;
      object-fit: cover;
      background: #222;
      flex-shrink: 0;
      cursor: pointer;
    }
    .seedy-ave-modal-photo.no-photo {
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 40px;
      background: var(--neutral-800, #1f2937);
    }
    .seedy-ave-modal-title {
      flex: 1;
    }
    .seedy-ave-modal-title h3 {
      margin: 0 0 4px;
      font-size: 1.15em;
      color: var(--primary-400, #d4a44a);
    }
    .seedy-ave-modal-title .anilla {
      font-size: 0.8em;
      color: var(--neutral-400, #9ca3af);
      font-family: monospace;
    }
    .seedy-ave-modal-grid {
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      gap: 10px;
      padding: 16px 20px;
    }
    .seedy-ave-modal-field {
      font-size: 0.8em;
    }
    .seedy-ave-modal-field label {
      display: block;
      color: var(--neutral-500, #6b7280);
      font-size: 0.75em;
      text-transform: uppercase;
      letter-spacing: 0.5px;
      margin-bottom: 2px;
    }
    .seedy-ave-modal-field span {
      color: var(--neutral-200, #e5e7eb);
      font-weight: 500;
    }
    .seedy-ave-modal-actions {
      padding: 0 20px 20px;
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .seedy-ave-modal-actions button {
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.8em;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: all 0.15s;
    }
    .seedy-ave-modal-actions .cam-btn {
      background: linear-gradient(135deg, #10b981, #059669);
      color: #fff;
    }
    .seedy-ave-modal-actions .cam-btn:hover { opacity: 0.85; }
    .seedy-ave-modal-actions .edit-btn {
      background: var(--neutral-800, #1f2937);
      color: var(--neutral-200, #e5e7eb);
      border: 1px solid var(--neutral-700, #374151);
    }
    .seedy-ave-modal-actions .edit-btn:hover { background: var(--neutral-700, #374151); }
    .seedy-ave-modal-notes {
      padding: 0 20px 16px;
      font-size: 0.82em;
      color: var(--neutral-400, #9ca3af);
      font-style: italic;
    }
    .seedy-ave-modal-vision {
      padding: 0 20px 16px;
      font-size: 0.78em;
      color: var(--neutral-500, #6b7280);
    }
    .seedy-ave-modal-vision code {
      background: rgba(255,255,255,0.06);
      padding: 2px 6px;
      border-radius: 4px;
      font-size: 0.95em;
    }
    /* ── Seedy capture button injected into OvoSfera edit modals ── */
    .seedy-capture-btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 14px;
      border-radius: 8px;
      font-size: 0.82em;
      font-weight: 600;
      background: linear-gradient(135deg, #10b981, #059669);
      color: #fff;
      border: none;
      cursor: pointer;
      transition: all 0.15s;
    }
    .seedy-capture-btn:hover { opacity: 0.85; }
    .seedy-capture-btn:disabled {
      opacity: 0.5;
      cursor: wait;
    }
    .seedy-capture-status {
      font-size: 0.75em;
      color: var(--neutral-400, #9ca3af);
      margin-top: 4px;
    }
    .seedy-photo-zoomable {
      cursor: zoom-in;
      transition: transform 0.15s;
    }
    .seedy-photo-zoomable:hover {
      transform: scale(1.05);
    }
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
    img.style.display = "none"; // hidden by default, shown in YOLO/IA mode
    wrap.appendChild(img);

    const video = document.createElement("video");
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.className = "seedy-cam-video";
    video.style.width = "100%";
    video.style.borderRadius = "8px";
    wrap.appendChild(video);

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

    // Camera selector for multi-camera gallineros
    if (cam.cameras && cam.cameras.length > 1) {
      const selector = document.createElement("div");
      selector.className = "seedy-cam-selector";
      cam.cameras.forEach(function (c) {
        const btn = document.createElement("button");
        btn.textContent = c.label;
        btn.dataset.camId = c.id;
        if (!c.active) btn.classList.add("offline");
        if (c.id === cam.cameras[0].id) btn.classList.add("active");
        btn.addEventListener("click", function (e) {
          e.stopPropagation();
          selector.querySelectorAll("button").forEach(function (b) { b.classList.remove("active"); });
          btn.classList.add("active");
          container.dataset.selectedCam = c.id;
          // Handle offline cameras
          var offlineEl = container.querySelector(".seedy-cam-offline");
          if (!c.active) {
            wrap.style.display = "none";
            toggle.style.display = "none";
            if (!offlineEl) {
              offlineEl = document.createElement("div");
              offlineEl.className = "seedy-cam-offline";
              offlineEl.innerHTML = "<strong>" + c.label + "</strong>Cámara no conectada<br><small>Próximamente</small>";
              container.insertBefore(offlineEl, toggle.nextSibling || null);
            }
          } else {
            wrap.style.display = "";
            toggle.style.display = "";
            if (offlineEl) offlineEl.remove();
            container.dataset.activeStream = c.stream;
            delete wrap.dataset._mseFailed; // reset MSE for new camera
            refreshSnapshot(wrap, gallineroId);
          }
        });
        selector.appendChild(btn);
      });
      container.appendChild(selector);
      container.dataset.selectedCam = cam.cameras[0].id;
      container.dataset.activeStream = cam.cameras[0].stream;
    }

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

  // ── MSE WebSocket streaming ──
  var _mseMap = new WeakMap();
  var _mseRetries = new WeakMap(); // retry counts per wrap element

  function _startMSE(wrap, streamName) {
    _stopMSE(wrap);
    var video = wrap.querySelector("video");
    var img = wrap.querySelector("img");
    if (!video) return;
    video.style.display = "";
    if (img) img.style.display = "none";

    var wsUrl = SEEDY_API.replace("https://", "wss://").replace("http://", "ws://")
      + "/ovosfera/stream/" + streamName + "_web/mse";

    var ws = new WebSocket(wsUrl);
    ws.binaryType = "arraybuffer";
    var ms = null, sb = null, queue = [];

    function appendNext() {
      if (sb && !sb.updating && queue.length > 0) {
        try { sb.appendBuffer(queue.shift()); }
        catch (e) {
          if (e.name === "QuotaExceededError" && sb.buffered.length > 0) {
            sb.remove(0, sb.buffered.end(sb.buffered.length - 1) - 5);
          }
        }
      }
    }

    ws.onopen = function () {
      ws.send(JSON.stringify({ type: "mse" }));
      // Reset retries on successful open
      _mseRetries.delete(wrap);
    };

    ws.onmessage = function (ev) {
      if (typeof ev.data === "string") {
        try {
          var msg = JSON.parse(ev.data);
          if (msg.type === "mse") {
            if (typeof MediaSource === "undefined" || !MediaSource.isTypeSupported(msg.value)) {
              console.warn("[Seedy] MSE codec not supported:", msg.value, "— fallback to snapshots");
              ws.close();
              _fallbackToSnapshot(wrap, streamName);
              return;
            }
            ms = new MediaSource();
            video.src = URL.createObjectURL(ms);
            ms.addEventListener("sourceopen", function () {
              try {
                sb = ms.addSourceBuffer(msg.value);
                sb.mode = "segments";
                sb.addEventListener("updateend", appendNext);
              } catch (e) {
                console.warn("[Seedy] SourceBuffer error:", e);
                ws.close();
                _fallbackToSnapshot(wrap, streamName);
              }
            });
            video.play().catch(function () {});
          }
        } catch (e) { /* ignore parse errors */ }
      } else {
        queue.push(ev.data);
        appendNext();
      }
    };

    ws.onerror = function () {
      _fallbackToSnapshot(wrap, streamName);
    };

    // Reconnect on clean close unless MSE already failed or wrap is removed
    ws.onclose = function () {
      if (wrap.dataset._mseFailed === "1") return;
      if (!document.body.contains(wrap)) return;
      var retries = (_mseRetries.get(wrap) || 0);
      if (retries < 3) {
        _mseRetries.set(wrap, retries + 1);
        var delay = Math.min(2000 * Math.pow(2, retries), 8000);
        console.info("[Seedy] MSE closed, retry " + (retries + 1) + "/3 in " + delay + "ms for " + streamName);
        setTimeout(function () {
          if (!document.body.contains(wrap)) return;
          if (wrap.dataset.mode === "live") _startMSE(wrap, streamName);
        }, delay);
      } else {
        console.warn("[Seedy] MSE max retries reached for " + streamName + ", falling back to snapshots");
        _fallbackToSnapshot(wrap, streamName);
      }
    };

    _mseMap.set(wrap, { ws: ws, ms: ms, stream: streamName });
  }

  function _stopMSE(wrap) {
    var session = _mseMap.get(wrap);
    if (!session) return;
    try { session.ws.close(); } catch (e) {}
    var video = wrap.querySelector("video");
    if (video) {
      if (video.src && video.src.startsWith("blob:")) URL.revokeObjectURL(video.src);
      video.src = "";
      video.load();
    }
    _mseMap.delete(wrap);
    _mseRetries.delete(wrap);
  }

  function _fallbackToSnapshot(wrap, streamName) {
    wrap.dataset._mseFailed = "1";
    var video = wrap.querySelector("video");
    var img = wrap.querySelector("img");
    if (video) video.style.display = "none";
    if (img) {
      img.style.display = "";
      _snapshotFallback(img, streamName, parseInt(wrap.dataset.gallineroId), null);
    }
  }

  // ── Refresh / start MSE ──
  function refreshSnapshot(wrap, gallineroId) {
    const img = wrap.querySelector("img");
    const video = wrap.querySelector("video");
    const mode = wrap.dataset.mode || "live";
    const cam = CAMERA_MAP[gallineroId];
    if (!cam) return;
    const container = wrap.parentElement;
    const activeStream = (container && container.dataset.activeStream) || cam.stream;
    const ts = Date.now();

    if (mode === "live") {
      // MSE WebSocket streaming (H.264 via ffmpeg, real-time)
      var currentMSE = _mseMap.get(wrap);
      if (!currentMSE || currentMSE.stream !== activeStream) {
        if (wrap.dataset._mseFailed !== "1") {
          _startMSE(wrap, activeStream);
        } else {
          // MSE failed, use snapshot fallback
          if (video) video.style.display = "none";
          if (img) { img.style.display = ""; _snapshotFallback(img, activeStream, gallineroId, cam); }
        }
      }
      const badge = wrap.querySelector(".seedy-cam-badge");
      if (badge) badge.innerHTML = `<span class="live">● LIVE</span><span>📷 ${cam.name}</span>`;
      return;
    }

    // Not live → stop MSE, show img
    _stopMSE(wrap);
    delete wrap.dataset._mseFailed;
    if (video) video.style.display = "none";
    if (img) img.style.display = "";
    img.classList.add("loading");

    if (mode === "yolo") {
      const url = `${SEEDY_API}/vision/identify/snapshot/${activeStream}/yolo?_t=${ts}`;
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
      fetch(`${SEEDY_API}/vision/identify/snapshot/${activeStream}/annotated?_t=${ts}`, {
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

  // Fallback: snapshot polling
  function _snapshotFallback(img, streamName, gallineroId, cam) {
    const url = `${SEEDY_API}/ovosfera/stream/${streamName}/snapshot?_t=${Date.now()}`;
    const tempImg = new Image();
    tempImg.onload = () => {
      if (img.src.startsWith("blob:")) URL.revokeObjectURL(img.src);
      img.src = tempImg.src;
      img.classList.remove("loading");
    };
    tempImg.onerror = () => img.classList.remove("loading");
    tempImg.src = url;
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
        // Live MSE: only poll if MSE failed and using snapshot fallback
        if (mode === "live" && wrap.dataset._mseFailed === "1") {
          const cam = CAMERA_MAP[gid];
          const container = wrap.parentElement;
          const activeStream = (container && container.dataset.activeStream) || (cam && cam.stream);
          const img = wrap.querySelector("img");
          if (activeStream && img) _snapshotFallback(img, activeStream, gid, cam);
        } else if (mode === "yolo") {
          refreshSnapshot(wrap, gid);
        }
      });
    }, 2000);

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

  function isAvesPage() {
    return window.location.pathname.match(/\/farm\/[^/]+\/aves/);
  }

  function isAveDetailPage() {
    return window.location.pathname.match(/\/farm\/[^/]+\/aves\/\d+/);
  }

  function isTargetFarm() {
    // Solo inyectar en el tenant configurado (palacio)
    var m = window.location.pathname.match(/\/farm\/([^/]+)/);
    return m && m[1] === SEEDY_FARM;
  }

  // ── Ave detail modal (popup) ──
  function openAveModal(aveId) {
    // Remove any existing modal
    var existing = document.querySelector(".seedy-ave-modal-overlay");
    if (existing) existing.remove();

    var overlay = document.createElement("div");
    overlay.className = "seedy-ave-modal-overlay";
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) overlay.remove();
    });

    var modal = document.createElement("div");
    modal.className = "seedy-ave-modal";
    modal.innerHTML = '<div style="padding:40px;text-align:center;color:#888">Cargando...</div>';
    overlay.appendChild(modal);
    document.body.appendChild(overlay);

    // Close on Escape
    function onKey(e) { if (e.key === "Escape") { overlay.remove(); document.removeEventListener("keydown", onKey); } }
    document.addEventListener("keydown", onKey);

    fetch(OVOSFERA_API + "/farms/" + SEEDY_FARM + "/aves/" + aveId)
      .then(function (r) { return r.json(); })
      .then(function (ave) {
        var closeBtn = '<button class="seedy-ave-modal-close" onclick="this.closest(\'.seedy-ave-modal-overlay\').remove()">✕</button>';

        var photoHtml;
        if (ave.foto && ave.foto.length > 50) {
          photoHtml = '<img class="seedy-ave-modal-photo" src="' + ave.foto + '" alt="Foto" />';
        } else {
          photoHtml = '<div class="seedy-ave-modal-photo no-photo">🐔</div>';
        }

        var raza = ave.raza || "—";
        var color = ave.color || ave.variedad || "";
        var nombre = raza + (color ? " — " + color : "");
        var sexoIcon = ave.sexo === "M" ? "♂" : ave.sexo === "H" ? "♀" : "?";
        var sexoText = ave.sexo === "M" ? "Macho" : ave.sexo === "H" ? "Hembra" : "—";
        var gallinero = ave.gallinero || "Sin asignar";
        var estado = ave.estado || "—";
        var peso = ave.peso ? ave.peso + " kg" : "—";
        var nacimiento = ave.fecha_nac || "—";
        var visionId = ave.ai_vision_id || "";

        var estadoColor = "#888";
        if (estado === "Ponedora activa") estadoColor = "#10b981";
        else if (estado === "Reproductor") estadoColor = "#3b82f6";

        modal.innerHTML = closeBtn +
          '<div class="seedy-ave-modal-header">' +
            photoHtml +
            '<div class="seedy-ave-modal-title">' +
              '<h3>' + nombre + '</h3>' +
              '<div class="anilla">' + (ave.anilla || "") + '</div>' +
              '<div style="margin-top:6px"><span style="background:' + estadoColor + ';color:#fff;padding:2px 8px;border-radius:4px;font-size:0.75em;font-weight:600">' + estado + '</span></div>' +
            '</div>' +
          '</div>' +
          '<div class="seedy-ave-modal-grid">' +
            '<div class="seedy-ave-modal-field"><label>Tipo</label><span>' + (ave.tipo || "—") + '</span></div>' +
            '<div class="seedy-ave-modal-field"><label>Sexo</label><span>' + sexoIcon + ' ' + sexoText + '</span></div>' +
            '<div class="seedy-ave-modal-field"><label>Peso</label><span>' + peso + '</span></div>' +
            '<div class="seedy-ave-modal-field"><label>Gallinero</label><span>' + gallinero + '</span></div>' +
            '<div class="seedy-ave-modal-field"><label>Nacimiento</label><span>' + nacimiento + '</span></div>' +
            '<div class="seedy-ave-modal-field"><label>Variedad</label><span>' + (color || "—") + '</span></div>' +
          '</div>' +
          (visionId ? '<div class="seedy-ave-modal-vision">AI-Vision ID: <code>' + visionId + '</code></div>' : '') +
          (ave.notas ? '<div class="seedy-ave-modal-notes">' + ave.notas + '</div>' : '') +
          '<div class="seedy-ave-modal-actions">' +
            '<button class="cam-btn" data-ave-id="' + aveId + '">📹 Cámara IA Vision</button>' +
            '<button class="edit-btn" data-ave-id="' + aveId + '">✏️ Editar</button>' +
          '</div>';

        // Photo click → fullscreen
        var photoEl = modal.querySelector(".seedy-ave-modal-photo");
        if (photoEl && photoEl.tagName === "IMG") {
          photoEl.addEventListener("click", function () {
            openFullscreen(ave.foto, nombre);
          });
        }

        // Camera button
        modal.querySelector(".cam-btn").addEventListener("click", function () {
          overlay.remove();
          openBirdMonitor(aveId, nombre);
        });

        // Edit button → navigate to OvoSfera edit page
        modal.querySelector(".edit-btn").addEventListener("click", function () {
          overlay.remove();
          window.location.href = "/farm/" + SEEDY_FARM + "/aves/" + aveId;
        });
      })
      .catch(function (e) {
        modal.innerHTML = '<div style="padding:40px;text-align:center;color:#e74c3c">Error al cargar ave: ' + e.message + '</div>';
      });
  }

  function openFullscreen(src, title) {
    var existing = document.querySelector(".seedy-fullscreen");
    if (existing) existing.remove();
    var overlay = document.createElement("div");
    overlay.className = "seedy-fullscreen";
    var img = document.createElement("img");
    img.src = src;
    img.alt = title || "";
    overlay.appendChild(img);
    var close = document.createElement("button");
    close.className = "seedy-fullscreen-close";
    close.textContent = "✕";
    close.addEventListener("click", function () { overlay.remove(); });
    overlay.appendChild(close);
    overlay.addEventListener("click", function (e) { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);
  }

  // ── Intercept clicks on aves list rows → trigger OvoSfera edit form ──
  function interceptAvesListClicks() {
    if (!isAvesPage() || isAveDetailPage()) return;
    if (document.body.dataset.seedyAvesIntercepted) return;
    document.body.dataset.seedyAvesIntercepted = "1";

    document.body.addEventListener("click", function (e) {
      if (!isAvesPage() || isAveDetailPage()) return;

      // Find if click was on a table row in the aves list
      var row = e.target.closest("tr[data-id], tr[class*='row'], tbody tr");
      if (!row) return;

      // Don't intercept clicks on action buttons (edit, delete, monitor icons)
      if (e.target.closest("button, a, .seedy-bird-monitor-btn, [class*='action'], svg, path")) return;
      // Don't intercept if clicking on icon buttons in the last column
      var cell = e.target.closest("td");
      if (cell) {
        var cells = Array.from(row.querySelectorAll("td"));
        if (cells.length > 0 && cell === cells[cells.length - 1]) return;
      }

      // Prevent OvoSfera's default expand behavior
      e.preventDefault();
      e.stopPropagation();

      // Find and click the edit (pencil) button in this row's actions column
      var editBtn = row.querySelector("td:last-child button:first-child, td:last-child a:first-child, [title*='dit'], [title*='ditar'], svg[data-icon*='edit']");
      if (editBtn) {
        editBtn.click();
        return;
      }
      // Fallback: find any pencil-like icon/button
      var actionBtns = row.querySelectorAll("td:last-child button, td:last-child a");
      if (actionBtns.length > 0) {
        actionBtns[0].click(); // first action is typically edit
        return;
      }

      // Last fallback: extract ID and navigate to detail page
      var aveId = row.dataset.id;
      if (!aveId) {
        var link = row.querySelector("a[href*='/aves/']");
        if (link) {
          var m = link.href.match(/\/aves\/(\d+)/);
          if (m) aveId = m[1];
        }
      }
      if (!aveId) {
        var anilla = row.querySelector("td:first-child");
        if (anilla) {
          var anillaMatch = anilla.textContent.match(/PAL-\d+-(\d+)/);
          if (anillaMatch) aveId = parseInt(anillaMatch[1], 10);
        }
      }
      if (aveId) {
        window.location.href = "/farm/" + SEEDY_FARM + "/aves/" + aveId;
      }
    }, true); // capture phase to intercept before OvoSfera
  }

  // ── Bird monitoring overlay ──
  function openBirdMonitor(aveId, aveName) {
    var existingOverlay = document.querySelector(".seedy-fullscreen");
    if (existingOverlay) existingOverlay.remove();

    var overlay = document.createElement("div");
    overlay.className = "seedy-fullscreen";

    var img = document.createElement("img");
    img.src = SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/snapshot?_t=" + Date.now();
    img.alt = "Monitoring " + (aveName || aveId);
    overlay.appendChild(img);

    var close = document.createElement("button");
    close.className = "seedy-fullscreen-close";
    close.textContent = "✕";
    close.addEventListener("click", function () { clearInterval(refreshTimer); overlay.remove(); });
    overlay.appendChild(close);

    var info = document.createElement("div");
    info.className = "seedy-bird-monitor-info";
    info.innerHTML = "📡 Monitorizando <b>" + (aveName || "ave #" + aveId) + "</b> — refresco cada 10s";
    overlay.appendChild(info);

    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) { clearInterval(refreshTimer); overlay.remove(); }
    });
    document.body.appendChild(overlay);

    var refreshTimer = setInterval(function () {
      var newImg = new Image();
      newImg.onload = function () { img.src = newImg.src; };
      newImg.src = SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/snapshot?_t=" + Date.now();
    }, 10000);
  }

  // ── Inject bird monitoring on aves detail/edit page ──
  function injectBirdMonitor() {
    if (!isAveDetailPage()) return;
    if (document.getElementById("seedy-bird-monitor-injected")) return;

    var m = window.location.pathname.match(/\/farm\/([^/]+)\/aves\/(\d+)/);
    if (!m) return;
    var slug = m[1];
    var aveId = m[2];

    fetch(OVOSFERA_API + "/farms/" + slug + "/aves/" + aveId)
      .then(function (r) { return r.json(); })
      .then(function (ave) {
        if (document.getElementById("seedy-bird-monitor-injected")) return;

        var container = document.createElement("div");
        container.id = "seedy-bird-monitor-injected";
        container.style.cssText = "padding: 0 16px; margin-bottom: 8px;";

        var btn = document.createElement("button");
        btn.className = "seedy-bird-monitor-btn";
        btn.innerHTML = "📹 Cámara IA Vision" + (ave.ai_vision_id ? " — " + ave.ai_vision_id : "");
        btn.addEventListener("click", function () {
          openBirdMonitor(aveId, (ave.raza || "") + " " + (ave.color || ""));
        });
        container.appendChild(btn);

        // If the ave has a photo, show a small preview
        if (ave.foto) {
          var preview = document.createElement("img");
          preview.src = ave.foto;
          preview.alt = "Foto IA";
          preview.style.cssText = "max-width:120px;border-radius:8px;margin-left:12px;vertical-align:middle;cursor:pointer;";
          preview.addEventListener("click", function () { openFullscreen(ave.foto, ave.raza + " " + ave.color); });
          container.appendChild(preview);
        }

        // Insert at top of main content
        var main = document.querySelector("main") || document.querySelector("[class*='content']") || document.body;
        var firstChild = main.querySelector("form") || main.firstElementChild;
        if (firstChild) {
          firstChild.parentNode.insertBefore(container, firstChild);
        } else {
          main.prepend(container);
        }
      })
      .catch(function (e) { console.debug("Seedy bird monitor inject failed:", e); });
  }

  // ── Inject monitoring buttons on aves list page ──
  function injectAvesListMonitor() {
    if (!isAvesPage() || isAveDetailPage()) return;

    // Find table rows or card elements that represent aves
    var rows = document.querySelectorAll("tr[data-id], [class*='card']");
    rows.forEach(function (row) {
      if (row.querySelector(".seedy-bird-monitor-btn")) return;

      // Try to find the ave ID from the row
      var aveId = row.dataset.id;
      if (!aveId) {
        var link = row.querySelector("a[href*='/aves/']");
        if (link) {
          var idMatch = link.href.match(/\/aves\/(\d+)/);
          if (idMatch) aveId = idMatch[1];
        }
      }
      if (!aveId) return;

      var btn = document.createElement("button");
      btn.className = "seedy-bird-monitor-btn";
      btn.textContent = "📹";
      btn.title = "Cámara IA Vision";
      btn.style.cssText = "padding:4px 8px;font-size:12px;margin-left:4px;";
      btn.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openBirdMonitor(aveId, "");
      });

      // Append to the last cell or the row itself
      var target = row.querySelector("td:last-child") || row;
      target.appendChild(btn);
    });
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
    if (!isTargetFarm()) {
      stopRefreshLoop();
      return;
    }
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
    } else if (isAveDetailPage()) {
      setTimeout(() => {
        injectBirdMonitor();
      }, 800);
    } else if (isAvesPage()) {
      setTimeout(() => {
        interceptAvesListClicks();
        injectAvesListMonitor();
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

  // ── Enhance OvoSfera edit modal with Seedy capture + photo zoom ──
  function enhanceEditModal() {
    // OvoSfera edit modal: look for the dialog/modal containing "Editar Ave" or photo upload buttons
    var modals = document.querySelectorAll("[class*='modal'], [class*='dialog'], [role='dialog'], [class*='Modal']");
    modals.forEach(function (modal) {
      if (modal.dataset.seedyEnhanced) return;

      // Detect if this is an edit modal (has "Editar" or "Subir foto" text)
      var text = modal.textContent || "";
      if (!text.includes("Editar") && !text.includes("Subir foto")) return;

      modal.dataset.seedyEnhanced = "1";

      // 1. Make existing photo zoomable
      var photos = modal.querySelectorAll("img");
      photos.forEach(function (img) {
        if (img.naturalWidth < 20) return; // skip icons
        if (img.classList.contains("seedy-photo-zoomable")) return;
        img.classList.add("seedy-photo-zoomable");
        img.addEventListener("click", function (e) {
          e.stopPropagation();
          openFullscreen(img.src, "Foto del ave");
        });
      });

      // 2. Find the "Subir foto" button area and add our "Cámara AI-Vision" button
      var uploadBtns = modal.querySelectorAll("button");
      var uploadBtn = null;
      uploadBtns.forEach(function (btn) {
        if (btn.textContent.includes("Subir foto") || btn.textContent.includes("Cámara AI")) {
          uploadBtn = btn;
        }
      });
      // Already has our button?
      if (modal.querySelector(".seedy-capture-btn")) return;

      // Find the ave ID from the form (look for ai_vision_id field or URL)  
      var aveId = null;
      var inputs = modal.querySelectorAll("input");
      inputs.forEach(function (inp) {
        // Hidden input or value matching PAL pattern or numeric ID
        if (inp.name === "id" || inp.dataset.id) aveId = inp.value || inp.dataset.id;
      });
      // Try to extract from any link/text in the modal containing the anilla
      if (!aveId) {
        var anillaMatch = text.match(/PAL-\d+-(\d+)/);
        if (anillaMatch) aveId = parseInt(anillaMatch[1], 10);
      }
      // Try from URL if on detail page
      if (!aveId) {
        var urlMatch = window.location.pathname.match(/\/aves\/(\d+)/);
        if (urlMatch) aveId = urlMatch[1];
      }

      // Find the photo container area
      var photoArea = uploadBtn ? uploadBtn.parentElement : null;
      if (!photoArea) {
        // Try common patterns: div containing "Foto" label
        var labels = modal.querySelectorAll("label, span, h4, h5, p");
        labels.forEach(function (lbl) {
          if (lbl.textContent.includes("Foto") && !photoArea) {
            photoArea = lbl.parentElement;
          }
        });
      }

      if (photoArea && aveId) {
        var captureBtn = document.createElement("button");
        captureBtn.className = "seedy-capture-btn";
        captureBtn.type = "button";
        captureBtn.innerHTML = "📸 Captura IA (4K)";
        captureBtn.title = "Captura una foto nítida del ave usando las cámaras + IA";

        var statusDiv = document.createElement("div");
        statusDiv.className = "seedy-capture-status";

        captureBtn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          captureBtn.disabled = true;
          captureBtn.innerHTML = "⏳ Capturando...";
          statusDiv.textContent = "Buscando al ave en las cámaras...";

          fetch(SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/capture-photo", {
            method: "POST",
          })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              if (data.success) {
                statusDiv.textContent = "✅ Foto capturada: " + data.resolution + " — " + data.message;
                // Update the photo preview in the modal
                var imgs = modal.querySelectorAll("img");
                imgs.forEach(function (img) {
                  if (img.naturalWidth > 20 || img.src.includes("data:image")) {
                    img.src = data.photo_data_uri;
                    img.classList.add("seedy-photo-zoomable");
                  }
                });
                captureBtn.innerHTML = "📸 Captura IA (4K)";
                captureBtn.disabled = false;
              } else {
                statusDiv.textContent = "⚠️ " + (data.message || "No se pudo capturar");
                captureBtn.innerHTML = "📸 Captura IA (4K)";
                captureBtn.disabled = false;
              }
            })
            .catch(function (err) {
              statusDiv.textContent = "❌ Error: " + err.message;
              captureBtn.innerHTML = "📸 Captura IA (4K)";
              captureBtn.disabled = false;
            });
        });

        photoArea.appendChild(captureBtn);
        photoArea.appendChild(statusDiv);
      }
    });
  }

  // ── Init ──
  function init() {
    injectStyles();
    loadSeedyWidget();

    // Initial check
    onPageChange();

    // Watch for SPA navigation and DOM changes
    const observer = new MutationObserver(() => {
      if (!isTargetFarm()) return;
      try { enhanceEditModal(); } catch (e) { console.warn("[Seedy] enhanceEditModal failed:", e); }
      if (isGallinerosPage()) {
        injectCameras();
      } else if (isDashboardPage()) {
        injectDashboardPanel();
        injectCameras();
      } else if (isAveDetailPage()) {
        injectBirdMonitor();
      } else if (isAvesPage()) {
        interceptAvesListClicks();
        injectAvesListMonitor();
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
