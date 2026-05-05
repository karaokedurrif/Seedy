# 📡 Configurar WiFi en Jetson Orin Nano

**Objetivo:** Conectar el Jetson a la red WiFi 192.168.20.x para acceso SSH desde el portátil MSI.

---

## 🖥️ PASO 1: EN EL JETSON (Monitor HDMI + Teclado)

### Opción A: Interfaz Gráfica (si tienes desktop)

1. Click en el ícono de red (arriba derecha)
2. Selecciona tu red WiFi
3. Ingresa la contraseña
4. Espera a que conecte
5. Abre terminal y ejecuta:

```bash
# Ver la IP asignada
ip addr show wlan0 | grep "inet "
```

Apunta la IP (será algo como 192.168.20.xxx).

---

### Opción B: Terminal (método nmcli - recomendado)

```bash
# Ver redes WiFi disponibles
sudo nmcli dev wifi list

# Conectar a tu red (reemplaza NOMBRE_RED y CONTRASEÑA)
sudo nmcli dev wifi connect "NOMBRE_RED" password "CONTRASEÑA"

# Verificar conexión
nmcli con show

# Ver IP asignada
ip addr show wlan0 | grep "inet "
```

**Ejemplo real:**
```bash
# Si tu WiFi se llama "Casa-5G" con contraseña "mipassword123"
sudo nmcli dev wifi connect "Casa-5G" password "mipassword123"
```

---

### Opción C: wpa_supplicant (método manual)

```bash
# Crear configuración WiFi
sudo bash -c 'wpa_passphrase "NOMBRE_RED" "CONTRASEÑA" >> /etc/wpa_supplicant/wpa_supplicant.conf'

# Reiniciar WiFi
sudo systemctl restart wpa_supplicant
sudo dhclient wlan0

# Ver IP
ip addr show wlan0
```

---

## 🔍 PASO 2: ENCONTRAR LA IP DEL JETSON

Una vez conectado, ejecuta en el Jetson:

```bash
# Obtener IP WiFi
hostname -I | awk '{print $1}'

# O más detallado
ip addr show wlan0 | grep "inet " | awk '{print $2}' | cut -d'/' -f1
```

**Apunta esta IP** (ejemplo: 192.168.20.99).

---

## 🔐 PASO 3: CONFIGURAR SSH (si no está activo)

En el Jetson, ejecuta:

```bash
# Instalar OpenSSH Server (si no está)
sudo apt update
sudo apt install -y openssh-server

# Habilitar y arrancar SSH
sudo systemctl enable ssh
sudo systemctl start ssh

# Verificar que esté corriendo
sudo systemctl status ssh

# Ver el puerto (debe ser 22)
sudo netstat -tulpn | grep ssh
```

---

## 💻 PASO 4: CONECTAR DESDE EL PORTÁTIL MSI

Una vez que tengas la IP del Jetson (ejemplo: 192.168.20.99):

```bash
# Test de conectividad
ping -c 3 192.168.20.99

# SSH al Jetson (usuario por defecto: jetson)
ssh jetson@192.168.20.99

# Si es la primera conexión, aceptar fingerprint (yes)
```

---

## 🔑 PASO 5: CONFIGURAR CLAVES SSH (opcional pero recomendado)

Desde el portátil MSI:

```bash
# Generar clave SSH (si no tienes)
ssh-keygen -t ed25519 -C "davidia@msi-vector" -f ~/.ssh/id_ed25519_jetson -N ""

# Copiar clave pública al Jetson
ssh-copy-id -i ~/.ssh/id_ed25519_jetson.pub jetson@192.168.20.99

# Probar conexión sin contraseña
ssh -i ~/.ssh/id_ed25519_jetson jetson@192.168.20.99 "hostname && uname -a"
```

---

## 📊 VERIFICAR CONECTIVIDAD

Desde el portátil MSI, ejecuta:

```bash
# Escanear red 192.168.20.x buscando el Jetson
sudo nmap -sn 192.168.20.0/24 | grep -B 2 -i "nvidia\|jetson\|tegra"

# O buscar por MAC address de NVIDIA
arp -a | grep -i "38:a7:46"  # MACs NVIDIA empiezan con este prefijo a veces
```

---

## 🛠️ SCRIPT AUTOMÁTICO DE BÚSQUEDA

Guarda esto como `~/find_jetson.sh`:

```bash
#!/bin/bash

echo "🔍 Buscando Jetson en la red 192.168.20.x..."
echo ""

# Método 1: nmap
if command -v nmap &> /dev/null; then
    echo "📡 Escaneando con nmap..."
    sudo nmap -sn 192.168.20.0/24 | grep -B 2 "Jetson\|NVIDIA\|Tegra" && echo ""
fi

# Método 2: Escanear IPs activas y probar SSH en puerto 22
echo "🔎 Probando SSH en IPs activas..."
for ip in 192.168.20.{50..150}; do
    # Ping rápido
    ping -c 1 -W 1 $ip &>/dev/null
    if [ $? -eq 0 ]; then
        # Probar SSH
        timeout 2 nc -z $ip 22 &>/dev/null
        if [ $? -eq 0 ]; then
            echo "✅ $ip tiene SSH activo"
            
            # Intentar obtener hostname
            HOSTNAME=$(timeout 3 ssh -o StrictHostKeyChecking=no -o ConnectTimeout=2 jetson@$ip "hostname" 2>/dev/null)
            if [ -n "$HOSTNAME" ]; then
                echo "   Hostname: $HOSTNAME"
            fi
        fi
    fi
done

echo ""
echo "🎯 Si encontraste una IP, conéctate con:"
echo "   ssh jetson@<IP>"
```

Ejecuta:

```bash
chmod +x ~/find_jetson.sh
~/find_jetson.sh
```

---

## 📝 RESUMEN RÁPIDO

1. **En el Jetson (HDMI+teclado):**
   ```bash
   sudo nmcli dev wifi connect "TU_RED_WIFI" password "TU_PASSWORD"
   hostname -I  # Apunta la IP
   ```

2. **En el portátil MSI:**
   ```bash
   ssh jetson@<IP_DEL_JETSON>
   ```

---

## ❓ TROUBLESHOOTING

### El Jetson no aparece en `nmcli dev wifi list`

```bash
# Verificar que el adaptador WiFi existe
ip link show | grep wlan

# Si no existe, verificar hardware
lspci | grep -i wireless
lsusb | grep -i wireless

# Activar interfaz WiFi
sudo ip link set wlan0 up
```

### No puedo hacer SSH (Connection refused)

```bash
# En el Jetson, verificar que SSH está corriendo
sudo systemctl status ssh

# Ver logs de SSH
sudo journalctl -u ssh -n 50

# Verificar firewall
sudo ufw status
```

### El Jetson tiene IP pero no hay internet

```bash
# En el Jetson, verificar gateway
ip route

# Si falta gateway, agregarlo (ejemplo: gateway 192.168.20.1)
sudo ip route add default via 192.168.20.1

# Verificar DNS
cat /etc/resolv.conf

# Si falta DNS, agregarlo
echo "nameserver 8.8.8.8" | sudo tee -a /etc/resolv.conf
```

---

**Creado:** 4 mayo 2026  
**Autor:** GitHub Copilot (ia-expert mode)
