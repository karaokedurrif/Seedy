# 🔧 CONEXIÓN AL DGX — RECORDATORIO PERMANENTE

**Creado:** 12 mayo 2026  
**Importancia:** CRÍTICA

---

## ⚠️ ERROR COMÚN QUE NUNCA MÁS DEBE OCURRIR

❌ **INCORRECTO:** `davidia@192.168.20.57`  
✅ **CORRECTO:** `daviddgx@192.168.20.57`

---

## CREDENCIALES DGX (MEMORIZAR)

```
Usuario:  daviddgx
Password: 4431
IP:       192.168.20.57
Hostname: thinkstationpgx-caca
Ruta:     ~/seedy/ (/home/davidia/Documentos/Seedy/)
```

---

## COMANDO RÁPIDO DE CONEXIÓN

```bash
# SSH
ssh daviddgx@192.168.20.57
# Password: 4431

# RSYNC con password
sshpass -p '4431' rsync -avz archivo.py daviddgx@192.168.20.57:~/seedy/

# SCP
scp archivo.py daviddgx@192.168.20.57:~/seedy/

# Test rápido
ssh daviddgx@192.168.20.57 "hostname && whoami"
# Output: thinkstationpgx-caca
#         daviddgx
```

---

## POR QUÉ ES CRÍTICO RECORDARLO

1. **DGX = Servidor de producción** (no el portátil)
2. **Stack completo:** 15 contenedores Docker
3. **Backend FastAPI :8000** corriendo 24/7
4. **Cámaras 4K** conectadas (red 10.10.10.x)
5. **Datos de producción** (InfluxDB, Qdrant, behavior events)

**Este portátil = solo programar**  
**DGX = producción real**

---

## HISTORIAL DEL PROBLEMA (12 mayo 2026)

- ❌ Intenté `davidia@192.168.20.57` → Permission denied
- ❌ Probé 3 passwords diferentes → todos fallaron
- ✅ Búsqueda en workspace encontró: `daviddgx`
- ✅ Conexión exitosa inmediatamente
- ✅ 13 archivos copiados (72 KB)

**Tiempo perdido:** 15 minutos  
**Solución:** Buscar en workspace con `@workspace`

---

## VERIFICACIÓN

```bash
ping -c 1 192.168.20.57 && \
ssh daviddgx@192.168.20.57 "echo '✅ Conexión OK: $(hostname) ($(whoami))'"
```

**Output esperado:**
```
✅ Conexión OK: thinkstationpgx-caca (daviddgx)
```

---

## COMANDOS FRECUENTES EN DGX

```bash
# Ver logs
ssh daviddgx@192.168.20.57 "cd ~/seedy && docker compose logs --tail=50 seedy-backend"

# Reiniciar backend
ssh daviddgx@192.168.20.57 "cd ~/seedy && docker compose restart seedy-backend"

# Git pull
ssh daviddgx@192.168.20.57 "cd ~/seedy && git pull origin main"

# Editar .env
ssh daviddgx@192.168.20.57
nano ~/seedy/backend/.env
docker compose restart seedy-backend
exit
```

---

## MINI PC (KARAOKE) — SECUNDARIO

```
Usuario:  karaoke@192.168.40.128
Password: 1234
Función:  Bridge drone_bridge.py :9090 → Bebop 2
```

---

**📌 RECORDAR SIEMPRE:** 
- DGX usuario = `daviddgx` (NO `davidia`)
- Portátil = solo programar
- DGX = producción
