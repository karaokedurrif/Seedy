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
      name: "Gallinero Durrif",
      stream: "gallinero_durrif_1",
      gallinero: "gallinero_durrif",
      cameras: [
        { id: "nueva", label: "Cám. Nueva (VIGI)", stream: "gallinero_durrif_1", active: true },
        { id: "sauna", label: "Cám. Sauna (Dahua)", stream: "sauna_durrif_1", active: true },
        { id: "gii", label: "Cám. Gallinero (VIGI)", stream: "gallinero_durrif_2", active: true },
        { id: "interior", label: "Cám. Interior (ESP32 IR)", stream: "gallinero_palacio_esp32", active: true },
      ],
    },
    3: {
      name: "Gallinero Pequeño",
      stream: "gallinero_pequeno_esp32",
      gallinero: "gallinero_pequeno",
      cameras: [
        { id: "interior", label: "Cám. Interior (ESP32 IR)", stream: "gallinero_pequeno_esp32", active: true },
      ],
    },
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
    /* ── Dashboard 2-column layout ── */
    .seedy-dashboard-panel {
      padding: 16px;
      max-width: 1400px;
      margin: 0 auto;
    }
    /* ── Dashboard sensor strip ── */
    .seedy-dash-sensors {
      display: flex;
      gap: 8px;
      margin-bottom: 14px;
      flex-wrap: wrap;
      overflow-x: auto;
    }
    .seedy-sens-card {
      flex: 1 1 180px;
      min-width: 160px;
      max-width: 280px;
      background: var(--neutral-900, #111827);
      border: 1px solid var(--neutral-800, #1f2937);
      border-radius: 10px;
      padding: 10px 12px;
    }
    .seedy-sens-card.seedy-sens-weather {
      border-color: #2563eb;
      background: linear-gradient(145deg, #0f172a 0%, #111827 100%);
    }
    .seedy-sens-name {
      font-size: 0.75em;
      font-weight: 600;
      color: var(--neutral-400, #9ca3af);
      margin-bottom: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .seedy-sens-vals {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }
    .seedy-sens-val {
      font-size: 0.9em;
      font-weight: 700;
      white-space: nowrap;
    }
    .seedy-sens-val small {
      font-size: 0.75em;
      font-weight: 400;
      margin-left: 1px;
    }
    .seedy-sens-alert {
      font-size: 0.75em;
      font-weight: 700;
      padding: 2px 6px;
      border-radius: 6px;
      background: rgba(239,68,68,0.15);
      color: #fca5a5;
      white-space: nowrap;
    }
    .seedy-kpi-strip {
      display: flex;
      gap: 10px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }
    .seedy-kpi-card {
      flex: 1 1 0;
      min-width: 120px;
      background: var(--neutral-900, #111827);
      border: 1px solid var(--neutral-800, #1f2937);
      border-radius: 10px;
      padding: 10px 14px;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .seedy-kpi-icon { font-size: 20px; }
    .seedy-kpi-body { flex: 1; }
    .seedy-kpi-value { font-size: 1.15em; font-weight: 700; }
    .seedy-kpi-label {
      font-size: 0.65em;
      color: var(--neutral-500,#6b7280);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .seedy-dashboard-layout {
      display: grid;
      grid-template-columns: 3fr 1fr;
      gap: 14px;
      align-items: start;
    }
    @media (max-width: 960px) {
      .seedy-dashboard-layout {
        grid-template-columns: 1fr;
      }
      .seedy-kpi-strip {
        gap: 6px;
      }
      .seedy-kpi-card {
        min-width: 90px;
        padding: 8px 10px;
      }
    }
    .seedy-dash-left {}
    .seedy-dash-right {
      display: flex;
      flex-direction: column;
      gap: 12px;
    }
    .seedy-dash-hero {
      border-radius: 14px;
      overflow: hidden;
      border: 1px solid var(--neutral-800,#1f2937);
      background: #0f1419;
      position: relative;
    }
    .seedy-dash-hero iframe {
      width: 100%;
      min-height: 500px;
      height: 60vh;
      border: none;
      display: block;
    }
    .seedy-dash-hero .hero-expand {
      position: absolute; top: 10px; right: 10px;
      background: rgba(0,0,0,0.6); color: #fff; border: none;
      border-radius: 6px; padding: 5px 10px; font-size: 11px;
      cursor: pointer; z-index: 2; backdrop-filter: blur(4px);
      display: none;
    }
    .seedy-dash-hero .hero-expand:hover { background: rgba(0,0,0,0.8); }
    .seedy-hero-modes {
      position: absolute; top: 10px; right: 10px;
      display: flex; gap: 4px; z-index: 3;
    }
    .seedy-hero-modes button {
      background: rgba(0,0,0,0.55); color: #fff; border: 1px solid rgba(255,255,255,0.15);
      border-radius: 6px; padding: 5px 10px; font-size: 11px; font-weight: 600;
      cursor: pointer; backdrop-filter: blur(4px); transition: all 0.15s;
    }
    .seedy-hero-modes button:hover { background: rgba(0,0,0,0.8); }
    .seedy-hero-modes button.active {
      background: rgba(59,130,246,0.8); border-color: rgba(59,130,246,0.6);
    }
    .seedy-hero-render {
      width: 100%; min-height: 500px; height: 60vh;
      object-fit: cover; display: block;
      background: #0f1419;
    }
    .seedy-feed-section {
      margin-top: 14px;
      background: var(--neutral-900,#111827);
      border: 1px solid var(--neutral-800,#1f2937);
      border-radius: 12px;
      padding: 12px 14px;
      max-height: 220px;
      overflow-y: auto;
    }
    .seedy-feed-section h4 {
      margin: 0 0 8px;
      font-size: 0.85em;
      color: var(--neutral-400,#9ca3af);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .seedy-feed-item {
      display: flex;
      gap: 8px;
      padding: 4px 0;
      font-size: 0.8em;
      color: var(--neutral-300,#d1d5db);
      border-bottom: 1px solid var(--neutral-800,#1f2937);
    }
    .seedy-feed-item:last-child { border-bottom: none; }
    .seedy-feed-time {
      color: var(--neutral-500,#6b7280);
      font-variant-numeric: tabular-nums;
      white-space: nowrap;
    }
    .seedy-cam-thumb-row {
      background: var(--neutral-900,#111827);
      border: 1px solid var(--neutral-800,#1f2937);
      border-radius: 10px;
      padding: 10px 12px;
    }
    .seedy-cam-thumb-row h4 {
      margin: 0 0 8px;
      font-size: 0.8em;
      color: var(--neutral-400,#9ca3af);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .seedy-cam-thumb {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 5px 0;
      cursor: pointer;
      transition: opacity 0.15s;
    }
    .seedy-cam-thumb:hover { opacity: 0.8; }
    .seedy-cam-thumb img {
      width: 84px; height: 48px;
      border-radius: 4px; object-fit: cover; background: #000;
    }
    .seedy-cam-thumb-name { font-size: 0.8em; font-weight: 600; color: var(--neutral-200,#e5e7eb); }
    .seedy-cam-thumb-status { font-size: 0.65em; color: #22c55e; }
    .seedy-twin-links {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    .seedy-twin-links a {
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
      padding: 10px 16px;
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
    @media (max-width: 960px) {
      .seedy-twin-links { flex-direction: row; }
      .seedy-twin-links a { flex: 1; }
    }
    .seedy-sidebar-kpis {
      background: var(--neutral-900,#111827);
      border: 1px solid var(--neutral-800,#1f2937);
      border-radius: 10px;
      padding: 12px 14px;
    }
    .seedy-sidebar-kpis h4 {
      margin: 0 0 8px;
      font-size: 0.8em;
      color: var(--neutral-400,#9ca3af);
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }
    .seedy-sidebar-kpi-item {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 4px 0;
      font-size: 0.82em;
      border-bottom: 1px solid var(--neutral-800,#1f2937);
    }
    .seedy-sidebar-kpi-item:last-child { border-bottom: none; }
    .seedy-sidebar-kpi-label { color: var(--neutral-400,#9ca3af); }
    .seedy-sidebar-kpi-val { font-weight: 700; }
    .seedy-geotwin-btn {
      display: flex; align-items: center; justify-content: center; gap: 6px;
      width: 100%; padding: 10px 16px; border-radius: 8px;
      font-size: 0.85em; font-weight: 600; text-decoration: none;
      background: linear-gradient(135deg, #059669, #10b981); color: #fff;
      border: none; cursor: pointer; transition: all 0.15s;
    }
    .seedy-geotwin-btn:hover { opacity: 0.85; }
    /* ── Drone control panel ── */
    .seedy-drone-panel {
      margin-top: 10px;
      background: var(--neutral-900, #111827);
      border: 1px solid var(--neutral-800, #1f2937);
      border-radius: 10px;
      padding: 12px 14px;
    }
    .seedy-drone-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 10px;
    }
    .seedy-drone-title {
      font-size: 0.85em; font-weight: 700;
      display: flex; align-items: center; gap: 6px;
    }
    .seedy-drone-dot {
      width: 8px; height: 8px; border-radius: 50%; display: inline-block;
    }
    .seedy-drone-dot.ok { background: #22c55e; box-shadow: 0 0 6px #22c55e; }
    .seedy-drone-dot.off { background: #6b7280; }
    .seedy-drone-dot.fly { background: #f59e0b; animation: seedy-pulse 1s infinite; }
    .seedy-drone-stats {
      display: flex; gap: 12px; margin-bottom: 10px; font-size: 0.75em;
    }
    .seedy-drone-stat { display: flex; flex-direction: column; align-items: center; }
    .seedy-drone-stat-val { font-weight: 700; font-size: 1.2em; }
    .seedy-drone-stat-label { color: var(--neutral-500, #6b7280); text-transform: uppercase; font-size: 0.8em; letter-spacing: 0.5px; }
    .seedy-drone-actions { display: flex; gap: 6px; }
    .seedy-drone-btn {
      flex: 1; padding: 7px 10px; border-radius: 6px;
      font-size: 0.78em; font-weight: 600; border: none;
      cursor: pointer; transition: all 0.15s;
      display: flex; align-items: center; justify-content: center; gap: 4px;
    }
    .seedy-drone-btn.connect { background: linear-gradient(135deg, #2563eb, #3b82f6); color: #fff; }
    .seedy-drone-btn.connect:hover { opacity: 0.85; }
    .seedy-drone-btn.disconnect { background: linear-gradient(135deg, #dc2626, #ef4444); color: #fff; }
    .seedy-drone-btn.disconnect:hover { opacity: 0.85; }
    .seedy-drone-btn.fly-btn { background: linear-gradient(135deg, #d97706, #f59e0b); color: #fff; }
    .seedy-drone-btn.fly-btn:hover { opacity: 0.85; }
    .seedy-drone-btn:disabled { opacity: 0.4; cursor: not-allowed; }
    .seedy-drone-log {
      margin-top: 8px; font-size: 0.7em; color: var(--neutral-500, #6b7280);
      max-height: 48px; overflow-y: auto;
    }
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
    .seedy-ave-modal-actions .capture-id-btn {
      background: linear-gradient(135deg, #f59e0b, #d97706);
      color: #fff;
    }
    .seedy-ave-modal-actions .capture-id-btn:hover { opacity: 0.85; }
    .seedy-ave-modal-actions .capture-id-btn:disabled { opacity: 0.5; cursor: wait; }
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
    /* ── Identification result panel ── */
    .seedy-id-panel {
      margin-top: 12px;
      padding: 14px;
      border-radius: 10px;
      background: rgba(16,185,129,0.08);
      border: 1px solid rgba(16,185,129,0.25);
    }
    .seedy-id-panel.rejected {
      background: rgba(239,68,68,0.08);
      border-color: rgba(239,68,68,0.25);
    }
    .seedy-id-header {
      display: flex;
      gap: 14px;
      align-items: flex-start;
    }
    .seedy-id-photo {
      width: 140px;
      height: 140px;
      object-fit: cover;
      border-radius: 8px;
      cursor: zoom-in;
      flex-shrink: 0;
      border: 2px solid rgba(16,185,129,0.3);
    }
    .seedy-id-info {
      flex: 1;
      font-size: 0.82em;
      line-height: 1.55;
    }
    .seedy-id-info .breed {
      font-size: 1.15em;
      font-weight: 700;
      color: var(--neutral-100, #f3f4f6);
    }
    .seedy-id-info .conf {
      display: inline-block;
      padding: 1px 8px;
      border-radius: 12px;
      font-size: 0.85em;
      font-weight: 600;
      margin-left: 6px;
    }
    .seedy-id-info .conf.high { background: #059669; color: #fff; }
    .seedy-id-info .conf.med  { background: #d97706; color: #fff; }
    .seedy-id-info .conf.low  { background: #dc2626; color: #fff; }
    .seedy-id-info .features {
      margin-top: 4px;
      color: var(--neutral-400, #9ca3af);
    }
    .seedy-id-info .reasoning {
      margin-top: 6px;
      font-style: italic;
      color: var(--neutral-400, #9ca3af);
    }
    .seedy-id-actions {
      display: flex;
      gap: 8px;
      margin-top: 12px;
    }
    .seedy-id-actions button {
      padding: 7px 16px;
      border-radius: 8px;
      font-size: 0.82em;
      font-weight: 600;
      border: none;
      cursor: pointer;
      transition: opacity 0.15s;
    }
    .seedy-id-actions button:hover { opacity: 0.85; }
    .seedy-id-actions .confirm { background: #059669; color: #fff; }
    .seedy-id-actions .reject  { background: #dc2626; color: #fff; }
    .seedy-id-actions .correct { background: #d97706; color: #fff; }
    .seedy-id-actions .download { background: #6366f1; color: #fff; }
    .seedy-id-actions button:disabled { opacity: 0.4; cursor: wait; }
    .seedy-correct-form {
      margin-top: 10px;
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      align-items: center;
    }
    .seedy-correct-form select, .seedy-correct-form input {
      padding: 5px 8px;
      border-radius: 6px;
      border: 1px solid rgba(255,255,255,0.15);
      background: rgba(255,255,255,0.06);
      color: #e5e7eb;
      font-size: 0.85em;
    }
    /* ── Manual ID mode overlay ── */
    .seedy-idmode-overlay {
      position: fixed;
      inset: 0;
      z-index: 10001;
      background: rgba(0,0,0,0.92);
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
    }
    .seedy-idmode-toolbar {
      display: flex;
      gap: 10px;
      padding: 12px 16px;
      align-items: center;
      color: #fff;
      font-size: 14px;
      font-weight: 600;
    }
    .seedy-idmode-toolbar button {
      padding: 8px 16px;
      border-radius: 8px;
      font-weight: 600;
      font-size: 13px;
      border: none;
      cursor: pointer;
      transition: 0.15s;
    }
    .seedy-idmode-toolbar .close-btn {
      background: rgba(255,255,255,0.15);
      color: #fff;
    }
    .seedy-idmode-toolbar .close-btn:hover { background: rgba(255,255,255,0.25); }
    .seedy-idmode-toolbar .refresh-btn {
      background: #3b82f6;
      color: #fff;
    }
    .seedy-idmode-toolbar .refresh-btn:hover { background: #2563eb; }
    .seedy-idmode-toolbar .refresh-btn:disabled { opacity: 0.5; cursor: wait; }
    .seedy-idmode-canvas-wrap {
      position: relative;
      max-width: 95vw;
      max-height: 75vh;
      display: flex;
      align-items: center;
      justify-content: center;
    }
    .seedy-idmode-canvas-wrap canvas {
      max-width: 95vw;
      max-height: 75vh;
      border-radius: 8px;
      cursor: crosshair;
      object-fit: contain;
    }
    .seedy-idmode-assign {
      position: fixed;
      z-index: 10002;
      background: var(--neutral-900, #1a1a2e);
      border: 1px solid var(--neutral-700, #374151);
      border-radius: 14px;
      width: 340px;
      max-height: 80vh;
      overflow-y: auto;
      box-shadow: 0 16px 48px rgba(0,0,0,0.5);
      color: #f1f5f9;
    }
    .seedy-idmode-assign-header {
      padding: 14px 16px 8px;
      display: flex;
      gap: 12px;
      align-items: center;
    }
    .seedy-idmode-assign-header img {
      width: 90px;
      height: 90px;
      object-fit: cover;
      border-radius: 10px;
      background: #222;
    }
    .seedy-idmode-assign-header .info {
      flex: 1;
      font-size: 0.85em;
    }
    .seedy-idmode-assign-header .info .breed-guess {
      font-size: 1.1em;
      font-weight: 700;
      color: #f59e0b;
    }
    .seedy-idmode-assign-list {
      max-height: 300px;
      overflow-y: auto;
      margin: 0 8px 8px;
    }
    .seedy-idmode-assign-list .ave-row {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 8px;
      cursor: pointer;
      transition: background 0.1s;
      font-size: 0.85em;
    }
    .seedy-idmode-assign-list .ave-row:hover {
      background: rgba(255,255,255,0.08);
    }
    .seedy-idmode-assign-list .ave-row .ave-thumb {
      width: 36px;
      height: 36px;
      border-radius: 6px;
      object-fit: cover;
      background: #333;
      flex-shrink: 0;
    }
    .seedy-idmode-assign-list .ave-row .ave-detail {
      flex: 1;
    }
    .seedy-idmode-assign-list .ave-row .anilla {
      font-family: monospace;
      font-weight: 700;
      color: #d4a44a;
    }
    .seedy-idmode-assign-list .ave-row .assigned {
      font-size: 0.75em;
      color: #059669;
    }
    .seedy-idmode-assign-list .ave-row .unassigned {
      font-size: 0.75em;
      color: #9ca3af;
    }
    .seedy-idmode-assign-list .ave-row.has-photo {
      opacity: 0.5;
    }
    .seedy-idmode-assign-close {
      position: absolute;
      top: 8px;
      right: 8px;
      background: rgba(255,255,255,0.1);
      color: #fff;
      border: none;
      border-radius: 50%;
      width: 28px;
      height: 28px;
      font-size: 14px;
      cursor: pointer;
    }
    .seedy-idmode-status {
      padding: 8px 16px;
      text-align: center;
      font-size: 12px;
      color: #9ca3af;
    }

    /* ── Devices / IoT page ── */
    .seedy-devices-page { padding: 20px 24px; }
    .seedy-devices-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 20px;
    }
    .seedy-devices-header h2 {
      margin: 0; font-size: 1.4em; font-weight: 700;
      color: var(--neutral-100, #f3f4f6);
    }
    .seedy-devices-header .seedy-z2m-link {
      font-size: 0.75em; color: #3b82f6; text-decoration: none;
      padding: 4px 10px; border: 1px solid #3b82f6; border-radius: 6px;
    }
    .seedy-devices-header .seedy-z2m-link:hover { background: rgba(59,130,246,0.15); }
    .seedy-devices-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr));
      gap: 16px;
    }
    .seedy-device-card {
      background: var(--neutral-900, #111827);
      border: 1px solid var(--neutral-800, #1f2937);
      border-radius: 14px; padding: 18px 20px;
      transition: border-color 0.2s;
    }
    .seedy-device-card:hover { border-color: #3b82f6; }
    .seedy-device-card.offline { opacity: 0.5; }
    .seedy-device-card-header {
      display: flex; align-items: center; justify-content: space-between;
      margin-bottom: 14px;
    }
    .seedy-device-card-header h3 {
      margin: 0; font-size: 1.05em; font-weight: 600;
      color: var(--neutral-100, #f3f4f6);
    }
    .seedy-device-card-header .seedy-device-status {
      font-size: 0.7em; font-weight: 600; padding: 3px 8px;
      border-radius: 20px; text-transform: uppercase; letter-spacing: 0.5px;
    }
    .seedy-device-card-header .seedy-device-status.online {
      background: rgba(34,197,94,0.15); color: #22c55e;
    }
    .seedy-device-card-header .seedy-device-status.offline {
      background: rgba(107,114,128,0.15); color: #6b7280;
    }
    .seedy-device-readings {
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px;
      margin-bottom: 14px;
    }
    .seedy-reading {
      background: var(--neutral-800, #1f2937);
      border-radius: 10px; padding: 12px; text-align: center;
    }
    .seedy-reading-icon { font-size: 1.3em; margin-bottom: 4px; }
    .seedy-reading-value {
      font-size: 1.4em; font-weight: 700;
      color: var(--neutral-100, #f3f4f6);
    }
    .seedy-reading-label {
      font-size: 0.65em; color: var(--neutral-500, #6b7280);
      text-transform: uppercase; letter-spacing: 0.5px; margin-top: 2px;
    }
    .seedy-device-meta {
      display: flex; justify-content: space-between; align-items: center;
      font-size: 0.75em; color: var(--neutral-500, #6b7280);
      border-top: 1px solid var(--neutral-800, #1f2937);
      padding-top: 10px;
    }
    .seedy-device-meta .seedy-lqi-bar {
      display: inline-flex; align-items: center; gap: 4px;
    }
    .seedy-lqi-bar span {
      display: inline-block; width: 3px; border-radius: 2px;
      background: var(--neutral-700, #374151);
    }
    .seedy-lqi-bar span.active { background: #22c55e; }
    .seedy-devices-empty {
      text-align: center; padding: 60px 20px;
      color: var(--neutral-500, #6b7280);
    }
    .seedy-devices-empty .seedy-empty-icon { font-size: 3em; margin-bottom: 12px; }

    /* ── Air Quality info panel ── */
    .seedy-air-quality-info {
      margin: 8px 0 4px;
      padding: 0;
    }
    .seedy-air-quality-info details {
      background: rgba(255,255,255,0.03);
      border: 1px solid rgba(255,255,255,0.08);
      border-radius: 8px;
      padding: 0;
    }
    .seedy-air-quality-info summary {
      cursor: pointer;
      padding: 8px 12px;
      font-size: 0.82em;
      color: #9ca3af;
      user-select: none;
    }
    .seedy-air-quality-info summary:hover { color: #d1d5db; }
    .seedy-air-quality-info details[open] summary { border-bottom: 1px solid rgba(255,255,255,0.06); margin-bottom: 0; }
    .seedy-limits-table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.78em;
      margin: 0;
      padding: 8px 10px;
    }
    .seedy-limits-table th, .seedy-limits-table td {
      padding: 5px 8px;
      text-align: left;
      border-bottom: 1px solid rgba(255,255,255,0.06);
      color: #d1d5db;
    }
    .seedy-limits-table th {
      color: #9ca3af;
      font-weight: 600;
      font-size: 0.9em;
    }
    .seedy-limits-table tr:last-child td { border-bottom: none; }

    /* ── Soil sensor card ── */
    .seedy-soil-card { border-color: #854d0e; }
    .seedy-soil-alert {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px; margin: 0 12px 8px; border-radius: 8px;
      font-size: 0.88em; line-height: 1.3;
    }
    .seedy-soil-alert-icon { font-size: 1.4em; flex-shrink: 0; }
    .seedy-soil-alert-urgent {
      background: rgba(239,68,68,0.15); border: 1px solid rgba(239,68,68,0.4); color: #fca5a5;
      animation: seedy-soil-pulse 2s ease-in-out infinite;
    }
    .seedy-soil-alert-warning {
      background: rgba(245,158,11,0.12); border: 1px solid rgba(245,158,11,0.3); color: #fcd34d;
    }
    .seedy-soil-alert-info {
      background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.25); color: #93c5fd;
    }
    @keyframes seedy-soil-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(239,68,68,0.3); }
      50% { box-shadow: 0 0 8px 2px rgba(239,68,68,0.15); }
    }

    /* ── Infrastructure card ── */
    .seedy-infra-card { border-color: #4b5563; opacity: 0.8; }
    .seedy-infra-card .seedy-device-card-header h3 { font-size: 0.95em; }

    @keyframes seedy-device-pulse {
      0%, 100% { box-shadow: 0 0 0 0 rgba(59,130,246,0.3); }
      50% { box-shadow: 0 0 0 6px rgba(59,130,246,0); }
    }

    /* ── Weather Station card (Ecowitt) ── */
    .seedy-device-card.weather-station {
      border-color: #2563eb;
      background: linear-gradient(145deg, #0f172a 0%, #111827 100%);
    }
    .seedy-weather-readings {
      display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;
      margin-bottom: 10px;
    }
    .seedy-weather-readings .seedy-reading { padding: 10px 8px; }
    .seedy-weather-readings .seedy-reading-value { font-size: 1.2em; }
    .seedy-weather-extra {
      display: grid; grid-template-columns: 1fr 1fr; gap: 8px;
      margin-bottom: 14px;
    }
    .seedy-weather-extra .seedy-reading { padding: 8px; }
    .seedy-weather-extra .seedy-reading-value { font-size: 1.0em; }
    .seedy-weather-extra .seedy-reading-icon { font-size: 1.1em; }

    /* ── Rain accumulation row ── */
    .seedy-weather-rain {
      border-top: 1px solid rgba(255,255,255,0.08);
      padding: 10px 0 6px;
      margin-top: 4px;
    }
    .seedy-rain-title {
      display: block;
      font-size: 0.82em;
      color: #9ca3af;
      margin-bottom: 8px;
      font-weight: 500;
    }
    .seedy-rain-bars {
      display: flex;
      gap: 6px;
      justify-content: space-between;
    }
    .seedy-rain-item {
      flex: 1;
      text-align: center;
      background: rgba(59,130,246,0.08);
      border: 1px solid rgba(59,130,246,0.15);
      border-radius: 8px;
      padding: 8px 4px;
    }
    .seedy-rain-item.seedy-rain-total {
      background: rgba(59,130,246,0.15);
      border-color: rgba(59,130,246,0.3);
    }
    .seedy-rain-val {
      display: block;
      font-size: 0.95em;
      font-weight: 600;
      color: #93c5fd;
    }
    .seedy-rain-total .seedy-rain-val {
      color: #60a5fa;
      font-size: 1.05em;
    }
    .seedy-rain-lbl {
      display: block;
      font-size: 0.72em;
      color: #6b7280;
      margin-top: 2px;
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
      <button data-mode="identify">🏷️ ID</button>
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
    ws.onclose = function () {};

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
    } else if (mode === "identify") {
      img.classList.remove("loading");
      openIdModeOverlay(gallineroId, activeStream, cam);
      // Revert to yolo after opening overlay
      wrap.dataset.mode = "yolo";
      updateToggle(wrap, "yolo");
      refreshSnapshot(wrap, gallineroId);
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

  // ── Manual ID mode overlay ──
  var _idOverlayActive = false;
  var _cachedAves = null;

  async function _fetchAves() {
    if (_cachedAves && _cachedAves._ts && Date.now() - _cachedAves._ts < 30000) {
      return _cachedAves.list;
    }
    try {
      const resp = await fetch(`${OVOSFERA_API}/farms/${SEEDY_FARM}/aves`);
      if (!resp.ok) return [];
      const data = await resp.json();
      const list = Array.isArray(data) ? data : (data.aves || []);
      _cachedAves = { list: list, _ts: Date.now() };
      return list;
    } catch (e) {
      console.error("[Seedy] Error fetching aves:", e);
      return [];
    }
  }

  async function openIdModeOverlay(gallineroId, streamName, cam) {
    if (_idOverlayActive) return;
    _idOverlayActive = true;

    // gallinero real para censo/asignación (puede diferir del stream)
    const censusGallinero = cam.gallinero || cam.stream || streamName;

    const overlay = document.createElement("div");
    overlay.className = "seedy-idmode-overlay";

    const toolbar = document.createElement("div");
    toolbar.className = "seedy-idmode-toolbar";

    const titleSpan = document.createElement("span");
    titleSpan.textContent = `🏷️ ID Manual — ${cam.name}`;
    toolbar.appendChild(titleSpan);

    const refreshBtn = document.createElement("button");
    refreshBtn.className = "refresh-btn";
    refreshBtn.textContent = "📸 Capturar";
    toolbar.appendChild(refreshBtn);

    const autoIdBtn = document.createElement("button");
    autoIdBtn.className = "refresh-btn";
    autoIdBtn.style.cssText = "background:#7c3aed !important;margin-left:4px;opacity:0.5;cursor:not-allowed;";
    autoIdBtn.textContent = "🤖 Auto-ID";
    autoIdBtn.title = "Próximamente — Identifica automáticamente TODAS las aves";
    autoIdBtn.disabled = true;
    toolbar.appendChild(autoIdBtn);

    const closeBtn = document.createElement("button");
    closeBtn.className = "close-btn";
    closeBtn.textContent = "✕ Cerrar";
    closeBtn.addEventListener("click", () => {
      overlay.remove();
      _idOverlayActive = false;
    });
    toolbar.appendChild(closeBtn);

    overlay.appendChild(toolbar);

    const statusDiv = document.createElement("div");
    statusDiv.className = "seedy-idmode-status";
    statusDiv.textContent = "Capturando frame + YOLO...";
    overlay.appendChild(statusDiv);

    const canvasWrap = document.createElement("div");
    canvasWrap.className = "seedy-idmode-canvas-wrap";
    const canvas = document.createElement("canvas");
    canvasWrap.appendChild(canvas);
    overlay.appendChild(canvasWrap);

    document.body.appendChild(overlay);

    var currentDetections = null;
    var currentFrameImg = null;

    async function doCapture() {
      refreshBtn.disabled = true;
      statusDiv.textContent = "Capturando frame + YOLO...";
      // Remove any open assign panels
      overlay.querySelectorAll(".seedy-idmode-assign").forEach(el => el.remove());
      currentDetections = null;

      try {
        console.log("[Seedy ID] Fetching detect:", streamName);
        const resp = await fetch(`${SEEDY_API}/vision/identify/snapshot/${streamName}/detect`);
        if (!resp.ok) {
          statusDiv.textContent = `❌ Error captura: HTTP ${resp.status}`;
          console.error("[Seedy ID] Detect failed:", resp.status);
          refreshBtn.disabled = false;
          return;
        }
        const data = await resp.json();
        currentDetections = data.detections;
        console.log("[Seedy ID] Detections:", data.count, "inference:", data.inference_ms, "ms");

        if (!data.count) {
          statusDiv.textContent = "⚠️ No se detectaron aves — prueba capturar de nuevo";
          refreshBtn.disabled = false;
          return;
        }

        statusDiv.textContent = `🎯 ${data.count} ave(s) detectada(s) · ${data.inference_ms}ms — Haz clic en un ave para asignarla`;

        // Draw frame on canvas
        const frameImg = new Image();
        frameImg.onload = function () {
          currentFrameImg = frameImg;
          canvas.width = frameImg.naturalWidth;
          canvas.height = frameImg.naturalHeight;
          const ctx = canvas.getContext("2d");
          ctx.drawImage(frameImg, 0, 0);

          // Draw bboxes
          drawDetectionBoxes(ctx, canvas.width, canvas.height, data.detections);
          refreshBtn.disabled = false;
          console.log("[Seedy ID] Frame drawn:", canvas.width, "x", canvas.height, "dets:", data.detections.length);
        };
        frameImg.onerror = function () {
          statusDiv.textContent = "❌ Error cargando frame — intenta de nuevo";
          console.error("[Seedy ID] Frame image load failed");
          refreshBtn.disabled = false;
        };
        frameImg.src = "data:image/jpeg;base64," + data.frame_b64;
      } catch (e) {
        statusDiv.textContent = "❌ Error de red: " + e.message;
        console.error("[Seedy ID] Capture error:", e);
        refreshBtn.disabled = false;
      }
    }

    refreshBtn.addEventListener("click", doCapture);

    // Auto-ID: identificar todas las aves automáticamente con Together.ai + galería
    autoIdBtn.addEventListener("click", async function () {
      autoIdBtn.disabled = true;
      refreshBtn.disabled = true;
      autoIdBtn.textContent = "🤖 Analizando...";
      statusDiv.textContent = "🧠 Enviando aves a Together.ai para identificación visual...";
      overlay.querySelectorAll(".seedy-idmode-assign").forEach(function (el) { el.remove(); });

      try {
        var resp = await fetch(SEEDY_API + "/vision/identify/auto-identify", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ gallinero_id: censusGallinero }),
        });
        if (!resp.ok) {
          statusDiv.textContent = "❌ Error auto-ID: " + resp.status;
          autoIdBtn.textContent = "🤖 Auto-ID";
          autoIdBtn.disabled = false;
          refreshBtn.disabled = false;
          return;
        }
        var data = await resp.json();

        // Draw frame
        var frameImg2 = new Image();
        frameImg2.onload = function () {
          currentFrameImg = frameImg2;
          canvas.width = frameImg2.naturalWidth;
          canvas.height = frameImg2.naturalHeight;
          var ctx = canvas.getContext("2d");
          ctx.drawImage(frameImg2, 0, 0);

          // Overlay results on each detection
          var identified = 0;
          var total = data.results ? data.results.length : 0;
          (data.results || []).forEach(function (r) {
            if (!r.best_match_anilla || r.confidence < 0.4) return;
            identified++;
            // Find approximate bbox from the crop (we don't have bbox in auto-identify)
            // Just show results as text overlay at bottom
          });

          // Show results panel
          var resultHtml = '<div style="position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:rgba(0,0,0,0.92);border:2px solid #22c55e;border-radius:12px;padding:16px;max-width:700px;max-height:60vh;overflow-y:auto;z-index:10002;color:#fff;font-size:14px;">';
          resultHtml += '<div style="font-size:16px;font-weight:700;margin-bottom:10px;color:#22c55e;">🤖 Auto-ID Results — ' + total + ' ave(s)</div>';

          (data.results || []).forEach(function (r, idx) {
            var conf = Math.round((r.confidence || 0) * 100);
            var confColor = conf >= 70 ? "#22c55e" : conf >= 40 ? "#f59e0b" : "#ef4444";
            var matchInfo = r.best_match_anilla || "❓ Sin match";
            var breedInfo = (r.breed || r.yolo_breed || "?") + (r.sex ? (r.sex === "male" ? " ♂" : " ♀") : "");
            var reasoning = r.reasoning || "";

            resultHtml += '<div style="display:flex;gap:10px;align-items:center;padding:8px;border-bottom:1px solid #333;' +
              (conf >= 70 ? 'background:rgba(34,197,94,0.1);' : '') + '">';

            if (r.crop_b64) {
              var src = r.crop_b64.startsWith("data:") ? r.crop_b64 : "data:image/jpeg;base64," + r.crop_b64;
              resultHtml += '<img src="' + src + '" style="width:60px;height:60px;object-fit:cover;border-radius:6px;border:2px solid ' + confColor + '">';
            }

            resultHtml += '<div style="flex:1">' +
              '<div style="font-weight:600;">' + matchInfo + ' <span style="color:' + confColor + '">' + conf + '%</span></div>' +
              '<div style="font-size:12px;color:#9ca3af">' + breedInfo + '</div>' +
              '<div style="font-size:11px;color:#6b7280;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">' + reasoning + '</div>' +
              '</div>';

            // Confirm button if high confidence
            if (r.best_match_id && conf >= 50 && r.crop_b64) {
              resultHtml += '<button class="auto-id-confirm" data-ave-id="' + r.best_match_id + '" data-anilla="' + (r.best_match_anilla || '') + '" data-idx="' + idx + '" ' +
                'style="background:#059669;color:#fff;border:none;border-radius:6px;padding:6px 10px;font-size:11px;font-weight:600;cursor:pointer;white-space:nowrap;">✅ Confirmar</button>';
            }

            resultHtml += '</div>';
          });

          resultHtml += '<div style="text-align:center;margin-top:10px;"><button class="auto-id-close" style="background:#374151;color:#fff;border:none;border-radius:8px;padding:8px 20px;cursor:pointer;font-weight:600;">Cerrar</button></div>';
          resultHtml += '</div>';

          var resultPanel = document.createElement("div");
          resultPanel.innerHTML = resultHtml;
          overlay.appendChild(resultPanel);

          // Close button
          resultPanel.querySelector(".auto-id-close").addEventListener("click", function () {
            resultPanel.remove();
          });

          // Confirm buttons — assign to OvoSfera
          resultPanel.querySelectorAll(".auto-id-confirm").forEach(function (btn) {
            btn.addEventListener("click", async function () {
              var aveId = parseInt(btn.dataset.aveId);
              var ridx = parseInt(btn.dataset.idx);
              var r = data.results[ridx];
              btn.disabled = true;
              btn.textContent = "⏳...";
              try {
                var assignResp = await fetch(SEEDY_API + "/vision/identify/manual-assign", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    ove_ave_id: aveId,
                    crop_b64: r.crop_b64 || "",
                    breed: r.breed || "",
                    color: r.color || "",
                    sex: r.sex === "male" ? "M" : r.sex === "female" ? "H" : "",
                    gallinero: censusGallinero,
                  }),
                });
                if (assignResp.ok) {
                  btn.textContent = "✅ OK";
                  btn.style.background = "#22c55e";
                  _cachedAves = null;
                } else {
                  btn.textContent = "❌ Error";
                  btn.style.background = "#ef4444";
                }
              } catch (e2) {
                btn.textContent = "❌ Red";
              }
            });
          });

          statusDiv.textContent = "🤖 Auto-ID completo: " + identified + "/" + total + " identificadas con confianza";
        };
        frameImg2.src = "data:image/jpeg;base64," + data.frame_b64;
      } catch (e) {
        statusDiv.textContent = "❌ Error: " + e.message;
      }
      autoIdBtn.textContent = "🤖 Auto-ID";
      autoIdBtn.disabled = false;
      refreshBtn.disabled = false;
    });

    // Click on canvas → find which bbox was clicked
    canvas.addEventListener("click", async function (e) {
      if (!currentDetections || !currentDetections.length || !currentFrameImg) {
        console.log("[Seedy ID] Canvas click ignored: no detections or frame");
        return;
      }
      const rect = canvas.getBoundingClientRect();
      const scaleX = canvas.width / rect.width;
      const scaleY = canvas.height / rect.height;
      const cx = (e.clientX - rect.left) * scaleX;
      const cy = (e.clientY - rect.top) * scaleY;

      // Find clicked detection (bbox is [x1_norm, y1_norm, x2_norm, y2_norm])
      var clicked = null;
      for (var i = 0; i < currentDetections.length; i++) {
        var det = currentDetections[i];
        var b = det.bbox;
        if (!b || b.length < 4) continue;
        var x1 = b[0] * canvas.width;
        var y1 = b[1] * canvas.height;
        var x2 = b[2] * canvas.width;
        var y2 = b[3] * canvas.height;
        if (cx >= x1 && cx <= x2 && cy >= y1 && cy <= y2) {
          clicked = det;
          break;
        }
      }
      if (!clicked) {
        console.log("[Seedy ID] Click at", Math.round(cx), Math.round(cy), "— no bbox hit");
        statusDiv.textContent = "⚠️ Haz clic DENTRO del recuadro de un ave";
        return;
      }

      console.log("[Seedy ID] Clicked det:", clicked.index, clicked.breed_guess, "conf:", clicked.breed_confidence);
      statusDiv.textContent = "✅ Ave seleccionada — cargando panel de asignación...";

      // Highlight selected bbox
      var ctx = canvas.getContext("2d");
      ctx.drawImage(currentFrameImg, 0, 0);
      drawDetectionBoxes(ctx, canvas.width, canvas.height, currentDetections, clicked.index);

      // Show assign panel
      showAssignPanel(overlay, canvas, clicked, e.clientX, e.clientY, censusGallinero, gallineroId, function () {
        // After assign: redraw without assigned detection
        currentDetections = currentDetections.filter(d => d.index !== clicked.index);
        ctx.drawImage(currentFrameImg, 0, 0);
        drawDetectionBoxes(ctx, canvas.width, canvas.height, currentDetections);
        statusDiv.textContent = `✅ Asignada — quedan ${currentDetections.length} detección(es)`;
      });
    });

    // First capture
    doCapture();
  }

  function drawDetectionBoxes(ctx, w, h, detections, highlightIndex) {
    var colors = ["#22c55e", "#3b82f6", "#f59e0b", "#ef4444", "#a855f7", "#06b6d4", "#ec4899"];
    for (var i = 0; i < detections.length; i++) {
      var det = detections[i];
      var b = det.bbox;
      if (!b || b.length < 4) continue;
      var x1 = b[0] * w, y1 = b[1] * h, x2 = b[2] * w, y2 = b[3] * h;
      var bw = x2 - x1, bh = y2 - y1;
      var isHighlighted = (highlightIndex !== undefined && det.index === highlightIndex);
      var color = isHighlighted ? "#fff" : colors[i % colors.length];

      ctx.strokeStyle = color;
      ctx.lineWidth = isHighlighted ? 4 : 2;
      ctx.strokeRect(x1, y1, bw, bh);

      // Label
      var label = det.breed_guess || "Ave";
      if (det.breed_confidence > 0) label += " " + Math.round(det.breed_confidence * 100) + "%";
      ctx.font = "bold 16px sans-serif";
      var tw = ctx.measureText(label).width + 12;
      ctx.fillStyle = color;
      ctx.fillRect(x1, y1 - 24, tw, 24);
      ctx.fillStyle = isHighlighted ? "#000" : "#fff";
      ctx.fillText(label, x1 + 6, y1 - 6);

      if (isHighlighted) {
        ctx.fillStyle = "rgba(255,255,255,0.15)";
        ctx.fillRect(x1, y1, bw, bh);
      }
    }
  }

  async function showAssignPanel(overlay, canvas, detection, clickX, clickY, streamName, gallineroId, onAssigned) {
    console.log("[Seedy ID] showAssignPanel: det=", detection.index, "breed=", detection.breed_guess, "stream=", streamName);
    // Remove any existing panel
    overlay.querySelectorAll(".seedy-idmode-assign").forEach(el => el.remove());

    var panel = document.createElement("div");
    panel.className = "seedy-idmode-assign";

    // Position near click but within viewport
    var px = Math.min(clickX + 10, window.innerWidth - 360);
    var py = Math.min(clickY - 50, window.innerHeight - 450);
    if (py < 10) py = 10;
    panel.style.position = "fixed";
    panel.style.left = px + "px";
    panel.style.top = py + "px";

    // Close button
    var closeBtn = document.createElement("button");
    closeBtn.className = "seedy-idmode-assign-close";
    closeBtn.textContent = "✕";
    closeBtn.addEventListener("click", () => panel.remove());
    panel.appendChild(closeBtn);

    // Header with crop
    var header = document.createElement("div");
    header.className = "seedy-idmode-assign-header";
    var cropImg = document.createElement("img");
    cropImg.src = detection.crop_b64
      ? (detection.crop_b64.startsWith("data:") ? detection.crop_b64 : "data:image/jpeg;base64," + detection.crop_b64)
      : "";
    header.appendChild(cropImg);

    var infoDiv = document.createElement("div");
    infoDiv.className = "info";
    infoDiv.innerHTML =
      '<div class="breed-guess">' + (detection.breed_guess || "Desconocida") + '</div>' +
      '<div>Conf: ' + Math.round((detection.breed_confidence || 0) * 100) + '%</div>' +
      (detection.breed_color ? '<div>Color: ' + detection.breed_color + '</div>' : '') +
      (detection.breed_sex && detection.breed_sex !== "unknown" ? '<div>Sexo: ' + (detection.breed_sex === "M" ? "♂ Macho" : "♀ Hembra") + '</div>' : '');
    header.appendChild(infoDiv);
    panel.appendChild(header);

    // Ave list (moved before smart match so it's available in closures)
    var listDiv = document.createElement("div");
    listDiv.className = "seedy-idmode-assign-list";
    listDiv.innerHTML = '<div style="padding:12px;text-align:center;color:#9ca3af">Cargando aves...</div>';
    panel.appendChild(listDiv);

    overlay.appendChild(panel);

    // Fetch aves
    console.log("[Seedy ID] Fetching aves from OvoSfera...");
    var aves = await _fetchAves();
    console.log("[Seedy ID] Aves loaded:", aves.length);
    listDiv.innerHTML = "";

    if (!aves.length) {
      listDiv.innerHTML = '<div style="padding:12px;text-align:center;color:#ef4444">❌ No se encontraron aves en OvoSfera</div>';
      return;
    }

    // Build score map from suggested_aves (from detect endpoint)
    var sugMap = {};
    if (detection.suggested_aves && detection.suggested_aves.length) {
      detection.suggested_aves.forEach(function (s, idx) {
        sugMap[s.id] = { score: s.score, rank: idx };
      });
    }

    // Sort: by suggestion score (highest first), then unassigned, then anilla
    aves.sort(function (a, b) {
      var sa = sugMap[a.id] ? sugMap[a.id].score : -100;
      var sb = sugMap[b.id] ? sugMap[b.id].score : -100;
      if (sa !== sb) return sb - sa;
      var aHas = a.foto ? 1 : 0;
      var bHas = b.foto ? 1 : 0;
      if (aHas !== bHas) return aHas - bHas;
      return (a.anilla || "").localeCompare(b.anilla || "");
    });

    aves.forEach(function (ave) {
      var sug = sugMap[ave.id];
      var isTop = sug && sug.rank === 0 && sug.score > 30;
      var row = document.createElement("div");
      row.className = "ave-row" + (ave.foto && !isTop ? " has-photo" : "");
      row.dataset.anilla = ave.anilla || "";
      if (isTop) row.style.background = "rgba(34,197,94,0.15)";

      var thumb = document.createElement("img");
      thumb.className = "ave-thumb";
      thumb.src = ave.foto || "";
      if (!ave.foto) thumb.style.background = "#444";
      row.appendChild(thumb);

      var detail = document.createElement("div");
      detail.className = "ave-detail";
      var scoreTag = sug && sug.score > 0
        ? ' <span style="background:rgba(34,197,94,0.3);padding:1px 5px;border-radius:4px;font-size:0.7em">★ ' + sug.score + '</span>'
        : '';
      detail.innerHTML =
        '<span class="anilla">' + (ave.anilla || "SIN ANILLA") + '</span> ' +
        (ave.raza ? ave.raza : '') +
        (ave.color ? ' · ' + ave.color : '') +
        (ave.sexo ? ' · ' + (ave.sexo === "M" ? "♂" : "♀") : '') +
        scoreTag +
        '<br>' +
        (ave.ai_vision_id
          ? '<span class="assigned">✔ ' + ave.ai_vision_id + '</span>'
          : '<span class="unassigned">Sin identificar</span>');
      row.appendChild(detail);

      row.addEventListener("click", async function () {
        if (row.dataset.assigning === "1") return;
        row.dataset.assigning = "1";
        row.style.opacity = "0.4";
        row.style.pointerEvents = "none";
        console.log("[Seedy ID] Assigning to ave:", ave.id, ave.anilla, "crop_len:", (detection.crop_b64 || "").length);

        try {
          var payload = {
            ove_ave_id: ave.id,
            crop_b64: detection.crop_b64 || "",
            breed: ave.raza || detection.breed_guess || "",
            color: ave.color || detection.breed_color || "",
            sex: ave.sexo || detection.breed_sex || "",
            gallinero: streamName,
          };
          console.log("[Seedy ID] POST manual-assign payload size:", JSON.stringify(payload).length, "bytes");
          var resp = await fetch(`${SEEDY_API}/vision/identify/manual-assign`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
          console.log("[Seedy ID] Assign response:", resp.status);
          if (!resp.ok) {
            var errText = await resp.text();
            console.error("[Seedy ID] Assign error:", errText);
            alert("❌ Error al asignar: " + errText);
            row.style.opacity = "";
            row.style.pointerEvents = "";
            row.dataset.assigning = "";
            return;
          }
          var result = await resp.json();
          console.log("[Seedy ID] Assign OK:", result);
          // Success
          _cachedAves = null; // invalidate cache
          panel.remove();
          if (onAssigned) onAssigned();
        } catch (e) {
          console.error("[Seedy ID] Assign network error:", e);
          alert("❌ Error de red al asignar: " + e.message);
          row.style.opacity = "";
          row.style.pointerEvents = "";
          row.dataset.assigning = "";
        }
      });

      listDiv.appendChild(row);
    });
  }

  // ── Find gallinero cards — 3 strategies ──
  function findGallineroCards() {
    // Strategy 1: Direct .nf-card class
    let cards = document.querySelectorAll(".nf-card");
    if (cards.length) return Array.from(cards);

    // Strategy 2: .nf-card-pad → parent is the card
    const pads = document.querySelectorAll(".nf-card-pad, [class*='card-pad'], [class*='CardPad']");
    if (pads.length) return Array.from(pads).map(p => p.parentElement).filter(Boolean);

    // Strategy 3: Generic divs with card-like class containing gallinero text
    const allCards = document.querySelectorAll("div[class*='card'], div[class*='Card']");
    const result = [];
    allCards.forEach(el => {
      const text = el.textContent || "";
      if (text.match(/#\d+/) && (text.includes("Durrif") || text.includes("Gallinero") || text.includes("gallinero") || text.includes("Zona"))) {
        result.push(el);
      }
    });
    return result;
  }

  // ── Fix aves_count in gallinero card (OvoSfera shows 0, real count from census) ──
  function _fixAvesCount(card, realCount) {
    // OvoSfera formats: "0/30", "0 / 30", or just "0" next to aves icon
    var walker = document.createTreeWalker(card, NodeFilter.SHOW_TEXT, null, false);
    var node;
    while ((node = walker.nextNode())) {
      // Match "0/N" or "0 / N" patterns
      if (/^\s*0\s*\/\s*\d+/.test(node.textContent)) {
        node.textContent = node.textContent.replace(/0\s*\//, realCount + " /");
      }
    }
  }

  // ── Inject cameras into gallinero cards ──
  // ── Inject camera thumbnails in gallineros LIST page ──
  function injectGallineroListThumbnails() {
    const cards = findGallineroCards();
    cards.forEach(function(card) {
      if (card.querySelector(".seedy-list-cam-thumb")) return;
      var gid = parseGallineroId(card);

      // Ocultar gallineros fusionados (ID 3 etc.)
      if (gid && !CAMERA_MAP[gid]) {
        var text = card.textContent || "";
        if (text.toLowerCase().includes("fusionado")) {
          card.style.display = "none";
          return;
        }
      }

      if (!gid || !CAMERA_MAP[gid]) return;

      // Corregir aves_count: OvoSfera muestra 0 — nosotros sabemos que son ~26
      _fixAvesCount(card, 26);

      var cam = CAMERA_MAP[gid];

      var wrap = document.createElement("div");
      wrap.className = "seedy-list-cam-thumb";
      wrap.style.cssText = "position:relative;margin:8px 0;border-radius:8px;overflow:hidden;cursor:pointer;border:1px solid rgba(255,255,255,.1)";

      var img = document.createElement("img");
      img.src = SEEDY_API + "/ovosfera/camera/" + gid + "/snapshot?_t=" + Date.now();
      img.alt = cam.name;
      img.style.cssText = "width:100%;height:120px;object-fit:cover;display:block;background:#111";
      img.onerror = function() { this.style.background = "#1f2937"; this.alt = "Sin señal"; };
      wrap.appendChild(img);

      var badge = document.createElement("div");
      badge.style.cssText = "position:absolute;bottom:6px;left:6px;background:rgba(0,0,0,.65);color:#22c55e;font-size:10px;padding:2px 8px;border-radius:4px;backdrop-filter:blur(4px)";
      badge.textContent = "● " + cam.name;
      wrap.appendChild(badge);

      wrap.addEventListener("click", function() {
        openCameraModal(gid);
      });

      // Insert into card
      var contentDiv = card.firstElementChild || card;
      var children = contentDiv.children;
      if (children.length > 2) {
        contentDiv.insertBefore(wrap, children[children.length - 1]);
      } else {
        contentDiv.appendChild(wrap);
      }
    });

    // Refresh thumbnails every 10s
    if (!window._galListThumbTimer) {
      window._galListThumbTimer = setInterval(function() {
        document.querySelectorAll(".seedy-list-cam-thumb img").forEach(function(img) {
          var src = img.src.split("?")[0];
          img.src = src + "?_t=" + Date.now();
        });
      }, 10000);
    }
  }

  // ── Camera fullscreen modal (opened from gallinero list thumbnails) ──
  function openCameraModal(gid) {
    var cam = CAMERA_MAP[gid];
    if (!cam) return;

    // Remove any previous camera modal
    var prev = document.querySelector(".seedy-camera-modal-overlay");
    if (prev) prev.remove();

    var overlay = document.createElement("div");
    overlay.className = "seedy-camera-modal-overlay";
    overlay.style.cssText = "position:fixed;inset:0;z-index:99999;background:rgba(0,0,0,.92);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px";

    // Close on backdrop click
    overlay.addEventListener("click", function(e) {
      if (e.target === overlay) closeCameraModal(overlay);
    });

    // Header bar
    var header = document.createElement("div");
    header.style.cssText = "width:100%;max-width:900px;display:flex;justify-content:space-between;align-items:center;margin-bottom:12px";
    var title = document.createElement("div");
    title.style.cssText = "color:#fff;font-size:18px;font-weight:600";
    title.textContent = "📷 " + cam.name;
    header.appendChild(title);
    var closeBtn = document.createElement("button");
    closeBtn.textContent = "✕";
    closeBtn.style.cssText = "background:none;border:none;color:#fff;font-size:24px;cursor:pointer;padding:4px 12px";
    closeBtn.addEventListener("click", function() { closeCameraModal(overlay); });
    header.appendChild(closeBtn);
    overlay.appendChild(header);

    // Camera element (reuse buildCameraElement)
    var camEl = buildCameraElement(gid);
    if (camEl) {
      camEl.style.cssText = "width:100%;max-width:900px;border-radius:12px;overflow:hidden";
      overlay.appendChild(camEl);
    }

    // Close with Escape key
    overlay._escHandler = function(e) {
      if (e.key === "Escape") closeCameraModal(overlay);
    };
    document.addEventListener("keydown", overlay._escHandler);

    document.body.appendChild(overlay);

    // Start refresh for the modal camera
    startRefreshLoop();
  }

  function closeCameraModal(overlay) {
    if (overlay._escHandler) document.removeEventListener("keydown", overlay._escHandler);
    stopRefreshLoop();
    overlay.remove();
  }

  function injectCameras() {
    const cards = findGallineroCards();
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
      } else {
        // Fallback: append directly to card
        card.appendChild(camEl);
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
    if (_feedTimer) {
      clearInterval(_feedTimer);
      _feedTimer = null;
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
  function isGallinerosListPage() {
    // /gallineros but NOT /gallineros/:id
    return window.location.pathname.match(/\/gallineros\/?$/) !== null;
  }

  function isGallineroDetailPage() {
    return window.location.pathname.match(/\/gallineros\/\d+/) !== null;
  }

  function isGallinerosPage() {
    // Matches any /gallineros path (list or detail)
    return window.location.pathname.includes("/gallineros");
  }

  function isDashboardPage() {
    return window.location.pathname.includes("/dashboard");
  }

  function isDigitalTwinPage() {
    return window.location.pathname.includes("/digital-twin");
  }

  function isDigitalTwin2DPage() {
    return window.location.pathname.includes("/digital-twin/2d");
  }

  function isDigitalTwin3DPage() {
    return window.location.pathname.includes("/digital-twin/3d");
  }

  function isSitePage() {
    return window.location.pathname.match(/\/farm\/[^/]+\/site/) !== null;
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

  function isDevicesPage() {
    return window.location.pathname.match(/\/farm\/[^/]+\/devices/);
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
            '<button class="capture-id-btn" data-ave-id="' + aveId + '">📸 Capturar + Identificar</button>' +
            '<button class="cam-btn" data-ave-id="' + aveId + '">📹 Cámara en vivo</button>' +
            '<button class="edit-btn" data-ave-id="' + aveId + '">✏️ Editar en OvoSfera</button>' +
          '</div>' +
          '<div class="seedy-capture-status" style="margin:8px 0;font-size:0.85em;color:#666"></div>' +
          '<div class="seedy-id-panel" style="display:none"></div>';

        // Photo click → fullscreen (robust: wait for load if needed)
        var photoEl = modal.querySelector(".seedy-ave-modal-photo");
        if (photoEl && photoEl.tagName === "IMG") {
          photoEl.style.cursor = "zoom-in";
          function enableZoom() {
            photoEl.addEventListener("click", function () {
              openFullscreen(photoEl.src, nombre);
            });
          }
          if (photoEl.complete && photoEl.naturalWidth > 0) {
            enableZoom();
          } else {
            photoEl.addEventListener("load", enableZoom);
          }
        }

        // ── Capture + Identify button ──
        var capIdBtn = modal.querySelector(".capture-id-btn");
        var capStatus = modal.querySelector(".seedy-capture-status");
        var capIdPanel = modal.querySelector(".seedy-id-panel");

        capIdBtn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          capIdBtn.disabled = true;
          capIdBtn.innerHTML = "⏳ Capturando + identificando...";
          capStatus.textContent = "Buscando al ave en las cámaras y analizando con Qwen2.5-VL...";
          capIdPanel.style.display = "none";

          fetch(SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/capture-identify", {
            method: "POST",
          })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              capIdBtn.innerHTML = "📸 Capturar + Identificar";
              capIdBtn.disabled = false;

              if (!data.success) {
                capStatus.textContent = "⚠️ " + (data.message || "No se pudo capturar");
                return;
              }

              capStatus.textContent = "Foto capturada: " + data.resolution + " — revisa la identificación:";

              var id = data.identification || {};
              var conf = id.confidence || 0;
              var confClass = conf >= 0.75 ? "high" : conf >= 0.5 ? "med" : "low";
              var features = (id.distinctive_features || []).join(", ");

              capIdPanel.style.display = "block";
              capIdPanel.innerHTML =
                '<div class="seedy-id-header">' +
                  '<img class="seedy-id-photo" src="' + data.photo_data_uri + '" alt="Foto capturada" />' +
                  '<div class="seedy-id-info">' +
                    '<div><span class="breed">' + (id.breed || "?") + '</span>' +
                    '<span class="conf ' + confClass + '">' + Math.round(conf * 100) + '%</span></div>' +
                    '<div>Color: ' + (id.color || "?") + ' · Sexo: ' + (id.sex || "?") + '</div>' +
                    '<div>Calidad: ' + (id.image_quality || "?") + '</div>' +
                    (features ? '<div class="features">Rasgos: ' + features + '</div>' : '') +
                    (id.reasoning ? '<div class="reasoning">"' + id.reasoning + '"</div>' : '') +
                  '</div>' +
                '</div>' +
                '<div class="seedy-id-actions">' +
                  '<button class="confirm" data-action="confirm">✅ Confirmar</button>' +
                  '<button class="reject" data-action="reject">❌ Rechazar</button>' +
                  '<button class="correct" data-action="correct">✏️ Corregir</button>' +
                  '<button class="download" data-action="download" title="Guardar foto para subir a otra ficha">💾 Guardar foto</button>' +
                '</div>' +
                '<div class="seedy-correct-form" style="display:none">' +
                  '<select class="correct-breed">' +
                    '<option value="">— Raza —</option>' +
                    '<option>Sussex</option><option>Bresse</option><option>Marans</option>' +
                    '<option>Araucana</option><option>Sulmtaler</option><option>Vorwerk</option>' +
                    '<option>Pita Pinta</option><option>Andaluza Azul</option>' +
                    '<option>Cruce F1</option><option>Desconocida</option>' +
                  '</select>' +
                  '<input class="correct-color" placeholder="Color" />' +
                  '<select class="correct-sex">' +
                    '<option value="">— Sexo —</option>' +
                    '<option value="gallina">Gallina</option><option value="gallo">Gallo</option>' +
                  '</select>' +
                  '<button class="confirm" data-action="save-correct">💾 Guardar</button>' +
                '</div>';

              // Photo zoom in ID panel
              var idPhoto = capIdPanel.querySelector(".seedy-id-photo");
              if (idPhoto) {
                idPhoto.addEventListener("click", function () {
                  openFullscreen(data.photo_data_uri, (id.breed || "Ave") + " " + (id.color || ""));
                });
              }

              // Also update the main modal photo
              if (photoEl && photoEl.tagName === "IMG") {
                photoEl.src = data.photo_data_uri;
              }

              // Action buttons
              var actionBtns = capIdPanel.querySelectorAll(".seedy-id-actions button");
              actionBtns.forEach(function (btn) {
                btn.addEventListener("click", function (ev) {
                  ev.preventDefault();
                  ev.stopPropagation();
                  var action = btn.dataset.action;

                  if (action === "download") {
                    var a = document.createElement("a");
                    a.href = data.photo_data_uri;
                    a.download = "ave_" + (id.breed || "captura").replace(/\s+/g, "_") + "_" + Date.now() + ".jpg";
                    a.click();
                    return;
                  }

                  // Si confirma con raza desconocida → forzar corrección
                  if (action === "confirm" && (!id.breed || id.breed.toLowerCase() === "desconocida" || id.breed.toLowerCase() === "unknown")) {
                    action = "correct";
                  }

                  if (action === "correct") {
                    var form = capIdPanel.querySelector(".seedy-correct-form");
                    form.style.display = "flex";
                    var breedSelect = form.querySelector(".correct-breed");
                    var colorInput = form.querySelector(".correct-color");
                    var sexSelect = form.querySelector(".correct-sex");
                    for (var i = 0; i < breedSelect.options.length; i++) {
                      if (breedSelect.options[i].text.toLowerCase() === (id.breed || "").toLowerCase()) {
                        breedSelect.selectedIndex = i; break;
                      }
                    }
                    colorInput.value = id.color || "";
                    for (var j = 0; j < sexSelect.options.length; j++) {
                      if (sexSelect.options[j].value === (id.sex || "")) {
                        sexSelect.selectedIndex = j; break;
                      }
                    }
                    return;
                  }

                  if (action === "save-correct") action = "correct";

                  actionBtns.forEach(function (b) { b.disabled = true; });
                  var saveBtn = capIdPanel.querySelector("[data-action='save-correct']");
                  if (saveBtn) saveBtn.disabled = true;

                  var confirmBody = {
                    action: action,
                    photo_data_uri: data.photo_data_uri,
                    breed: id.breed || "",
                    color: id.color || "",
                    sex: id.sex || "",
                    existing_vision_id: (data.ave && data.ave.ai_vision_id) || "",
                  };

                  if (action === "correct") {
                    var form = capIdPanel.querySelector(".seedy-correct-form");
                    confirmBody.breed = form.querySelector(".correct-breed").value || id.breed;
                    confirmBody.color = form.querySelector(".correct-color").value || id.color;
                    confirmBody.sex = form.querySelector(".correct-sex").value || id.sex;
                  }

                  fetch(SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/confirm-identity", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(confirmBody),
                  })
                    .then(function (r) { return r.json(); })
                    .then(function (result) {
                      if (action === "reject") {
                        capIdPanel.className = "seedy-id-panel rejected";
                        capStatus.textContent = "❌ Rechazada — puedes intentar otra captura";
                      } else {
                        capStatus.textContent = (action === "confirm" ? "✅ Confirmado" : "✏️ Corregido") +
                          ": " + confirmBody.breed + " " + confirmBody.color;
                      }
                      var actionsDiv = capIdPanel.querySelector(".seedy-id-actions");
                      if (actionsDiv) actionsDiv.style.display = "none";
                      var correctForm = capIdPanel.querySelector(".seedy-correct-form");
                      if (correctForm) correctForm.style.display = "none";
                    })
                    .catch(function (err) {
                      capStatus.textContent = "❌ Error: " + err.message;
                      actionBtns.forEach(function (b) { b.disabled = false; });
                    });
                });
              });
            })
            .catch(function (err) {
              capStatus.textContent = "❌ Error: " + err.message;
              capIdBtn.innerHTML = "📸 Capturar + Identificar";
              capIdBtn.disabled = false;
            });
        });

        // Camera live button
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

    // Capture-phase listener on row clicks:
    // 1. Record the anilla → window.__seedySelectedAveId (for enhanceEditModal)
    // 2. If click was NOT on a button/icon, force-click the pencil (edit) button
    //    so the native "Editar Ave" modal opens.
    document.body.addEventListener("click", function (e) {
      var row = e.target.closest("tbody tr");
      if (!row) return;

      // Record anilla
      var cells = row.querySelectorAll("td");
      if (cells.length >= 2) {
        var anillaText = (cells[1].textContent || "").trim();
        var m = anillaText.match(/PAL-\d+-(\d+)/);
        if (m) {
          window.__seedySelectedAveId = parseInt(m[1], 10);
          window.__seedySelectedAnilla = anillaText;
        }
      }

      // If the user clicked directly on a button/icon, let it through unchanged
      if (e.target.closest("button, a, svg, path")) return;

      // Otherwise, force open the edit modal via the pencil button
      var editBtn = row.querySelector("button[title='Editar'], button[title*='dit'], td:last-child button:first-child");
      if (editBtn) {
        e.preventDefault();
        e.stopPropagation();
        editBtn.click();
      }
    }, true);
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

        // Digital Twin button — opens ave_twin.html with OvoSfera ID mapped
        var twinBtn = document.createElement("a");
        twinBtn.className = "seedy-bird-monitor-btn";
        twinBtn.style.cssText = "background:linear-gradient(135deg,#8b5cf6,#6d28d9);margin-left:8px;text-decoration:none;display:inline-flex";
        twinBtn.innerHTML = "🐔 Digital Twin del Ave";
        twinBtn.href = SEEDY_API + "/dashboard/ave_twin.html?id=" + (ave.anilla || "PAL-2026-" + String(aveId).padStart(4, "0"));
        twinBtn.target = "_blank";
        container.appendChild(twinBtn);

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
        var main = document.querySelector(".nf-content") || document.querySelector("main") || document.body;
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

  // ── Dashboard panel: 2-column layout — plano hero (65%) + side panel (35%) ──
  function injectDashboardPanel() {
    if (document.getElementById("seedy-dashboard-injected")) return;

    // Find a suitable container — OvoSfera uses .nf-content inside .nf-main
    // IMPORTANT: target .nf-content (NOT .nf-main) to preserve the .nf-status-bar
    let main =
      document.querySelector(".nf-content") ||
      document.querySelector("main > [class*='content']") ||
      document.querySelector("[class*='nf-content']") ||
      document.querySelector("main");

    // Fallback: look for headers with relevant text → use their parent
    if (!main) {
      const headers = document.querySelectorAll("h1, h2, h3");
      for (const h of headers) {
        const t = h.textContent || "";
        if (t.includes("Gallinero") || t.includes("Dashboard") || t.includes("Palacio") || t.includes("dashboard")) {
          main = h.parentElement;
          break;
        }
      }
    }

    // Last resort: #__next or body
    if (!main) {
      main = document.getElementById("__next") || document.body;
    }

    if (!main) return;

    // Hide existing OvoSfera dashboard content (keep nf-status-bar visible)
    Array.from(main.children).forEach(function(el) {
      if (el.classList && el.classList.contains("nf-status-bar")) return;
      if (el.id === "seedy-dashboard-injected") return;
      el.style.display = "none";
      el.dataset.seedyDashHidden = "1";
    });

    const panel = document.createElement("div");
    panel.id = "seedy-dashboard-injected";
    panel.className = "seedy-dashboard-panel";

    // ── 2-column layout with KPI strip on top ──
    // == KPI STRIP (horizontal, across full width — compact) ==
    const kpiStrip = document.createElement("div");
    kpiStrip.className = "seedy-kpi-strip";
    const kpis = [
      { icon: "🐔", label: "Aves", value: "~26", color: "#22c55e", id: "kpi-aves" },
      { icon: "🏠", label: "Gallineros", value: "2", color: "#3b82f6", id: "kpi-gall" },
      { icon: "🥚", label: "Huevos hoy", value: "—", color: "#f59e0b", id: "kpi-huevos" },
      { icon: "🌡️", label: "Temp media", value: "—", color: "#ef4444", id: "kpi-temp" },
      { icon: "⚠️", label: "Alertas", value: "0", color: "#6b7280", id: "kpi-alertas" },
    ];
    kpis.forEach(function(k) {
      const card = document.createElement("div");
      card.className = "seedy-kpi-card";
      card.id = k.id;
      card.innerHTML = '<div class="seedy-kpi-icon">' + k.icon + '</div>'
        + '<div class="seedy-kpi-body">'
        + '<div class="seedy-kpi-value" style="color:' + k.color + '">' + k.value + '</div>'
        + '<div class="seedy-kpi-label">' + k.label + '</div>'
        + '</div>';
      kpiStrip.appendChild(card);
    });
    panel.appendChild(kpiStrip);

    // == 2-COLUMN GRID (75% / 25%) ==
    const layout = document.createElement("div");
    layout.className = "seedy-dashboard-layout";

    // ═══════════ LEFT COLUMN: Hero with mode switching ═══════════
    const leftCol = document.createElement("div");
    leftCol.className = "seedy-dash-left";

    // -- Hero: multi-mode (2D / 3D / IA render) --
    const heroSection = document.createElement("div");
    heroSection.className = "seedy-dash-hero";

    const heroIframe = document.createElement("iframe");
    heroIframe.id = "seedy-hero-iframe";
    heroIframe.title = "Plano 2D interactivo";
    heroIframe.style.display = "none";
    heroSection.appendChild(heroIframe);

    // Render IA image element (shown by default)
    const heroImg = document.createElement("img");
    heroImg.id = "seedy-hero-render";
    heroImg.className = "seedy-hero-render";
    heroImg.alt = "Render IA de la granja";
    heroSection.appendChild(heroImg);

    // Load IA render immediately
    fetch(SEEDY_API + "/api/renders/latest?concept=isometric")
      .then(function(r) { return r.ok ? r.json() : {}; })
      .then(function(data) {
        if (data.url) { heroImg.src = SEEDY_API + data.url; }
        else { heroImg.alt = "Sin renders — genera con POST /api/renders/generate"; }
      })
      .catch(function() {});

    // Mode switching buttons
    const modeBar = document.createElement("div");
    modeBar.className = "seedy-hero-modes";
    var _heroMode = "ia";
    var modes = [
      { key: "2d", label: "📐 2D" },
      { key: "3d", label: "🧊 3D" },
      { key: "ia", label: "📸 IA" },
      { key: "fs", label: "⛶" },
    ];
    modes.forEach(function(m) {
      var btn = document.createElement("button");
      btn.textContent = m.label;
      btn.dataset.mode = m.key;
      if (m.key === "ia") btn.classList.add("active");
      btn.addEventListener("click", function() {
        if (m.key === "fs") {
          // Fullscreen: open current mode in new tab
          if (_heroMode === "3d") {
            window.open(SEEDY_API + "/dashboard/digital_twin_3d.html", "_blank");
          } else if (_heroMode === "ia") {
            var src = heroImg.src;
            if (src) window.open(src, "_blank");
          } else {
            window.open(SEEDY_API + "/dashboard/plano_2d.html", "_blank");
          }
          return;
        }
        _heroMode = m.key;
        // Update active button
        modeBar.querySelectorAll("button").forEach(function(b) { b.classList.remove("active"); });
        btn.classList.add("active");
        // Switch content
        if (m.key === "2d") {
          heroIframe.src = SEEDY_API + "/dashboard/plano_2d.html?embed";
          heroIframe.style.display = "block";
          heroImg.style.display = "none";
        } else if (m.key === "3d") {
          heroIframe.src = SEEDY_API + "/dashboard/digital_twin_3d.html";
          heroIframe.style.display = "block";
          heroImg.style.display = "none";
        } else if (m.key === "ia") {
          heroIframe.style.display = "none";
          heroImg.style.display = "block";
          // Load latest render
          fetch(SEEDY_API + "/api/renders/latest?concept=isometric")
            .then(function(r) { return r.ok ? r.json() : {}; })
            .then(function(data) {
              if (data.url) {
                heroImg.src = SEEDY_API + data.url;
              } else {
                heroImg.alt = "Sin renders generados — usa POST /api/renders/generate";
              }
            })
            .catch(function() {});
        }
      });
      modeBar.appendChild(btn);
    });
    heroSection.appendChild(modeBar);
    leftCol.appendChild(heroSection);

    layout.appendChild(leftCol);

    // ═══════════ RIGHT COLUMN: KPIs compact + Activity feed + Actions ═══════════
    const rightCol = document.createElement("div");
    rightCol.className = "seedy-dash-right";

    // -- Sidebar KPIs (compact text, no big cards) --
    const sideKpi = document.createElement("div");
    sideKpi.className = "seedy-sidebar-kpis";
    sideKpi.innerHTML = '<h4>Estado</h4>';
    var sideKpis = [
      { label: "Aves", value: "~26", color: "#22c55e", id: "skpi-aves" },
      { label: "Gallineros", value: "2", color: "#3b82f6", id: "skpi-gall" },
      { label: "Huevos hoy", value: "—", color: "#f59e0b", id: "skpi-huevos" },
      { label: "Temp media", value: "—", color: "#ef4444", id: "skpi-temp" },
      { label: "Alertas", value: "0", color: "#6b7280", id: "skpi-alertas" },
    ];
    sideKpis.forEach(function(k) {
      var row = document.createElement("div");
      row.className = "seedy-sidebar-kpi-item";
      row.id = k.id;
      row.innerHTML = '<span class="seedy-sidebar-kpi-label">' + k.label + '</span>'
        + '<span class="seedy-sidebar-kpi-val" style="color:' + k.color + '">' + k.value + '</span>';
      sideKpi.appendChild(row);
    });
    rightCol.appendChild(sideKpi);

    // -- Activity feed (compact) --
    const feedSection = document.createElement("div");
    feedSection.className = "seedy-feed-section";
    feedSection.id = "seedy-activity-feed";
    feedSection.innerHTML = '<h4>Actividad reciente</h4>';
    const feedList = document.createElement("div");
    feedList.id = "seedy-feed-list";

    // Seed with placeholder
    const now = new Date();
    const hh = String(now.getHours()).padStart(2, "0");
    const mm = String(now.getMinutes()).padStart(2, "0");
    var seedItem = document.createElement("div");
    seedItem.className = "seedy-feed-item";
    seedItem.innerHTML = '<span class="seedy-feed-time">' + hh + ":" + mm + '</span><span>Dashboard cargado</span>';
    feedList.appendChild(seedItem);
    feedSection.appendChild(feedList);
    rightCol.appendChild(feedSection);

    // Start polling for real events
    _pollActivityFeed(feedList);

    // -- Action links --
    const links = document.createElement("div");
    links.className = "seedy-twin-links";
    links.innerHTML = '<a href="' + SEEDY_API + '/dashboard/digital_twin_3d.html" target="_blank" class="twin-3d">🏗️ Digital Twin 3D</a>';
    rightCol.appendChild(links);

    // -- GeoTwin button --
    const geoBtn = document.createElement("button");
    geoBtn.className = "seedy-geotwin-btn";
    geoBtn.innerHTML = "🌍 Abrir en GeoTwin";
    geoBtn.addEventListener("click", function() {
      window.open("https://geotwin.es?twin=Yasg5zxsF_&lat=40.91541&lon=-4.06827&zoom=18", "_blank");
    });
    rightCol.appendChild(geoBtn);

    // -- Drone control panel --
    var dronePanel = document.createElement("div");
    dronePanel.className = "seedy-drone-panel";
    dronePanel.id = "seedy-drone-panel";
    dronePanel.innerHTML =
      '<div class="seedy-drone-header">' +
        '<span class="seedy-drone-title"><span class="seedy-drone-dot off" id="seedy-drone-dot"></span> Dron Bebop 2</span>' +
        '<span id="seedy-drone-status" style="font-size:0.7em;color:var(--neutral-500,#6b7280);">Desconectado</span>' +
      '</div>' +
      '<div class="seedy-drone-stats">' +
        '<div class="seedy-drone-stat"><span class="seedy-drone-stat-val" id="seedy-drone-batt">--</span><span class="seedy-drone-stat-label">Batería</span></div>' +
        '<div class="seedy-drone-stat"><span class="seedy-drone-stat-val" id="seedy-drone-flights">--</span><span class="seedy-drone-stat-label">Vuelos hoy</span></div>' +
        '<div class="seedy-drone-stat"><span class="seedy-drone-stat-val" id="seedy-drone-cooldown">--</span><span class="seedy-drone-stat-label">Cooldown</span></div>' +
      '</div>' +
      '<div class="seedy-drone-actions">' +
        '<button class="seedy-drone-btn connect" id="seedy-drone-connect">Conectar</button>' +
        '<button class="seedy-drone-btn fly-btn" id="seedy-drone-fly" disabled>Vuelo manual</button>' +
      '</div>' +
      '<div class="seedy-drone-log" id="seedy-drone-log"></div>';
    rightCol.appendChild(dronePanel);

    // Drone panel logic
    _initDronePanel();

    layout.appendChild(rightCol);
    panel.appendChild(layout);

    // ── Sensors summary strip (between KPIs and hero) ──
    var sensorsStrip = document.createElement("div");
    sensorsStrip.id = "seedy-dash-sensors";
    sensorsStrip.className = "seedy-dash-sensors";
    sensorsStrip.innerHTML = '<div style="color:#6b7280;font-size:0.85em;padding:8px">Cargando sensores...</div>';
    // Insert between kpiStrip and layout
    panel.insertBefore(sensorsStrip, layout);

    // Insert at the top of main content
    if (main.firstChild) {
      main.insertBefore(panel, main.firstChild);
    } else {
      main.appendChild(panel);
    }

    // ── Fetch live sensor data and populate KPIs + sensor strip ──
    _fetchDashboardSensors();
    _dashSensorTimer = setInterval(_fetchDashboardSensors, 30000);
  }

  var _dashSensorTimer = null;

  function _fetchDashboardSensors() {
    Promise.all([
      fetch(SEEDY_API + "/ovosfera/devices", { mode: "cors" }).then(function(r) { return r.ok ? r.json() : {}; }),
      fetch(SEEDY_API + "/ovosfera/devices/status", { mode: "cors" }).then(function(r) { return r.ok ? r.json() : {}; }),
    ])
    .then(function(results) {
      var devData = results[0];
      var statusData = results[1];
      var devices = devData.devices || [];
      var gallineros = statusData.gallineros || {};
      var weather = statusData.weather || null;

      // ── Update KPIs ──
      var temps = [];
      var alertCount = 0;

      devices.forEach(function(dev) {
        var t = dev.last_temperature;
        if (t !== null && t !== undefined && dev.device_category !== 'infrastructure') {
          temps.push(t);
        }
        // Count alerts: soil humidity < 40%, CO2 > 1200, temp > 32 or < 5
        var hum = dev.last_humidity;
        if (dev.device_category === 'soil' && hum !== null && hum < 40) alertCount++;
        if (dev.last_co2 && dev.last_co2 > 1200) alertCount++;
        if (t !== null && t !== undefined && dev.device_category === 'sensor') {
          if (t > 32 || t < 5) alertCount++;
        }
      });

      var avgTemp = temps.length ? (temps.reduce(function(a, b) { return a + b; }, 0) / temps.length).toFixed(1) + '°C' : '—';

      // Update top KPI strip
      _updateKpiValue('kpi-temp', avgTemp);
      _updateKpiValue('kpi-alertas', String(alertCount), alertCount > 0 ? '#ef4444' : '#6b7280');

      // Update sidebar KPIs
      _updateKpiValue('skpi-temp', avgTemp);
      _updateKpiValue('skpi-alertas', String(alertCount), alertCount > 0 ? '#ef4444' : '#6b7280');

      // ── Build sensor strip ──
      var strip = document.getElementById("seedy-dash-sensors");
      if (!strip) return;

      var html = '';

      // Gallinero sensors (temp+hum)
      devices.forEach(function(dev) {
        if (dev.device_category === 'infrastructure' || dev.type === 'ecowitt') return;
        var cat = dev.device_category || 'sensor';
        var icon = cat === 'soil' ? '🌱' : cat === 'air_quality' ? '🌬️' : '🏠';
        var name = dev.gallinero_name || dev.friendly_name;
        var temp = dev.last_temperature;
        var hum = dev.last_humidity;
        var tempStr = temp !== null && temp !== undefined ? temp.toFixed(1) + '°C' : '—';
        var humStr = hum !== null && hum !== undefined ? hum + '%' : '—';

        // Color coding
        var tempColor = '#f3f4f6';
        if (temp !== null && temp !== undefined) {
          if (temp < 10) tempColor = '#3b82f6';
          else if (temp < 18) tempColor = '#22c55e';
          else if (temp < 28) tempColor = '#f59e0b';
          else tempColor = '#ef4444';
        }

        var humColor = '#f3f4f6';
        if (cat === 'soil' && hum !== null && hum !== undefined) {
          if (hum < 25) humColor = '#ef4444';
          else if (hum < 40) humColor = '#f59e0b';
          else if (hum <= 70) humColor = '#22c55e';
          else humColor = '#3b82f6';
        }

        var extra = '';
        if (cat === 'air_quality' && dev.last_co2 !== null && dev.last_co2 !== undefined) {
          var co2Color = dev.last_co2 < 800 ? '#22c55e' : dev.last_co2 < 1200 ? '#f59e0b' : '#ef4444';
          extra = '<span class="seedy-sens-val" style="color:' + co2Color + '">' + dev.last_co2 + '<small>ppm</small></span>';
        }
        if (cat === 'soil' && hum !== null && hum < 40) {
          extra = '<span class="seedy-sens-alert">' + (hum < 25 ? '🚨 Riego urgente' : '💧 Regar') + '</span>';
        }

        html += '<div class="seedy-sens-card">'
          + '<div class="seedy-sens-name">' + icon + ' ' + _escHtml(name) + '</div>'
          + '<div class="seedy-sens-vals">'
          + '<span class="seedy-sens-val" style="color:' + tempColor + '">🌡️' + tempStr + '</span>'
          + '<span class="seedy-sens-val" style="color:' + humColor + '">💧' + humStr + '</span>'
          + extra
          + '</div>'
          + '</div>';
      });

      // Weather compact
      if (weather) {
        var out = weather.outdoor || {};
        var wind = weather.wind || {};
        html += '<div class="seedy-sens-card seedy-sens-weather">'
          + '<div class="seedy-sens-name">🌤️ Exterior</div>'
          + '<div class="seedy-sens-vals">'
          + '<span class="seedy-sens-val">🌡️' + (out.temperature != null ? out.temperature.toFixed(1) + '°C' : '—') + '</span>'
          + '<span class="seedy-sens-val">💧' + (out.humidity != null ? out.humidity + '%' : '—') + '</span>'
          + '<span class="seedy-sens-val">💨' + (wind.speed != null ? wind.speed + 'km/h' : '—') + '</span>'
          + '</div>'
          + '</div>';
      }

      strip.innerHTML = html;
    })
    .catch(function(e) {
      console.debug("Seedy dashboard sensors fetch error:", e);
    });
  }

  function _updateKpiValue(id, value, color) {
    var el = document.getElementById(id);
    if (!el) return;
    var valEl = el.querySelector(".seedy-kpi-value, .seedy-sidebar-kpi-val");
    if (valEl) {
      valEl.textContent = value;
      if (color) valEl.style.color = color;
    }
  }

  // ── Activity feed poller — fetches YOLO/ReID/sensor events ──
  var _feedTimer = null;
  function _pollActivityFeed(feedList) {
    if (_feedTimer) clearInterval(_feedTimer);
    var seenIds = {};

    function fetchEvents() {
      fetch(SEEDY_API + "/api/tracking/" + SEEDY_FARM + "/latest", { mode: "cors" })
        .then(function(r) { return r.ok ? r.json() : []; })
        .then(function(data) {
          if (!Array.isArray(data) || !data.length) return;
          data.slice(0, 15).reverse().forEach(function(ev) {
            var key = (ev.timestamp || "") + (ev.bird_id || "") + (ev.type || "");
            if (seenIds[key]) return;
            seenIds[key] = true;
            var ts = ev.timestamp ? new Date(ev.timestamp) : new Date();
            var t = String(ts.getHours()).padStart(2, "0") + ":" + String(ts.getMinutes()).padStart(2, "0");
            var text = "";
            if (ev.type === "yolo" || ev.breed) {
              text = "YOLO: " + (ev.breed || "ave") + " detectada" + (ev.camera ? " en " + ev.camera : "");
            } else if (ev.type === "reid") {
              text = "Re-ID: " + (ev.bird_id || "ave") + " identificada";
            } else if (ev.type === "sensor") {
              text = "Sensor: " + (ev.metric || "") + " = " + (ev.value || "—");
            } else {
              text = ev.type + ": " + (ev.summary || ev.bird_id || "evento");
            }
            var item = document.createElement("div");
            item.className = "seedy-feed-item";
            item.innerHTML = '<span class="seedy-feed-time">' + t + '</span><span>' + text + '</span>';
            feedList.insertBefore(item, feedList.firstChild);
            // Keep max 15 items
            while (feedList.children.length > 15) feedList.removeChild(feedList.lastChild);
          });
        })
        .catch(function() { /* silent */ });
    }

    fetchEvents();
    _feedTimer = setInterval(fetchEvents, 8000);
  }

  // ── Retry timer: reintenta inyección cada 2s durante 30s (React hydration) ──
  let _retryTimer = null;
  function retryInjection(fn, maxMs) {
    if (_retryTimer) clearInterval(_retryTimer);
    const deadline = Date.now() + (maxMs || 30000);
    _retryTimer = setInterval(() => {
      fn();
      if (Date.now() > deadline) {
        clearInterval(_retryTimer);
        _retryTimer = null;
      }
    }, 2000);
  }

  // ── Clean up dashboard panel when leaving dashboard ──
  function cleanupDashboardPanel() {
    var panel = document.getElementById("seedy-dashboard-injected");
    if (panel) panel.remove();
    _cleanupDronePoller();
    // Restore hidden OvoSfera dashboard content
    document.querySelectorAll("[data-seedy-dash-hidden]").forEach(function(el) {
      el.style.display = "";
      delete el.dataset.seedyDashHidden;
    });
    // Clean up timers
    if (_feedTimer) { clearInterval(_feedTimer); _feedTimer = null; }
    if (_dashSensorTimer) { clearInterval(_dashSensorTimer); _dashSensorTimer = null; }
  }

  // ── Drone control panel logic ──
  var _dronePoller = null;

  function _droneLog(msg) {
    var log = document.getElementById("seedy-drone-log");
    if (!log) return;
    var t = new Date();
    var ts = String(t.getHours()).padStart(2,"0") + ":" + String(t.getMinutes()).padStart(2,"0");
    log.innerHTML = '<div>' + ts + ' ' + msg + '</div>' + log.innerHTML;
    if (log.children.length > 5) log.removeChild(log.lastChild);
  }

  function _updateDroneUI(data) {
    var dot = document.getElementById("seedy-drone-dot");
    var statusEl = document.getElementById("seedy-drone-status");
    var battEl = document.getElementById("seedy-drone-batt");
    var flightsEl = document.getElementById("seedy-drone-flights");
    var coolEl = document.getElementById("seedy-drone-cooldown");
    var connectBtn = document.getElementById("seedy-drone-connect");
    var flyBtn = document.getElementById("seedy-drone-fly");
    if (!dot) return;

    if (data.connected) {
      if (data.is_flying) {
        dot.className = "seedy-drone-dot fly";
        statusEl.textContent = "En vuelo...";
        statusEl.style.color = "#f59e0b";
      } else {
        dot.className = "seedy-drone-dot ok";
        statusEl.textContent = "Conectado";
        statusEl.style.color = "#22c55e";
      }
      connectBtn.textContent = "Desconectar";
      connectBtn.className = "seedy-drone-btn disconnect";
      flyBtn.disabled = data.is_flying || !data.can_fly;
    } else {
      dot.className = "seedy-drone-dot off";
      statusEl.textContent = "Desconectado";
      statusEl.style.color = "var(--neutral-500,#6b7280)";
      connectBtn.textContent = "Conectar";
      connectBtn.className = "seedy-drone-btn connect";
      flyBtn.disabled = true;
    }

    battEl.textContent = data.battery_pct != null ? data.battery_pct + "%" : "--";
    if (data.battery_pct != null && data.battery_pct < 30) battEl.style.color = "#ef4444";
    else if (data.battery_pct != null && data.battery_pct < 50) battEl.style.color = "#f59e0b";
    else battEl.style.color = "";

    flightsEl.textContent = data.flights_today != null ? data.flights_today : "--";
    if (data.cooldown_remaining != null && data.cooldown_remaining > 0) {
      coolEl.textContent = data.cooldown_remaining + "s";
    } else {
      coolEl.textContent = data.can_fly ? "Listo" : "--";
      if (data.can_fly) coolEl.style.color = "#22c55e";
    }
  }

  function _pollDroneStatus() {
    fetch(SEEDY_API + "/api/dron/status", { mode: "cors" })
      .then(function(r) { return r.ok ? r.json() : null; })
      .then(function(data) { if (data) _updateDroneUI(data); })
      .catch(function() {
        _updateDroneUI({ connected: false });
      });
  }

  function _initDronePanel() {
    var connectBtn = document.getElementById("seedy-drone-connect");
    var flyBtn = document.getElementById("seedy-drone-fly");
    if (!connectBtn) return;

    connectBtn.addEventListener("click", function() {
      var isDisconnect = connectBtn.textContent.includes("Desconectar");
      var url = SEEDY_API + "/api/dron/" + (isDisconnect ? "disconnect" : "connect");
      connectBtn.disabled = true;
      connectBtn.textContent = isDisconnect ? "Desconectando..." : "Conectando...";
      _droneLog(isDisconnect ? "Desconectando dron..." : "Conectando al Bebop 2...");
      fetch(url, { method: "POST", mode: "cors" })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          _droneLog(data.status || (data.connected ? "Conectado" : "Desconectado"));
          _pollDroneStatus();
        })
        .catch(function(e) { _droneLog("Error: " + e.message); })
        .finally(function() { connectBtn.disabled = false; });
    });

    flyBtn.addEventListener("click", function() {
      if (!confirm("El dron va a despegar y volar 20m. Espacio despejado?")) return;
      flyBtn.disabled = true;
      flyBtn.textContent = "Volando...";
      _droneLog("Vuelo anti-gorriones iniciado");
      fetch(SEEDY_API + "/api/dron/sparrow-deterrent", { method: "POST", mode: "cors" })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          _droneLog("Vuelo: " + (data.status || "completado") + (data.duration_s ? " (" + data.duration_s + "s)" : ""));
          flyBtn.textContent = "Vuelo manual";
          _pollDroneStatus();
        })
        .catch(function(e) {
          _droneLog("Error vuelo: " + e.message);
          flyBtn.textContent = "Vuelo manual";
        })
        .finally(function() { flyBtn.disabled = false; });
    });

    // Poll status every 5s
    _pollDroneStatus();
    _dronePoller = setInterval(_pollDroneStatus, 5000);
  }

  function _cleanupDronePoller() {
    if (_dronePoller) { clearInterval(_dronePoller); _dronePoller = null; }
  }

  // ── Inject "Site" link into OvoSfera sidebar ──
  function injectSidebarSiteLink() {
    if (!isTargetFarm()) return;
    if (document.getElementById("seedy-site-link")) return;

    // OvoSfera sidebar: <aside class="nf-sidebar">
    //   <nav class="nf-sidebar-nav">
    //     <div> <div class="nf-nav-label">Sostenibilidad</div> ... </div>
    //     <div> <div class="nf-nav-label">Sistema</div> ... </div>
    var labels = document.querySelectorAll(".nf-nav-label");
    var sistemaGroup = null;
    labels.forEach(function (lbl) {
      if (lbl.textContent.trim() === "Sistema") {
        sistemaGroup = lbl.parentElement;
      }
    });
    if (!sistemaGroup) return;

    // Create the Site link group
    var siteGroup = document.createElement("div");
    siteGroup.id = "seedy-site-link";

    var siteLink = document.createElement("a");
    siteLink.href = SEEDY_API + "/dashboard/site_palacio.html";
    siteLink.className = "nf-nav-item";
    siteLink.target = "_blank";
    siteLink.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M3 9l9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><polyline points="9 22 9 12 15 12 15 22"/></svg>'
      + '<span class="nf-nav-text">Site</span>';

    siteGroup.appendChild(siteLink);
    sistemaGroup.parentNode.insertBefore(siteGroup, sistemaGroup);

    // Create the Devices link (IoT sensors)
    // OvoSfera may already have a native "Dispositivos" link — hijack it instead of duplicating
    if (!document.getElementById("seedy-devices-link")) {
      var existingDevLink = null;
      var navItems = sistemaGroup.parentNode.querySelectorAll("a.nf-nav-item");
      navItems.forEach(function(a) {
        if ((a.href || "").indexOf("/devices") !== -1 || (a.textContent || "").trim() === "Dispositivos") {
          existingDevLink = a;
        }
      });
      if (existingDevLink) {
        // Hijack the native link: add our SPA click handler
        existingDevLink.parentElement.id = "seedy-devices-link";
        existingDevLink.addEventListener("click", function(e) {
          e.preventDefault();
          var farmSlug = (window.location.pathname.match(/\/farm\/([^/]+)/) || [])[1] || SEEDY_FARM;
          window.history.pushState({}, "", "/farm/" + farmSlug + "/devices");
          window.dispatchEvent(new PopStateEvent("popstate"));
          onPageChange();
        });
      } else {
        var devGroup = document.createElement("div");
        devGroup.id = "seedy-devices-link";
        var devLink = document.createElement("a");
        var farmSlug = (window.location.pathname.match(/\/farm\/([^/]+)/) || [])[1] || SEEDY_FARM;
        devLink.href = "/farm/" + farmSlug + "/devices";
        devLink.className = "nf-nav-item";
        devLink.innerHTML = '<svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="flex-shrink:0;"><path d="M12 2a3 3 0 0 0-3 3v1H5a2 2 0 0 0-2 2v4a2 2 0 0 0 2 2h1v5a2 2 0 0 0 2 2h8a2 2 0 0 0 2-2v-5h1a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-4V5a3 3 0 0 0-3-3z"/><circle cx="9" cy="14" r="1"/><circle cx="15" cy="14" r="1"/></svg>'
          + '<span class="nf-nav-text">Dispositivos</span>';
        devLink.addEventListener("click", function(e) {
          e.preventDefault();
          window.history.pushState({}, "", devLink.href);
          window.dispatchEvent(new PopStateEvent("popstate"));
          onPageChange();
        });
        devGroup.appendChild(devLink);
        siteGroup.parentNode.insertBefore(devGroup, sistemaGroup);
      }
    }
  }

  // ── Inject Site landing page content ──
  function injectSitePage() {
    // Replace main content area with the landing page in an iframe
    var main = document.querySelector("main.nf-main") || document.querySelector("main");
    if (!main) return;
    if (document.getElementById("seedy-site-frame")) return;

    // Clear existing page content (the Next.js rendered page below status bar)
    var statusBar = main.querySelector(".nf-status-bar");
    // Remove all children except the status bar
    Array.from(main.children).forEach(function (child) {
      if (child.classList && child.classList.contains("nf-status-bar")) return;
      child.style.display = "none";
      child.dataset.seedySiteHidden = "1";
    });

    var frame = document.createElement("iframe");
    frame.id = "seedy-site-frame";
    frame.src = SEEDY_API + "/dashboard/site_palacio.html?embed=1";
    frame.style.cssText = "width:100%;border:none;min-height:calc(100vh - 48px);display:block;";
    frame.setAttribute("allowfullscreen", "");
    main.appendChild(frame);

    // Auto-resize iframe to content height
    frame.addEventListener("load", function () {
      try {
        var h = frame.contentDocument.body.scrollHeight;
        if (h > 200) frame.style.height = h + "px";
      } catch (e) { /* cross-origin, use min-height fallback */ }
    });
  }

  function cleanupSitePage() {
    var frame = document.getElementById("seedy-site-frame");
    if (frame) frame.remove();
    // Restore hidden children
    document.querySelectorAll("[data-seedy-site-hidden]").forEach(function (el) {
      el.style.display = "";
      delete el.dataset.seedySiteHidden;
    });
  }

  // ── Devices / IoT Sensors page ──
  var _devicesRefreshTimer = null;

  function injectDevicesPage() {
    if (document.getElementById("seedy-devices-injected")) return;

    var main = document.querySelector("main.nf-main") || document.querySelector("main");
    if (!main) return;

    // Hide existing page content
    Array.from(main.children).forEach(function (child) {
      if (child.classList && child.classList.contains("nf-status-bar")) return;
      child.style.display = "none";
      child.dataset.seedyDevicesHidden = "1";
    });

    var container = document.createElement("div");
    container.id = "seedy-devices-injected";
    container.className = "seedy-devices-page";
    container.innerHTML = '<div class="seedy-devices-header">'
      + '<h2>🌡️ Dispositivos IoT</h2>'
      + '<a href="http://192.168.40.128:8080" target="_blank" class="seedy-z2m-link">⚙️ Zigbee2MQTT</a>'
      + '</div>'
      + '<div class="seedy-devices-grid" id="seedy-devices-grid">'
      + '<div class="seedy-devices-empty"><div class="seedy-empty-icon">📡</div>Cargando sensores...</div>'
      + '</div>';
    main.appendChild(container);

    // Load data immediately + auto-refresh
    _refreshDevicesData();
    _devicesRefreshTimer = setInterval(_refreshDevicesData, 15000);
  }

  function _refreshDevicesData() {
    fetch(SEEDY_API + "/ovosfera/devices/status")
      .then(function (r) { return r.json(); })
      .then(function (statusData) {
        return fetch(SEEDY_API + "/ovosfera/devices")
          .then(function (r2) { return r2.json(); })
          .then(function (devData) {
            _renderDevicesGrid(devData.devices || [], statusData.gallineros || {});
          });
      })
      .catch(function (e) {
        console.error("Seedy devices fetch error:", e);
        var grid = document.getElementById("seedy-devices-grid");
        if (grid) grid.innerHTML = '<div class="seedy-devices-empty"><div class="seedy-empty-icon">⚠️</div>Error cargando sensores</div>';
      });
  }

  function _renderDevicesGrid(devices, gallineros) {
    var grid = document.getElementById("seedy-devices-grid");
    if (!grid) return;

    if (!devices.length) {
      grid.innerHTML = '<div class="seedy-devices-empty">'
        + '<div class="seedy-empty-icon">📡</div>'
        + '<p>No hay sensores conectados.</p>'
        + '<p style="font-size:0.85em">Abre <a href="http://192.168.40.128:8080" target="_blank" style="color:#3b82f6">Zigbee2MQTT</a> para emparejar.</p>'
        + '</div>';
      return;
    }

    var html = '';
    devices.forEach(function (dev) {
      var cat = dev.device_category || '';
      if (dev.type === 'ecowitt') {
        html += _renderEcowittCard(dev);
      } else if (dev.type === 'esp32_cam' || cat === 'camera') {
        html += _renderEsp32CamCard(dev);
      } else if (cat === 'soil') {
        html += _renderSoilSensorCard(dev, gallineros);
      } else if (cat === 'air_quality' || (dev.last_co2 !== null && dev.last_co2 !== undefined)) {
        html += _renderAirQualityCard(dev, gallineros);
      } else if (cat === 'infrastructure') {
        html += _renderInfraCard(dev);
      } else {
        html += _renderZigbeeCard(dev, gallineros);
      }
    });

    grid.innerHTML = html;
  }

  function _renderEsp32CamCard(dev) {
    var cam = dev.esp32_cam || {};
    var fname = dev.friendly_name || 'Cámara ESP32';
    var gName = dev.gallinero_name || '';
    var rssi = dev.last_linkquality || cam.rssi || 0;
    var fw = cam.firmware || '?';
    var ip = cam.ip || '?';
    var lux = cam.lux != null ? cam.lux.toFixed(0) : '—';
    var irOn = cam.ir_on ? '🔴 ON' : '⚫ OFF';
    var psramMB = cam.free_psram ? (cam.free_psram / 1048576).toFixed(1) : '—';
    var uptimeH = cam.uptime_s ? (cam.uptime_s / 3600).toFixed(1) : '—';
    var isOnline = !!cam.ip;
    var audioOk = !!cam.audio_available;

    // Determine stream name and device_id from friendly_name
    var streamName = '';
    var espDeviceId = '';
    if (fname.indexOf('Palacio') !== -1) { streamName = 'gallinero_palacio_esp32'; espDeviceId = 'palacio'; }
    else if (fname.indexOf('Peque') !== -1) { streamName = 'gallinero_pequeno_esp32'; espDeviceId = 'pequeno'; }
    var snapUrl = streamName ? (SEEDY_API + '/ovosfera/stream/' + streamName + '/snapshot?_t=' + Date.now()) : '';

    // RSSI bars (WiFi: -30=excellent ... -90=weak)
    var rssiLevel = 0;
    if (rssi && rssi < 0) {
      if (rssi >= -50) rssiLevel = 5;
      else if (rssi >= -60) rssiLevel = 4;
      else if (rssi >= -70) rssiLevel = 3;
      else if (rssi >= -80) rssiLevel = 2;
      else rssiLevel = 1;
    }
    var rssiBars = '';
    for (var i = 1; i <= 5; i++) {
      var h = 6 + i * 3;
      rssiBars += '<span style="height:' + h + 'px" class="' + (i <= rssiLevel ? 'active' : '') + '"></span>';
    }

    var snapHtml = snapUrl
      ? '<div style="margin:8px 0;border-radius:8px;overflow:hidden;background:#111;position:relative;cursor:pointer" '
        + 'onclick="this.querySelector(\'img\').src=\'' + SEEDY_API + '/ovosfera/stream/' + streamName + '/snapshot?_t=\' + Date.now()">'
        + '<img src="' + snapUrl + '" style="width:100%;display:block;border-radius:8px" onerror="this.style.display=\'none\'" />'
        + '<div style="position:absolute;bottom:6px;right:8px;background:rgba(0,0,0,0.6);color:#fff;font-size:10px;padding:2px 6px;border-radius:4px">📷 Click = refresh</div>'
        + '</div>'
      : '';

    // Audio controls (only when audio_available)
    var audioHtml = '';
    if (audioOk && espDeviceId) {
      var levelId = 'audio-level-' + espDeviceId;
      var btnId = 'audio-btn-' + espDeviceId;
      audioHtml = '<div style="margin:6px 0;padding:8px 12px;background:rgba(78,205,196,0.08);border-radius:8px;display:flex;align-items:center;gap:10px">'
        + '<span style="font-size:1.2em">🎙️</span>'
        + '<span id="' + levelId + '" style="font-size:0.85em;color:#aaa">— dBFS</span>'
        + '<button id="' + btnId + '" onclick="window._seedyRecordAudio(\'' + espDeviceId + '\',this)" '
        + 'style="margin-left:auto;padding:4px 12px;background:#4ecdc4;color:#111;border:none;border-radius:6px;cursor:pointer;font-size:0.82em;font-weight:600">'
        + '⏺ Grabar 5s</button>'
        + '</div>';
    }

    return '<div class="seedy-device-card ' + (isOnline ? '' : 'offline') + '" style="grid-column: span 2;">'
      + '<div class="seedy-device-card-header">'
      + '<h3>📹 ' + _escHtml(fname) + '</h3>'
      + '<span class="seedy-device-status ' + (isOnline ? 'online' : 'offline') + '">' + (isOnline ? '● Online' : '● Offline') + '</span>'
      + '</div>'
      + snapHtml
      + audioHtml
      + '<div class="seedy-device-readings">'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">💡</div><div class="seedy-reading-value">' + lux + '</div><div class="seedy-reading-label">Lux amb.</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">' + (cam.ir_on ? '🔴' : '⚫') + '</div><div class="seedy-reading-value">' + irOn + '</div><div class="seedy-reading-label">IR LED</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">📶</div><div class="seedy-reading-value">' + rssi + '</div><div class="seedy-reading-label">RSSI dBm</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">⏱️</div><div class="seedy-reading-value">' + uptimeH + 'h</div><div class="seedy-reading-label">Uptime</div></div>'
      + '</div>'
      + '<div class="seedy-device-meta">'
      + '<span>🏠 ' + _escHtml(gName) + ' · ' + _escHtml(ip) + ' · FW ' + _escHtml(fw) + ' · PSRAM ' + psramMB + 'MB'
      + (audioOk ? ' · 🎙️ Audio' : '') + '</span>'
      + '<span class="seedy-lqi-bar" title="WiFi: ' + rssi + 'dBm">' + rssiBars + '</span>'
      + '</div>'
      + '</div>';
  }

  function _renderEcowittCard(dev) {
    var ecowitt = dev.ecowitt || {};
    var outdoor = ecowitt.outdoor || {};
    var indoor = ecowitt.indoor || {};
    var wind = ecowitt.wind || {};
    var rain = ecowitt.rain || {};
    var pressure = ecowitt.pressure || {};
    var solar = ecowitt.solar || {};
    var lastTs = ecowitt.last_seen;
    var isOnline = !!lastTs;

    var seenStr = '—';
    if (lastTs) {
      try {
        var d = new Date(parseInt(lastTs) * 1000);
        var now = new Date();
        var diffMin = Math.floor((now - d) / 60000);
        if (diffMin < 1) seenStr = 'ahora';
        else if (diffMin < 60) seenStr = 'hace ' + diffMin + ' min';
        else if (diffMin < 1440) seenStr = 'hace ' + Math.floor(diffMin/60) + 'h';
        else seenStr = d.toLocaleDateString('es');
      } catch(e) { seenStr = '?'; }
    }

    function fmt(v, unit, dec) {
      if (v === null || v === undefined) return '—';
      return (dec !== undefined ? v.toFixed(dec) : v) + (unit || '');
    }

    // Temperature color
    var temp = outdoor.temperature;
    var tempColor = '#f3f4f6';
    if (temp !== null && temp !== undefined) {
      if (temp < 5) tempColor = '#3b82f6';
      else if (temp < 15) tempColor = '#22c55e';
      else if (temp < 28) tempColor = '#f59e0b';
      else tempColor = '#ef4444';
    }

    // Wind direction arrow
    var windDir = wind.direction;
    var windArrow = '';
    if (windDir !== null && windDir !== undefined) {
      windArrow = '<span style="display:inline-block;transform:rotate(' + windDir + 'deg);font-size:0.8em">↑</span> ';
    }

    // UVI color
    var uvi = solar.uvi;
    var uviColor = '#f3f4f6';
    if (uvi !== null && uvi !== undefined) {
      if (uvi <= 2) uviColor = '#22c55e';
      else if (uvi <= 5) uviColor = '#f59e0b';
      else if (uvi <= 7) uviColor = '#f97316';
      else if (uvi <= 10) uviColor = '#ef4444';
      else uviColor = '#a855f7';
    }

    return '<div class="seedy-device-card weather-station ' + (isOnline ? '' : 'offline') + '" style="grid-column: span 2;">'
      + '<div class="seedy-device-card-header">'
      + '<h3>🌤️ Estación Meteorológica · Finca Palacio</h3>'
      + '<span class="seedy-device-status ' + (isOnline ? 'online' : 'offline') + '">' + (isOnline ? '● Online' : '● Offline') + '</span>'
      + '</div>'
      // Main readings (3 columns)
      + '<div class="seedy-weather-readings">'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">🌡️</div><div class="seedy-reading-value" style="color:' + tempColor + '">' + fmt(temp, '°C', 1) + '</div><div class="seedy-reading-label">Exterior</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">🤒</div><div class="seedy-reading-value">' + fmt(outdoor.feels_like, '°C', 1) + '</div><div class="seedy-reading-label">Sensación</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">💧</div><div class="seedy-reading-value">' + fmt(outdoor.humidity, '%', 0) + '</div><div class="seedy-reading-label">Humedad ext.</div></div>'
      + '</div>'
      // Second row: indoor + dew point + pressure
      + '<div class="seedy-weather-extra">'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">🏠</div><div class="seedy-reading-value">' + fmt(indoor.temperature, '°C', 1) + '</div><div class="seedy-reading-label">Interior</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">🏠💧</div><div class="seedy-reading-value">' + fmt(indoor.humidity, '%', 0) + '</div><div class="seedy-reading-label">Humedad int.</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">💦</div><div class="seedy-reading-value">' + fmt(outdoor.dew_point, '°C', 1) + '</div><div class="seedy-reading-label">Punto rocío</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">💨</div><div class="seedy-reading-value">' + windArrow + fmt(wind.speed, ' km/h', 1) + '</div><div class="seedy-reading-label">Viento</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">🌬️</div><div class="seedy-reading-value">' + fmt(wind.gust, ' km/h', 1) + '</div><div class="seedy-reading-label">Ráfagas</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">📊</div><div class="seedy-reading-value">' + fmt(pressure.relative, ' hPa', 1) + '</div><div class="seedy-reading-label">Presión</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">☀️</div><div class="seedy-reading-value">' + fmt(solar.radiation, ' W/m²', 0) + '</div><div class="seedy-reading-label">Radiación</div></div>'
      + '<div class="seedy-reading"><div class="seedy-reading-icon">🔆</div><div class="seedy-reading-value" style="color:' + uviColor + '">' + fmt(uvi, '', 0) + '</div><div class="seedy-reading-label">Índice UV</div></div>'
      + '</div>'
      // Rain accumulation row
      + '<div class="seedy-weather-rain">'
      + '<span class="seedy-rain-title">🌧️ Precipitación acumulada</span>'
      + '<div class="seedy-rain-bars">'
      + '<div class="seedy-rain-item"><span class="seedy-rain-val">' + fmt(rain.rate, ' mm/h', 1) + '</span><span class="seedy-rain-lbl">Ahora</span></div>'
      + '<div class="seedy-rain-item"><span class="seedy-rain-val">' + fmt(rain.daily, ' mm', 1) + '</span><span class="seedy-rain-lbl">Hoy</span></div>'
      + '<div class="seedy-rain-item"><span class="seedy-rain-val">' + fmt(rain.weekly, ' mm', 1) + '</span><span class="seedy-rain-lbl">Semana</span></div>'
      + '<div class="seedy-rain-item"><span class="seedy-rain-val">' + fmt(rain.monthly, ' mm', 1) + '</span><span class="seedy-rain-lbl">Mes</span></div>'
      + '<div class="seedy-rain-item seedy-rain-total"><span class="seedy-rain-val">' + fmt(rain.yearly, ' mm', 1) + '</span><span class="seedy-rain-lbl">Año</span></div>'
      + '</div>'
      + '</div>'
      + '<div class="seedy-device-meta">'
      + '<span>📡 Ecowitt GW2000A · ' + seenStr + '</span>'
      + '</div>'
      + '</div>';
  }

  function _renderAirQualityCard(dev, gallineros) {
      var fname = dev.friendly_name || '';
      var gName = dev.gallinero_name || 'Sin asignar';
      var temp = dev.last_temperature;
      var hum = dev.last_humidity;
      var co2 = dev.last_co2;
      var voc = dev.last_voc;
      var formaldehyd = dev.last_formaldehyd;
      var lqi = dev.last_linkquality;
      var seen = dev.last_seen;
      var isOnline = seen !== null && seen !== undefined;

      var tempStr = temp !== null && temp !== undefined ? temp.toFixed(1) + '°C' : '—';
      var humStr = hum !== null && hum !== undefined ? hum.toFixed(0) + '%' : '—';
      var co2Str = co2 !== null && co2 !== undefined ? co2 + ' ppm' : '—';
      var vocStr = voc !== null && voc !== undefined ? voc + ' ppb' : '—';
      var formalStr = formaldehyd !== null && formaldehyd !== undefined ? formaldehyd + ' µg/m³' : '—';
      var seenStr = '—';
      if (seen) {
        try {
          var d = new Date(seen);
          var now = new Date();
          var diffMin = Math.floor((now - d) / 60000);
          if (diffMin < 1) seenStr = 'ahora';
          else if (diffMin < 60) seenStr = 'hace ' + diffMin + ' min';
          else if (diffMin < 1440) seenStr = 'hace ' + Math.floor(diffMin/60) + 'h';
          else seenStr = d.toLocaleDateString('es');
        } catch(e) { seenStr = '?'; }
      }

      // CO2 color (green <800, yellow <1200, red >=1200)
      var co2Color = '#f3f4f6';
      if (co2 !== null && co2 !== undefined) {
        if (co2 < 800) co2Color = '#22c55e';
        else if (co2 < 1200) co2Color = '#f59e0b';
        else co2Color = '#ef4444';
      }

      // VOC color (green <300, yellow <500, red >=500)
      var vocColor = '#f3f4f6';
      if (voc !== null && voc !== undefined) {
        if (voc < 300) vocColor = '#22c55e';
        else if (voc < 500) vocColor = '#f59e0b';
        else vocColor = '#ef4444';
      }

      // Formaldehyde color (green <30, yellow <100, red >=100)
      var formalColor = '#f3f4f6';
      if (formaldehyd !== null && formaldehyd !== undefined) {
        if (formaldehyd < 30) formalColor = '#22c55e';
        else if (formaldehyd < 100) formalColor = '#f59e0b';
        else formalColor = '#ef4444';
      }

      // Temperature color
      var tempColor = '#f3f4f6';
      if (temp !== null && temp !== undefined) {
        if (temp < 10) tempColor = '#3b82f6';
        else if (temp < 18) tempColor = '#22c55e';
        else if (temp < 28) tempColor = '#f59e0b';
        else tempColor = '#ef4444';
      }

      // LQI signal bars
      var lqiBars = '';
      var lqiLevel = lqi ? Math.min(Math.ceil(lqi / 51), 5) : 0;
      for (var i = 1; i <= 5; i++) {
        var h = 6 + i * 3;
        lqiBars += '<span style="height:' + h + 'px" class="' + (i <= lqiLevel ? 'active' : '') + '"></span>';
      }

      return '<div class="seedy-device-card ' + (isOnline ? '' : 'offline') + '" style="grid-column: span 2;">'
        + '<div class="seedy-device-card-header">'
        + '<h3>🌬️ Calidad del Aire · ' + _escHtml(gName) + '</h3>'
        + '<span class="seedy-device-status ' + (isOnline ? 'online' : 'offline') + '">' + (isOnline ? '● Online' : '● Offline') + '</span>'
        + '</div>'
        + '<div class="seedy-weather-readings">'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🌡️</div><div class="seedy-reading-value" style="color:' + tempColor + '">' + tempStr + '</div><div class="seedy-reading-label">Temperatura</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">💧</div><div class="seedy-reading-value">' + humStr + '</div><div class="seedy-reading-label">Humedad</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">💨</div><div class="seedy-reading-value" style="color:' + co2Color + '">' + co2Str + '</div><div class="seedy-reading-label">CO₂</div></div>'
        + '</div>'
        + '<div class="seedy-weather-extra">'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🧪</div><div class="seedy-reading-value" style="color:' + vocColor + '">' + vocStr + '</div><div class="seedy-reading-label">VOC</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">⚗️</div><div class="seedy-reading-value" style="color:' + formalColor + '">' + formalStr + '</div><div class="seedy-reading-label">Formaldehído</div></div>'
        + '</div>'
        // Nota aclaratoria de límites
        + '<div class="seedy-air-quality-info">'
        + '<details><summary>ℹ️ ¿Qué mide este sensor? — Límites de referencia</summary>'
        + '<table class="seedy-limits-table">'
        + '<tr><th>Métrica</th><th>Qué mide</th><th style="color:#22c55e">✓ Bueno</th><th style="color:#f59e0b">⚠ Moderado</th><th style="color:#ef4444">✗ Malo</th></tr>'
        + '<tr><td><b>CO₂</b></td><td>Dióxido de carbono — indicador de ventilación. Niveles altos causan estrés y bajan la puesta.</td><td>&lt; 800 ppm</td><td>800–1200 ppm</td><td>&gt; 1200 ppm</td></tr>'
        + '<tr><td><b>VOC</b></td><td>Compuestos Orgánicos Volátiles (ppb) — gases de cama húmeda, heces, desinfectantes. Irritan vías respiratorias.</td><td>&lt; 300 ppb</td><td>300–500 ppb</td><td>&gt; 500 ppb</td></tr>'
        + '<tr><td><b>HCHO</b></td><td>Formaldehído (µg/m³) — gas tóxico de materiales, desinfectantes o combustión. Límite OMS: 100 µg/m³.</td><td>&lt; 30 µg/m³</td><td>30–100 µg/m³</td><td>&gt; 100 µg/m³</td></tr>'
        + '<tr><td><b>Temp.</b></td><td>Temperatura ambiente del gallinero. Rango ideal gallinas ponedoras: 15–25 °C.</td><td>10–28 °C</td><td>5–10 / 28–32 °C</td><td>&lt; 5 / &gt; 32 °C</td></tr>'
        + '<tr><td><b>Humedad</b></td><td>Humedad relativa. Ideal 50–70%. Alta humedad favorece hongos y amoníaco.</td><td>40–70%</td><td>30–40 / 70–80%</td><td>&lt; 30 / &gt; 80%</td></tr>'
        + '</table>'
        + '<p style="margin:6px 0 0;font-size:0.8em;color:#9ca3af">Sensor Tuya TS0601 · Alimentación red · Zigbee router · Actualización cada ~60s</p>'
        + '</details>'
        + '</div>'
        + '<div class="seedy-device-meta">'
        + '<span>📡 ' + _escHtml(fname) + ' · ' + seenStr + '</span>'
        + '<span class="seedy-lqi-bar" title="Señal: ' + (lqi || 0) + '/255">' + lqiBars + '</span>'
        + '</div>'
        + '</div>';
  }

  function _renderZigbeeCard(dev, gallineros) {
      var fname = dev.friendly_name || '';
      var gName = dev.gallinero_name || 'Sin asignar';
      var temp = dev.last_temperature;
      var hum = dev.last_humidity;
      var bat = dev.last_battery;
      var lqi = dev.last_linkquality;
      var seen = dev.last_seen;
      var isOnline = seen !== null && seen !== undefined;

      // If we have data from status endpoint, override
      if (dev.gallinero_id && gallineros[dev.gallinero_id]) {
        var gs = gallineros[dev.gallinero_id];
        if (gs.temperature !== null && gs.temperature !== undefined) temp = gs.temperature;
        if (gs.humidity !== null && gs.humidity !== undefined) hum = gs.humidity;
        if (gs.battery !== null && gs.battery !== undefined) bat = gs.battery;
        if (gs.linkquality !== null && gs.linkquality !== undefined) lqi = gs.linkquality;
        if (gs.last_seen) { seen = gs.last_seen; isOnline = true; }
      }

      var tempStr = temp !== null && temp !== undefined ? temp.toFixed(1) + '°C' : '—';
      var humStr = hum !== null && hum !== undefined ? hum.toFixed(1) + '%' : '—';
      var batStr = bat !== null && bat !== undefined ? bat + '%' : '—';
      var seenStr = '—';
      if (seen) {
        try {
          var d = new Date(seen);
          var now = new Date();
          var diffMin = Math.floor((now - d) / 60000);
          if (diffMin < 1) seenStr = 'ahora';
          else if (diffMin < 60) seenStr = 'hace ' + diffMin + ' min';
          else if (diffMin < 1440) seenStr = 'hace ' + Math.floor(diffMin/60) + 'h';
          else seenStr = d.toLocaleDateString('es');
        } catch(e) { seenStr = '?'; }
      }

      // LQI signal bars (0-255)
      var lqiBars = '';
      var lqiLevel = lqi ? Math.min(Math.ceil(lqi / 51), 5) : 0;
      for (var i = 1; i <= 5; i++) {
        var h = 6 + i * 3;
        lqiBars += '<span style="height:' + h + 'px" class="' + (i <= lqiLevel ? 'active' : '') + '"></span>';
      }

      // Temperature color
      var tempColor = '#f3f4f6';
      if (temp !== null && temp !== undefined) {
        if (temp < 10) tempColor = '#3b82f6';
        else if (temp < 18) tempColor = '#22c55e';
        else if (temp < 28) tempColor = '#f59e0b';
        else tempColor = '#ef4444';
      }

      return '<div class="seedy-device-card ' + (isOnline ? '' : 'offline') + '">'
        + '<div class="seedy-device-card-header">'
        + '<h3>🏠 ' + _escHtml(gName) + '</h3>'
        + '<span class="seedy-device-status ' + (isOnline ? 'online' : 'offline') + '">' + (isOnline ? '● Online' : '● Offline') + '</span>'
        + '</div>'
        + '<div class="seedy-device-readings">'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🌡️</div><div class="seedy-reading-value" style="color:' + tempColor + '">' + tempStr + '</div><div class="seedy-reading-label">Temperatura</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">💧</div><div class="seedy-reading-value">' + humStr + '</div><div class="seedy-reading-label">Humedad</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🔋</div><div class="seedy-reading-value">' + batStr + '</div><div class="seedy-reading-label">Batería</div></div>'
        + '</div>'
        + '<div class="seedy-device-meta">'
        + '<span>📡 ' + _escHtml(fname) + ' · ' + seenStr + '</span>'
        + '<span class="seedy-lqi-bar" title="Señal: ' + (lqi || 0) + '/255">' + lqiBars + '</span>'
        + '</div>'
        + '</div>';
  }

  function _renderSoilSensorCard(dev, gallineros) {
      var fname = dev.friendly_name || '';
      var gName = dev.gallinero_name || 'Sensor Suelo';
      var temp = dev.last_temperature;
      var hum = dev.last_humidity;  // soil humidity %
      var soilMoisture = dev.last_soil_moisture;
      var bat = dev.last_battery;
      var lqi = dev.last_linkquality;
      var seen = dev.last_seen;
      var isOnline = seen !== null && seen !== undefined;

      // Override from status endpoint if available
      if (dev.gallinero_id && gallineros[dev.gallinero_id]) {
        var gs = gallineros[dev.gallinero_id];
        if (gs.temperature !== null && gs.temperature !== undefined) temp = gs.temperature;
        if (gs.humidity !== null && gs.humidity !== undefined) hum = gs.humidity;
        if (gs.battery !== null && gs.battery !== undefined) bat = gs.battery;
        if (gs.last_seen) { seen = gs.last_seen; isOnline = true; }
      }

      var tempStr = temp !== null && temp !== undefined ? temp.toFixed(1) + '°C' : '—';
      var humStr = hum !== null && hum !== undefined ? hum.toFixed(0) + '%' : '—';
      var batStr = bat !== null && bat !== undefined ? bat + '%' : '—';
      var seenStr = '—';
      if (seen) {
        try {
          var d = new Date(seen);
          var now = new Date();
          var diffMin = Math.floor((now - d) / 60000);
          if (diffMin < 1) seenStr = 'ahora';
          else if (diffMin < 60) seenStr = 'hace ' + diffMin + ' min';
          else if (diffMin < 1440) seenStr = 'hace ' + Math.floor(diffMin/60) + 'h';
          else seenStr = d.toLocaleDateString('es');
        } catch(e) { seenStr = '?'; }
      }

      // Soil temperature color (soil tends to be cooler)
      var tempColor = '#f3f4f6';
      if (temp !== null && temp !== undefined) {
        if (temp < 5) tempColor = '#3b82f6';
        else if (temp < 15) tempColor = '#22c55e';
        else if (temp < 30) tempColor = '#f59e0b';
        else tempColor = '#ef4444';
      }

      // Soil moisture color + irrigation alert
      // <25% = seco (necesita riego urgente), 25-40% = algo seco, 40-70% = ideal, >70% = muy húmedo
      var humColor = '#f3f4f6';
      var irrigationAlert = '';
      if (hum !== null && hum !== undefined) {
        if (hum < 25) {
          humColor = '#ef4444';
          irrigationAlert = '<div class="seedy-soil-alert seedy-soil-alert-urgent">'
            + '<span class="seedy-soil-alert-icon">🚨</span>'
            + '<span><b>¡Riego urgente!</b> Humedad del suelo muy baja (' + hum + '%). Las raíces y el pasto se secan.</span>'
            + '</div>';
        } else if (hum < 40) {
          humColor = '#f59e0b';
          irrigationAlert = '<div class="seedy-soil-alert seedy-soil-alert-warning">'
            + '<span class="seedy-soil-alert-icon">💧</span>'
            + '<span><b>Conviene regar.</b> Humedad del suelo algo baja (' + hum + '%). Regar en las próximas horas.</span>'
            + '</div>';
        } else if (hum <= 70) {
          humColor = '#22c55e';
        } else {
          humColor = '#3b82f6';
          irrigationAlert = '<div class="seedy-soil-alert seedy-soil-alert-info">'
            + '<span class="seedy-soil-alert-icon">🌊</span>'
            + '<span>Suelo muy húmedo (' + hum + '%). No regar — riesgo de encharcamiento.</span>'
            + '</div>';
        }
      }

      // Battery warning
      var batColor = '';
      if (bat !== null && bat !== undefined && bat < 20) {
        batColor = ' style="color:#ef4444"';
      }

      // LQI signal bars
      var lqiBars = '';
      var lqiLevel = lqi ? Math.min(Math.ceil(lqi / 51), 5) : 0;
      for (var i = 1; i <= 5; i++) {
        var h = 6 + i * 3;
        lqiBars += '<span style="height:' + h + 'px" class="' + (i <= lqiLevel ? 'active' : '') + '"></span>';
      }

      return '<div class="seedy-device-card seedy-soil-card ' + (isOnline ? '' : 'offline') + '">'
        + '<div class="seedy-device-card-header">'
        + '<h3>🌱 ' + _escHtml(gName) + '</h3>'
        + '<span class="seedy-device-status ' + (isOnline ? 'online' : 'offline') + '">' + (isOnline ? '● Online' : '● Offline') + '</span>'
        + '</div>'
        + irrigationAlert
        + '<div class="seedy-device-readings">'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🌡️</div><div class="seedy-reading-value" style="color:' + tempColor + '">' + tempStr + '</div><div class="seedy-reading-label">Temp. Suelo</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">💧</div><div class="seedy-reading-value" style="color:' + humColor + '">' + humStr + '</div><div class="seedy-reading-label">Humedad Suelo</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🔋</div><div class="seedy-reading-value"' + batColor + '>' + batStr + '</div><div class="seedy-reading-label">Batería</div></div>'
        + '</div>'
        + '<details style="padding:0 16px 8px"><summary style="font-size:0.8em;color:#9ca3af;cursor:pointer">ℹ️ Umbrales de riego</summary>'
        + '<table class="seedy-limits-table">'
        + '<tr><th>Nivel</th><th>Humedad</th><th>Acción</th></tr>'
        + '<tr style="color:#ef4444"><td>🚨 Seco</td><td>&lt; 25%</td><td>Riego urgente</td></tr>'
        + '<tr style="color:#f59e0b"><td>💧 Algo seco</td><td>25–40%</td><td>Regar pronto</td></tr>'
        + '<tr style="color:#22c55e"><td>✅ Ideal</td><td>40–70%</td><td>No regar</td></tr>'
        + '<tr style="color:#3b82f6"><td>🌊 Húmedo</td><td>&gt; 70%</td><td>No regar — encharcamiento</td></tr>'
        + '</table></details>'
        + '<div class="seedy-device-meta">'
        + '<span>📡 ' + _escHtml(fname) + ' · ' + seenStr + '</span>'
        + '<span class="seedy-lqi-bar" title="Señal: ' + (lqi || 0) + '/255">' + lqiBars + '</span>'
        + '</div>'
        + '</div>';
  }

  function _renderInfraCard(dev) {
      var fname = dev.friendly_name || '';
      var gName = dev.gallinero_name || 'Infraestructura';
      var lqi = dev.last_linkquality;
      var seen = dev.last_seen;
      var isOnline = seen !== null && seen !== undefined;

      var seenStr = '—';
      if (seen) {
        try {
          var d = new Date(seen);
          var now = new Date();
          var diffMin = Math.floor((now - d) / 60000);
          if (diffMin < 1) seenStr = 'ahora';
          else if (diffMin < 60) seenStr = 'hace ' + diffMin + ' min';
          else if (diffMin < 1440) seenStr = 'hace ' + Math.floor(diffMin/60) + 'h';
          else seenStr = d.toLocaleDateString('es');
        } catch(e) { seenStr = '?'; }
      }

      var lqiBars = '';
      var lqiLevel = lqi ? Math.min(Math.ceil(lqi / 51), 5) : 0;
      for (var i = 1; i <= 5; i++) {
        var h = 6 + i * 3;
        lqiBars += '<span style="height:' + h + 'px" class="' + (i <= lqiLevel ? 'active' : '') + '"></span>';
      }

      return '<div class="seedy-device-card seedy-infra-card ' + (isOnline ? '' : 'offline') + '">'
        + '<div class="seedy-device-card-header">'
        + '<h3>🔌 ' + _escHtml(gName) + '</h3>'
        + '<span class="seedy-device-status ' + (isOnline ? 'online' : 'offline') + '">' + (isOnline ? '● Online' : '● Offline') + '</span>'
        + '</div>'
        + '<div class="seedy-device-readings">'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">📶</div><div class="seedy-reading-value">' + (lqi || 0) + '</div><div class="seedy-reading-label">Link Quality</div></div>'
        + '<div class="seedy-reading"><div class="seedy-reading-icon">🔄</div><div class="seedy-reading-value" style="font-size:0.9em">' + _escHtml(dev.model || '') + '</div><div class="seedy-reading-label">Modelo</div></div>'
        + '</div>'
        + '<div class="seedy-device-meta">'
        + '<span>📡 ' + _escHtml(fname) + ' · ' + seenStr + '</span>'
        + '<span class="seedy-lqi-bar" title="Señal: ' + (lqi || 0) + '/255">' + lqiBars + '</span>'
        + '</div>'
        + '</div>';
  }

  function _escHtml(s) {
    var d = document.createElement('div');
    d.textContent = s;
    return d.innerHTML;
  }

  function cleanupDevicesPage() {
    if (_devicesRefreshTimer) { clearInterval(_devicesRefreshTimer); _devicesRefreshTimer = null; }
    var el = document.getElementById("seedy-devices-injected");
    if (el) el.remove();
    document.querySelectorAll("[data-seedy-devices-hidden]").forEach(function (child) {
      child.style.display = "";
      delete child.dataset.seedyDevicesHidden;
    });
  }

  function onPageChange() {
    if (!isTargetFarm()) {
      stopRefreshLoop();
      cleanupDashboardPanel();
      if (_retryTimer) { clearInterval(_retryTimer); _retryTimer = null; }
      return;
    }
    if (isDigitalTwinPage()) {
      // Digital twin pages: no camera injection needed
      stopRefreshLoop();
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
    } else if (isSitePage()) {
      stopRefreshLoop();
      cleanupDashboardPanel();
      cleanupDevicesPage();
      setTimeout(function () { injectSitePage(); }, 400);
    } else if (isDashboardPage()) {
      cleanupSitePage();
      cleanupDevicesPage();
      setTimeout(() => {
        injectDashboardPanel();
        // NO injectCameras() on dashboard — only small thumbnails in the panel
      }, 800);
      retryInjection(() => {
        injectDashboardPanel();
      }, 30000);
    } else if (isGallineroDetailPage()) {
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
      // /gallineros/:id — HERE we show full camera streams
      setTimeout(() => {
        injectCameras();
        startRefreshLoop();
      }, 800);
      retryInjection(() => injectCameras(), 30000);
    } else if (isGallinerosListPage()) {
      // /gallineros — inject small camera thumbnails in each gallinero card
      stopRefreshLoop();
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
      setTimeout(() => injectGallineroListThumbnails(), 800);
      retryInjection(() => injectGallineroListThumbnails(), 30000);
    } else if (isDevicesPage()) {
      stopRefreshLoop();
      cleanupDashboardPanel();
      cleanupSitePage();
      setTimeout(() => { injectDevicesPage(); }, 400);
    } else if (isAveDetailPage()) {
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
      setTimeout(() => {
        injectBirdMonitor();
      }, 800);
    } else if (isAvesPage()) {
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
      setTimeout(() => {
        interceptAvesListClicks();
        injectAvesListMonitor();
      }, 800);
    } else if (isFarmPage()) {
      // Any other farm page
      stopRefreshLoop();
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
    } else {
      stopRefreshLoop();
      cleanupDashboardPanel();
      cleanupSitePage();
      cleanupDevicesPage();
    }
  }

  // ── Enhance OvoSfera edit modal with Seedy capture + photo zoom ──
  function enhanceEditModal() {
    // OvoSfera edit modal: inline-styled div (no classes/role), rendered as:
    //   div[style*="position: fixed; inset: 0"] (overlay)
    //     └─ div[style*="maxWidth: 560"] (the form panel)
    // Also try standard selectors as fallback.
    var modals = [];

    // Strategy 1: find fixed-position overlays containing "Editar Ave"
    document.querySelectorAll("div").forEach(function (el) {
      var s = el.style;
      if (s && s.position === "fixed" && (s.inset === "0px" || s.inset === "0")) {
        var inner = el.querySelector("div");
        if (inner && (inner.textContent || "").includes("Editar")) {
          modals.push(inner);
        }
      }
    });

    // Strategy 2: standard class/role selectors
    document.querySelectorAll("[class*='modal'], [class*='dialog'], [role='dialog'], [class*='Modal']").forEach(function (el) {
      if ((el.textContent || "").includes("Editar") || (el.textContent || "").includes("Subir foto")) {
        modals.push(el);
      }
    });

    // Strategy 3: find any element with h3 containing "Editar Ave" → use its scroll container
    if (!modals.length) {
      document.querySelectorAll("h3").forEach(function (h) {
        if ((h.textContent || "").includes("Editar Ave")) {
          // Walk up to find the scrollable container
          var container = h.closest("div[style*='overflow']") || h.parentElement.parentElement;
          if (container) modals.push(container);
        }
      });
    }

    modals.forEach(function (modal) {
      if (modal.dataset.seedyEnhanced) return;

      modal.dataset.seedyEnhanced = "1";

      // 1. Make existing photo zoomable (robust: retry on load for lazy/data-uri images)
      var photos = modal.querySelectorAll("img");
      photos.forEach(function (img) {
        if (img.classList.contains("seedy-photo-zoomable")) return;
        function makeZoomable() {
          if (img.naturalWidth < 20 && !img.src.startsWith("data:image")) return;
          img.classList.add("seedy-photo-zoomable");
          img.addEventListener("click", function (e) {
            e.stopPropagation();
            openFullscreen(img.src, "Foto del ave");
          });
        }
        if (img.complete && img.naturalWidth > 0) {
          makeZoomable();
        } else {
          img.addEventListener("load", makeZoomable);
        }
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

      // Find the ave ID — OvoSfera's native edit modal has no ID in the DOM.
      // We rely on __seedySelectedAveId set by interceptAvesListClicks.
      var aveId = null;

      // Strategy A: captured from table row click (most reliable)
      if (window.__seedySelectedAveId) {
        aveId = window.__seedySelectedAveId;
      }
      // Strategy B: PAL-YYYY-NNNN in the modal text (visible in "new ave" mode only)
      if (!aveId) {
        var modalText = modal.textContent || "";
        var anillaMatch = modalText.match(/PAL-\d+-(\d+)/);
        if (anillaMatch) aveId = parseInt(anillaMatch[1], 10);
      }
      // Strategy C: URL has /aves/{id} (detail page)
      if (!aveId) {
        var urlMatch = window.location.pathname.match(/\/aves\/(\d+)/);
        if (urlMatch) aveId = parseInt(urlMatch[1], 10);
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
        captureBtn.innerHTML = "📸 Capturar + Identificar";
        captureBtn.title = "Captura una foto nítida y la identifica con IA (Qwen2.5-VL)";

        var manualBtn = document.createElement("button");
        manualBtn.className = "seedy-capture-btn";
        manualBtn.type = "button";
        manualBtn.innerHTML = "📷 Subir foto manual";
        manualBtn.title = "Sube una foto desde tu dispositivo para identificar";
        manualBtn.style.background = "linear-gradient(135deg, #6366f1, #8b5cf6)";

        var manualInput = document.createElement("input");
        manualInput.type = "file";
        manualInput.accept = "image/*";
        manualInput.style.display = "none";

        var statusDiv = document.createElement("div");
        statusDiv.className = "seedy-capture-status";

        var idPanel = document.createElement("div");
        idPanel.className = "seedy-id-panel";
        idPanel.style.display = "none";

        // ── Shared: render ID result panel ──
        function renderIdResult(data) {
          var id = data.identification || {};
          var conf = id.confidence || 0;
          var confClass = conf >= 0.75 ? "high" : conf >= 0.5 ? "med" : "low";
          var features = (id.distinctive_features || []).join(", ");

          statusDiv.textContent = (data.source_camera === "manual_upload" ? "Foto subida" : "Foto capturada: " + data.resolution) + " — revisa la identificación:";

          idPanel.className = "seedy-id-panel";
          idPanel.style.display = "block";
          idPanel.innerHTML =
            '<div class="seedy-id-header">' +
              '<img class="seedy-id-photo" src="' + data.photo_data_uri + '" alt="Foto" />' +
              '<div class="seedy-id-info">' +
                '<div><span class="breed">' + (id.breed || "?") + '</span>' +
                '<span class="conf ' + confClass + '">' + Math.round(conf * 100) + '%</span></div>' +
                '<div>Color: ' + (id.color || "?") + ' · Sexo: ' + (id.sex || "?") + '</div>' +
                '<div>Calidad: ' + (id.image_quality || "?") + ' · Modelo: ' + (id.model || "Qwen2.5-VL") + '</div>' +
                (features ? '<div class="features">Rasgos: ' + features + '</div>' : '') +
                (id.reasoning ? '<div class="reasoning">"' + id.reasoning + '"</div>' : '') +
              '</div>' +
            '</div>' +
            '<div class="seedy-id-actions">' +
              '<button class="confirm" data-action="confirm">✅ Confirmar</button>' +
              '<button class="reject" data-action="reject">❌ Rechazar</button>' +
              '<button class="correct" data-action="correct">✏️ Corregir</button>' +
              '<button class="download" data-action="download" title="Guardar foto para subir a otra ficha">💾 Guardar foto</button>' +
            '</div>' +
            '<div class="seedy-correct-form" style="display:none">' +
              '<select class="correct-breed">' +
                '<option value="">— Raza —</option>' +
                '<option>Sussex</option><option>Bresse</option><option>Marans</option>' +
                '<option>Araucana</option><option>Sulmtaler</option><option>Vorwerk</option>' +
                '<option>Pita Pinta</option><option>Andaluza Azul</option>' +
                '<option>Cruce F1</option><option>Desconocida</option>' +
              '</select>' +
              '<input class="correct-color" placeholder="Color" />' +
              '<select class="correct-sex">' +
                '<option value="">— Sexo —</option>' +
                '<option value="gallina">Gallina</option><option value="gallo">Gallo</option>' +
              '</select>' +
              '<button class="confirm" data-action="save-correct">💾 Guardar</button>' +
            '</div>';

          var idPhoto = idPanel.querySelector(".seedy-id-photo");
          if (idPhoto) {
            idPhoto.addEventListener("click", function () {
              openFullscreen(data.photo_data_uri, (id.breed || "Ave") + " " + (id.color || ""));
            });
          }

          var actionBtns = idPanel.querySelectorAll(".seedy-id-actions button");
          actionBtns.forEach(function (btn) {
            btn.addEventListener("click", function (ev) {
              ev.preventDefault();
              ev.stopPropagation();
              var action = btn.dataset.action;

              if (action === "download") {
                var a = document.createElement("a");
                a.href = data.photo_data_uri;
                a.download = "ave_" + (id.breed || "captura").replace(/\s+/g, "_") + "_" + Date.now() + ".jpg";
                a.click();
                return;
              }

              // Si confirma con raza desconocida → forzar corrección
              if (action === "confirm" && (!id.breed || id.breed.toLowerCase() === "desconocida" || id.breed.toLowerCase() === "unknown")) {
                action = "correct";
              }

              if (action === "correct") {
                var form = idPanel.querySelector(".seedy-correct-form");
                form.style.display = "flex";
                var breedSelect = form.querySelector(".correct-breed");
                var colorInput = form.querySelector(".correct-color");
                var sexSelect = form.querySelector(".correct-sex");
                for (var i = 0; i < breedSelect.options.length; i++) {
                  if (breedSelect.options[i].text.toLowerCase() === (id.breed || "").toLowerCase()) {
                    breedSelect.selectedIndex = i; break;
                  }
                }
                colorInput.value = id.color || "";
                for (var j = 0; j < sexSelect.options.length; j++) {
                  if (sexSelect.options[j].value === (id.sex || "")) {
                    sexSelect.selectedIndex = j; break;
                  }
                }
                return;
              }

              if (action === "save-correct") action = "correct";

              actionBtns.forEach(function (b) { b.disabled = true; });
              var saveBtn = idPanel.querySelector("[data-action='save-correct']");
              if (saveBtn) saveBtn.disabled = true;

              var confirmBody = {
                action: action,
                photo_data_uri: data.photo_data_uri,
                breed: id.breed || "",
                color: id.color || "",
                sex: id.sex || "",
                existing_vision_id: (data.ave && data.ave.ai_vision_id) || "",
              };

              if (action === "correct") {
                var form = idPanel.querySelector(".seedy-correct-form");
                confirmBody.breed = form.querySelector(".correct-breed").value || id.breed;
                confirmBody.color = form.querySelector(".correct-color").value || id.color;
                confirmBody.sex = form.querySelector(".correct-sex").value || id.sex;
              }

              fetch(SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/confirm-identity", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(confirmBody),
              })
                .then(function (r) { return r.json(); })
                .then(function (result) {
                  if (action === "reject") {
                    idPanel.className = "seedy-id-panel rejected";
                    statusDiv.textContent = "❌ Identificación rechazada — ai_vision_id y foto limpiados";
                  } else {
                    statusDiv.textContent = (action === "confirm" ? "✅ Confirmado" : "✏️ Corregido") +
                      ": " + confirmBody.breed + " " + confirmBody.color;
                    var imgs = modal.querySelectorAll("img");
                    imgs.forEach(function (img) {
                      if (img.naturalWidth > 20 || img.src.startsWith("data:image")) {
                        img.src = data.photo_data_uri;
                      }
                    });
                  }
                  var actionsDiv = idPanel.querySelector(".seedy-id-actions");
                  if (actionsDiv) actionsDiv.style.display = "none";
                  var correctForm = idPanel.querySelector(".seedy-correct-form");
                  if (correctForm) correctForm.style.display = "none";
                })
                .catch(function (err) {
                  statusDiv.textContent = "❌ Error: " + err.message;
                  actionBtns.forEach(function (b) { b.disabled = false; });
                });
            });
          });
        }

        // ── Capturar desde cámaras ──
        captureBtn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          captureBtn.disabled = true;
          captureBtn.innerHTML = "⏳ Capturando + identificando...";
          statusDiv.textContent = "Buscando al ave en las cámaras y analizando con Qwen2.5-VL...";
          idPanel.style.display = "none";

          fetch(SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/capture-identify", {
            method: "POST",
          })
            .then(function (r) { return r.json(); })
            .then(function (data) {
              captureBtn.innerHTML = "📸 Capturar + Identificar";
              captureBtn.disabled = false;
              if (!data.success) {
                statusDiv.textContent = "⚠️ " + (data.message || "No se pudo capturar") + " — prueba subir foto manual";
                return;
              }
              renderIdResult(data);
            })
            .catch(function (err) {
              statusDiv.textContent = "❌ Error: " + err.message;
              captureBtn.innerHTML = "📸 Capturar + Identificar";
              captureBtn.disabled = false;
            });
        });

        // ── Subir foto manual ──
        manualBtn.addEventListener("click", function (e) {
          e.preventDefault();
          e.stopPropagation();
          manualInput.click();
        });

        manualInput.addEventListener("change", function () {
          var file = manualInput.files[0];
          if (!file) return;
          manualBtn.disabled = true;
          manualBtn.innerHTML = "⏳ Identificando...";
          statusDiv.textContent = "Analizando foto con Qwen2.5-VL...";
          idPanel.style.display = "none";

          var reader = new FileReader();
          reader.onload = function () {
            var dataUri = reader.result;
            fetch(SEEDY_API + "/vision/identify/bird/ovosfera/" + aveId + "/identify-photo", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ photo_data_uri: dataUri }),
            })
              .then(function (r) { return r.json(); })
              .then(function (data) {
                manualBtn.innerHTML = "📷 Subir foto manual";
                manualBtn.disabled = false;
                if (!data.success) {
                  statusDiv.textContent = "⚠️ " + (data.message || "Error al identificar");
                  return;
                }
                renderIdResult(data);
              })
              .catch(function (err) {
                statusDiv.textContent = "❌ Error: " + err.message;
                manualBtn.innerHTML = "📷 Subir foto manual";
                manualBtn.disabled = false;
              });
          };
          reader.readAsDataURL(file);
          manualInput.value = "";
        });

        photoArea.appendChild(captureBtn);
        photoArea.appendChild(manualBtn);
        photoArea.appendChild(manualInput);

        // Digital Twin del Ave button (purple)
        var twinBtn = document.createElement("a");
        twinBtn.className = "seedy-capture-btn";
        twinBtn.style.cssText = "background:linear-gradient(135deg,#8b5cf6,#6d28d9);text-decoration:none;display:inline-flex;align-items:center;gap:4px;margin-top:6px;";
        twinBtn.innerHTML = "🐔 Digital Twin del Ave";
        twinBtn.href = SEEDY_API + "/dashboard/ave_twin.html?id=" + (window.__seedySelectedAnilla || ave.anilla || "PAL-2026-" + String(aveId).padStart(4, "0"));
        twinBtn.target = "_blank";
        photoArea.appendChild(twinBtn);

        photoArea.appendChild(statusDiv);
        photoArea.appendChild(idPanel);
      }
    });
  }

  // ── Init ──
  function init() {
    injectStyles();
    loadSeedyWidget();

    // Inject sidebar link (retry until sidebar available)
    injectSidebarSiteLink();
    var _sidebarRetry = setInterval(function () {
      if (document.getElementById("seedy-site-link")) { clearInterval(_sidebarRetry); return; }
      injectSidebarSiteLink();
    }, 1000);
    setTimeout(function () { clearInterval(_sidebarRetry); }, 15000);

    // Initial check
    onPageChange();

    // Watch for SPA navigation and DOM changes (debounced to prevent storms during navigation)
    let _mutationTimer = null;
    const observer = new MutationObserver(() => {
      if (_mutationTimer) return; // debounce: skip if already scheduled
      _mutationTimer = setTimeout(() => {
        _mutationTimer = null;
        if (!isTargetFarm()) return;
        injectSidebarSiteLink();
        enhanceEditModal(); // inject Seedy into any open OvoSfera edit modal
        // Only inject for the CURRENT page — don't re-inject dashboard on other pages
        if (isSitePage() && !document.getElementById("seedy-site-frame")) {
          injectSitePage();
        } else if (isDashboardPage() && !document.getElementById("seedy-dashboard-injected")) {
          injectDashboardPanel();
        } else if (isGallineroDetailPage()) {
          injectCameras();
        } else if (isAveDetailPage()) {
          injectBirdMonitor();
        } else if (isDevicesPage() && !document.getElementById("seedy-devices-injected")) {
          injectDevicesPage();
        } else if (isAvesPage()) {
          interceptAvesListClicks();
          injectAvesListMonitor();
        }
      }, 300);
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

  // ── ESP32 Audio helpers ──
  window._seedyRecordAudio = function(deviceId, btn) {
    if (!SEEDY_API || !deviceId) return;
    btn.disabled = true;
    btn.textContent = '⏺ Grabando...';
    btn.style.background = '#ef4444';
    fetch(SEEDY_API + '/ovosfera/esp32/' + deviceId + '/audio?seconds=5')
      .then(function(r) {
        if (!r.ok) throw new Error('HTTP ' + r.status);
        return r.blob();
      })
      .then(function(blob) {
        var url = URL.createObjectURL(blob);
        // Play audio
        var audio = new Audio(url);
        audio.play().catch(function(){});
        // Also offer download
        var a = document.createElement('a');
        a.href = url; a.download = 'seedy_' + deviceId + '_' + Date.now() + '.wav';
        a.click();
        btn.textContent = '✅ Grabado';
        btn.style.background = '#22c55e';
        setTimeout(function() { btn.textContent = '⏺ Grabar 5s'; btn.style.background = '#4ecdc4'; btn.disabled = false; }, 3000);
      })
      .catch(function(e) {
        btn.textContent = '❌ Error';
        btn.style.background = '#ef4444';
        setTimeout(function() { btn.textContent = '⏺ Grabar 5s'; btn.style.background = '#4ecdc4'; btn.disabled = false; }, 3000);
      });
  };

  // Poll audio levels for ESP32 cards
  function _pollEsp32AudioLevels() {
    ['palacio', 'pequeno'].forEach(function(devId) {
      var el = document.getElementById('audio-level-' + devId);
      if (!el || !SEEDY_API) return;
      fetch(SEEDY_API + '/ovosfera/esp32/' + devId + '/audio/level')
        .then(function(r) { return r.ok ? r.json() : null; })
        .then(function(d) {
          if (!d) return;
          el.textContent = d.db_fs.toFixed(0) + ' dBFS (peak ' + d.peak + ')';
          el.style.color = d.db_fs > -20 ? '#4ecdc4' : '#888';
        })
        .catch(function() { el.textContent = '— dBFS'; el.style.color = '#666'; });
    });
  }
  setInterval(_pollEsp32AudioLevels, 10000);

  // Start when DOM ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
