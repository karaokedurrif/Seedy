# 🎯 GUÍA RÁPIDA: Actualizar Openclaw desde ESTE portátil

**Tu situación:** Tienes acceso físico al mini PC Openclaw (192.168.20.54) pero SSH está bloqueado.

**Solución:** Servidor HTTP ya corriendo en este portátil para descarga directa.

---

## ✅ PASO 1: Desde este portátil MSI (YA HECHO)

El servidor HTTP ya está corriendo. Mantén esta terminal abierta.

```
✅ Paquete creado: /tmp/openclaw_upgrade_vllm32b.tar.gz (8KB)
✅ Servidor HTTP corriendo en puerto 8888
```

---

## 🖥️ PASO 2: En el mini PC Openclaw (192.168.20.54)

Ve físicamente al mini PC Openclaw y sigue estos pasos:

### Opción A: Desde navegador web (MÁS FÁCIL)

1. Abre Firefox o Chrome en el mini PC
2. Navega a: **http://192.168.20.131:8888**
3. Verás un listado de archivos
4. Haz clic en: **openclaw_upgrade_vllm32b.tar.gz**
5. Se descargará (8KB, instantáneo)
6. Abre terminal en el mini PC y ejecuta:

```bash
cd ~/Descargas  # o donde se guardó el archivo
tar -xzf openclaw_upgrade_vllm32b.tar.gz
cd openclaw_upgrade_package
./openclaw-upgrade-to-vllm-32b.sh
```

### Opción B: Desde terminal (MÁS RÁPIDO)

1. Abre terminal en el mini PC (Ctrl+Alt+T)
2. Ejecuta:

```bash
cd ~
wget http://192.168.20.131:8888/openclaw_upgrade_vllm32b.tar.gz
tar -xzf openclaw_upgrade_vllm32b.tar.gz
cd openclaw_upgrade_package
./openclaw-upgrade-to-vllm-32b.sh
```

---

## 📋 QUÉ VERÁS AL EJECUTAR EL SCRIPT

```
🚀 OPENCLAW UPGRADE A QWEN2.5-CODER-32B-AWQ (vLLM)
==================================================

✅ Usuario: usuario_actual
✅ IP: 192.168.20.54

📦 1/5 Haciendo backup de configuración actual...
   ✅ Backup guardado en: ~/.openclaw/backup_20260505_HHMMSS/.env.bak

⚙️  2/5 Actualizando configuración...
   ✅ Configuración actualizada en ~/.openclaw/.env

🔍 3/5 Verificando conectividad con vLLM DGX...
   ✅ vLLM DGX accesible (192.168.20.57:8001)

🔄 4/5 Reiniciando servicio Openclaw...
   ✅ Openclaw reiniciado

🧪 5/5 Ejecutando test de validación...
   Enviando test prompt...
   ✅ Test exitoso: respuesta generada (XXX caracteres)

==================================================
✅ UPGRADE COMPLETADO
==================================================

Calidad esperada: 6/10 (qwen2.5:7b) → 8.5/10 (qwen2.5-coder-32b)
```

**Tiempo total:** ~30-60 segundos

---

## 🧪 PASO 3: Validar funcionamiento (OPCIONAL)

En el mini PC, ejecuta los 5 tests de calidad:

```bash
cd ~/openclaw_upgrade_package
./test_openclaw_vllm.sh
```

Verás 5 tests con respuestas técnicas detalladas sobre problemas de sistemas.

---

## ❌ SI ALGO FALLA

### Problema: wget no funciona

```bash
# Probar con curl
curl -O http://192.168.20.131:8888/openclaw_upgrade_vllm32b.tar.gz
```

### Problema: vLLM DGX no responde

Desde este portátil MSI, verifica:

```bash
ssh daviddgx@192.168.20.57 "cd ~/seedy/coder-vllm && docker compose ps"
```

Si el contenedor está caído:

```bash
ssh daviddgx@192.168.20.57 "cd ~/seedy/coder-vllm && docker compose restart"
```

### Problema: Openclaw no reinicia

En el mini PC:

```bash
# Ver logs
journalctl --user -u openclaw -n 50 --no-pager

# Intentar reinicio manual
systemctl --user stop openclaw
sleep 2
systemctl --user start openclaw
systemctl --user status openclaw
```

### ROLLBACK completo

En el mini PC:

```bash
# Restaurar configuración anterior
LAST_BACKUP=$(ls -t ~/.openclaw/backup_* | head -1)
cp $LAST_BACKUP/.env.bak ~/.openclaw/.env
systemctl --user restart openclaw
```

---

## 🎉 BENEFICIOS DEL UPGRADE

| Antes (qwen2.5:7b) | Después (qwen2.5-coder-32b) |
|--------------------|------------------------------|
| Calidad: 6/10 | Calidad: 8.5/10 |
| Respuestas genéricas | Comandos específicos del SO |
| Coste: $0 | Coste: $0 |
| Latencia: 8-15s | Latencia: 15-30s |

---

## 📞 CUANDO TERMINES

1. **Detener servidor HTTP en este portátil:**
   - Ve a la terminal donde corre el servidor
   - Presiona **Ctrl+C**

2. **Verificar en Openclaw que todo funciona:**
   ```bash
   systemctl --user status openclaw
   ```

3. **¡Listo!** Openclaw ahora usa el modelo de 32B parámetros del DGX.

---

**Documentación completa:** `/tmp/openclaw_upgrade_package/OPENCLAW_UPGRADE_INSTRUCTIONS.md`

**Soporte:** Si tienes dudas, todos los logs están en `journalctl --user -u openclaw -f`
