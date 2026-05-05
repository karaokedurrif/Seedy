# 🔧 Troubleshooting Jetson USB Device Mode

**Problema:** El Jetson Orin Nano no aparece como dispositivo USB en el portátil MSI.  
**Síntoma:** No hay interfaz `usb0` o `enx*` en `ip addr show`, no aparece en `lsusb`.

---

## ✅ PROCEDIMIENTO DE DIAGNÓSTICO

### Paso 1: Verificar que el cable transmite datos

**Desconecta y reconecta el USB-C** mientras ejecutas este comando:

```bash
# Monitorear eventos USB en tiempo real
watch -n 0.5 'lsusb | tail -15'
```

**¿Qué debes ver?**  
- Cuando conectes el Jetson, debería aparecer una **nueva línea** en lsusb
- Si no aparece nada → el cable NO transmite datos o el Jetson no está en modo Device

---

### Paso 2: Activar el puerto USB Device en el Jetson

El Jetson tiene **2 puertos USB-C**:
- **Puerto 1:** USB Device (para conectar a PC) — suele estar marcado como "OTG" o cerca de la alimentación
- **Puerto 2:** USB Host (para periféricos)

**IMPORTANTE:** Debes conectar el cable al puerto correcto (USB Device/OTG).

---

### Paso 3: Verificar que el Jetson tiene USB Device Mode activado

Si puedes acceder al Jetson por monitor HDMI o por red WiFi:

```bash
# SSH al Jetson (si está en WiFi)
ssh jetson@<IP_JETSON_EN_WIFI>

# Verificar que USB Device está configurado
cat /sys/kernel/config/usb_gadget/l4t/UDC
# Debe mostrar algo como: 3550000.xudc

# Verificar IP asignada a usb0
ip addr show usb0
# Debe mostrar: inet 192.168.55.1/24
```

**Si `usb0` NO existe en el Jetson o no tiene IP:**

```bash
# Activar USB Device Network manualmente
sudo modprobe g_ether
sudo ip addr add 192.168.55.1/24 dev usb0
sudo ip link set usb0 up
```

---

### Paso 4: Configurar el portátil MSI (cuando aparezca la interfaz USB)

Una vez que el Jetson aparezca como dispositivo USB en el portátil, ejecuta:

```bash
# Detectar la nueva interfaz USB
NEW_IFACE=$(ip link show | grep -oP '^\d+: \K(usb\d+|enx[0-9a-f]+)' | head -1)
echo "Interfaz USB detectada: $NEW_IFACE"

# Configurar IP en el portátil (192.168.55.0/24)
sudo ip addr add 192.168.55.100/24 dev $NEW_IFACE
sudo ip link set $NEW_IFACE up

# Verificar conectividad
ping -c 3 192.168.55.1

# SSH al Jetson
ssh jetson@192.168.55.1
```

---

## 🛠️ SCRIPT AUTOMÁTICO DE DETECCIÓN

Guarda esto como `~/jetson_usb_setup.sh`:

```bash
#!/bin/bash

echo "🔍 Esperando interfaz USB del Jetson..."
echo "Conecta/desconecta el USB-C del Jetson ahora."
echo ""

while true; do
    # Buscar interfaces USB (usb0, enx*)
    USB_IFACE=$(ip link show | grep -oP '^\d+: \K(usb\d+|enx[0-9a-f]+)' | head -1)
    
    if [ -n "$USB_IFACE" ]; then
        echo "✅ Interfaz USB detectada: $USB_IFACE"
        
        # Configurar IP
        echo "🔧 Configurando IP 192.168.55.100/24..."
        sudo ip addr add 192.168.55.100/24 dev $USB_IFACE 2>/dev/null || true
        sudo ip link set $USB_IFACE up
        
        # Verificar
        echo "📡 Probando conectividad con el Jetson (192.168.55.1)..."
        if ping -c 2 -W 2 192.168.55.1 >/dev/null 2>&1; then
            echo ""
            echo "╔═══════════════════════════════════════════════════╗"
            echo "║  ✅ JETSON CONECTADO POR USB                    ║"
            echo "╚═══════════════════════════════════════════════════╝"
            echo ""
            echo "🎯 Conecta por SSH:"
            echo "   ssh jetson@192.168.55.1"
            echo ""
            exit 0
        else
            echo "⚠️ Interfaz detectada pero no responde en 192.168.55.1"
            echo "Verifica que el Jetson tenga USB Device Mode activo."
        fi
        
        sleep 5
    fi
    
    sleep 1
done
```

Ejecuta:

```bash
chmod +x ~/jetson_usb_setup.sh
~/jetson_usb_setup.sh
```

---

## ❓ PREGUNTAS FRECUENTES

### P: No aparece nada en lsusb cuando conecto el Jetson

**R:** El cable no transmite datos o estás usando el puerto USB-C incorrecto:
- Prueba con otro cable USB-C (debe ser USB 3.0+)
- Verifica que estás usando el puerto USB **Device/OTG**, no el Host

### P: Aparece en lsusb pero no crea interfaz de red

**R:** El Jetson no tiene USB Device Network activado:
- Conecta por HDMI o WiFi y ejecuta: `sudo modprobe g_ether`
- Verifica: `ip addr show usb0`

### P: El Jetson no tiene WiFi configurada y no tengo monitor HDMI

**R:** Necesitas flashear el Jetson con SDK Manager:
- Sigue la guía `JETSON_SETUP_GUIDE.md` (modo recovery)
- SDK Manager configurará automáticamente USB Device Mode

---

## 🎯 SIGUIENTE PASO SI NADA FUNCIONA

Si el Jetson no aparece como dispositivo USB después de probar todo lo anterior:

1. **Flashear el Jetson con SDK Manager** (requiere modo recovery):
   - Botón REC + RST → lsusb muestra "NVIDIA APX"
   - SDK Manager → JetPack 6.2
   - Activar Super Mode

2. **Usar Ethernet en lugar de USB:**
   - Conecta el Jetson a la red 10.10.10.x vía cable Ethernet
   - Configura IP estática 10.10.10.250/24
   - SSH desde el DGX o portátil

---

**Creado:** 4 mayo 2026  
**Autor:** GitHub Copilot (ia-expert mode)
