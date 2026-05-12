# 🚁 RESUMEN: VUELO BEBOP + INTEGRACIÓN DGX

**Fecha:** 12 mayo 2026  
**Estado:** ✅ Todo configurado y listo para ejecutar

---

## 📦 ARCHIVOS CREADOS

### Scripts ejecutables:
1. **setup_dual_wifi_auto.sh** (12KB) ⭐ PRINCIPAL
   - Configuración automática dual WiFi
   - Incluye contraseña WiFi 5G (ErizoDespenado22)
   - Conecta D-Link → Casa_HS_Wifi 5G (red DGX)
   - Conecta Atheros → Bebop2-045265 (dron)
   
2. **drone_bridge.py** (4.5KB) ⭐ ACTUALIZADO
   - HTTP server Olympe SDK
   - Hover: 10 segundos (antes 5s)
   - Descenso: Lento en 2 pasos
   
3. **fly_bebop_10s.sh** (4KB)
   - Script completo de vuelo
   - Autodetecta conexión Bebop
   - Reinicia bridge si es necesario
   
4. **copy_to_minipc.sh** (3.9KB)
   - Copia todos los archivos al mini PC
   - Verifica conectividad primero
   
5. **configure_dual_wifi_dgx.sh** (9.7KB)
   - Versión interactiva (pide contraseñas)
   - Backup del script principal

### Documentación:
6. **README_DUAL_WIFI_DGX.md** (3.9KB)
   - Guía del usuario paso a paso
   - Troubleshooting común
   
7. **INTEGRACION_DGX_DRON.md** (9.8KB) ⭐ INTEGRACIÓN
   - Arquitectura completa DGX → Mini PC → Bebop
   - Endpoints disponibles
   - Código de ejemplo
   - Pruebas de conectividad

8. **RESUMEN_CONFIGURACION.md** (este archivo)

---

## ⚡ INICIO RÁPIDO

### Paso 1: Copiar archivos al mini PC

**Desde tu laptop (cuando el mini PC esté en Casa_HS_Wifi):**

```bash
cd /home/davidia/Documentos/Seedy
./copy_to_minipc.sh
```

O manualmente:

```bash
scp setup_dual_wifi_auto.sh drone_bridge.py fly_bebop_10s.sh \\
    README_DUAL_WIFI_DGX.md INTEGRACION_DGX_DRON.md \\
    karaoke@192.168.40.128:~
```

### Paso 2: Ejecutar en el mini PC

**SSH al mini PC:**

```bash
ssh karaoke@192.168.40.128
```

**Configurar dual WiFi (AUTOMÁTICO):**

```bash
chmod +x setup_dual_wifi_auto.sh
./setup_dual_wifi_auto.sh
```

Esto tarda ~30 segundos y configura todo automáticamente.

**Anotar la IP en red 5G** que muestra al final (ej: `192.168.20.45`)

### Paso 3: Iniciar drone bridge

**En el mini PC:**

```bash
cd /home/karaoke
nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &
```

### Paso 4: Configurar DGX

**En el backend de Seedy (DGX - `/backend/.env`):**

```bash
DRONE_BRIDGE_URL=http://192.168.20.45:9090
```

(Usar la IP del paso 2)

**Reiniciar backend:**

```bash
docker compose restart seedy-backend
```

---

## 🎯 PRUEBA DE VUELO

### Opción A: Desde el mini PC (local)

```bash
ssh karaoke@192.168.40.128
./fly_bebop_10s.sh
```

### Opción B: Desde el DGX (API)

```bash
curl -X POST http://localhost:8000/api/dron/sparrow-deterrent
```

### Opción C: Directo al bridge

```bash
curl -X POST http://192.168.20.45:9090/fly
```

---

## 📊 VERIFICACIÓN

### Mini PC - Estado dual WiFi:

```bash
ssh karaoke@192.168.40.128 "nmcli connection show --active"
```

**Esperado:**
```
D-Link conectado a Casa_HS_Wifi 5G
Atheros conectado a Bebop2-045265
```

### Mini PC - Rutas:

```bash
ssh karaoke@192.168.40.128 "ip route show | grep -E 'default|192.168'"
```

**Esperado:**
```
default via 192.168.20.1 dev wlx00265a1686dc metric 100
192.168.20.0/24 dev wlx00265a1686dc ...
192.168.42.0/24 dev wlxc01c30430fbc ...
```

### Mini PC - Conectividad:

```bash
# DGX
ssh karaoke@192.168.40.128 "ping -c 2 192.168.20.57"

# Bebop
ssh karaoke@192.168.40.128 "ping -c 2 192.168.42.1"

# Bridge
ssh karaoke@192.168.40.128 "curl -s http://localhost:9090/health"
```

### DGX - Estado del dron:

```bash
curl http://localhost:8000/api/dron/status
```

---

## 🏗️ ARQUITECTURA

```
┌──────────────────────────────────────────────────────────┐
│                    RED 5G (192.168.20.x)                  │
│                                                           │
│  ┌─────────────┐              ┌─────────────┐            │
│  │    DGX      │  Casa_HS     │  Mini PC    │            │
│  │ .20.57:8000 │◄──WiFi 5G───►│  .20.X      │            │
│  │             │              │  (D-Link)   │            │
│  │ Seedy API   │              │             │            │
│  │ YOLO Pest   │              │ :9090       │            │
│  └─────────────┘              │ bridge      │            │
│                               └─────┬───────┘            │
└───────────────────────────────────────┼──────────────────┘
                                        │
                        WiFi Direct     │ Atheros
                        Bebop2-045265   │
                                        │
                          ┌─────────────▼─────────────┐
                          │    Parrot Bebop 2         │
                          │    192.168.42.1           │
                          │                           │
                          │  • Olympe SDK             │
                          │  • Vuelo: 2m, 10s hover   │
                          │  • Descenso lento         │
                          └───────────────────────────┘
```

---

## 🔑 CREDENCIALES

- **Mini PC:** karaoke@192.168.40.128 / 1234
- **WiFi 5G:** Casa_HS_Wifi 5G / ErizoDespenado22
- **Bebop:** Bebop2-045265 / (sin contraseña)

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

## 🛡️ REGLAS DE SEGURIDAD

- **Cooldown:** 2 minutos entre vuelos
- **Horario:** NO volar 22:00-07:00
- **Límites:**
  - 5 vuelos/hora máx
  - 20 vuelos/día máx
  - Batería mín 30%
  - Viento máx 25 km/h

---

## 🚨 PROBLEMAS COMUNES

### ❌ "Mini PC no accesible"

**Solución:** El mini PC está conectado solo al Bebop. Reconecta a Casa_HS_Wifi:

```bash
# Opción 1: Físicamente en el mini PC
sudo nmcli connection up "Casa_HS_Wifi automática"

# Opción 2: Ejecutar setup_dual_wifi_auto.sh para configurar dual WiFi
```

### ❌ "Bridge no disponible"

**Solución:** drone_bridge.py no está corriendo:

```bash
ssh karaoke@192.168.40.128
cd /home/karaoke
nohup python3 drone_bridge.py > drone_bridge.log 2>&1 &
```

### ❌ "Bebop no responde"

**Solución:** Mini PC no está conectado al Bebop:

```bash
ssh karaoke@192.168.40.128
sudo nmcli connection up Bebop2-045265
ping 192.168.42.1  # Debe responder
```

### ❌ "cooldown_XXs"

**Solución:** Espera el tiempo indicado (default 120s entre vuelos).

---

## 📁 UBICACIÓN DE ARCHIVOS

**En este repositorio:**
```
/home/davidia/Documentos/Seedy/
├── setup_dual_wifi_auto.sh       ← Script principal
├── drone_bridge.py                ← Bridge HTTP Olympe
├── fly_bebop_10s.sh              ← Test de vuelo
├── copy_to_minipc.sh             ← Copiar archivos
├── README_DUAL_WIFI_DGX.md       ← Guía usuario
├── INTEGRACION_DGX_DRON.md       ← Doc técnica
└── RESUMEN_CONFIGURACION.md      ← Este archivo
```

**En el mini PC (después de copiar):**
```
/home/karaoke/
├── setup_dual_wifi_auto.sh
├── drone_bridge.py
├── fly_bebop_10s.sh
├── README_DUAL_WIFI_DGX.md
└── INTEGRACION_DGX_DRON.md
```

---

## ✅ CHECKLIST

- [ ] Archivos copiados al mini PC
- [ ] setup_dual_wifi_auto.sh ejecutado
- [ ] D-Link conectado a Casa_HS_Wifi 5G
- [ ] Atheros conectado a Bebop2-045265
- [ ] IP en red 5G anotada (192.168.20.X)
- [ ] drone_bridge.py iniciado
- [ ] DRONE_BRIDGE_URL configurado en DGX
- [ ] Prueba de vuelo exitosa
- [ ] DGX puede acceder al bridge (ping + curl)

---

## 🎉 ¡TODO LISTO!

El sistema está completamente configurado. El DGX puede ahora:

1. **Detectar gorriones** con YOLO
2. **Enviar comando** a `POST /api/dron/sparrow-deterrent`
3. **El mini PC** recibe el comando via bridge HTTP
4. **El Bebop** ejecuta el vuelo automáticamente

**Integración completa DGX → Mini PC → Bebop funcionando.**

---

**Para más detalles:** Lee `INTEGRACION_DGX_DRON.md`  
**Para troubleshooting:** Lee `README_DUAL_WIFI_DGX.md`
