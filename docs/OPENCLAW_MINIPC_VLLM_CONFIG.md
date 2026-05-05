# OpenClaw Mini PC → vLLM DGX Configuration

**Fecha:** 5 mayo 2026  
**Actualización de:** OPENCLAW_MINIPC_OLLAMA_CONFIG.md  
**Nueva configuración:** vLLM Qwen2.5-Coder-32B-AWQ en lugar de Ollama 7B

---

## 🎯 Mejora Significativa

### Antes (Ollama qwen2.5:7b)
- ❌ **"Va torpe"** para análisis SOC
- ⚠️ Confunde alarmas reales con ruido
- ⚠️ Sugerencias de código básicas
- ✅ Respuestas rápidas (~2-3s para 200 tokens)

### Después (vLLM Qwen2.5-Coder-32B-AWQ)
- ✅ **Capacidad SOC profesional**
- ✅ Identifica patrones de ataque complejos
- ✅ Código production-ready (tests, async, SOLID)
- ⚠️ Respuestas ligeramente más lentas (~10-15s para 200 tokens)

**Trade-off aceptable:** 10s más de latencia a cambio de saltar de junior a senior en calidad.

---

## 📝 Configuración OpenClaw

### Método 1: Variables de Entorno (Recomendado)

#### 1. Editar archivo de configuración

```bash
# Desde el mini PC (192.168.20.54)
cd ~/openclaw  # O donde esté instalado OpenClaw

# Editar .env o crear si no existe
nano .env
```

#### 2. Configuración actualizada

```bash
# ============================================
# CONFIGURACIÓN vLLM DGX (32B CODER) - SIN COSTE
# ============================================

# Proveedor: OpenAI-compatible (vLLM emula la API)
LLM_PROVIDER=openai

# Endpoint del vLLM en el DGX (puerto 8001, NO 11434)
OPENAI_API_BASE=http://192.168.20.57:8001/v1

# API Key (obtener del DGX)
# SSH a DGX: cat ~/seedy/coder-vllm/.env
OPENAI_API_KEY=e37eea8c23dd665a7e19169ab05a30c23766b336e410367217031c8cd9303ed4

# Modelo (nombre del servicio en vLLM)
OPENAI_MODEL=qwen2.5-coder-32b

# Parámetros de generación
OPENAI_TEMPERATURE=0.2          # Más determinista para SOC/coding
OPENAI_MAX_TOKENS=2048
OPENAI_TIMEOUT=120              # 2 minutos (el 32B es más lento que 7B)

# ============================================
# DESACTIVAR APIS DE PAGO (IMPORTANTE)
# ============================================

# Estas deben estar vacías o comentadas:
ANTHROPIC_API_KEY=
TOGETHER_API_KEY=
GOOGLE_API_KEY=
```

#### 3. Reiniciar OpenClaw

```bash
# Dependiendo de cómo lo ejecutes:

# Si es Docker:
docker compose restart

# Si es Python directo:
# Parar proceso actual (Ctrl+C) y volver a ejecutar
python -m openclaw

# Si es systemd service:
sudo systemctl restart openclaw
```

---

## 🔧 System Prompt Optimizado para 32B-Coder

El modelo 32B-Coder es más capaz, pero hay que guiarlo bien:

```yaml
# En OpenClaw config (si lo soporta) o hardcodeado en código
system_prompt: |
  Eres un **Ingeniero de Ciberseguridad Senior y Desarrollador Full-Stack experto**.
  
  CONTEXTO DE OPERACIÓN:
  - Monitorizas el homeserver de Durrif (192.168.20.x).
  - Stack: Ubuntu 24.04, Docker, Tailscale, Pi-hole, NAS OMV, MQTT, Grafana, DGX Spark.
  - Rol: SOC (Security Operations Center) + DevOps automation.
  
  REGLAS ESTRICTAS:
  
  1. **Precisión técnica primero.**
     - Sintaxis correcta de comandos Linux/Unix. Verificar flags.
     - No inventar opciones que no existen (ej: `iptables -R` no existe, es `-R` de `replace` en chains).
  
  2. **Modo SOC: detección de amenazas.**
     - Logs con múltiples intentos fallidos: brute-force.
     - Puertos atípicos abiertos (ej: 4444, 31337): posible backdoor.
     - Tráfico volumétrico anómalo: exfiltración o C2.
     - IPs sospechosas: correlacionar con feeds (AbuseIPDB, Tor exit nodes).
  
  3. **Antes de comandos destructivos, advertir.**
     - `rm -rf`, `iptables -F`, `dd`, `mkfs`: pedir confirmación explícita.
     - Sugerir dry-run primero (`--dry-run`, `-n`, etc.).
  
  4. **Código siguiendo best practices.**
     - SOLID principles.
     - Tests unitarios (pytest/unittest).
     - Async/await para I/O (asyncio, aiohttp).
     - Type hints en Python.
     - Logging estructurado (no prints).
  
  5. **Brevedad operativa.**
     - Ir al grano: comando o diagnóstico primero, explicación después.
     - Sin "espero que esto te ayude" ni frases de relleno.
     - Formato preferido: comando → output esperado → qué hacer si falla.
  
  6. **Escalado a especialistas.**
     - Si la pregunta es sobre **ganadería/avicultura** (Durrif, NeoFarm, Palacio):
       → "Esta pregunta es de ganadería. Consulta Seedy en https://seedy.neofarm.io"
     - Si es genética aviar, nutrición, comportamiento animal:
       → "No es mi dominio. Usa el sistema Seedy que tiene expertos en avicultura."
  
  WORKFLOW TÍPICO PARA ALERTAS:
  1. Recibo log o alerta.
  2. Identifico: ¿es ruido o amenaza real?
  3. Si es amenaza: clasifico (brute-force, scan, exploit, data exfiltration).
  4. Propongo mitigación inmediata (iptables, fail2ban, docker stop).
  5. Sugiero investigación profunda (tcpdump, auditd, SIEM query).
  6. Genero regla permanente si aplica.
  
  EJEMPLOS DE RESPUESTAS CORRECTAS:
  
  **Pregunta:** "Tengo 50 intentos fallidos SSH desde 185.220.101.42 en 2 minutos."
  **Respuesta:**
  ```bash
  # 1. Bloqueo inmediato
  sudo iptables -I INPUT -s 185.220.101.42 -j DROP
  
  # 2. Verificar si es Tor exit node
  whois 185.220.101.42 | grep -i tor
  # (185.220.101.* es rango conocido de Tor)
  
  # 3. Regla permanente con fail2ban
  # Editar /etc/fail2ban/jail.local:
  [sshd]
  enabled = true
  bantime = 86400
  maxretry = 3
  
  sudo systemctl restart fail2ban
  
  # 4. Log de la IP para análisis
  echo "185.220.101.42|$(date)|brute-force-ssh|blocked" >> /var/log/soc/threats.log
  ```
  
  **Pregunta:** "Dame un script para monitorizar temperatura del NAS via SNMP."
  **Respuesta:**
  ```python
  # monitor_nas_temp.py
  import asyncio
  from pysnmp.hlapi.asyncio import *
  from prometheus_client import Gauge, start_http_server
  
  temp_gauge = Gauge('nas_temperature_celsius', 'NAS temperature')
  
  async def poll_temp(host, community):
      errorIndication, errorStatus, errorIndex, varBinds = await getCmd(
          SnmpEngine(),
          CommunityData(community),
          UdpTransportTarget((host, 161)),
          ContextData(),
          ObjectType(ObjectIdentity('1.3.6.1.4.1.2021.13.16.2.1.3.1'))  # UCD-SNMP-MIB
      )
      if not errorIndication and not errorStatus:
          temp = int(varBinds[0][1])
          temp_gauge.set(temp)
          return temp
      raise Exception(f"SNMP error: {errorIndication or errorStatus}")
  
  async def main():
      start_http_server(9100)  # Prometheus metrics
      while True:
          temp = await poll_temp('192.168.30.100', 'public')
          if temp > 60:
              print(f"ALERT: NAS temperature {temp}°C > 60°C")
          await asyncio.sleep(60)
  
  if __name__ == '__main__':
      asyncio.run(main())
  ```
  
  **Test:** `pytest test_monitor_nas_temp.py` (implementar mocking de SNMP)
  
  FIN DE SYSTEM PROMPT.
```

---

## 🧪 Tests de Validación

Ejecutar estos 5 tests **después de la migración** para confirmar mejora de calidad:

### Test 1: SOC Analyst — Brute Force Detection

**Prompt:**
```
Tengo este fragmento de /var/log/auth.log:

May 5 03:42:11 srv-home sshd[12847]: Failed password for root from 185.220.101.42 port 38291 ssh2
May 5 03:42:14 srv-home sshd[12847]: Failed password for root from 185.220.101.42 port 38291 ssh2
May 5 03:42:17 srv-home sshd[12849]: Failed password for invalid user admin from 185.220.101.42 port 38292 ssh2
May 5 03:42:20 srv-home sshd[12851]: Failed password for invalid user oracle from 185.220.101.42 port 38293 ssh2
May 5 03:42:23 srv-home sshd[12853]: Connection closed by invalid user test 185.220.101.42 port 38294

¿Qué está pasando? ¿Qué hago?
```

**Esperado del 32B:**
- Identifica brute-force con rotación de usuarios (root → admin → oracle → test).
- Menciona que 185.220.101.* es rango Tor exit node conocido.
- Sugiere: iptables DROP inmediato + fail2ban configuración + considerar deshabilitar root login.

**Esperado del 7B (para comparar):**
- Identifica brute-force genérico.
- Sugiere fail2ban.
- Probablemente se pierde el detalle de Tor y la rotación de usuarios.

### Test 2: Code Refactor Cross-File

**Prompt:**
```
Tengo este script de monitor de temperatura del home server. Está hecho un asco.
Refactorízalo: separa I/O del SNMP de la lógica de alertas, mete tests, async,
y un endpoint /metrics estilo Prometheus.

[pegar 80 líneas de un script monolítico]
```

**Esperado del 32B:**
- Estructura modular limpia (3-4 archivos).
- Async correcto con asyncio.
- FastAPI endpoint `/metrics` con prometheus_client.
- Ejemplo de pytest con mocking de SNMP.

**Esperado del 7B:**
- Intento decente pero lógica acoplada.
- Probablemente olvida tests o los hace mal.

### Test 3: Debug Network — Pi-hole DNS

**Prompt:**
```
Mi container Pi-hole no resuelve DNS para clientes de la VLAN 30. Otros containers sí.
docker-compose, iptables, network bridge — ¿qué reviso primero?
```

**Esperado del 32B:**
- Lista priorizada de checks (8-10 puntos).
- Comando específico para cada uno.
- Menciona FORWARD chain de iptables, dnsmasq listening interfaces, route entre VLANs.

### Test 4: Bash One-Liner

**Prompt:**
```
One-liner: encuentra todos los .py en mi home, dime cuál tiene más líneas no-vacías,
ignorando archivos en venv/ y __pycache__/.
```

**Esperado del 32B:**
```bash
find ~ -type f -name "*.py" ! -path "*/venv/*" ! -path "*/__pycache__/*" \
  -exec awk 'NF {lines++} END {print FILENAME, lines}' {} \; 2>/dev/null \
  | sort -k2 -nr | head -1
```

**Esperado del 7B:** Similar pero probablemente con pequeño error de sintaxis o sin el `2>/dev/null`.

### Test 5: Pregunta Fuera de Dominio (Control)

**Prompt:**
```
¿Qué cruce me recomiendas entre Sussex Light Silver gallo y Sulmtaler hembras
para línea de capón gourmet?
```

**Esperado del 32B:**
- "Esta pregunta es de ganadería aviar. No es mi especialidad."
- "Consulta el sistema Seedy en https://seedy.neofarm.io — tiene conocimiento profundo en genética avícola."
- **NO debe** intentar responder con conocimiento general de avicultura.

**Si responde intentando dar consejos:** indica que el system prompt no está bien configurado. Revisar la sección "Escalado a especialistas".

---

## 📊 Comparativa Lado a Lado

| Métrica | Ollama 7B (antes) | vLLM 32B (ahora) | Mejora |
|---------|-------------------|------------------|--------|
| **Latencia 200 tokens** | ~2-3s | ~10-15s | -80% velocidad |
| **Calidad SOC (subjetivo)** | 6/10 | 9/10 | +50% |
| **HumanEval score** | ~65% | ~90% | +38% |
| **Code refactor multi-file** | Básico | Profesional | +++  |
| **Detección patrones ataque** | Genérico | Específico | +++ |
| **Coste mensual** | $0 | $0 | Igual |

**Conclusión:** Merece la pena el trade-off de latencia por la calidad.

---

## 🔧 Troubleshooting OpenClaw → vLLM

### Problema 1: "Connection refused" http://192.168.20.57:8001

**Causa:** vLLM no está corriendo o no es accesible desde el mini-PC.

**Diagnóstico desde mini-PC:**
```bash
# 1. Ping al DGX
ping -c 2 192.168.20.57

# 2. Check puerto abierto
nc -zv 192.168.20.57 8001
# Esperado: "Connection to 192.168.20.57 8001 port [tcp/*] succeeded!"

# 3. Si falla, verificar en el DGX:
ssh daviddgx@192.168.20.57 "docker ps | grep vllm-coder"
ssh daviddgx@192.168.20.57 "curl localhost:8001/health"
```

**Solución:** Reiniciar vLLM en el DGX:
```bash
ssh daviddgx@192.168.20.57 "cd ~/seedy/coder-vllm && docker compose restart"
```

### Problema 2: "Unauthorized" o 401

**Causa:** API key incorrecta o no enviada.

**Diagnóstico:**
```bash
# En mini-PC, verificar .env de OpenClaw
cat ~/openclaw/.env | grep OPENAI_API_KEY

# Comparar con el del DGX
ssh daviddgx@192.168.20.57 "cat ~/seedy/coder-vllm/.env | grep VLLM_API_KEY"

# Deben coincidir
```

**Solución:** Copiar la key correcta del DGX al mini-PC.

### Problema 3: Respuestas muy lentas (>60s)

**Causa posible:** vLLM compitiendo con Ollama por VRAM (qwen2.5:72b cargado simultáneamente).

**Diagnóstico en DGX:**
```bash
ssh daviddgx@192.168.20.57 "nvidia-smi"
# Si hay ~100 GB ocupados, 72B está cargado
```

**Solución:** Descargar 72B temporalmente:
```bash
ssh daviddgx@192.168.20.57 "docker exec ollama ollama stop qwen2.5:72b"
```

### Problema 4: OpenClaw sigue usando modelo antiguo

**Causa:** Caché de configuración.

**Solución:**
```bash
# Limpiar caché y reiniciar completamente
cd ~/openclaw
rm -rf .cache/ __pycache__/
docker compose down && docker compose up -d  # Si es Docker
# O reiniciar servicio/proceso
```

---

## 🚀 Próximos Pasos

### Corto plazo (1 semana)

1. **Documentar casos reales**
   - Guardar 10-20 queries SOC reales que OpenClaw maneja.
   - Comparar respuestas 7B vs 32B side-by-side.
   - Compartir con el equipo para validación subjetiva.

2. **Métricas cuantitativas**
   - Tiempo promedio de respuesta (aceptable <30s).
   - Tasa de detección de falsos positivos (debe bajar con 32B).
   - Tasa de comandos que funcionan al primer intento.

3. **Tuning del system prompt**
   - Iterar basándose en casos edge que fallen.
   - Añadir few-shot examples si hay patrones recurrentes.

### Medio plazo (1 mes)

4. **Fine-tune SOC (opcional)**
   - **Solo si** el 32B base falla en casos específicos recurrentes.
   - Dataset: 200-500 ejemplos de logs reales + respuestas gold.
   - Método: LoRA con Unsloth, mantener el modelo base para código general.
   - **Probabilidad:** Baja. El 32B base debería ser suficiente.

5. **Integración con SIEM**
   - OpenClaw → parser de logs → vLLM análisis → SIEM ticketing automático.
   - Wazuh/Elastic Security como destino.

---

## 📝 Notas Finales

### Por qué 32B y no fine-tuned 7B

El documento original sugería fine-tunear el 7B en seguridad. **No tiene sentido:**

- Un 32B base de coding ya cubre ciberseguridad general.
- Fine-tune del 7B requiere 200-500 ejemplos gold + GPUs + días de trabajo.
- ROI negativo: gastarías 3 días para ganar ~10% sobre el 32B que ya tienes gratis.
- El fine-tune de Seedy (`seedy:v16` 14B) sí tiene sentido porque es avicultura (dominio que NO está en training base).

### Cuándo SÍ tiene sentido fine-tune SOC

- Tienes >500 logs anotados con respuestas gold de nivel senior SOC.
- El 32B falla sistemáticamente en un patrón específico de tu infraestructura.
- Tienes presupuesto de GPU y tiempo (2-3 días full-time).

Hasta entonces: **el 32B base es más que suficiente** para SOC de homeserver.

---

**Última actualización:** 5 mayo 2026  
**Reemplaza a:** OPENCLAW_MINIPC_OLLAMA_CONFIG.md  
**Autor:** Seedy Team  
**Versión:** v4.7.0
