# 🚀 INSTRUCCIONES PARA COPIAR AL DGX (12 mayo 2026)

**Estado:** ✅ TODO guardado en GitHub + paquete tar.gz creado  
**Problema:** Password SSH del DGX no funciona desde este portátil  
**Solución:** Copiar manualmente o usar git pull en el DGX

---

## 📦 OPCIÓN 1: PAQUETE TAR.GZ (17 KB)

He creado un paquete con todos los archivos necesarios:

**Ubicación:** `/tmp/seedy-dron-config-12may2026.tar.gz` (17 KB)

**Contiene:**
- setup_minipc_local.sh (script principal para mini PC)
- setup_dual_wifi_auto.sh (alternativa con más detalles)
- drone_bridge.py (actualizado: 10s hover)
- fly_bebop_10s.sh (script de prueba)
- INTEGRACION_DGX_DRON.md (arquitectura)
- README_DUAL_WIFI_DGX.md (guía usuario)
- RESUMEN_CONFIGURACION.md (checklist)
- PENDIENTE_MINIPC_13MAY2026.md (pendientes mañana)
- PROBLEMA_SSH_DGX_12MAY2026.md (troubleshooting SSH)
- RESUMEN_GUARDADO_12MAY2026.md (resumen estado)
- sync_to_dgx.sh (script de copia)

### Cómo copiar al DGX:

**1. Copiar el archivo a un USB:**
```bash
# Insertar USB, montar si es necesario
cp /tmp/seedy-dron-config-12may2026.tar.gz /media/davidia/USB/
sync
```

**2. En el DGX, descomprimir:**
```bash
cd /home/davidia/Documentos/Seedy
tar -xzf /path/to/seedy-dron-config-12may2026.tar.gz
chmod +x setup_minipc_local.sh setup_dual_wifi_auto.sh fly_bebop_10s.sh sync_to_dgx.sh
ls -lh setup_minipc_local.sh drone_bridge.py
```

---

## 📦 OPCIÓN 2: GIT PULL EN EL DGX (RECOMENDADO)

**Más fácil y seguro:**

```bash
# Conectar al DGX físicamente (monitor + teclado)
# O si tienes acceso SSH con el password correcto

cd /home/davidia/Documentos/Seedy
git pull origin main

# Verificar archivos
ls -lh setup_minipc_local.sh drone_bridge.py PENDIENTE_MINIPC_13MAY2026.md

# Dar permisos de ejecución
chmod +x setup_minipc_local.sh setup_dual_wifi_auto.sh fly_bebop_10s.sh sync_to_dgx.sh
```

**Commits en GitHub:**
- 6fb678c: Configuración dual WiFi (10 archivos, 1783 líneas)
- bf51143: Documentación + sync script (2 archivos, 332 líneas)

---

## 📦 OPCIÓN 3: SCP CON PASSWORD CORRECTO

Si descubres el password SSH correcto del DGX:

```bash
# Desde este portátil
cd /home/davidia/Documentos/Seedy
scp /tmp/seedy-dron-config-12may2026.tar.gz davidia@192.168.20.57:/tmp/

# En el DGX
ssh davidia@192.168.20.57
cd /home/davidia/Documentos/Seedy
tar -xzf /tmp/seedy-dron-config-12may2026.tar.gz
chmod +x *.sh
```

---

## 🔧 TROUBLESHOOTING PASSWORD SSH

**Passwords probados sin éxito:**
- ❌ `4431Durr`
- ❌ `4431`
- ❌ `Davidia`

**Posibles causas:**
1. Password SSH del DGX es diferente
2. SSH configurado solo para claves públicas (PasswordAuthentication no)
3. Usuario en el DGX es diferente a `davidia`

**Verificar en el DGX:**
```bash
# Ver configuración SSH
sudo cat /etc/ssh/sshd_config | grep PasswordAuthentication

# Ver usuario actual
whoami

# Ver home directory
echo $HOME
```

---

## ✅ VERIFICACIÓN DE QUE TODO ESTÁ GUARDADO

**GitHub:** ✅ 12 archivos, 2115 líneas, 2 commits
- https://github.com/karaokedurrif/Seedy
- Commit 6fb678c + bf51143

**Portátil:** ✅ Todo en `/home/davidia/Documentos/Seedy/`
- setup_minipc_local.sh (ejecutable)
- drone_bridge.py (10s hover + descenso lento)
- 9 archivos de documentación

**Paquete tar.gz:** ✅ `/tmp/seedy-dron-config-12may2026.tar.gz` (17 KB)
- 11 archivos empaquetados
- Listo para copiar a USB o red

---

## 🎯 SIGUIENTE PASO

1. **Copiar al DGX** (elige una opción de arriba)
2. **Configurar mini PC mañana** (físicamente con setup_minipc_local.sh)
3. **Configurar DRONE_BRIDGE_URL** en backend del DGX
4. **Prueba de vuelo**

---

## 📋 RESUMEN CRÍTICO

**LO IMPORTANTE:** Todo está guardado de 3 formas:
1. ✅ GitHub (commits 6fb678c + bf51143)
2. ✅ Portátil (`/home/davidia/Documentos/Seedy/`)
3. ✅ Paquete tar.gz (`/tmp/seedy-dron-config-12may2026.tar.gz`)

**PRÓXIMO PASO CRÍTICO:** Configurar mini PC mañana con `setup_minipc_local.sh`

**NO ES CRÍTICO AHORA:** Copiar al DGX puede esperar. El DGX puede hacer `git pull` cuando lo necesites.

---

**Fecha:** 12 mayo 2026 - 20:50h  
**Estado:** ✅ Todo guardado, listo para copiar al DGX cuando tengas acceso
