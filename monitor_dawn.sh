#!/bin/bash
# Monitor de amanecer — captura estado del loop de identificación
# Se ejecuta con: bash monitor_dawn.sh
# Escribe resultados en monitor_dawn.log

LOG="/home/davidia/Documentos/Seedy/monitor_dawn.log"
API="http://localhost:8000"

check() {
    echo "══════════════════════════════════════════════" >> "$LOG"
    echo "🕐 CHECK $(date '+%Y-%m-%d %H:%M:%S')" >> "$LOG"
    echo "══════════════════════════════════════════════" >> "$LOG"

    # 1. Estado del loop
    STATUS=$(curl -s "$API/vision/identify/status")
    RUNNING=$(echo "$STATUS" | python3 -c "import json,sys; print(json.load(sys.stdin).get('running','?'))" 2>/dev/null)
    echo "Loop running: $RUNNING" >> "$LOG"

    # 2. Detecciones por cámara
    echo "$STATUS" | python3 -c "
import json, sys
d = json.load(sys.stdin)
for cam, info in d.get('last_results', {}).items():
    a = info.get('analysis', {})
    ts = info.get('timestamp','?')[:19]
    birds = a.get('birds', [])
    breeds = [b.get('breed','?') for b in birds]
    print(f'  {info.get(\"camera\",cam)}: {a.get(\"total_visible\",0)} aves visibles, {len(birds)} identificadas {breeds} (cycle {info.get(\"cycle\")}, {ts})')
" >> "$LOG" 2>/dev/null

    # 3. Brillo actual de cámaras
    python3 -c "
import httpx, io
from PIL import Image, ImageStat
cams = [
    ('Durrif I',  'http://10.10.10.11/cgi-bin/snapshot.cgi'),
    ('Durrif II', 'http://10.10.10.10/cgi-bin/snapshot.cgi'),
]
for name, url in cams:
    try:
        r = httpx.get(url, auth=('admin','123456'), timeout=5)
        img = Image.open(io.BytesIO(r.content))
        b = ImageStat.Stat(img.convert('L')).mean[0]
        mode = 'COLOR' if img.mode == 'RGB' and img.getpixel((0,0))[0] != img.getpixel((0,0))[1] else 'IR/BN'
        print(f'  {name}: brightness={b:.0f}/255 mode={mode} size={img.size}')
    except Exception as e:
        print(f'  {name}: ERROR {e}')
" >> "$LOG" 2>/dev/null

    # 4. Últimos logs del backend relevantes
    echo "  --- Últimos logs relevantes ---" >> "$LOG"
    docker compose -f /home/davidia/Documentos/Seedy/docker-compose.yml logs seedy-backend --tail=50 2>&1 | \
        grep -iE "Full cycle|Quick scan|Poca luz|reanudando|birds? ID|register|sync|error|WARNING" | \
        tail -10 >> "$LOG" 2>/dev/null

    echo "" >> "$LOG"
}

# Cabecera
echo "" >> "$LOG"
echo "🌅 MONITOR AMANECER — $(date '+%Y-%m-%d')" >> "$LOG"
echo "Checks programados: 07:00, 07:30, 08:00" >> "$LOG"

# Esperar hasta las 07:00
TARGET_7="07:00"
TARGET_730="07:30"
TARGET_8="08:00"

wait_until() {
    local target="$1"
    while [[ "$(date +%H:%M)" < "$target" ]]; do
        sleep 30
    done
}

echo "⏳ Esperando hasta las 07:00... (iniciado $(date '+%H:%M'))" >> "$LOG"

wait_until "$TARGET_7"
check

wait_until "$TARGET_730"
check

wait_until "$TARGET_8"
check

echo "✅ Monitoreo completado. Revisa: $LOG" >> "$LOG"
echo "🏁 Monitor finalizado $(date '+%H:%M')" >> "$LOG"
