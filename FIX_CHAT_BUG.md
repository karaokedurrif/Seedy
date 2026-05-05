# FIX: Seedy no responde en Open WebUI — ERROR 500 Internal Server Error

**Fecha:** 5 mayo 2026, 06:30 AM  
**Fase:** Despliegue v4.6 DGX  
**Síntoma:** Open WebUI devuelve respuestas vacías (`"content": ""`) al hacer preguntas a Seedy

## Diagnóstico

### Error en logs de Open WebUI:
```
ERROR | open_webui.routers.openai:generate_chat_completion:1195 - 500, 
message='Attempt to decode JSON with unexpected mimetype: text/plain; charset=utf-8', 
url='http://seedy-backend:8000/v1/chat/completions'
```

### Error en backend (traceback Python):
```python
TypeError: evaluate_technical_accuracy() takes 3 positional arguments but 4 were given
  File "/app/routers/openai_compat.py", line 1060, in _non_stream_response
    evaluate_technical(query, evidence_text, answer, species_hint),
```

### Causa raíz:
**Archivo `backend/services/critic.py` desactualizado en DGX**

- **Versión vieja (DGX):** `evaluate_technical(query, context_chunks, draft_answer)` — 3 parámetros
- **Versión nueva (local):** `evaluate_technical(query, evidence, draft_answer, species_hint)` — 4 parámetros

El archivo no se transfirió durante el despliegue inicial de v4.6 (días 1-3).

## Solución

```bash
# 1. Transferir critic.py actualizado
scp backend/services/critic.py daviddgx@192.168.20.57:~/seedy/backend/services/critic.py

# 2. Reiniciar backend para recargar módulo
ssh daviddgx@192.168.20.57 "cd ~/seedy && docker compose restart seedy-backend"
```

## Verificación

```bash
# Test endpoint directo (debe devolver JSON válido, no "Internal Server Error")
curl -X POST http://localhost:8000/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{"model":"seedy-rag","messages":[{"role":"user","content":"Qué es Seedy?"}],"stream":false}'

# Resultado esperado: JSON con campo "choices[0].message.content" con respuesta completa
```

## Archivos afectados

- `backend/services/critic.py` — función `evaluate_technical()` actualizada con 4 parámetros
- `backend/routers/openai_compat.py` — llama a `evaluate_technical()` en línea 1060

## Lecciones aprendidas

1. **Siempre verificar sincronización de archivos tras despliegues:** Aunque se transfirieron los workers y LLMRouter, no se revisó que TODOS los módulos de `backend/services/` estuvieran actualizados.
2. **Logs de FastAPI no muestran tracebacks completos por defecto:** Fue necesario ejecutar el endpoint directamente con `docker exec python -c` para ver el `TypeError` completo.
3. **Error silencioso en producción:** El backend devolvía HTTP 500 con `text/plain` en vez de JSON, lo que causaba que Open WebUI no pudiera parsear la respuesta y devolviera `"content": ""`.

## Impacto

- **Tiempo sin servicio:** ~30 minutos (desde que el usuario reportó hasta fix aplicado)
- **Usuarios afectados:** Solo el usuario principal (ganadero), ya que el despliegue v4.6 acababa de completarse
- **Funcionalidad afectada:** TODO el chat de Open WebUI (endpoint `/v1/chat/completions`)
- **Funcionalidad NO afectada:** 
  - Visión (YOLO + Gemini)
  - Backend health check
  - Workers de Celery
  - Grafana dashboards

## Estado final

✅ Chat completamente operativo  
✅ Backend respondiendo con JSON válido  
✅ Open WebUI funcionando correctamente  
✅ Todos los servicios en producción (15 contenedores running)
