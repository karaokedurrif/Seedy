# Mini PC — Configurar IP Fija 192.168.40.54

## Situación (13 mayo 2026)

El Mini PC Zigbee (user: karaoke) fue reiniciado y reporta IP **192.168.40.54**.  
**Problema:** La IP no responde a ping todavía (el Mini PC puede estar arrancando o la red no está lista).

## Pasos para configurar IP fija en el Mini PC

### Opción 1: Desde el propio Mini PC (físicamente)

```bash
# 1. Abrir terminal en el Mini PC

# 2. Ver conexiones actuales
nmcli connection show

# 3. Identificar conexión WiFi (ej: "WiFi-Home" o similar)
WIFI_NAME="WiFi-Home"  # Reemplazar con el nombre real

# 4. Configurar IP fija 192.168.40.54
sudo nmcli connection modify "$WIFI_NAME" \
  ipv4.addresses "192.168.40.54/24" \
  ipv4.gateway "192.168.40.1" \
  ipv4.dns "8.8.8.8,1.1.1.1" \
  ipv4.method manual

# 5. Reconectar
sudo nmcli connection down "$WIFI_NAME"
sudo nmcli connection up "$WIFI_NAME"

# 6. Verificar
ip addr show | grep "192.168.40.54"
ping -c 3 192.168.40.1  # Ping al gateway
```

### Opción 2: Desde interfaz gráfica (Linux Mint)

1. Clic en icono de red (esquina superior derecha)
2. **Configuración de red** → WiFi conectado
3. ⚙️ Engranaje (Settings)
4. Pestaña **IPv4**
5. Método: **Manual**
6. Agregar dirección:
   - **Address:** 192.168.40.54
   - **Netmask:** 255.255.255.0 (o /24)
   - **Gateway:** 192.168.40.1
7. **DNS:** 8.8.8.8, 1.1.1.1
8. **Aplicar** → Reconectar WiFi

### Opción 3: Editar netplan (si usa netplan en lugar de NetworkManager)

```bash
# 1. Editar configuración
sudo nano /etc/netplan/01-network-manager-all.yaml

# 2. Añadir configuración estática:
network:
  version: 2
  renderer: NetworkManager
  wifis:
    wlp2s0:  # Verificar nombre con: ip link show
      dhcp4: no
      addresses:
        - 192.168.40.54/24
      gateway4: 192.168.40.1
      nameservers:
        addresses: [8.8.8.8, 1.1.1.1]
      access-points:
        "NOMBRE-WIFI":  # Nombre de tu red WiFi
          password: "TU-PASSWORD"

# 3. Aplicar
sudo netplan apply

# 4. Verificar
ip addr show
```

## Verificación desde otro equipo

```bash
# Esperar 30 segundos después de configurar IP fija, luego probar:

# 1. Ping
ping -c 5 192.168.40.54

# 2. SSH
ssh karaoke@192.168.40.54

# 3. Verificar Zigbee2MQTT
ssh karaoke@192.168.40.54 "docker ps | grep zigbee"

# 4. Verificar mensajes MQTT
ssh karaoke@192.168.40.54 "docker logs --tail=50 zigbee2mqtt | grep -i mqtt"
```

## Actualizar configuración backend Seedy

Una vez confirmada la IP fija 192.168.40.54:

### 1. Actualizar telemetry.py (NO NECESARIO - usa hostname "mosquitto")

El servicio `telemetry.py` conecta al broker MQTT del DGX (`mosquitto:1883`), NO al Mini PC directamente.

### 2. Actualizar WiFi Watchdog en Mini PC

```bash
# En el Mini PC
ssh karaoke@192.168.40.54

# Editar watchdog (si existe)
sudo nano /etc/systemd/system/wifi-watchdog.service

# Verificar que apunta al DGX correcto:
# MQTT_HOST=192.168.20.57 (DGX Spark)
# MQTT_PORT=1883

# Reiniciar watchdog
sudo systemctl restart wifi-watchdog
sudo systemctl status wifi-watchdog
```

### 3. Actualizar documentación

```bash
# Archivos a actualizar con nueva IP 192.168.40.54:
# - README_HARDWARE.md
# - DIAGNOSTICO_ZIGBEE_13MAY2026.md
# - /memories/seedy-zigbee-troubleshooting.md
# - Prompt mode ia-expert (sección "HARDWARE Y RED")
```

## Resumen checklist

- [ ] Mini PC encendido y conectado a red
- [ ] IP fija configurada: 192.168.40.54
- [ ] Ping responde desde otro equipo
- [ ] SSH funciona: `ssh karaoke@192.168.40.54`
- [ ] Zigbee2MQTT corriendo: `docker ps | grep zigbee`
- [ ] Z2M publicando a MQTT: ver logs con "Connected to MQTT"
- [ ] Backend DGX recibiendo mensajes: logs de telemetry.py
- [ ] Sensores ONLINE en hub.ovosfera.com/farm/palacio/devices

## Troubleshooting

### Problema: IP 192.168.40.54 no responde después de configurar

**Causa posible:** Conflicto de IP (otro dispositivo ya la tiene)

**Solución:** Verificar con nmap desde otro equipo:
```bash
nmap -sn 192.168.40.0/24 | grep "192.168.40.54"
```

Si aparece pero no responde SSH → firewall o servicio SSH down.

### Problema: WiFi se desconecta constantemente

**Solución:** WiFi Watchdog debe estar activo y configurado correctamente.

```bash
# Ver status
systemctl status wifi-watchdog

# Ver logs
journalctl -u wifi-watchdog -f
```

### Problema: Zigbee2MQTT no arranca

```bash
# Ver logs
docker logs zigbee2mqtt

# Verificar dongle USB
ls -la /dev/ttyUSB* /dev/ttyACM*

# Reiniciar contenedor
docker restart zigbee2mqtt
```

---

**Actualizado:** 13 mayo 2026 11:17 UTC  
**IP Objetivo:** 192.168.40.54 (fija)  
**IP Anterior:** 192.168.40.128 (DHCP, ahora inaccesible)
