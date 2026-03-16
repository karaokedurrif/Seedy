#!/bin/bash
# apply-pwa-branding.sh — Copies Seedy PWA icons + manifest into Open WebUI container
# Run after docker compose up, or as a post-start hook.

set -e
ICON_DIR="$(cd "$(dirname "$0")/../Icons" && pwd)"
CONTAINER="open-webui"

echo "Applying Seedy PWA branding..."

# Static icons
docker cp "$ICON_DIR/favicon.png"                   "$CONTAINER:/app/build/static/favicon.png"
docker cp "$ICON_DIR/favicon.png"                   "$CONTAINER:/app/build/favicon.png"
docker cp "$ICON_DIR/favicon.ico"                   "$CONTAINER:/app/build/static/favicon.ico"
docker cp "$ICON_DIR/apple-touch-icon.png"          "$CONTAINER:/app/build/static/apple-touch-icon.png"
docker cp "$ICON_DIR/icon-192.png"                  "$CONTAINER:/app/build/static/favicon-96x96.png"
docker cp "$ICON_DIR/web-app-manifest-192x192.png"  "$CONTAINER:/app/build/static/web-app-manifest-192x192.png"
docker cp "$ICON_DIR/web-app-manifest-512x512.png"  "$CONTAINER:/app/build/static/web-app-manifest-512x512.png"
docker cp "$ICON_DIR/icon-512.png"                  "$CONTAINER:/app/build/static/splash.png"
docker cp "$ICON_DIR/icon-512.png"                  "$CONTAINER:/app/build/static/splash-dark.png"
docker cp "$ICON_DIR/logo.png"                      "$CONTAINER:/app/build/static/logo.png"

# Also copy to /app/backend/open_webui/static/ (used by some routes)
docker cp "$ICON_DIR/favicon.png"                   "$CONTAINER:/app/backend/open_webui/static/favicon.png"
docker cp "$ICON_DIR/favicon.ico"                   "$CONTAINER:/app/backend/open_webui/static/favicon.ico"
docker cp "$ICON_DIR/apple-touch-icon.png"          "$CONTAINER:/app/backend/open_webui/static/apple-touch-icon.png"
docker cp "$ICON_DIR/icon-192.png"                  "$CONTAINER:/app/backend/open_webui/static/favicon-96x96.png"

# manifest.json (root)
docker exec "$CONTAINER" sh -c 'cat > /app/build/manifest.json << MEOF
{
  "name": "Seedy - NeoFarm AI",
  "short_name": "Seedy",
  "description": "Asistente tecnico agrotech de NeoFarm",
  "start_url": "/",
  "scope": "/",
  "display": "standalone",
  "orientation": "portrait",
  "theme_color": "#1a7a3a",
  "background_color": "#ffffff",
  "icons": [
    {"src": "/static/favicon.png",                  "sizes": "32x32",   "type": "image/png"},
    {"src": "/static/apple-touch-icon.png",          "sizes": "180x180", "type": "image/png"},
    {"src": "/static/web-app-manifest-192x192.png",  "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/static/web-app-manifest-192x192.png",  "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
    {"src": "/static/web-app-manifest-512x512.png",  "sizes": "512x512", "type": "image/png", "purpose": "any"},
    {"src": "/static/web-app-manifest-512x512.png",  "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ]
}
MEOF'

# site.webmanifest (static)
docker exec "$CONTAINER" sh -c 'cat > /app/build/static/site.webmanifest << MEOF
{
  "name": "Seedy - NeoFarm AI",
  "short_name": "Seedy",
  "description": "Asistente tecnico agrotech de NeoFarm",
  "icons": [
    {"src": "/static/web-app-manifest-192x192.png",  "sizes": "192x192", "type": "image/png", "purpose": "any"},
    {"src": "/static/web-app-manifest-192x192.png",  "sizes": "192x192", "type": "image/png", "purpose": "maskable"},
    {"src": "/static/web-app-manifest-512x512.png",  "sizes": "512x512", "type": "image/png", "purpose": "any"},
    {"src": "/static/web-app-manifest-512x512.png",  "sizes": "512x512", "type": "image/png", "purpose": "maskable"}
  ],
  "theme_color": "#1a7a3a",
  "background_color": "#ffffff",
  "display": "standalone"
}
MEOF'

echo "✅ Seedy PWA branding applied successfully"

# Patch env.py to remove "(Open WebUI)" suffix from WEBUI_NAME
docker exec "$CONTAINER" sed -i 's/WEBUI_NAME += " (Open WebUI)"/pass  # Seedy patch: no suffix/' /app/backend/open_webui/env.py 2>/dev/null || true
echo "✅ WEBUI_NAME suffix removed"
