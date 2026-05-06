# Jetson Orin Nano — Situación 5 Mayo 2026

**Fecha:** 5 mayo 2026 19:30 CEST  
**Estado:** ✅ Acceso visual obtenido, pendiente flasheo JetPack 6.2

---

## ✅ PROGRESO

### Hardware confirmado
- ✅ Jetson Orin Nano 8GB encendida
- ✅ Alimentación DC conectada
- ✅ USB-C conectado a portátil MSI
- ✅ Ethernet conectado (red cámaras 10.10.10.x)
- ✅ Monitor DisplayPort/HDMI conectado → **ACCESO VISUAL OBTENIDO**

### Estado actual del sistema
- 📺 **Pantalla muestra:** UEFI Interactive Shell v2.2 (EDK II)
- ⚠️ **Diagnóstico:** NO tiene sistema operativo booteable
- 🎯 **Acción requerida:** Flashear JetPack 6.2 con Super Mode (67 TOPS)

### Mapping table visible
```
FS1: Alias(s):F1:
     MemoryMapped(0x0,0x272000000,0x27231FFFF)
FS0: Alias(s):F0:
     PciRoot(0x0)/Pci(0x1,0x4)/USB(0x0,0x0)/USB(0x3,0x0)/HD(1,MBR,0x00000000,0x800,0x3A3800)
```

---

## 🛠️ SCRIPTS CREADOS

### 1. JETSON_FLASHEO_RAPIDO.sh
**Ubicación:** `~/Documentos/JETSON_FLASHEO_RAPIDO.sh`

**Función:**
- Verifica si Jetson está en modo recovery (`lsusb | grep 0955`)
- Valida SDK Manager instalado
- Lanza SDK Manager con configuración guiada

**Uso:**
```bash
~/Documentos/JETSON_FLASHEO_RAPIDO.sh
```

### 2. INSTALAR_SDK_MANAGER.sh
**Ubicación:** `~/Documentos/INSTALAR_SDK_MANAGER.sh`

**Función:**
- Abre navegador en página de descarga NVIDIA SDK Manager
- Guía paso a paso para instalación del .deb
- Requiere cuenta NVIDIA Developer (gratuita)

**Uso:**
```bash
~/Documentos/INSTALAR_SDK_MANAGER.sh
```

---

## 🚀 PRÓXIMOS PASOS

### OPCIÓN A: Intentar boot desde UEFI (2 minutos)

**Si crees que la Jetson ya tiene JetPack instalado:**

1. En la pantalla de la Jetson, presiona **ESC** cuando aparezca la cuenta regresiva
2. Selecciona "**Boot Manager**"
3. Busca opciones con "Linux", "Ubuntu" o "Jetson"
4. Intenta bootear desde ahí

**Resultado esperado:**
- Si bootea → ✅ JetPack ya instalado, continuar con configuración IP/SSH
- Si no bootea → ⚠️ Proceder con OPCIÓN B

### OPCIÓN B: Flashear JetPack 6.2 desde cero (60 minutos) ⭐ RECOMENDADO

#### Paso 1: Instalar SDK Manager (portátil MSI)
```bash
# Descargar
~/Documentos/INSTALAR_SDK_MANAGER.sh
# Abre https://developer.nvidia.com/sdk-manager
# Inicia sesión con cuenta NVIDIA
# Descarga último .deb

# Instalar
cd ~/Descargas
sudo dpkg -i sdkmanager_*.deb
sudo apt install -f
```

#### Paso 2: Poner Jetson en Recovery Mode

**Secuencia física (CRÍTICO):**
1. **Desconecta** alimentación DC de la Jetson
2. **Localiza** botón "REC" o "Force Recovery" (pequeño, cerca de GPIO)
3. **Mantén presionado** el botón REC
4. **Conecta** alimentación DC (mientras mantienes REC)
5. **Cuenta** 2 segundos
6. **Suelta** el botón REC

**Verificación (portátil MSI):**
```bash
lsusb | grep NVIDIA
# Debe mostrar: "Bus XXX Device XXX: ID 0955:7323 NVIDIA Corp. APX"
```

#### Paso 3: Flashear con SDK Manager
```bash
~/Documentos/JETSON_FLASHEO_RAPIDO.sh

# En la interfaz gráfica de SDK Manager:
# 1. Target: Jetson Orin Nano 8GB Developer Kit
# 2. OS: JetPack 6.2 (última disponible)
# 3. Componentes:
#    ✅ Jetson OS
#    ✅ CUDA Toolkit
#    ✅ TensorRT
#    ✅ cuDNN
#    ✅ VPI
# 4. Durante el flasheo:
#    Usuario: jetson
#    Password: 4431Durr
#    Hostname: jetson-edge-seedy
# 5. Tiempo: ~45-60 minutos
```

#### Paso 4: Activar Super Mode (67 TOPS)

**Una vez booteado el Jetson, SSH o terminal local:**
```bash
# Verificar modo actual
sudo /usr/sbin/nvpmodel -q

# Activar MAXN (67 TOPS)
sudo /usr/sbin/nvpmodel -m 0

# Aumentar clocks GPU
sudo /usr/bin/jetson_clocks

# Verificar
sudo tegrastats
# Debe mostrar: EMC 3199MHz, GPU 1300MHz
```

---

## 📊 CONFIGURACIÓN POST-FLASHEO

### Red cámaras (Ethernet)
```bash
# IP estática 10.10.10.250/24
sudo nmcli con mod "Wired connection 1" ipv4.addresses "10.10.10.250/24"
sudo nmcli con mod "Wired connection 1" ipv4.method manual
sudo nmcli con up "Wired connection 1"

# Verificar
ip addr show eth0 | grep "inet "
```

### SSH habilitado
```bash
# Ya viene instalado, solo asegurar
sudo systemctl enable ssh
sudo systemctl start ssh

# Desde portátil MSI
ssh jetson@10.10.10.250
# Password: 4431Durr
```

### Python environment
```bash
# Python 3.10+ ya incluido en JetPack 6.2
python3 --version

# Instalar venv
sudo apt install python3-venv python3-pip

# Crear environment
mkdir -p ~/seedy-edge
cd ~/seedy-edge
python3 -m venv .venv
source .venv/bin/activate
```

### Redis cliente
```bash
pip install redis
```

---

## 🎯 SIGUIENTE FASE: Edge Pipeline (Prompt v4.5)

**Cuando JetPack esté instalado y Jetson accesible por SSH:**

1. **YOLO TensorRT conversion** (Phase 6)
   - Transferir `yolov8s.pt` desde DGX
   - Convertir a TensorRT FP16 en Jetson ARM64
   - Test inference ~30ms/frame

2. **Camera supervisors** (Phase 6)
   - 5× `camera_supervisor.py` (1 por cámara)
   - Sub-stream MJPEG → YOLO → tracker
   - Main-stream capture bajo trigger

3. **Redis queue** (Phase 6)
   - Jetson: `RPUSH events` a `redis://10.10.10.200:6379`
   - DGX: consumer `BLPOP` → `POST /vision/edge_event`

4. **Systemd services** (Phase 6)
   - Auto-start camera supervisors
   - Watchdog restart on crash

---

## 📝 DOCUMENTACIÓN RELACIONADA

- `JETSON_SETUP_GUIDE.md` - Guía completa 17KB
- `JETSON_USB_TROUBLESHOOTING.md` - Troubleshooting USB 5.1KB
- `JETSON_WIFI_SETUP.md` - Configuración WiFi
- `PROGRESO_PROMPT_V4.5.md` - Arquitectura Edge+Core

---

## ✅ CHECKLIST DE VALIDACIÓN

### Pre-flasheo
- [x] Jetson encendida
- [x] Alimentación DC conectada
- [x] USB-C conectado a MSI
- [x] Ethernet conectado
- [x] Monitor conectado → acceso visual
- [x] Scripts creados en MSI
- [ ] SDK Manager instalado
- [ ] Jetson en recovery mode
- [ ] lsusb detecta 0955:7323

### Post-flasheo
- [ ] JetPack 6.2 booteando
- [ ] Super Mode activado (67 TOPS)
- [ ] IP 10.10.10.250 configurada
- [ ] SSH funcional desde MSI
- [ ] Ping a cámaras 10.10.10.x OK
- [ ] Python 3.10+ disponible
- [ ] Redis cliente instalado

---

**Última actualización:** 5 mayo 2026 19:30 CEST  
**Estado:** ✅ Acceso visual obtenido, scripts preparados  
**Próxima acción:** Usuario decide OPCIÓN A (boot) u OPCIÓN B (flasheo)
