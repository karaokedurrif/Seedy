#!/usr/bin/env python3
"""
build_v8.py — Genera seedy_dataset_sft_v8.jsonl
Fuentes:
  1. Dataset v7 base (491 ejemplos)
  2. Wikipedia ES+EN (157 artículos → Q/A generados)
  3. Artículos científicos OpenAlex (546 abstracts → Q/A generados)
  4. Cruces gourmet Segovia CSV
  5. Conocimientos RAG existentes
  6. Correcciones manuales (avicultura, capones, razas)
  7. Ejemplos de rechazo ("no sé / fuera de dominio")
"""
import json, os, re, csv, textwrap
from collections import Counter

SYSTEM = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData 7 capas), nutrición animal (NRC 2012), "
    "genética aplicada (EPDs, FarmMatch, heterosis), normativa SIGE (RD 306/2020), "
    "Digital Twins productivos, GIS/GeoTwin (Cesium 3D, PNOA), Computer Vision ganadera "
    "(YOLO, TensorRT), economía agropecuaria, avicultura (capones, pollos de engorde, "
    "gallinas ponedoras) y ganadería extensiva (vacuno, ovino, caprino).\n\n"
    "Responde siempre en español, en prosa natural y profesional.\n"
    "No inventes cifras, normativa ni parámetros técnicos.\n"
    "Si falta un dato imprescindible, pide solo el mínimo necesario (máximo 2 preguntas).\n"
    "Si das un número, incluye unidades y aclara si es aproximado.\n"
    "Prioriza precisión técnica sobre tono comercial."
)

BASE_DIR = "/home/davidia/Documentos/Seedy"

def make(user: str, assistant: str, tags: list[str] = None) -> dict:
    d = {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]}
    if tags:
        d["_tags"] = tags
    return d


# ================================================================
# 1. CARGAR BASE v7
# ================================================================
def load_v7():
    path = os.path.join(BASE_DIR, "seedy_dataset_sft_v7.jsonl")
    with open(path) as f:
        data = [json.loads(l) for l in f]
    # Update system prompt
    for d in data:
        d["messages"][0]["content"] = SYSTEM
    print(f"  v7 base: {len(data)} ejemplos")
    return data


# ================================================================
# 2. GENERAR Q/A DESDE WIKIPEDIA
# ================================================================
def generate_qa_from_wiki():
    """Genera pares Q/A desde artículos de Wikipedia."""
    path = os.path.join(BASE_DIR, "wikipedia_articles/wiki_articles_raw.jsonl")
    if not os.path.exists(path):
        print("  ⚠ No hay artículos Wikipedia descargados")
        return []

    with open(path) as f:
        articles = [json.loads(l) for l in f]

    examples = []
    seen_titles = set()

    for art in articles:
        title = art["title"]
        text = art["text"]
        cat = art["category"]
        lang = art.get("lang", "es")

        # Skip duplicates (some Wikipedia redirects)
        if title in seen_titles:
            continue
        seen_titles.add(title)

        # Skip very short or very generic articles
        if len(text) < 500:
            continue

        # Skip overly generic articles (IA, GPS, etc. — too broad for our domain)
        skip_generic = {"Inteligencia artificial", "Internet de las cosas", "GPS",
                       "Vehículo aéreo no tripulado", "RFID", "Sensor", "Genética",
                       "Proteína (nutriente)", "Vitamina", "Calcio", "Fósforo",
                       "Antibiótico", "Visión artificial", "Aprendizaje automático",
                       "Triticum", "Vacunación", "Castración", "Leche",
                       "Inseminación artificial", "Bos taurus",
                       "Ovis orientalis aries", "Sus scrofa domestica"}
        if title in skip_generic:
            continue

        # Extract first meaningful paragraphs (max ~2000 chars for response)
        paragraphs = [p.strip() for p in text.split('\n\n') if len(p.strip()) > 80]
        if not paragraphs:
            continue

        # Build a concise response from the article
        response_text = "\n\n".join(paragraphs[:3])
        if len(response_text) > 2500:
            response_text = response_text[:2500].rsplit('. ', 1)[0] + '.'

        # Generate questions based on category
        questions = _generate_questions_for_article(title, cat, lang)

        for q in questions[:2]:  # Max 2 Q/A per article
            tags = [cat]
            if lang == "en":
                # Translate to Spanish response context
                response = f"Según la literatura técnica sobre {title}:\n\n{response_text}"
            else:
                response = response_text

            examples.append(make(q, response, tags))

    print(f"  Wikipedia Q/A: {len(examples)} ejemplos generados")
    return examples


def _generate_questions_for_article(title: str, category: str, lang: str) -> list[str]:
    """Genera preguntas relevantes basadas en el título y categoría."""
    title_clean = re.sub(r'\s*\(.*?\)', '', title).strip()

    templates = {
        "avicultura": [
            f"¿Qué características tiene la raza {title_clean}?",
            f"¿Es {title_clean} una buena opción para producción avícola?",
        ],
        "porcino": [
            f"¿Qué sabes sobre {title_clean} en producción porcina?",
            f"Háblame sobre {title_clean} en el sector porcino.",
        ],
        "vacuno": [
            f"¿Qué características tiene la raza {title_clean}?",
            f"¿Cómo se utiliza {title_clean} en ganadería?",
        ],
        "ovino_caprino": [
            f"¿Qué sabes sobre {title_clean} en ganado ovino/caprino?",
            f"Háblame sobre {title_clean}.",
        ],
        "nutricion": [
            f"¿Cuál es el papel de {title_clean} en la nutrición animal?",
            f"¿Cómo se utiliza {title_clean} en alimentación ganadera?",
        ],
        "genetica": [
            f"¿Qué es {title_clean} y cómo se aplica en mejora genética ganadera?",
            f"Explícame {title_clean} en el contexto de la genética animal.",
        ],
        "sanidad": [
            f"¿Qué es {title_clean} y cómo afecta a la ganadería?",
            f"¿Cómo se previene/controla {title_clean} en explotaciones ganaderas?",
        ],
        "tecnologia": [
            f"¿Cómo se aplica {title_clean} en ganadería de precisión?",
            f"¿Qué papel juega {title_clean} en la ganadería inteligente?",
        ],
        "normativa": [
            f"¿Qué implica {title_clean} para el sector ganadero?",
            f"Explícame {title_clean} en el contexto normativo ganadero.",
        ],
        "en_breeds": [
            f"¿Qué características tiene {title_clean}?",
            f"¿Cómo se utiliza {title_clean} en producción ganadera?",
        ],
    }

    return templates.get(category, [
        f"¿Qué sabes sobre {title_clean}?",
        f"Háblame sobre {title_clean}.",
    ])


# ================================================================
# 3. GENERAR Q/A DESDE ARTÍCULOS CIENTÍFICOS
# ================================================================
def generate_qa_from_science():
    """Genera pares Q/A desde abstracts de artículos científicos."""
    path = os.path.join(BASE_DIR, "science_articles/science_articles_raw.jsonl")
    if not os.path.exists(path):
        print("  ⚠ No hay artículos científicos descargados")
        return []

    with open(path) as f:
        articles = [json.loads(l) for l in f]

    examples = []
    seen_titles = set()

    # Group by topic and take top-cited ones
    by_topic = {}
    for art in articles:
        topic = art["topic"]
        by_topic.setdefault(topic, []).append(art)

    for topic, arts in by_topic.items():
        # Sort by citations, take top 8 per topic
        arts.sort(key=lambda x: -x.get("cited_by", 0))
        for art in arts[:8]:
            title = art["title"]
            if title in seen_titles:
                continue
            seen_titles.add(title)

            abstract = art["abstract"]
            if len(abstract) < 100:
                continue

            authors = ", ".join(art.get("authors", [])[:3])
            journal = art.get("journal", "")
            year = art.get("year", "")
            cited = art.get("cited_by", 0)

            # Create a professional response that cites the source
            source_info = f"{journal} ({year})" if journal and year else f"({year})"
            auth_info = f"Según {authors} et al." if authors else "Según la investigación"

            response = (
                f"{auth_info}, publicado en {source_info}"
                f"{f', con {cited} citaciones' if cited > 50 else ''}:\n\n"
                f"{abstract}"
            )

            # Generate question from topic
            q = _generate_question_for_topic(topic, title)
            examples.append(make(q, response, [topic, "ciencia"]))

    print(f"  Ciencia Q/A: {len(examples)} ejemplos generados")
    return examples


def _generate_question_for_topic(topic: str, title: str) -> str:
    """Genera una pregunta natural basada en el tema y título del paper."""
    title_lower = title.lower()

    topic_questions = {
        "avicultura_capones": f"¿Qué dice la investigación sobre la producción de capones y calidad de carne?",
        "avicultura_engorde": f"¿Cuáles son los últimos avances en engorde de pollos según la ciencia?",
        "avicultura_razas": f"¿Qué razas de pollo son más recomendadas según los estudios científicos?",
        "avicultura_capones_calidad": f"¿Cómo influye la caponización en la calidad sensorial de la carne?",
        "avicultura_ponedoras": f"¿Qué factores genéticos afectan la producción de huevos?",
        "avicultura_bienestar": f"¿Cómo se mejora el bienestar animal en avicultura?",
        "avicultura_nutricion": f"¿Qué aminoácidos son críticos en la formulación de piensos avícolas?",
        "porcino_iberico": f"¿Cómo afecta la alimentación con bellotas a la calidad del cerdo ibérico?",
        "porcino_nutricion": f"¿Cuáles son los requerimientos de aminoácidos en cerdos según la investigación?",
        "porcino_genetica": f"¿Cómo se aplica la selección genómica en la mejora porcina?",
        "porcino_bienestar": f"¿Qué indica la ciencia sobre bienestar animal en porcino?",
        "porcino_calidad": f"¿Qué factores determinan la calidad de la carne de cerdo?",
        "porcino_reproduccion": f"¿Cómo se puede reducir la mortalidad de lechones según la investigación?",
        "porcino_iot": f"¿Qué sensores IoT se usan en granjas porcinas según los estudios?",
        "porcino_sanidad": f"¿Cuál es la situación actual de la peste porcina africana según la ciencia?",
        "porcino_microbioma": f"¿Cómo influye el microbioma intestinal en el rendimiento porcino?",
        "vacuno_extensivo": f"¿Qué dice la investigación sobre ganadería extensiva en España?",
        "vacuno_genetica": f"¿Cómo se aplica la evaluación genómica en vacuno de carne?",
        "vacuno_calidad": f"¿Qué factores afectan la terneza y calidad de la carne de vacuno?",
        "vacuno_lechero": f"¿Cuáles son los avances en nutrición de vacuno lechero?",
        "vacuno_iot": f"¿Qué tecnologías wearable se usan en ganadería vacuna?",
        "vacuno_cria": f"¿Cómo mejorar la cría de terneros según la investigación?",
        "vacuno_medioambiente": f"¿Qué estrategias reducen las emisiones de metano en vacuno?",
        "nutricion_formulacion": f"¿Cuáles son las técnicas de optimización en formulación de piensos?",
        "nutricion_eficiencia": f"¿Cómo se mide y mejora el índice de conversión alimenticia?",
        "nutricion_micotoxinas": f"¿Qué impacto tienen las micotoxinas en la producción ganadera?",
        "nutricion_aminoacidos": f"¿Cuáles son los requerimientos de aminoácidos esenciales en ganado?",
        "nutricion_suplementacion": f"¿Qué dice la ciencia sobre suplementación vitamínico-mineral?",
        "genetica_genomica": f"¿Cómo funciona la selección genómica con GWAS y SNP en ganadería?",
        "genetica_cruzamiento": f"¿Qué dicen los estudios sobre heterosis y cruzamientos en ganado?",
        "genetica_consanguinidad": f"¿Cómo afecta la consanguinidad a la producción ganadera?",
        "iot_digital_twin": f"¿Cómo se aplican los gemelos digitales en ganadería de precisión?",
        "iot_sensores": f"¿Qué redes LPWAN son mejores para monitorización ganadera?",
        "iot_vision": f"¿Cómo se usa la visión artificial para comportamiento animal?",
        "iot_analytics": f"¿Qué técnicas de machine learning se aplican en smart farming?",
        "iot_rfid": f"¿Cómo se usa RFID para trazabilidad ganadera?",
        "normativa_bienestar": f"¿Qué dice la normativa europea sobre bienestar animal?",
        "normativa_sostenibilidad": f"¿Cómo está evolucionando la sostenibilidad ganadera según la investigación?",
    }

    return topic_questions.get(topic, f"¿Qué dice la investigación más reciente sobre {title}?")


# ================================================================
# 4. CRUCES GOURMET SEGOVIA (CSV)
# ================================================================
def generate_qa_from_cruces_csv():
    """Genera Q/A desde cruces_gourmet_segovia.csv."""
    path = os.path.join(BASE_DIR, "conocimientos/2.Nutricion & Formulacion/cruces_gourmet_segovia.csv")
    if not os.path.exists(path):
        print("  ⚠ No se encontró cruces_gourmet_segovia.csv")
        return []

    examples = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f, delimiter=';')
        rows = list(reader)

    # Generar Q/A por cruce individual (selección de cruces interesantes)
    for row in rows:
        cruce_id = row.get("Cruce_ID", "")
        materna = row.get("Raza_materna", "")
        paterna = row.get("Raza_paterna", "")
        objetivo = row.get("Objetivo_principal", "")
        rend = row.get("Rendimiento_canal_%", "")
        marmoleo = row.get("Marmoleo", "")
        terneza = row.get("Terneza", "")
        crecimiento = row.get("Crecimiento", "")
        rusticidad = row.get("Rusticidad", "")
        notas = row.get("Notas", "")
        tipo = row.get("Tipo_esquema", "")
        apto_pasto = row.get("Apto_pasto", "")
        apto_altitud = row.get("Apto_altitud_frio", "")

        q = f"¿Qué resultado da el cruce de {materna} con {paterna} para carne de vacuno?"
        a = (
            f"El cruce {materna} × {paterna} ({tipo}) tiene como objetivo principal: "
            f"{objetivo}. "
            f"Rendimiento canal: {rend}%, marmoleo: {marmoleo}, terneza: {terneza}, "
            f"crecimiento: {crecimiento}. "
            f"Rusticidad: {rusticidad}, aptitud a pasto: {apto_pasto}, "
            f"aptitud altitud/frío: {apto_altitud}. "
            f"{notas}"
        )
        examples.append(make(q, a, ["vacuno", "cruces_gourmet"]))

    # Generar preguntas resumen
    # Mejores cruces para marmoleo
    alto_marmoleo = [r for r in rows if r.get("Marmoleo", "").lower() in ("alto", "muy alto")]
    if alto_marmoleo:
        nombres = [f"{r['Raza_materna']}×{r['Raza_paterna']}" for r in alto_marmoleo[:8]]
        examples.append(make(
            "¿Cuáles son los mejores cruces de vacuno para conseguir alto marmoleo?",
            f"Los cruces con mayor marmoleo (alto o muy alto) según la tabla de cruces gourmet de Segovia son: "
            f"{', '.join(nombres)}. Destacan especialmente los cruces con Angus y Wagyu como raza paterna, "
            f"ya que aportan mayor infiltración grasa intramuscular. Los cruces con Wagyu alcanzan marmoleo "
            f"'muy alto' pero tienen crecimiento más lento y requieren acabado/terminación especial. "
            f"Los cruces con Angus ofrecen un buen equilibrio entre marmoleo alto y crecimiento medio-alto.",
            ["vacuno", "cruces_gourmet"]
        ))

    # Mejores para montaña
    montana = [r for r in rows if r.get("Apto_altitud_frio", "").lower() == "muy alta"]
    if montana:
        nombres = [f"{r['Raza_materna']}×{r['Raza_paterna']}" for r in montana[:8]]
        examples.append(make(
            "¿Qué cruces de vacuno son mejores para zonas de montaña y altitud?",
            f"Para zonas de montaña con frío y altitud, los cruces más recomendados (aptitud altitud/frío 'muy alta') son: "
            f"{', '.join(nombres)}. "
            f"Todos estos cruces conservan la rusticidad de la raza materna autóctona (Avileña, Pirenaica, "
            f"Asturiana de la Montaña, Salers, Aubrac, Galloway, Highland) mientras mejoran la calidad de carne "
            f"con la raza paterna. Para Segovia en particular, el cruce Avileña×Angus es el más recomendado por "
            f"su equilibrio entre rusticidad extrema y calidad de carne gourmet a pasto.",
            ["vacuno", "cruces_gourmet"]
        ))

    # Máximo rendimiento canal
    alto_rend = [r for r in rows if "63" in r.get("Rendimiento_canal_%", "") or "65" in r.get("Rendimiento_canal_%", "")]
    if alto_rend:
        nombres = [f"{r['Raza_materna']}×{r['Raza_paterna']}" for r in alto_rend[:6]]
        examples.append(make(
            "¿Qué cruces de vacuno dan el máximo rendimiento canal?",
            f"Los cruces con mayor rendimiento canal (58-65%) son: {', '.join(nombres)}. "
            f"Destaca el cruce Limusina×Charolesa con 60-65% de rendimiento canal, aunque requiere buena "
            f"oferta forrajera y vigilancia de partos. Los cruces con base Avileña que usan Limusina o "
            f"Charolesa como terminal también alcanzan 58-63%. El rendimiento canal alto se debe a la "
            f"alta musculatura de estas razas terminales, pero suele ir acompañado de menor marmoleo.",
            ["vacuno", "cruces_gourmet"]
        ))

    print(f"  Cruces gourmet: {len(examples)} ejemplos")
    return examples


# ================================================================
# 5. CORRECCIONES MANUALES (errores detectados)
# ================================================================
def manual_corrections():
    """Correcciones de errores conocidos y ejemplos críticos."""
    examples = []

    # ── CORRECCIÓN: Retinto es vacuno, NO gallina ──
    examples.append(make(
        "¿Qué es la raza Retinta?",
        "La Retinta es una raza bovina autóctona española, no una raza de gallina. Es una de las principales "
        "razas de vacuno de carne en España, originaria del suroeste peninsular (Extremadura, Andalucía). "
        "Sus características principales son: pelaje retinto (colorado oscuro uniforme), gran rusticidad, "
        "excelente adaptación a climas extremos mediterráneos, buena aptitud materna, peso adulto de "
        "550-650 kg en vacas y 900-1100 kg en toros. Se explota en régimen extensivo en dehesa, "
        "aprovechando pastos naturales. Es habitual cruzarla con razas mejorantes como Charolais o "
        "Limusín para mejorar la conformación de los terneros.",
        ["vacuno", "correccion"]
    ))

    # ── CAPONES: información correcta y detallada ──
    examples.append(make(
        "¿Qué razas de gallina se usan para producir capones?",
        "Para producir capones (pollos castrados) se necesitan razas pesadas de crecimiento lento. "
        "Las razas más utilizadas son:\n\n"
        "• Malinas (Coucou de Malines): la raza caponera por excelencia en Europa, con peso adulto "
        "de 4-5 kg y excelente calidad de carne.\n"
        "• Brahma: raza gigante asiática, muy dócil, peso adulto de 4-5 kg.\n"
        "• Cochinchina: raza pesada con buena infiltración grasa.\n"
        "• Plymouth Rock: raza dual americana, buena para capones de 3-4 kg.\n"
        "• Orpington: raza inglesa pesada (3.5-4.5 kg), muy dócil.\n"
        "• Sussex: raza dual inglesa con buena canal.\n"
        "• Cornish (Indian Game): base genética del pollo industrial, muy musculado.\n\n"
        "En España, las razas autóctonas usadas para capones son la Castellana negra, Prat leonada, "
        "Empordanesa y Gallina de Mos. El capón de Villalba (Lugo) con Gallina de Mos tiene "
        "Indicación Geográfica Protegida. La caponización se realiza entre las 6-8 semanas de vida "
        "y el engorde dura 6-8 meses hasta alcanzar 3-5 kg.",
        ["avicultura", "correccion"]
    ))

    examples.append(make(
        "¿Cuánto tarda un capón en estar listo para consumo?",
        "Un capón tarda entre 6 y 8 meses desde la caponización (castración quirúrgica) hasta estar "
        "listo para sacrificio. El proceso completo es:\n\n"
        "1. Selección de gallos jóvenes de razas pesadas (Malinas, Brahma, Castellana, etc.)\n"
        "2. Caponización quirúrgica a las 6-8 semanas de vida (extirpación testicular)\n"
        "3. Periodo de recuperación: 2-3 semanas\n"
        "4. Fase de crecimiento: 3-4 meses con alimentación balanceada\n"
        "5. Fase de acabado/cebo: 2-3 meses con alimentación rica en cereales, leche y grasa\n"
        "6. Sacrificio: entre los 7-10 meses de edad, con peso de 3-5 kg según raza\n\n"
        "La alimentación de acabado suele incluir maíz, cebada, leche desnatada y a veces castañas, "
        "lo que produce una carne tierna, jugosa y con infiltración grasa. El capón es un producto "
        "tradicionalmente navideño, con precios de 15-30 €/kg por su largo ciclo productivo.",
        ["avicultura", "correccion"]
    ))

    examples.append(make(
        "¿Qué es una pularda?",
        "La pularda es una gallina joven que se ceba intensivamente sin haber puesto huevos, "
        "sacrificada entre los 6-8 meses con un peso de 2.5-3.5 kg. A diferencia del capón "
        "(gallo castrado), la pularda es hembra y no se le realiza intervención quirúrgica, "
        "sino que se confina con alimentación rica para impedir que ponga huevos.\n\n"
        "Las razas más utilizadas para pulardas son las mismas de aptitud cárnica pesada: "
        "Malinas, Brahma, Plymouth Rock, Orpington y Cornish. En Francia, la pularda de "
        "Bresse tiene AOC y se considera el pollo de máxima calidad del mundo.\n\n"
        "La carne de pularda es más tierna y jugosa que la de pollo estándar, con mayor "
        "infiltración grasa intramuscular. Su precio oscila entre 12-25 €/kg, situándose "
        "entre el pollo de corral y el capón en el segmento premium.",
        ["avicultura", "correccion"]
    ))

    # ── Razas de gallinas españolas ──
    examples.append(make(
        "¿Qué razas de gallina autóctonas hay en España?",
        "España tiene una rica diversidad de razas avícolas autóctonas, muchas en peligro de extinción:\n\n"
        "• Castellana negra: Castilla, ponedora de huevo blanco, ligera (~2 kg)\n"
        "• Prat leonada (Prat): Cataluña, dual carne/huevo, ~3 kg, carne excelente\n"
        "• Empordanesa: Girona, dual, ~2.5 kg, variedad roja y aperdizada\n"
        "• Gallina de Mos: Lugo, cárnica pesada (~3.5 kg), base del Capón de Villalba (IGP)\n"
        "• Gallina del Sobrarbe: Aragón, rústica, en peligro crítico\n"
        "• Euskal Oiloa (gallina vasca): País Vasco, ponedora, ~2.5 kg\n"
        "• Utrerana: Andalucía, ponedora, variedades blanca, negra, franciscana y perdiz\n"
        "• Extremeña azul: Extremadura, rústica, plumaje azul\n"
        "• Murciana: Murcia, ligera, buena ponedora\n"
        "• Andaluza azul: ponedora, plumaje azul andaluz\n"
        "• Menorquina: Menorca, ponedora de huevo blanco grande\n"
        "• Ibicenca: Ibiza, rústica\n\n"
        "El programa de conservación del INIA-CSIC mantiene bancos de germoplasma de estas razas. "
        "Varias están catalogadas como 'en peligro de extinción' por el MAPA.",
        ["avicultura", "razas_españolas"]
    ))

    # ── PORCINO: Montanera ──
    examples.append(make(
        "¿Qué es la montanera del cerdo ibérico?",
        "La montanera es el periodo de engorde final del cerdo ibérico en dehesa, alimentándose "
        "de bellotas de encina y alcornoque, hierba y otros recursos naturales. Se desarrolla "
        "entre octubre y febrero-marzo, coincidiendo con la caída de la bellota.\n\n"
        "Características clave:\n"
        "• Duración: 2-4 meses (mínimo 60 días para calificar como 'de bellota')\n"
        "• Peso entrada: ~100-115 kg, peso salida: ~160-180 kg\n"
        "• Reposición mínima: 46 kg según normativa (RD 4/2014)\n"
        "• Carga ganadera: 0.75-1.25 cerdos/ha de dehesa\n"
        "• Consumo bellota: 6-10 kg/cerdo/día\n"
        "• Ejercicio: recorren 8-14 km/día buscando bellotas\n\n"
        "El ácido oleico de las bellotas se incorpora a la grasa del cerdo, dando al jamón "
        "ibérico de bellota su perfil lipídico característico (55-65% ácido oleico), similar "
        "al aceite de oliva. La normativa del ibérico distingue: bellota 100% ibérico, "
        "bellota ibérico, cebo de campo ibérico y cebo ibérico.",
        ["porcino", "iberico", "correccion"]
    ))

    # ── Digital Twins en ganadería ──
    examples.append(make(
        "¿Qué es un gemelo digital en ganadería?",
        "Un gemelo digital (Digital Twin) en ganadería es una réplica virtual de una explotación "
        "ganadera que integra datos en tiempo real de sensores IoT para simular, predecir y "
        "optimizar la producción. En NeoFarm, el Digital Twin incluye:\n\n"
        "• Modelo 3D de las instalaciones (naves, corrales, silos)\n"
        "• Datos IoT en tiempo real: temperatura, humedad, NH3, CO2, peso, consumo agua/pienso\n"
        "• Estado individual de cada animal: peso, salud, ciclo reproductivo, genética\n"
        "• Simulación predictiva: crecimiento, brotes sanitarios, impacto de cambios de dieta\n"
        "• Alertas automáticas: estrés térmico, caída de consumo, anomalías acústicas\n\n"
        "La arquitectura típica usa MQTT para ingesta de datos, InfluxDB para series temporales, "
        "y un frontend 3D (ej. Cesium/Three.js) para visualización. Los modelos predictivos "
        "se entrenan con datos históricos y pueden anticipar eventos como partos, enfermedades "
        "o el momento óptimo de sacrificio.",
        ["digital_twins", "iot"]
    ))

    # ── PorciData capas ──
    examples.append(make(
        "¿Cuáles son las 7 capas de sensores de PorciData?",
        "PorciData utiliza un sistema de 7+1 capas de sensores IoT para monitorización integral "
        "de granjas porcinas:\n\n"
        "1. Capa acústica (~15 €): micrófono INMP441 + ESP32 para detectar tos, estrés, "
        "vocalizaciones de dolor y actividad.\n"
        "2. Capa visual RGB (~150 €): cámara IP 4MP con visión artificial para conteo, "
        "comportamiento y detección de anomalías.\n"
        "3. Capa térmica (~550 €): cámara Hikvision bi-espectro para mapas de temperatura "
        "corporal sin contacto, detección precoz de fiebre.\n"
        "4. Capa ambiental (~200 €): sensores Dragino + Renke para temperatura, humedad "
        "relativa, NH3, CO2 y calidad del aire.\n"
        "5. Capa agua (~80 €): caudalímetro + sensor pH para consumo hídrico y calidad.\n"
        "6. Capa gases avanzada (~50 €): BME688 + SPS30 como nariz electrónica para VOCs "
        "y partículas PM2.5.\n"
        "7. Capa radar mmWave (~25 €): Seeed MR60BHA1 para respiración y frecuencia "
        "cardíaca sin contacto.\n"
        "+1. Capa peso walk-over (~350 €): células de carga + RFID para pesaje automático.\n\n"
        "Coste total: ~1.420 €/nave, unas 10x más económico que alternativas comerciales "
        "como Fancom (~14.500 €/nave).",
        ["iot", "porcidata"]
    ))

    # ── Nutrición: NRC ──
    examples.append(make(
        "¿Qué es el NRC en nutrición animal?",
        "El NRC (National Research Council) publica las tablas de referencia de requerimientos "
        "nutricionales para todas las especies ganaderas. Es el estándar mundial más utilizado "
        "para formular dietas:\n\n"
        "• NRC Swine (2012): requerimientos de cerdos por fase (gestación, lactación, "
        "crecimiento, acabado), incluyendo aminoácidos digestibles ileal estandarizado (SID).\n"
        "• NRC Dairy (2001, actualizado 2021): vacuno lechero, modelo CNCPS.\n"
        "• NRC Beef (2016): vacuno de carne, modelo de energía neta.\n"
        "• NRC Poultry (1994): aves, requerimientos de aminoácidos y energía metabolizable.\n\n"
        "En formulación práctica, el NRC define los niveles mínimos de lisina, metionina, "
        "treonina, triptófano y otros aminoácidos esenciales por kg de pienso, ajustados "
        "por fase productiva y genética. En Europa, las tablas FEDNA (España) e INRA "
        "(Francia) complementan al NRC con datos de materias primas locales.",
        ["nutricion", "formulacion"]
    ))

    # ── Ejemplos de RECHAZO (fuera de dominio) ──
    examples.append(make(
        "¿Cuál es la capital de Francia?",
        "Esa pregunta está fuera de mi dominio. Soy Seedy, asistente técnico especializado "
        "en agrotech para NeoFarm. Puedo ayudarte con ganadería (porcino, vacuno, avicultura), "
        "nutrición animal, genética, IoT ganadero, Digital Twins, normativa SIGE y más. "
        "¿Tienes alguna consulta sobre estos temas?",
        ["rechazo"]
    ))

    examples.append(make(
        "Escríbeme un poema sobre el amor",
        "No puedo ayudarte con eso. Soy Seedy, asistente técnico de NeoFarm especializado "
        "en agrotech: ganadería, nutrición animal, genética, IoT, Digital Twins y normativa. "
        "Si tienes alguna consulta técnica sobre estos temas, estaré encantado de ayudarte.",
        ["rechazo"]
    ))

    examples.append(make(
        "¿Qué tiempo hace mañana en Madrid?",
        "No tengo acceso a datos meteorológicos en tiempo real. Soy Seedy, asistente técnico "
        "de NeoFarm especializado en ganadería inteligente. Sin embargo, puedo ayudarte con "
        "temas relacionados como la gestión del estrés térmico en ganado, protocolos de "
        "ventilación en naves según temperatura, o el impacto del clima en la producción "
        "ganadera. ¿Te interesa alguno de estos temas?",
        ["rechazo"]
    ))

    examples.append(make(
        "Dame la receta del arroz con pollo",
        "No soy un asistente de cocina. Soy Seedy, especializado en agrotech para NeoFarm. "
        "Puedo ayudarte con temas como la producción de pollo de engorde, formulación de "
        "piensos avícolas, manejo de capones y pulardas, o razas de gallina para carne. "
        "¿Alguna consulta técnica sobre avicultura?",
        ["rechazo"]
    ))

    # ── Heterosis / vigor híbrido ──
    examples.append(make(
        "¿Qué es la heterosis en ganadería?",
        "La heterosis o vigor híbrido es la superioridad que muestran los animales cruzados "
        "(F1) respecto a la media de sus razas parentales. Es un fenómeno genético fundamental "
        "en los programas de cruzamiento ganadero.\n\n"
        "Tipos de heterosis:\n"
        "• Heterosis individual: mejora en el propio animal F1 (crecimiento, viabilidad)\n"
        "• Heterosis materna: mejora en la capacidad materna de hembras F1 (fertilidad, "
        "producción de leche, habilidad materna)\n\n"
        "Valores típicos de heterosis:\n"
        "• Supervivencia de crías: +5-15%\n"
        "• Tasa de crecimiento: +5-10%\n"
        "• Fertilidad de hembras F1: +10-25%\n"
        "• Peso al destete: +5-8%\n"
        "• Producción de leche materna: +5-15%\n\n"
        "La heterosis es máxima cuando se cruzan razas genéticamente distantes (ej. raza "
        "autóctona × raza mejorante). Se aprovecha en esquemas rotacionales y en cruzamientos "
        "terminales (ej. Avileña × Angus F1 como madre, terminada con Limusín).",
        ["genetica", "cruzamiento"]
    ))

    # ── SIGE / Normativa ──
    examples.append(make(
        "¿Qué es el SIGE en ganadería porcina?",
        "El SIGE (Sistema Integral de Gestión de Explotaciones) es el sistema de registro "
        "obligatorio para explotaciones ganaderas en España, regulado por el Real Decreto "
        "306/2020. Para porcino incluye:\n\n"
        "• Registro de movimientos: entradas, salidas y muertes de animales\n"
        "• Libro de explotación digital: censos, categorías de animales\n"
        "• Registro de tratamientos veterinarios y recetas\n"
        "• Guías de movimiento (documentos de traslado)\n"
        "• Información sanitaria: programas de vigilancia, resultados analíticos\n\n"
        "Desde 2022, la gestión se realiza a través de la plataforma REGA (Registro General "
        "de Explotaciones Ganaderas) y conecta con el sistema TRACES de la UE para "
        "movimientos intracomunitarios. El incumplimiento puede suponer sanciones de "
        "6.000-600.000 € según gravedad. El código REGA es obligatorio para cualquier "
        "explotación ganadera en España.",
        ["normativa", "sige"]
    ))

    # ── ECOGAN ──
    examples.append(make(
        "¿Qué es ECOGAN?",
        "ECOGAN es el estándar voluntario de calificación ambiental para granjas porcinas en "
        "España, desarrollado por el MAPA. Evalúa las prácticas de la explotación en materia "
        "de emisiones de amoníaco (NH3), gases de efecto invernadero y gestión de purines.\n\n"
        "Las granjas se clasifican en categorías según sus Mejores Técnicas Disponibles (MTD):\n"
        "• Gestión del purín: foso, slurry, separación sólido-líquido\n"
        "• Tipo de suelo: emparrillado total, parcial o cama profunda\n"
        "• Ventilación: natural o forzada con scrubbers\n"
        "• Alimentación: multifase, bajo proteína, fitasas\n"
        "• Almacenamiento: balsa cubierta, digestión anaerobia\n"
        "• Aplicación al campo: inyección, abanico, tubos colgantes\n\n"
        "ECOGAN otorga una puntuación que puede vincular a ayudas PAC y eco-esquemas. "
        "Las granjas con mejor calificación reducen hasta un 80% las emisiones de NH3 "
        "respecto a la referencia.",
        ["normativa", "ecogan"]
    ))

    print(f"  Correcciones manuales: {len(examples)} ejemplos")
    return examples


# ================================================================
# 6. Q/A DE AVICULTURA ESPECÍFICOS (contenido que falta)
# ================================================================
def avicultura_extra():
    """Q/A de avicultura que faltan en v7."""
    examples = []

    examples.append(make(
        "¿Cuál es la diferencia entre un capón y un pollo de engorde?",
        "El capón y el pollo de engorde (broiler) son productos muy diferentes:\n\n"
        "Pollo de engorde (broiler):\n"
        "• Raza: híbridos industriales (Cobb 500, Ross 308)\n"
        "• Edad sacrificio: 35-42 días\n"
        "• Peso: 2-2.5 kg\n"
        "• Sin castrar\n"
        "• Alimentación intensiva con pienso industrial\n"
        "• Carne magra, textura blanda\n"
        "• Precio: 2-4 €/kg\n\n"
        "Capón:\n"
        "• Raza: razas pesadas (Malinas, Brahma, Castellana, Mos)\n"
        "• Edad sacrificio: 7-10 meses\n"
        "• Peso: 3-5 kg\n"
        "• Castrado quirúrgicamente a las 6-8 semanas\n"
        "• Alimentación prolongada con cereales, leche\n"
        "• Carne tierna, jugosa, con grasa infiltrada\n"
        "• Precio: 15-30 €/kg\n\n"
        "La castración del capón elimina las hormonas sexuales, lo que produce un ave más "
        "tranquila que acumula grasa intramuscular de forma uniforme, dando una carne de "
        "calidad superior. Es un producto gourmet estacional, típico de Navidad.",
        ["avicultura"]
    ))

    examples.append(make(
        "¿Cómo se hace la caponización?",
        "La caponización es la castración quirúrgica de gallos jóvenes. El procedimiento:\n\n"
        "• Edad óptima: 6-8 semanas (antes del desarrollo sexual)\n"
        "• Ayuno previo: 12-24 horas\n"
        "• Anestesia: local o general según legislación del país\n"
        "• Técnica: incisión entre las dos últimas costillas del lado izquierdo, retracción, "
        "localización y extracción de los testículos (situados junto a los riñones)\n"
        "• Se repite por el lado derecho si es necesario\n"
        "• Sutura o cierre con grapas\n"
        "• Recuperación: 2-3 semanas\n"
        "• Mortalidad perioperatoria: 2-5% con técnica correcta\n\n"
        "Existen también métodos hormonales (implantes de estrógenos) pero están prohibidos "
        "en la UE desde 2006. Solo se permite la castración quirúrgica con analgesia/anestesia "
        "según el Reglamento (CE) 1099/2009 de protección en el sacrificio.\n\n"
        "En Francia y Bélgica, la caponización la realizan veterinarios especializados. "
        "En España, tradiciones como el Capón de Villalba (Lugo) mantienen la técnica "
        "artesanal transmitida entre generaciones.",
        ["avicultura"]
    ))

    examples.append(make(
        "¿Qué alimentación lleva un capón durante el engorde?",
        "La alimentación del capón es clave para conseguir la calidad gourmet. Se divide en fases:\n\n"
        "Fase de crecimiento (2-5 meses post-caponización):\n"
        "• Pienso balanceado con 18-20% proteína bruta\n"
        "• Cereales: maíz, trigo, cebada\n"
        "• Acceso a hierba y pasto si es crianza campera\n"
        "• Objetivo: desarrollo óseo y muscular\n\n"
        "Fase de acabado/cebo (últimos 2-3 meses):\n"
        "• Dieta hipercalórica para infiltración grasa\n"
        "• Base: maíz molido (60-70% de la ración)\n"
        "• Leche desnatada o suero lácteo ad libitum\n"
        "• Grasa añadida: manteca o sebo\n"
        "• En Galicia (Capón de Villalba): castañas cocidas\n"
        "• En Francia (Bresse): trigo sarraceno con leche\n"
        "• Restricción de movimiento en los últimos 15-30 días\n\n"
        "Índice de conversión del capón: 5-7:1 (vs 1.6-1.8:1 del broiler industrial), "
        "lo que explica su alto precio. El consumo total de pienso es de 15-25 kg por capón.",
        ["avicultura", "nutricion"]
    ))

    examples.append(make(
        "¿Qué razas de gallina se usan para pollo campero?",
        "Para pollo campero (label, de corral) se usan razas de crecimiento medio-lento. "
        "Las más comunes en España:\n\n"
        "Razas e híbridos para campero:\n"
        "• Red Label / JA57: híbrido francés de cuello desnudo, crecimiento lento (81-90 días), "
        "el más usado en España para campero certificado.\n"
        "• Sasso: híbridos italianos de crecimiento lento, varias líneas de color.\n"
        "• Prat leonada: raza autóctona catalana, excelente sabor, 3-3.5 kg en 16 semanas.\n"
        "• Gallina de Mos: gallega, cárnica, hasta 3.5 kg, base del Capón de Villalba.\n"
        "• Castellana negra: castellana, huevos blancos, carne firme.\n"
        "• Empordanesa: catalana, dual.\n"
        "• Hubbard: híbridos industriales de crecimiento medio para 'campero económico'.\n\n"
        "La normativa europea para pollo campero exige:\n"
        "• Edad mínima al sacrificio: 56 días (campero) o 81 días (campero tradicional)\n"
        "• Acceso al aire libre: mínimo 2 m²/pollo\n"
        "• Densidad interior: máximo 27.5 kg/m² (campero) o 25 kg/m² (tradicional)\n"
        "• Alimentación: mínimo 70% cereales en la fórmula del pienso.",
        ["avicultura"]
    ))

    examples.append(make(
        "¿Cuánto pesa una gallina Malinas?",
        "La gallina Malinas (Coucou de Malines / Mechelse Koekoek) es una de las razas de "
        "gallina más pesadas del mundo:\n\n"
        "• Gallo adulto: 4.5-5.5 kg\n"
        "• Gallina adulta: 3.5-4.5 kg\n"
        "• Capón (8-10 meses): 4.5-6 kg\n\n"
        "Origen: Malinas (Mechelen), Bélgica. Su nombre francés es 'Coucou de Malines' "
        "por su plumaje barrado (coucou). Es la raza caponera europea por excelencia:\n"
        "• Crecimiento lento pero constante\n"
        "• Carne de textura fina y sabor intenso\n"
        "• Excelente infiltración grasa como capón\n"
        "• Temperamento dócil, ideal para engorde en confinamiento\n"
        "• Puesta moderada: 120-160 huevos/año (huevo de color crema)\n\n"
        "El 'Mechelse Koekoek' tiene denominación de calidad en Bélgica. "
        "Es la base genética del capón belga premium de Navidad.",
        ["avicultura", "razas"]
    ))

    print(f"  Avicultura extra: {len(examples)} ejemplos")
    return examples


# ================================================================
# MAIN: Ensamblar v8
# ================================================================
def main():
    print("=" * 60)
    print("🌱 CONSTRUYENDO DATASET v8")
    print("=" * 60)

    # 1. Base v7
    print("\n📦 Cargando fuentes:")
    v7 = load_v7()

    # 2. Wikipedia Q/A
    wiki = generate_qa_from_wiki()

    # 3. Science Q/A
    science = generate_qa_from_science()

    # 4. Cruces gourmet
    cruces = generate_qa_from_cruces_csv()

    # 5. Correcciones
    corrections = manual_corrections()

    # 6. Avicultura extra
    avi = avicultura_extra()

    # ── Merge all ──
    all_examples = v7 + wiki + science + cruces + corrections + avi

    # ── Deduplicación por pregunta ──
    print(f"\n🔧 Deduplicación...")
    seen = {}
    unique = []
    dupes = 0
    for ex in all_examples:
        user_msg = ex["messages"][1]["content"].strip().lower()
        if user_msg in seen:
            dupes += 1
            # Keep the newer one (corrections override base)
            if "_tags" in ex and "correccion" in ex.get("_tags", []):
                # Replace old with correction
                unique[seen[user_msg]] = ex
        else:
            seen[user_msg] = len(unique)
            unique.append(ex)

    print(f"  Duplicados eliminados: {dupes}")

    # ── Limpiar tags internos antes de guardar ──
    for ex in unique:
        ex.pop("_tags", None)

    # ── Stats ──
    print(f"\n📊 ESTADÍSTICAS DATASET v8:")
    print(f"   Total ejemplos: {len(unique)}")

    # Contar por longitud de respuesta
    resp_lengths = [len(e["messages"][2]["content"]) for e in unique]
    avg_len = sum(resp_lengths) / len(resp_lengths) if resp_lengths else 0
    print(f"   Longitud media respuesta: {avg_len:.0f} chars")
    print(f"   Respuesta más corta: {min(resp_lengths)} chars")
    print(f"   Respuesta más larga: {max(resp_lengths)} chars")

    # Guardar
    output_path = os.path.join(BASE_DIR, "seedy_dataset_sft_v8.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for ex in unique:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"\n   ✅ Guardado en: {output_path}")
    print(f"   📈 Crecimiento: v7({len(v7)}) → v8({len(unique)}) = +{len(unique)-len(v7)} ejemplos")
    print("=" * 60)


if __name__ == "__main__":
    main()
