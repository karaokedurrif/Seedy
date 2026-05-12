# 🚁 PENDIENTE: CONFIGURACIÓN DUAL WiFi MINI PC (13 mayo 2026)

**Estado:** ✅ Todo el código listo en GitHub - Falta ejecución física en el mini PC

---

## 📦 ARCHIVOS LISTOS (Commit 6fb678c)

### Scripts ejecutables (en /home/davidia/Documentos/Seedy/):
1. **setup_minipc_local.sh** ⭐ USAR ESTE MAÑANA
   - Ejecución directa en el mini PC (con teclado/monitor)
   - Configura dual WiFi automáticamente
   - Inicia drone_bridge.py
   - Muestra IP para configurar en DGX

2. **setup_dual_wifi_auto.sh**
   - Alternativa con más outputs detallados
   - Contraseña WiFi 5G: ErizoDespenado22

3. **drone_bridge.py**
   - HTTP server Olympe SDK
   - Puerto 9090
   - Hover: 10 segundos
   - Descenso: lento en 2 pasos

4. **fly_bebop_10s.sh**
   - Test de vuelo completo
   - 2m altura, 10s hover, descenso controlado

### Documentación:
- **INTEGRACION_DGX_DRON.md** - Arquitectura completa
- **README_DUAL_WIFI_DGX.md** - Guía usuario
- **RESUMEN_CONFIGURACION.md** - Checklist completo

---

## ⚡ INSTRUCCIONES PARA MAÑANA

### PASO 1: En el mini PC (con monitor y teclado)

Abrir terminal (`Ctrl+Alt+T`) y ejecutar:

```bash
cd /home/karaoke
git clone https://github.com/karaokedurrif/Seedy.git seedy-config
cd seedy-config
chmod +x setup_minipc_local.sh
./setup_minipc_local.sh
```

**O si ya tienes el código:**

```bash
cd /home/karaoke
# Buscar el archivo setup_minipc_local.sh
chmod +x setup_minipc_local.sh
./setup_minipc_local.sh
```

**O copiar manualmente** (si no tienes el archivo):

```bash
# Crear el archivo directamente en el mini PC
nano ~/setup_minipc_local.sh
# Copiar el contenido del archivo setup_minipc_local.sh
# Guardar (Ctrl+X, Y, Enter)
chmod +x setup_minipc_local.sh
./setup_minipc_local.sh
```

**Duración:** ~30-40 segundos

**Resultado:** El script mostrará:
```
IP en red DGX (5G): 192.168.20.X
```

**Anotar esa IP** (ej: 192.168.20.45)

---

### PASO 2: En el DGX (192.168.20.57)

Configurar la IP del mini PC en el backend de Seedy:

```bash
# En el DGX
cd /ruta/a/Seedy/backend
nano .env

# Agregar o modificar esta línea:
DRONE_BRIDGE_URL=http://192.168.20.45:9090
# (usar la IP que anotaste del paso 1)

# Guardar y salir (Ctrl+X, Y, Enter)

# Reiniciar backend
docker compose restart seedy-backend
```

---

### PASO 3: Prueba de vuelo

**Desde el DGX:**

```bash
curl -X POST http://localhost:8000/api/dron/sparrow-deterrent
```

**O desde el mini PC:**

```bash
cd /home/karaoke
./fly_bebop_10s.sh
```

---

## 🎯 QUÉ HACE setup_minipc_local.sh

1. ✅ Detecta 2 interfaces WiFi (D-Link por MAC 00:26:5a:16:86:dc, Atheros por MAC c0:1c:30:43:0f:bc)
2. ✅ Desconecta todas las conexiones WiFi actuales
3. ✅ Conecta D-Link → Casa_HS_Wifi 5G (contraseña: ErizoDespenado22)
4. ✅ Configura D-Link con metric 100, autoconnect yes (default route)
5. ✅ Configura Atheros → Bebop2-045265 con never-default (sin default route)
6. ✅ Conecta al Bebop (si está encendido)
7. ✅ Inicia drone_bridge.py en background
8. ✅ Muestra resumen con IP, rutas, conexiones activas

---

## 🏗️ ARQUITECTURA

```
DGX (192.168.20.57)          Mini PC (192.168.20.X)         Bebop (192.168.42.1)
┌─────────────────┐          ┌──────────────────┐           ┌────────────────┐
│ Seedy Backend   │ WiFi 5G  │ D-Link (default) │ WiFi      │ Parrot Bebop 2 │
│ :8000           │◄────────►│ Casa_HS_Wifi 5G  │ Direct    │                │
│                 │          │                  │           │                │
│ YOLO Pest       │          │ Atheros (no-def) │◄─────────►│ Vuelo 2m       │
│ Detection       │          │ Bebop2-045265    │           │ 10s hover      │
│                 │          │                  │           │ Descenso lento │
│                 │          │ drone_bridge.py  │           │                │
│                 │          │ :9090            │           │                │
└─────────────────┘          └──────────────────┘           └────────────────┘
```

---

## 📋 CHECKLIST PARA MAÑANA

- [ ] Conectar monitor + teclado al mini PC
- [ ] Arrancar mini PC
- [ ] Abrir terminal
- [ ] Ejecutar `setup_minipc_local.sh`
- [ ] Anotar IP en red 5G (192.168.20.X)
- [ ] Configurar DRONE_BRIDGE_URL en DGX
- [ ] Reiniciar backend Seedy en DGX
- [ ] Prueba de vuelo
- [ ] Verificar que el Bebop despega, sube 2m, hace hover 10s, baja lentamente

---

## 🛡️ SI ALGO FALLA

### Error: "No se detectaron ambas interfaces WiFi"

**Solución:** Verifica que el D-Link DWA-140 esté conectado por USB:

```bash
lsusb | grep -i "d-link\|07d1:3c0a"
```

Debería mostrar: `Bus 001 Device 003: ID 07d1:3c0a D-Link System DWA-140`

Si no aparece, desconecta y reconecta el USB.

### Error: "No se pudo conectar a Casa_HS_Wifi 5G"

**Solución:** Verifica la contraseña en el script:

```bash
nano setup_minipc_local.sh
# Buscar: password "ErizoDespenado22"
# Verificar que sea correcta
```

### Error: "Bebop no responde"

**Solución:** Verifica que el Bebop esté encendido (LEDs verdes).

### Error: "Bridge no se inició"

**Solución:** Verifica que drone_bridge.py esté en /home/karaoke/:

```bash
ls -lh /home/karaoke/drone_bridge.py
# Si no existe, copiar desde el repositorio
```

---

## 📁 UBICACIONES DE ARCHIVOS

**En GitHub:** https://github.com/karaokedurrif/Seedy (commit 6fb678c)

**En laptop:** `/home/davidia/Documentos/Seedy/`

**Para copiar al mini PC manualmente:**
```bash
# Desde la laptop (cuando el mini PC esté accesible)
scp setup_minipc_local.sh drone_bridge.py fly_bebop_10s.sh karaoke@192.168.40.128:~
```

---

## 🎬 PARÁMETROS DE VUELO

- **Altura:** 2 metros
- **Hover:** 10 segundos (actualizado de 5s)
- **Descenso:** Lento en 2 pasos:
  1. Bajar a 1m
  2. Bajar a 0.5m
  3. Aterrizaje suave
- **Duración total:** ~20-25 segundos

---

## 🔑 CREDENCIALES

- **Mini PC:** karaoke@192.168.40.128 / 1234
- **WiFi 5G:** Casa_HS_Wifi 5G / ErizoDespenado22
- **Bebop:** Bebop2-045265 / (sin contraseña)
- **GitHub:** karaokedurrif/Seedy

---

## ✅ LO QUE YA ESTÁ LISTO

✅ Código actualizado con hover de 10s y descenso lento  
✅ Script de configuración dual WiFi completo  
✅ Script de ejecución local para mini PC  
✅ Documentación completa (3 archivos)  
✅ Backend Seedy con integración del dron  
✅ Todo en GitHub (commit 6fb678c)  
✅ Push exitoso a remote  

---

## ❌ LO QUE FALTA

❌ Ejecutar `setup_minipc_local.sh` en el mini PC (MAÑANA)  
❌ Configurar DRONE_BRIDGE_URL en el DGX  
❌ Prueba de vuelo  

---

**Fecha:** 12 mayo 2026 - 20:35h  
**Siguiente paso:** Ejecutar en mini PC mañana 13 mayo 2026  
**Commit:** 6fb678c  
**Archivos:** 10 archivos (1783 líneas añadidas)
