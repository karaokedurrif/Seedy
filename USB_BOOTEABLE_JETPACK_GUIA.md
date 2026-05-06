# USB Booteable JetPack 6.2 para Jetson Orin Nano 8GB

**Fecha:** 5 mayo 2026  
**Propósito:** Crear USB booteable para instalar JetPack 6.2 en Jetson Orin Nano

---

## 🎯 MÉTODO RECOMENDADO: balenaEtcher (GUI)

### Script
```bash
~/Documentos/CREAR_USB_JETPACK_ETCHER.sh
```

### Qué hace
1. ✅ Instala balenaEtcher automáticamente (AppImage)
2. ✅ Abre navegador en página de descarga NVIDIA
3. ✅ Detecta la imagen descargada
4. ✅ Extrae el .img del .zip
5. ✅ Lanza Etcher con interfaz gráfica
6. ✅ Muestra instrucciones post-flasheo

### Ventajas
- 🟢 **Fácil:** Interfaz gráfica intuitiva
- 🟢 **Seguro:** Validación automática de la escritura
- 🟢 **Visual:** Barra de progreso en tiempo real
- 🟢 **Rápido:** Optimizado para velocidad

---

## ⚙️ MÉTODO ALTERNATIVO: dd (línea de comandos)

### Script
```bash
~/Documentos/CREAR_USB_JETPACK.sh
```

### Qué hace
1. ✅ Detecta dispositivos USB conectados
2. ✅ Descarga imagen JetPack (si es posible sin login)
3. ✅ Descomprime automáticamente
4. ✅ Escribe al USB con `dd`
5. ✅ Muestra progreso con `status=progress`

### Ventajas
- 🟢 **Universal:** Funciona en cualquier Linux
- 🟢 **Scriptable:** Automatizable 100%
- 🟢 **Sin dependencias:** Solo herramientas estándar

---

## 📋 REQUISITOS

| Requisito | Detalle |
|-----------|---------|
| **USB** | 16GB mínimo, USB 3.0 recomendado |
| **Imagen** | JetPack 6.2 (~15-20 GB) |
| **Cuenta NVIDIA** | Gratuita, requiere registro |
| **Tiempo** | 30-40 minutos total |
| **Conexión** | Buena para descargar imagen |

---

## 🚀 PROCESO COMPLETO (paso a paso)

### PARTE 1: Crear USB Booteable (MSI portátil)

1. **Conecta USB a MSI** (16GB+, será borrado)

2. **Ejecuta script** (elige uno):
   ```bash
   # Opción 1: GUI con Etcher
   ~/Documentos/CREAR_USB_JETPACK_ETCHER.sh
   
   # Opción 2: CLI con dd
   ~/Documentos/CREAR_USB_JETPACK.sh
   ```

3. **Descarga imagen** desde NVIDIA Developer:
   - URL: https://developer.nvidia.com/embedded/jetpack
   - Busca: "Jetson Orin Nano Developer Kit SD Card Image"
   - Versión: JetPack 6.2 (R36.x)
   - Archivo: `jetson-orin-nano-devkit-sd-card-image-*.zip`

4. **Sigue las instrucciones del script**

5. **Espera** que termine (10-20 min según velocidad USB)

### PARTE 2: Bootear desde USB (Jetson)

1. **Apaga Jetson** (desconecta DC)

2. **Inserta USB** en Jetson (puerto USB 3.0 si es posible)

3. **Conecta monitor + teclado** (DisplayPort/HDMI + USB)

4. **Enciende Jetson** (conecta DC)

5. **Presiona ESC** cuando veas cuenta regresiva

6. **Entra a Boot Manager**

7. **Selecciona USB Storage** (o "EFI USB Device")

8. **Espera el instalador de Ubuntu** (~30 segundos)

### PARTE 3: Instalar JetPack en eMMC (Jetson)

El instalador gráfico de Ubuntu te guiará:

| Campo | Valor |
|-------|-------|
| **Idioma** | Español (o English) |
| **Keyboard** | Spanish |
| **Usuario** | jetson |
| **Password** | 4431Durr |
| **Hostname** | jetson-edge-seedy |
| **Instalación** | Borrar disco y usar todo (eMMC) |

⏱️ **Tiempo:** 20-30 minutos

### PARTE 4: Primer Boot (Jetson)

1. **Remueve el USB** cuando el instalador termine

2. **Reinicia** la Jetson

3. **Login:**
   - User: jetson
   - Password: 4431Durr

4. **Configura red Ethernet:**
   ```bash
   sudo nmcli con mod "Wired connection 1" ipv4.addresses "10.10.10.250/24"
   sudo nmcli con mod "Wired connection 1" ipv4.method manual
   sudo nmcli con up "Wired connection 1"
   ```

5. **Habilita SSH:**
   ```bash
   sudo systemctl enable ssh
   sudo systemctl start ssh
   ```

6. **Test desde MSI:**
   ```bash
   ssh jetson@10.10.10.250
   # Password: 4431Durr
   ```

### PARTE 5: Activar Super Mode (67 TOPS)

```bash
ssh jetson@10.10.10.250

# Ver modo actual
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

## 🎯 PRÓXIMOS PASOS (después de Super Mode)

1. **Instalar dependencias Edge Pipeline:**
   ```bash
   sudo apt update
   sudo apt install -y python3-venv python3-pip redis-tools ffmpeg
   ```

2. **Transferir YOLO desde DGX:**
   ```bash
   scp daviddgx@192.168.20.57:~/seedy/yolo_models/yolov8s.pt ~/
   ```

3. **Convertir YOLO a TensorRT:**
   ```bash
   # Script de conversión (crear después)
   python3 convert_yolo_to_tensorrt.py yolov8s.pt
   ```

4. **Implementar camera supervisors** (Phase 6 Prompt v4.5)

5. **Setup Redis queue** → DGX backend

---

## ⚠️ TROUBLESHOOTING

### USB no aparece en Boot Manager
- ✅ Verifica que el USB sea USB 3.0 o 2.0 (algunos USB-C no funcionan)
- ✅ Prueba otro puerto USB de la Jetson
- ✅ Re-escribe el USB con el otro script (dd vs Etcher)

### Instalador no arranca
- ✅ Verifica que descargaste la imagen correcta: "Orin Nano", no "Orin NX"
- ✅ Re-descarga la imagen (puede estar corrupta)
- ✅ Usa checksum MD5/SHA256 si NVIDIA lo proporciona

### Jetson no bootea después de instalar
- ✅ Asegúrate de haber removido el USB antes de reiniciar
- ✅ Entra al Boot Manager y verifica que esté seleccionado el eMMC

### No hay red después de instalar
- ✅ Verifica cable Ethernet conectado
- ✅ Ejecuta: `ip link show` para ver interfaces
- ✅ Configura IP manualmente con `nmcli` (ver Parte 4)

---

## 📊 COMPARACIÓN: USB vs SDK Manager vs Recovery

| Método | Tiempo | Dificultad | Requisitos |
|--------|--------|------------|------------|
| **USB Booteable** | 40 min | ⭐⭐ Fácil | USB 16GB + monitor |
| **SDK Manager** | 60 min | ⭐⭐⭐ Media | USB-C + recovery mode |
| **Recovery Serial** | 90 min | ⭐⭐⭐⭐ Difícil | Cables especiales |

**Recomendación:** Si tienes monitor → USB booteable (este método)

---

## 📝 CHECKLIST FINAL

### Pre-flasheo
- [ ] USB 16GB+ disponible (será borrado)
- [ ] Cuenta NVIDIA Developer creada
- [ ] Imagen JetPack 6.2 descargada
- [ ] Script ejecutado exitosamente
- [ ] USB validado (Etcher muestra checkmark)

### Post-instalación
- [ ] Jetson bootea desde eMMC (USB removido)
- [ ] Login funciona (jetson / 4431Durr)
- [ ] Red Ethernet configurada (10.10.10.250)
- [ ] SSH accesible desde MSI
- [ ] Super Mode activado (67 TOPS)
- [ ] `nvidia-smi` muestra GPU info
- [ ] `tegrastats` muestra EMC 3199MHz

---

**Última actualización:** 5 mayo 2026 19:45 CEST  
**Scripts:** `CREAR_USB_JETPACK.sh`, `CREAR_USB_JETPACK_ETCHER.sh`  
**Documentos relacionados:** `JETSON_SITUACION_ACTUAL_05MAY.md`, `JETSON_SETUP_GUIDE.md`
