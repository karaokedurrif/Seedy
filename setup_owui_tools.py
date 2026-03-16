#!/usr/bin/env python3
"""
Setup Open WebUI Tools for Seedy AI
Creates: Wikipedia, Dify KB, DateTime, Web Scraper tools
"""

import requests
import json
import sys

BASE_URL = "http://localhost:3000"

# Re-authenticate
def get_token():
    r = requests.post(f"{BASE_URL}/api/v1/auths/signin", json={
        "email": "durrif@gmail.com",
        "password": "4431Durr$"
    })
    if r.status_code == 200:
        token = r.json().get("token")
        with open("/tmp/owui_token.txt", "w") as f:
            f.write(token)
        return token
    else:
        print(f"Auth failed: {r.status_code}")
        sys.exit(1)

TOKEN = get_token()
HEADERS = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}

def create_tool(tool_id, name, description, code):
    url = f"{BASE_URL}/api/v1/tools/create"
    payload = {
        "id": tool_id,
        "name": name,
        "content": code,
        "meta": {
            "description": description,
            "manifest": {"version": "0.2.0", "author": "NeoFarm"}
        }
    }
    r = requests.post(url, headers=HEADERS, json=payload)
    if r.status_code == 200:
        print(f"  ✅ Tool '{name}' created (id={tool_id})")
        return True
    else:
        detail = r.json().get("detail", r.text[:200])
        print(f"  ❌ Tool '{name}' failed: {r.status_code} - {detail}")
        return False

# ─────────────────────────────────────────────
# TOOL 1: Wikipedia Search
# ─────────────────────────────────────────────
WIKI_TOOL = '''"""
title: Wikipedia Search
author: NeoFarm
version: 0.2.0
description: Busca articulos en Wikipedia (ES/EN) para complementar conocimiento agricola y ganadero
"""

import requests
from typing import Callable, Any

HEADERS = {"User-Agent": "SeedyBot/1.0 (https://seedy.neofarm.io; durrif@gmail.com)"}

class Tools:
    def __init__(self):
        self.citation = True

    class UserValves:
        pass

    async def search_wikipedia(
        self,
        query: str,
        lang: str = "es",
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Busca informacion en Wikipedia. Util para definiciones, conceptos cientificos, razas animales, cultivos, normativas, etc.
        :param query: Termino o pregunta a buscar en Wikipedia
        :param lang: Idioma de busqueda (es=espanol, en=ingles). Por defecto espanol.
        :return: Resumen del articulo de Wikipedia
        """
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Buscando en Wikipedia ({lang}): {query}", "done": False}})

        try:
            search_url = f"https://{lang}.wikipedia.org/w/api.php"
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 3,
                "format": "json",
                "utf8": 1
            }
            resp = requests.get(search_url, params=search_params, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            results = data.get("query", {}).get("search", [])

            if not results:
                if __event_emitter__:
                    await __event_emitter__({"type": "status", "data": {"description": "No se encontraron resultados en Wikipedia", "done": True}})
                return f"No se encontraron articulos en Wikipedia ({lang}) para: {query}"

            title = results[0]["title"]
            summary_url = f"https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
            resp2 = requests.get(summary_url, headers=HEADERS, timeout=10)
            resp2.raise_for_status()
            summary_data = resp2.json()

            extract = summary_data.get("extract", "Sin resumen disponible")
            page_url = summary_data.get("content_urls", {}).get("desktop", {}).get("page", "")

            other_titles = [r["title"] for r in results[1:]]
            other_text = ""
            if other_titles:
                other_text = "\\n\\nArticulos relacionados: " + ", ".join(other_titles)

            result = f"## {title}\\n\\n{extract}\\n\\nFuente: {page_url}{other_text}"

            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Wikipedia: {title}", "done": True}})
                if page_url:
                    await __event_emitter__({"type": "citation", "data": {"document": [extract], "metadata": [{"source": page_url, "name": f"Wikipedia: {title}"}], "source": {"name": f"Wikipedia: {title}", "url": page_url}}})

            return result

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Error Wikipedia: {str(e)}", "done": True}})
            return f"Error buscando en Wikipedia: {str(e)}"
'''

# ─────────────────────────────────────────────
# TOOL 2: Dify Knowledge Base Query
# ─────────────────────────────────────────────
DIFY_TOOL = '''"""
title: NeoFarm Knowledge Base
author: NeoFarm
version: 0.2.0
description: Consulta la base de conocimiento NeoFarm/Seedy en Dify con 298 documentos tecnicos sobre porcino, vacuno, nutricion, genetica, IoT, normativa
"""

import requests
from typing import Callable, Any

class Tools:
    def __init__(self):
        self.citation = True

    class UserValves:
        pass

    async def query_neofarm_kb(
        self,
        query: str,
        top_k: int = 5,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Consulta la base de conocimiento tecnico de NeoFarm con 298 documentos sobre ganaderia porcina/vacuna, nutricion, genetica, IoT, normativa, digital twins, etc.
        :param query: Pregunta o tema a buscar en la KB
        :param top_k: Numero de fragmentos relevantes a devolver (default 5)
        :return: Fragmentos relevantes de la base de conocimiento
        """
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Consultando KB NeoFarm: {query[:50]}...", "done": False}})

        try:
            url = "http://dify-api:5001/v1/datasets/880d67ee-3bd3-40ce-a457-ef46a3ad6be6/retrieve"
            headers = {
                "Authorization": "Bearer dataset-seedyNeoFarm2026kb",
                "Content-Type": "application/json"
            }
            payload = {
                "query": query,
                "retrieval_model": {
                    "search_method": "hybrid_search",
                    "reranking_enable": True,
                    "reranking_mode": "reranking_model",
                    "top_k": top_k,
                    "score_threshold_enabled": True,
                    "score_threshold": 0.2
                }
            }

            resp = requests.post(url, headers=headers, json=payload, timeout=30)
            data = resp.json()

            records = data.get("records", [])
            if not records:
                if __event_emitter__:
                    await __event_emitter__({"type": "status", "data": {"description": "Sin resultados en KB NeoFarm", "done": True}})
                return f"No se encontraron documentos relevantes en la KB de NeoFarm para: {query}"

            results = []
            for i, rec in enumerate(records):
                segment = rec.get("segment", {})
                content = segment.get("content", "")
                doc_name = rec.get("document", {}).get("name", "Documento")
                score = rec.get("score", 0)
                results.append(f"### Fragmento {i+1} (score: {score:.2f}) - {doc_name}\\n{content}")

                if __event_emitter__:
                    await __event_emitter__({"type": "citation", "data": {"document": [content[:500]], "metadata": [{"source": f"KB NeoFarm: {doc_name}", "name": doc_name}], "source": {"name": f"KB: {doc_name}"}}})

            full_result = "\\n\\n---\\n\\n".join(results)

            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"KB NeoFarm: {len(records)} fragmentos encontrados", "done": True}})

            return f"## Resultados KB NeoFarm ({len(records)} fragmentos)\\n\\n{full_result}"

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Error KB: {str(e)}", "done": True}})
            return f"Error consultando KB NeoFarm: {str(e)}"
'''

# ─────────────────────────────────────────────
# TOOL 3: DateTime & Calculator
# ─────────────────────────────────────────────
DATETIME_TOOL = '''"""
title: Fecha, Hora y Calculadora
author: NeoFarm
version: 0.1.0
description: Proporciona fecha/hora actual y calculadora para operaciones ganaderas (conversiones de peso, indices, formulas)
"""

from datetime import datetime, timedelta
import math
from typing import Callable, Any

class Tools:
    def __init__(self):
        pass

    class UserValves:
        pass

    async def get_current_datetime(
        self,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Devuelve la fecha y hora actual en zona horaria de Espana (CET/CEST).
        :return: Fecha y hora actual formateada
        """
        try:
            from zoneinfo import ZoneInfo
            now = datetime.now(ZoneInfo("Europe/Madrid"))
        except ImportError:
            now = datetime.utcnow() + timedelta(hours=1)
        
        dias = ["Lunes", "Martes", "Miercoles", "Jueves", "Viernes", "Sabado", "Domingo"]
        meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        
        dia_sem = dias[now.weekday()]
        mes = meses[now.month - 1]
        
        return f"{dia_sem}, {now.day} de {mes} de {now.year}, {now.strftime('%H:%M:%S')} (hora peninsular espanola)"

    async def calculate(
        self,
        expression: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Evalua expresiones matematicas. Util para calculos ganaderos: conversiones de peso, indices de conversion, formulas de nutricion, costes, etc.
        :param expression: Expresion matematica a evaluar (ejemplo: 2.5 * 1000 / 365)
        :return: Resultado del calculo
        """
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Calculando: {expression[:50]}", "done": False}})
        
        try:
            allowed_names = {
                "abs": abs, "round": round, "min": min, "max": max,
                "sum": sum, "len": len, "pow": pow,
                "sqrt": math.sqrt, "log": math.log, "log10": math.log10,
                "pi": math.pi, "e": math.e, "ceil": math.ceil, "floor": math.floor,
            }
            result = eval(expression, {"__builtins__": {}}, allowed_names)
            
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Resultado: {result}", "done": True}})
            
            return f"Expresion: {expression}\\nResultado: {result}"
        except Exception as e:
            return f"Error en calculo '{expression}': {str(e)}"
'''

# ─────────────────────────────────────────────
# TOOL 4: Web Page Reader
# ─────────────────────────────────────────────
WEBPAGE_TOOL = '''"""
title: Lector de Paginas Web
author: NeoFarm
version: 0.1.0
description: Lee y extrae contenido de paginas web para obtener informacion actualizada sobre ganaderia, precios, normativas
"""

import requests
import re
from typing import Callable, Any

class Tools:
    def __init__(self):
        self.citation = True

    class UserValves:
        pass

    async def read_webpage(
        self,
        url: str,
        __event_emitter__: Callable[[dict], Any] = None,
    ) -> str:
        """
        Lee y extrae el contenido de texto de una pagina web. Util para consultar precios de mercado, normativas actualizadas, articulos tecnicos, etc.
        :param url: URL completa de la pagina web a leer
        :return: Contenido de texto extraido de la pagina
        """
        if __event_emitter__:
            await __event_emitter__({"type": "status", "data": {"description": f"Leyendo pagina web...", "done": False}})

        try:
            headers_req = {
                "User-Agent": "Mozilla/5.0 (compatible; SeedyBot/1.0; NeoFarm)"
            }
            resp = requests.get(url, headers=headers_req, timeout=15)
            resp.raise_for_status()
            html = resp.text

            # Simple HTML to text extraction
            # Remove script and style
            html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
            html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', html)
            # Clean whitespace
            text = re.sub(r'\\s+', ' ', text).strip()
            # Decode HTML entities
            text = text.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&nbsp;', ' ').replace('&quot;', '"')
            
            # Limit to 3000 chars
            if len(text) > 3000:
                text = text[:3000] + "... [contenido truncado]"

            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Pagina leida: {len(text)} chars", "done": True}})
                await __event_emitter__({"type": "citation", "data": {"document": [text[:500]], "metadata": [{"source": url, "name": url}], "source": {"name": url, "url": url}}})

            return f"## Contenido de {url}\\n\\n{text}"

        except Exception as e:
            if __event_emitter__:
                await __event_emitter__({"type": "status", "data": {"description": f"Error leyendo web: {str(e)}", "done": True}})
            return f"Error leyendo {url}: {str(e)}"
'''

# ─────────────────────────────────────────────
# CREATE ALL TOOLS
# ─────────────────────────────────────────────
print("=" * 50)
print("Creando Tools en Open WebUI para Seedy")
print("=" * 50)

tools = [
    ("wikipedia_search", "Wikipedia Search", "Busca articulos en Wikipedia (ES/EN)", WIKI_TOOL),
    ("neofarm_kb", "NeoFarm Knowledge Base", "Consulta KB NeoFarm/Dify (298 docs)", DIFY_TOOL),
    ("datetime_calc", "Fecha, Hora y Calculadora", "Fecha/hora actual y calculadora", DATETIME_TOOL),
    ("webpage_reader", "Lector de Paginas Web", "Lee contenido de paginas web", WEBPAGE_TOOL),
]

created = 0
for tid, name, desc, code in tools:
    if create_tool(tid, name, desc, code):
        created += 1

print(f"\n{'='*50}")
print(f"Resultado: {created}/{len(tools)} tools creados")

# Verify
r = requests.get(f"{BASE_URL}/api/v1/tools/", headers=HEADERS)
all_tools = r.json()
print(f"Total tools en Open WebUI: {len(all_tools)}")
for t in all_tools:
    print(f"  - {t['id']}: {t['name']}")
