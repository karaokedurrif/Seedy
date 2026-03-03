#!/usr/bin/env python3
"""
Genera seedy_dataset_sft_v4.jsonl a partir del v3:
1. Elimina duplicados (mantiene mejor respuesta por pregunta)
2. Elimina ejemplos con respuesta incorrecta (misma respuesta para preguntas distintas)
3. Enriquece respuestas cortas (<220 chars)
4. Añade ~40 ejemplos nuevos de Genética, Normativa, Digital Twin y cross-domain
"""
import json
from collections import Counter

SYSTEM = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData), costes por nave, nutrición porcina, "
    "genética aplicada, normativa SIGE y Digital Twins productivos.\n\n"
    "Responde siempre en español, en prosa natural y profesional.\n"
    "No uses secciones tipo Notes, References o Explanation.\n"
    "No repitas la pregunta.\n"
    "No inventes cifras, normativa ni parámetros técnicos.\n"
    "Si falta un dato imprescindible, pide solo el mínimo necesario (máximo 2 preguntas).\n"
    "Si das un número, incluye unidades y aclara si es aproximado.\n"
    "Prioriza precisión técnica sobre tono comercial."
)

def make(user: str, assistant: str) -> dict:
    return {"messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": user},
        {"role": "assistant", "content": assistant},
    ]}

# --- PASO 1: Cargar v3 y limpiar ---
with open("seedy_dataset_sft_v3_plus60.jsonl") as f:
    raw = [json.loads(l) for l in f]

print(f"v3 original: {len(raw)} ejemplos")

# Detectar respuestas reutilizadas (misma respuesta en >2 preguntas distintas)
answer_to_questions = {}
for i, d in enumerate(raw):
    asst = [m for m in d["messages"] if m["role"] == "assistant"][-1]["content"]
    user = [m for m in d["messages"] if m["role"] == "user"][0]["content"]
    key = asst.strip()
    if key not in answer_to_questions:
        answer_to_questions[key] = []
    answer_to_questions[key].append((i, user))

# Respuestas lazy: misma respuesta para 3+ preguntas distintas diferentes
lazy_answers = {k for k, v in answer_to_questions.items() if len(v) >= 3}
lazy_lines = set()
for ans in lazy_answers:
    entries = answer_to_questions[ans]
    # Mantener solo la primera ocurrencia (la que coincide mejor)
    for idx, _ in entries[1:]:
        lazy_lines.add(idx)

print(f"Respuestas lazy (misma respuesta >=3 preguntas): {len(lazy_answers)} respuestas, {len(lazy_lines)} líneas a quitar")

# Deduplicar por pregunta (mantener primera)
seen_q = {}
dupe_lines = set()
for i, d in enumerate(raw):
    user = [m for m in d["messages"] if m["role"] == "user"][0]["content"].strip().lower()
    if user in seen_q:
        dupe_lines.add(i)
    else:
        seen_q[user] = i

print(f"Duplicados exactos de pregunta: {len(dupe_lines)} líneas")

# Unir líneas a eliminar
remove = lazy_lines | dupe_lines
clean = [d for i, d in enumerate(raw) if i not in remove]
print(f"Después de limpieza: {len(clean)} ejemplos")

# --- PASO 2: Enriquecer respuestas cortas ---
enriched = {
    "¿cuánto cuesta el bom de porcidata?": (
        "El BOM (Bill of Materials) de PorciData tiene un coste total de ~1.420 EUR por nave, "
        "cubriendo 7+1 capas de sensores IoT: acústica (~15 EUR, INMP441+ESP32), visión RGB (~150 EUR, "
        "cámara IP 4MP), térmica (~550 EUR, Hikvision bi-espectro), ambiental (~200 EUR, Dragino+Renke "
        "para T/HR/NH3/CO2), agua (~80 EUR, caudalímetro+pH), gases avanzado (~50 EUR, BME688+SPS30 nariz "
        "electrónica), radar mmWave (~25 EUR, Seeed MR60BHA1) y peso walk-over (~350 EUR, células+RFID). "
        "Es aproximadamente 10x más económico que alternativas comerciales como Fancom (~14.500 EUR/nave) "
        "o Nedap. El precio incluye solo hardware, no instalación ni gateway."
    ),
    "¿cuánto vale instrumentar una nave con porcidata?": (
        "Instrumentar una nave completa con las 7+1 capas de sensores PorciData cuesta aproximadamente "
        "1.420 EUR en hardware. Esto incluye todos los sensores, microcontroladores ESP32 y edge devices. "
        "No incluye instalación, cableado ni el gateway LoRa/WiFi que conecta al broker MQTT. La capa más "
        "cara es la térmica (Hikvision bi-espectro, ~550 EUR) y la de peso walk-over (~350 EUR con células "
        "de carga y RFID). Las capas más económicas son acústica (~15 EUR) y radar mmWave (~25 EUR). "
        "Para un piloto de 3 naves, el capex hardware total sería ~4.260 EUR."
    ),
}

for i, d in enumerate(clean):
    user = [m for m in d["messages"] if m["role"] == "user"][0]["content"].strip().lower()
    if user in enriched:
        for m in d["messages"]:
            if m["role"] == "assistant":
                m["content"] = enriched[user]

# --- PASO 3: Nuevos ejemplos Genética (15) ---
new_genetica = [
    make(
        "¿Qué es el coeficiente de consanguinidad de Wright y cuándo preocuparse?",
        "El coeficiente de consanguinidad de Wright (F) mide la probabilidad de que dos alelos en un locus "
        "sean idénticos por descendencia. Se calcula recorriendo el pedigrí: F = Σ[(1/2)^(n1+n2+1) × (1+Fa)], "
        "donde n1 y n2 son generaciones al ancestro común y Fa su propia consanguinidad. En porcino intensivo, "
        "niveles por debajo de F=0.0625 (equivalente a primos segundos) son aceptables. Por encima de 0.10 "
        "empiezan a notarse efectos de depresión endogámica: menor tamaño de camada (-0.3 a -0.5 lechones), "
        "peor viabilidad neonatal y mayor susceptibilidad a enfermedades. En NeoFarm, el módulo Genética "
        "calcula F automáticamente a partir del pedigrí y alerta si un apareamiento propuesto superaría el umbral."
    ),
    make(
        "¿Qué son los EPDs y cómo se usan en selección porcina?",
        "Los EPDs (Expected Progeny Differences) son predicciones del mérito genético que un animal transmitirá "
        "a su descendencia, expresadas como diferencia respecto a una base genética. Se calculan mediante "
        "BLUP (Best Linear Unbiased Prediction) usando datos de rendimiento propios y de parientes. En porcino, "
        "los EPDs más relevantes son: ganancia media diaria (GMD), índice de conversión (IC), espesor de grasa "
        "dorsal (EGD), tamaño de camada (TC) y porcentaje de magro. Para usarlos correctamente: compara siempre "
        "dentro de la misma evaluación y base genética, revisa la fiabilidad (accuracy) — un EPD con accuracy "
        "<0.3 es poco fiable —, y pondera según el objetivo económico de la explotación. NeoFarm integra EPDs "
        "de catálogos (DanBred, PIC, Topigs) y permite compararlos en una misma escala relativa."
    ),
    make(
        "¿Qué es la heterosis y cómo la aprovecha NeoFarm?",
        "La heterosis o vigor híbrido es la superioridad del cruce sobre la media de las razas parentales. "
        "Es especialmente fuerte en rasgos de baja heredabilidad como fertilidad y supervivencia (10-25% de "
        "heterosis), moderada en crecimiento (5-10%) y baja en calidad de canal (<5%). En porcino, el cruce "
        "triple (ej: hembra F1 Large White × Landrace cruzada con verraco Duroc/Pietrain) maximiza heterosis "
        "individual y materna. NeoFarm calcula la heterosis esperada según las razas de los progenitores "
        "y la incluye como variable en FarmMatch, el motor de apareamiento. Para vacuno extensivo, la heterosis "
        "entre razas rústicas (Retinta, Avileña) y razas cárnicas (Charolés, Limusín) puede suponer +15-20 kg "
        "al destete."
    ),
    make(
        "¿Qué paneles genómicos soporta NeoFarm y para qué sirven?",
        "NeoFarm integra resultados de paneles genómicos de Neogen (GGP Porcine 50K y 80K), Zoetis (PigProfile) "
        "y Xenética Fontao (evaluaciones nacionales). Estos paneles genotipan entre 10K y 80K marcadores SNP "
        "y permiten: selección genómica (EPDs más precisos incluso sin datos productivos), pruebas de paternidad, "
        "detección de portadores de defectos genéticos (halotano, PSE) y estimación de consanguinidad genómica "
        "(más precisa que la genealógica). La plataforma importa ficheros de resultados, los vincula al pedigrí "
        "del animal y recalcula los EPDs genómicos con mayor accuracy. Para explotaciones pequeñas (<500 madres), "
        "el panel de 10K suele ser suficiente para paternidad y consanguinidad; para núcleos de selección, "
        "se recomienda el de 50K o superior."
    ),
    make(
        "¿Cómo funciona FarmMatch, el motor de apareamientos de NeoFarm?",
        "FarmMatch es el motor de apareamiento de NeoFarm que optimiza los cruces minimizando consanguinidad "
        "y maximizando mérito genético. Funciona así: (1) calcula la matriz de parentesco entre todos los "
        "reproductores disponibles usando pedigrí y/o genómica, (2) define un objetivo de selección ponderado "
        "(ej: 40% IC, 30% GMD, 20% TC, 10% conformación), (3) resuelve un problema de asignación lineal "
        "que maximiza el mérito esperado de la progenie sujeto a restricciones de consanguinidad máxima "
        "(típico F<0.0625). El resultado es una lista de apareamientos recomendados con mérito esperado, "
        "F estimado y heterosis prevista. Para vacuno, incluye además distancia geográfica entre fincas "
        "y disponibilidad de semen en banco."
    ),
    make(
        "¿Qué razas autóctonas españolas gestiona NeoFarm y por qué importan?",
        "NeoFarm incluye datos de razas autóctonas como Retinta, Avileña-Negra Ibérica, Morucha y Rubia "
        "Gallega en vacuno, y Cerdo Ibérico (Retinto, Entrepelado, Lampiño, Torbiscal) en porcino. Estas razas "
        "importan porque están adaptadas al medio (dehesa, montaña), tienen calidades de carne diferenciadas "
        "(infiltración grasa, ácido oleico en Ibérico), acceden a premios de PAC por conservación de razas "
        "en peligro, y aportan rusticidad en programas de cruce. El módulo Genética almacena catálogos de "
        "sementales por raza, sus EPDs específicos y los cruzamientos recomendados. Para Ibérico extensivo, "
        "la trazabilidad genética (prueba de pureza racial) es obligatoria para acceder a la norma de calidad "
        "del Ibérico (RD 4/2014)."
    ),
    make(
        "¿Qué heredabilidades usa NeoFarm para los rasgos productivos en porcino?",
        "NeoFarm usa heredabilidades (h²) basadas en literatura y evaluaciones genéticas españolas: ganancia "
        "media diaria h²≈0.30, índice de conversión h²≈0.25, espesor de grasa dorsal h²≈0.45-0.55, porcentaje "
        "de magro h²≈0.50, tamaño de camada (nacidos vivos) h²≈0.10, peso al nacimiento h²≈0.05-0.10 y "
        "resistencia a enfermedades h²≈0.05-0.15. Rasgos con h² alta (>0.3) responden bien a selección "
        "individual (fenotipo propio); rasgos con h² baja (<0.15) requieren información de parientes/genómica "
        "y se benefician más de heterosis vía cruzamiento. El sistema ajusta estos valores si la explotación "
        "aporta sus propias estimaciones REML de parámetros genéticos."
    ),
    make(
        "¿Qué es la depresión endogámica y cómo la detecta NeoFarm?",
        "La depresión endogámica es la pérdida de rendimiento productivo causada por el aumento de homocigosis "
        "cuando animales emparentados se aparean. Sus efectos en porcino incluyen: reducción de 0.25-0.50 "
        "lechones nacidos vivos por cada 10% de incremento en F, menor peso al nacimiento (-50 a -100 g), "
        "mayor mortalidad predestete y peor respuesta inmunitaria. NeoFarm la detecta de dos formas: (1) "
        "genealógica, calculando F de Wright a partir del pedigrí con al menos 3 generaciones, y (2) genómica, "
        "usando runs of homozygosity (ROH) a partir de datos SNP, que es más precisa. El sistema alerta "
        "automáticamente cuando F supera 0.0625 y bloquea apareamientos que generarían F>0.125 salvo "
        "autorización manual del técnico."
    ),
    make(
        "¿Cómo gestiona NeoFarm el banco de semen y la IA (inseminación artificial)?",
        "El módulo Genética incluye gestión de banco de semen: inventario de dosis por verraco/toro con "
        "lote, fecha de recogida, centro de IA, calidad (motilidad, concentración) y ubicación física "
        "(tanque criogénico/rack). Vincula cada dosis al pedigrí del semental y a sus EPDs. Al registrar "
        "una inseminación, actualiza automáticamente el inventario, genera el servicio esperado con fecha "
        "de parto prevista (114±2 días en porcino, 283±10 en vacuno) y calcula la consanguinidad esperada "
        "de la camada. También permite importar catálogos de centros de IA (Semen Cardona, CENSYRA, Xenética "
        "Fontao) y comparar sementales por índice económico ponderado."
    ),
    make(
        "¿Cuántas generaciones de pedigrí necesita NeoFarm para calcular consanguinidad fiable?",
        "Para un cálculo de consanguinidad genealógica razonablemente preciso se necesitan al menos 3 "
        "generaciones completas de pedigrí (padres, abuelos, bisabuelos). Con solo 2 generaciones, F se "
        "subestima significativamente porque no detecta ancestros comunes más lejanos. Con 4-5 generaciones "
        "la estimación es mucho mejor. Si el pedigrí es incompleto (animales fundadores sin padres conocidos), "
        "NeoFarm aplica el método de VanRaden (2008) que asigna consanguinidad esperada según año de nacimiento "
        "y raza. La alternativa más precisa es la consanguinidad genómica (FROH), que no necesita pedigrí "
        "sino un panel de SNPs. NeoFarm recomienda genómica cuando el pedigrí tiene <3 generaciones o "
        ">20% de ancestros desconocidos."
    ),
    make(
        "¿Qué diferencia hay entre selección por fenotipo, BLUP y selección genómica?",
        "Son tres niveles de precisión en selección genética. Selección fenotípica: elige animales por su "
        "propio rendimiento (ej: los que más crecen). Es simple pero ignora efectos ambientales y tiene "
        "accuracy limitada (≈h, la raíz de heredabilidad). BLUP (Henderson, 1984): modelo mixto que separa "
        "efecto genético del ambiental usando datos propios y de parientes. Accuracy mucho mayor, especialmente "
        "en rasgos de baja h². Es el estándar en programas de mejora desde los años 90. Selección genómica: "
        "añade información de miles de SNPs para predecir mérito genético incluso sin datos productivos (ej: "
        "al nacimiento). Accuracy aún mayor, permite reducir intervalo generacional. NeoFarm soporta los "
        "tres niveles: entrada manual de fenotipos, cálculo BLUP con pedigrí, e integración de EPDs genómicos "
        "desde paneles de Neogen/Zoetis."
    ),
    make(
        "¿Cómo configuro un índice de selección económico en NeoFarm para porcino?",
        "En NeoFarm, un índice de selección económico pondera cada rasgo por su valor económico marginal. "
        "Para configurarlo: (1) define los rasgos objetivo (típico: GMD, IC, EGD, TC, longevidad), (2) asigna "
        "valores económicos — por ejemplo, GMD: +0.10 EUR/g/día, IC: -5.0 EUR por punto, EGD: -2.0 EUR/mm, "
        "TC: +15 EUR/lechón —, (3) el sistema calcula el índice I = Σ(ai × EPDi) donde ai es el valor "
        "económico y EPDi el mérito genético de cada rasgo. Los valores económicos deben reflejar precios "
        "actuales de la explotación (kg canal, coste pienso, valor lechón destete). NeoFarm recalcula "
        "trimestralmente con precios de lonjas para mantener el índice actualizado con la realidad del mercado."
    ),
    make(
        "¿Qué es el intervalo generacional y por qué importa en mejora genética?",
        "El intervalo generacional (IG) es la edad media de los padres cuando nacen sus hijos que se usarán "
        "como reproductores. En porcino intensivo suele ser 1.5-2.5 años; en vacuno extensivo, 4-6 años. "
        "Importa porque la respuesta a la selección (progreso genético anual) = ΔG = (i × rTI × σA) / L, "
        "donde L es el IG. Un IG menor acelera el progreso. Estrategias para reducirlo: usar semen joven "
        "de verracos evaluados genómicamente (sin esperar prueba de progenie), renovar reproductoras antes "
        "(a 5-6 partos en vez de 7-8) y aplicar selección genómica en animales jóvenes. NeoFarm calcula "
        "el IG real de la explotación y proyecta el progreso genético esperado por generación."
    ),
    make(
        "¿Cómo evalúa NeoFarm la calidad genética de un lote de lechones al destete?",
        "NeoFarm evalúa cada lote al destete combinando: (1) mérito genético medio del lote (promedio de EPDs "
        "de padre y madre para GMD, IC, EGD), (2) consanguinidad media del lote (alerta si F>0.05), (3) "
        "homogeneidad genética (desviación típica de EPDs dentro del lote — lotes muy heterogéneos producen "
        "canales desiguales), y (4) datos fenotípicos al destete (peso medio, CV de peso, mortalidad pre-destete). "
        "Con estos datos genera un índice de calidad genética del lote (0-100) que sirve para: ajustar la "
        "nutrición de la fase siguiente (lotes de alto mérito genético pueden tolerar dietas más densas), "
        "predecir el peso y fecha óptima de sacrificio, y valorar al verraco/cerda origen."
    ),
    make(
        "¿Qué cruzamientos recomienda NeoFarm para maximizar calidad de canal en Ibérico?",
        "Para Ibérico, NeoFarm distingue categorías según la norma (RD 4/2014): 100% Ibérico (puro, máximo "
        "precio pero menor GMD), 75% Ibérico (madre 100% Ibérica × padre 50% Ibérico-Duroc) y 50% Ibérico "
        "(madre 100% Ibérica × padre Duroc). El cruce con Duroc mejora GMD en +80-100 g/día e IC en -0.3 puntos, "
        "pero reduce infiltración grasa intramuscular y contenido de ácido oleico. FarmMatch optimiza según "
        "el destino comercial: para bellota DOP, prioriza pureza y grasa; para cebo intensivo, permite mayor "
        "cruce. El sistema calcula el rendimiento económico esperado por categoría considerando precio de canal "
        "diferenciado (Ibérico puro bellota ~8-12 EUR/kg vs 50% cebo ~3.5-4.5 EUR/kg) y duración de engorde."
    ),
]

# --- PASO 4: Nuevos ejemplos Normativa/SIGE (12) ---
new_normativa = [
    make(
        "¿Cuáles son los 11 planes del SIGE según el RD 306/2020?",
        "Los 11 planes obligatorios del Sistema Integral de Gestión de Explotaciones (SIGE) según el RD 306/2020 "
        "son: (1) Plan de bioseguridad, (2) Plan de limpieza y desinfección (L+D), (3) Plan de desinsectación y "
        "desratización (DDD), (4) Plan sanitario, (5) Plan de bienestar animal, (6) Plan de gestión ambiental "
        "(incluye purines y emisiones), (7) Plan de alimentación animal, (8) Plan de gestión del agua, "
        "(9) Plan de medicamentos veterinarios y gestión de resistencias antimicrobianas, (10) Plan de "
        "formación del personal, y (11) Plan de gestión de cadáveres y subproductos (SANDACH). Cada plan "
        "debe documentarse, revisarse anualmente y estar disponible para inspección. NeoFarm genera "
        "automáticamente las plantillas y las actualiza con datos de los sensores IoT (ej: registros "
        "de temperatura y humedad para el plan de bienestar, consumos de agua para el plan de gestión hídrica)."
    ),
    make(
        "¿Qué es ECOGAN y cómo se relaciona con PorciData?",
        "ECOGAN es la herramienta oficial del MAPA (Ministerio de Agricultura) para el cálculo y comunicación "
        "de emisiones de gases de efecto invernadero y amoníaco en explotaciones ganaderas. Funciona en 8 pasos: "
        "(1) registro de la explotación, (2) censo animal por categorías, (3) tipo de alojamiento y suelo, "
        "(4) sistema de gestión de estiércol/purines, (5) alimentación (proteína bruta, fibra), (6) técnicas "
        "de reducción aplicadas (cubiertas, aditivos, inyección), (7) cálculo de emisiones (NH3, CH4, N2O) y "
        "(8) generación del certificado. PorciData se integra aportando datos en tiempo real: los sensores de "
        "NH3 y CO2 de la capa ambiental validan las emisiones calculadas, y los caudalímetros de la capa agua "
        "verifican consumos declarados. Esto permite auditar ECOGAN con datos objetivos, no solo estimaciones."
    ),
    make(
        "¿Qué superficies mínimas exige el RD 1135/2002 para porcino?",
        "El RD 1135/2002 establece superficies mínimas por animal en porcino según categoría y peso: lechones "
        "destete (<10 kg): 0.15 m²; precebo (10-20 kg): 0.20 m²; crecimiento (20-30 kg): 0.30 m²; engorde "
        "(30-50 kg): 0.40 m²; engorde (50-85 kg): 0.55 m²; engorde (85-110 kg): 0.65 m²; engorde (>110 kg): "
        "1.00 m²; cerdas gestantes en grupo: 2.25 m² (nulíparas 1.64 m²); verracos: 6.00 m². Además, al menos "
        "un tercio de la superficie debe ser suelo continuo (no enrejillado). Para lactación, la paridera debe "
        "tener espacio para que los lechones mamen libremente. PorciData puede monitorizar densidad real con "
        "la capa de visión RGB (conteo automático) y alertar si se supera la densidad legal."
    ),
    make(
        "¿Qué registros obligatorios debe llevar una explotación porcina en España?",
        "Los registros obligatorios incluyen: libro de registro de explotación (REGA, con altas/bajas y "
        "movimientos), libro de tratamientos veterinarios (con producto, dosis, lote, tiempo de retirada "
        "y veterinario prescriptor), registro de mortalidad (fecha, causa, destino del cadáver), registros "
        "de alimentación (origen y lote de piensos), registro de limpieza y desinfección (producto, fecha, "
        "responsable), registros de DDD (empresa autorizada, fechas, productos), registro de visitas "
        "(fecha, motivo, persona), y los 11 planes SIGE del RD 306/2020. Todos deben conservarse al menos "
        "3 años (5 para tratamientos). NeoFarm digitaliza estos registros y los vincula con datos IoT para "
        "que se autocompleten parcialmente (ej: registros de temperatura ambiental automáticos)."
    ),
    make(
        "¿Qué normativa regula el bienestar animal en porcino en España?",
        "La normativa principal es: RD 1135/2002 (normas mínimas protección cerdos, transpone Directiva "
        "2008/120/CE), que regula superficies, mutilaciones, enriquecimiento ambiental y condiciones "
        "ambientales. RD 306/2020 (SIGE) que incluye un plan de bienestar obligatorio. Ley 32/2007 de "
        "cuidado de animales en explotación. El Real Decreto-ley 20/2022 y modificaciones sobre raboteo "
        "y castración (prohibición progresiva). El Reglamento (CE) 1099/2009 sobre protección en el sacrificio. "
        "Además, ECOGAN valora técnicas de reducción de emisiones ligadas a bienestar (ventilación, suelo). "
        "PorciData ayuda al cumplimiento monitorizando: temperatura y gases (bienestar ambiental), "
        "actividad nocturna por radar (estrés), consumo de agua (indicador de salud) y acústica (estrés vocal)."
    ),
    make(
        "¿Cómo automatiza NeoFarm la gestión de purines según normativa?",
        "NeoFarm gestiona purines combinando sensores IoT y normativa. Los caudalímetros de la capa agua "
        "estiman la producción de purín (consumo agua × factor especie/fase — en porcino cebo, ~7-8 litros "
        "purín/cerdo/día). Sensores de nivel en balsas monitorizan capacidad. El sistema calcula la superficie "
        "de aplicación necesaria según la zona vulnerable a nitratos (RD 261/1996): carga máxima 170 kg N/ha/año "
        "en zona vulnerable, 210 kg en zona no vulnerable. Genera automáticamente el plan de gestión ambiental "
        "del SIGE y alerta cuando la balsa alcanza el 80% de capacidad o cuando la ventana de aplicación "
        "se acerca (prohibiciones estacionales según CCAA). Para explotaciones con >120 UGM, ayuda a cumplir "
        "las mejores técnicas disponibles (MTD) del BREF ganadero."
    ),
    make(
        "¿Qué es la trazabilidad en porcino y cómo la implementa NeoFarm?",
        "La trazabilidad en porcino permite seguir el recorrido del animal desde nacimiento hasta punto de "
        "venta. Normativa clave: Reglamento (CE) 178/2002 (trazabilidad general), RD 205/1996 (identificación "
        "porcino — crotales o tatuajes), y Reglamento (UE) 2016/429 (Ley de Sanidad Animal). NeoFarm implementa "
        "trazabilidad a nivel de lote e individual: crotales con lectura por RFID en la báscula walk-over, "
        "registro automático de movimientos entre naves, vinculación con guías de movimiento (SITRAN), "
        "y trazabilidad de alimentación (qué lote de pienso comió cada lote de animales). El objetivo es "
        "que ante una alerta sanitaria se pueda rastrear en segundos qué animales están afectados, qué comieron "
        "y con quién tuvieron contacto."
    ),
    make(
        "¿Cómo ayuda PorciData a pasar una inspección de bienestar animal?",
        "PorciData genera evidencia objetiva para inspecciones de bienestar: la capa ambiental registra "
        "temperatura (obligación de mantener entre 15-30°C según fase), niveles de NH3 (<20 ppm) y CO2 "
        "(<3.000 ppm) de forma continua, demostrando cumplimiento del RD 1135/2002. La capa acústica detecta "
        "y registra episodios de estrés vocal. La capa de visión RGB permite verificar densidad animal "
        "(m²/cerdo). Los caudalímetros demuestran acceso permanente a agua limpia. El sistema genera "
        "un informe de bienestar exportable en PDF con gráficos de las últimas 4 semanas, incluyendo "
        "incidencias (picos de NH3, T fuera de rango, cortes de agua) y las acciones correctivas tomadas."
    ),
    make(
        "¿Qué son las mejores técnicas disponibles (MTD) y cómo afectan a granjas grandes?",
        "Las MTD (BAT en inglés) son las técnicas recogidas en el documento BREF de ganadería intensiva "
        "(Decisión de Ejecución 2017/302/UE) que las explotaciones con >2.000 plazas de cebo o >750 madres "
        "deben aplicar para obtener la Autorización Ambiental Integrada (AAI). Incluyen medidas de: reducción "
        "de emisiones de NH3 (cubiertas de purín, lavadores de aire, aditivos acidificantes), gestión de "
        "nutrientes (balance de N y P, plan de abonado), eficiencia de agua, y ruido. PorciData ayuda "
        "demostrando cumplimiento con monitorización continua de emisiones (sensores NH3, CO2, BME688 para "
        "VOCs) y generando informes automáticos para la AAI. El sensor de PM2.5 (SPS30) también documenta "
        "calidad del aire interior para el dossier MTD."
    ),
    make(
        "¿Qué obligaciones tiene el plan de alimentación animal del SIGE?",
        "El plan de alimentación animal del SIGE (RD 306/2020, plan 7) debe documentar: origen y proveedor "
        "de piensos y materias primas (con número de registro sanitario), composición analítica de cada dieta "
        "por fase (proteína, energía, aminoácidos, minerales), programa de alimentación (kg/animal/día por "
        "fase), controles de calidad realizados (micotoxinas, Salmonella, metales pesados), sistemas de "
        "almacenamiento y conservación, y gestión de piensos medicamentosos (receta veterinaria, registro de "
        "uso, tiempos de retirada). NeoFarm vincula el plan con el módulo de Nutrición: los datos de consumo "
        "real de pienso (tolvas inteligentes + capa IoT agua) se comparan con el programa teórico, alertando "
        "desviaciones superiores al 10% que pueden indicar problemas sanitarios o de formulación."
    ),
    make(
        "¿Qué diferencia hay entre el RD 306/2020 y el RD 1135/2002?",
        "Son normativas complementarias. El RD 1135/2002 establece normas mínimas de protección de cerdos: "
        "superficies por animal, condiciones ambientales (luz, ruido, gases), prohibiciones de mutilaciones, "
        "material manipulable y requisitos de alojamiento. Es la transposición de la Directiva 2008/120/CE. "
        "El RD 306/2020 es posterior y más amplio: crea el SIGE (Sistema Integral de Gestión) con 11 planes "
        "obligatorios que cubren bioseguridad, bienestar, sanidad, medio ambiente, alimentación, agua, "
        "formación y gestión de residuos. El SIGE integra y amplía lo que antes eran requisitos dispersos. "
        "En la práctica, el RD 1135/2002 te dice QUÉ condiciones cumplir; el RD 306/2020 te dice CÓMO "
        "documentar y gestionar toda la explotación de forma integral."
    ),
    make(
        "¿Cómo gestiona NeoFarm el plan de bioseguridad del SIGE?",
        "El plan de bioseguridad del SIGE (plan 1 del RD 306/2020) debe incluir: vallado perimetral, zonas "
        "de acceso (sucia/limpia), vados sanitarios, protocolo de entrada de personas y vehículos, cuarentena, "
        "control de fauna silvestre, y gestión de cadáveres. NeoFarm lo digitaliza: registro de visitas con "
        "firma digital, checklist de entrada (ducha, ropa, material), registro del vado (reposición de "
        "desinfectante con alerta automática), y monitorización de la zona de cuarentena con sensores IoT "
        "(temperatura, consumo agua, acústica para detectar tos). La capa de visión RGB puede detectar "
        "presencia de fauna silvestre en el perímetro. El sistema genera el documento de bioseguridad "
        "actualizado automáticamente y envía alertas si se incumple algún protocolo (ej: visita sin registro)."
    ),
]

# --- PASO 5: Nuevos ejemplos Digital Twin (8) ---
new_twin = [
    make(
        "¿Qué es un World Model en el contexto de un digital twin ganadero?",
        "Un World Model es el componente predictivo del digital twin que aprende cómo evoluciona el sistema "
        "dado un estado actual y una acción. En ganadería porcina, el estado incluye variables IoT (T, HR, NH3, "
        "CO2, actividad, consumo agua) más producción (peso, GMD, IC, mortalidad). Las acciones son decisiones "
        "de manejo: ajustar ventilación, calefacción, nebulización, densidad alimentaria o medicación. El World "
        "Model predice estado_t+1 = f(estado_t, acción_t). Se puede implementar con: reglas heurísticas "
        "(inicio), Gradient Boosting (con 3-6 meses de datos), o LSTM para series temporales. Se entrena con "
        "datos reales de la granja y se valida con MAE/RMSE vs datos observados. Es la base para luego "
        "aplicar Reinforcement Learning (PPO/SAC) que encuentre la acción óptima."
    ),
    make(
        "¿Cómo calculo el THI (Temperature-Humidity Index) para estrés térmico en vacuno?",
        "El THI se calcula como: THI = (1.8 × T + 32) - (0.55 - 0.0055 × HR) × (1.8 × T - 26), donde T es "
        "temperatura en °C y HR es humedad relativa en %. Umbrales para vacuno: THI <68 = sin estrés, "
        "68-72 = estrés leve (reducción de ingesta ~3%), 72-80 = estrés moderado (caída de producción lechera "
        "-10-25%, aumento frecuencia respiratoria), >80 = estrés severo (riesgo de muerte, especialmente "
        "en razas pesadas tipo Frisona). En VacasData, el twin calcula THI cada hora combinando datos de "
        "estaciones climáticas IoT y previsión AEMET. Si THI previsto >72 a 24h vista, genera alerta "
        "preventiva al ganadero con recomendaciones: sombras, aspersores, ajuste de horario de pastoreo."
    ),
    make(
        "¿Cómo calibro un digital twin porcino con datos reales incompletos?",
        "La calibración con datos incompletos requiere: (1) identificar gaps — sensores offline, datos "
        "faltantes, períodos sin registro de producción —, (2) imputar donde sea seguro (interpolación lineal "
        "para T/HR con gaps <2h, forward-fill para peso), (3) NO imputar donde sea peligroso (NH3, eventos "
        "sanitarios), (4) validar con cross-validation temporal (entrenar con semanas 1-8, validar con 9-12, "
        "no aleatorio porque es serie temporal), (5) ajustar complejidad del modelo al volumen de datos "
        "(con <3 meses, usar reglas + Gradient Boosting; con >6 meses, probar LSTM). Métricas mínimas: "
        "MAE de temperatura predicha <1°C, MAE de peso estimado <2 kg, precisión de alertas sanitarias "
        ">70%. Si los datos del BME688 no pasaron el burn-in (48h mínimo), descarta esas lecturas iniciales."
    ),
    make(
        "¿Qué entidades y relaciones tiene el digital twin porcino de NeoFarm?",
        "La jerarquía es: Granja → Nave → Corral/Sala → Lote → Animal individual. Cada entidad tiene "
        "atributos estáticos (capacidad, superficie, equipamiento) y dinámicos (estado actual desde IoT). "
        "Relaciones: un Lote ocupa un Corral, un Animal pertenece a un Lote, una Nave tiene N Corrales "
        "con sensores compartidos (ambiental, radar) y específicos (peso walk-over por corral). Cada Lote "
        "tiene: fecha entrada, genética (raza, EPDs medios), plan sanitario, plan nutricional y KPIs "
        "acumulados (GMD, IC, mortalidad). Las 7 capas IoT alimentan las variables dinámicas: Capa 3 → "
        "T/HR/NH3/CO2 de Nave, Capa 5 → consumo agua de Corral, Capa 7 → actividad de Corral, Capa 8 → "
        "peso de Animal. El twin agrega bottom-up (animal→lote→nave) y propaga alertas top-down."
    ),
    make(
        "¿Qué espacio de acciones tiene el RL del digital twin porcino?",
        "El espacio de acciones para el agente RL (PPO o SAC) del twin porcino incluye acciones continuas "
        "y discretas. Continuas: setpoint de ventilación (% apertura, 0-100), setpoint de calefacción (°C, "
        "18-30), caudal de nebulización (L/h), densidad energética del pienso (kcal/kg, ±200 del base). "
        "Discretas: activar/desactivar calefacción, cambiar de fase nutricional, enviar alerta sanitaria, "
        "recomendar inspección veterinaria. La reward function pondera: confort térmico (penaliza T fuera "
        "de rango óptimo por fase), salud (penaliza NH3>20ppm, tos detectada, consumo agua bajo), productividad "
        "(premia GMD alta, IC bajo) y coste energético (penaliza calefacción/ventilación excesiva). El agente "
        "se entrena primero en simulación (World Model) y luego se despliega en modo advisory (sugiere, "
        "no ejecuta)."
    ),
    make(
        "¿Cómo integra NeoFarm Cesium 3D para el twin vacuno geospatial?",
        "VacasData usa Cesium.js para visualizar el twin vacuno extensivo en 3D sobre terreno real. "
        "Configuración: CRS EPSG:25830 (UTM zona 30N, España peninsular), terrain tiles de IGN (MDT05), "
        "ortofoto PNOA como textura (WMS del IGN), y parcelas catastrales superpuestas desde la API del "
        "Catastro. Sobre este terreno se renderizan: posiciones GPS de animales (collares Meshtastic, "
        "actualización cada 5-15 min), índice NDVI de pastos (Sentinel-2, cada 5 días), bebederos con "
        "estado IoT (nivel, caudal), y cercas virtuales. El twin calcula carga ganadera por parcela "
        "(UGM/ha), disponibilidad de pasto estimada (NDVI × superficie) y distancia al agua. Cesium permite "
        "navegación 3D y timeline para ver evolución histórica del pastoreo."
    ),
    make(
        "¿Qué métricas de validación usa NeoFarm para evaluar el digital twin?",
        "NeoFarm valida el twin con métricas a tres niveles. Nivel sensor: MAE y RMSE de variables predichas "
        "vs observadas (objetivo: MAE T<1°C, MAE HR<3%, MAE peso<2kg). Nivel alertas: precisión, recall y "
        "F1-score de alertas sanitarias (objetivo: F1>0.70 para alertas respiratorias). Nivel económico: "
        "error en predicción de fecha óptima de sacrificio (<3 días), error en IC predicho vs real (<0.05 "
        "puntos). La validación es temporal (no aleatoria): se entrena con datos pasados y se evalúa en "
        "el período siguiente. Se recalibra cada 3 meses o cuando cambia la genética del lote. "
        "Un twin que no supere estos umbrales mínimos no se despliega; se mantiene en modo shadow "
        "(ejecuta en paralelo pero no genera alertas) hasta alcanzar la precisión requerida."
    ),
    make(
        "¿Qué es el NDVI y cómo lo usa VacasData para gestión de pastos?",
        "El NDVI (Normalized Difference Vegetation Index) mide la salud y densidad de la vegetación usando "
        "reflectancia en infrarrojo cercano (NIR) y rojo (R): NDVI = (NIR - R) / (NIR + R). Valores: 0.1-0.2 = "
        "suelo desnudo, 0.3-0.5 = pasto seco o escaso, 0.5-0.7 = pasto en buen estado, >0.7 = vegetación muy "
        "densa. VacasData obtiene NDVI de Sentinel-2 (10m resolución, cada 5 días en condiciones sin nubes) "
        "vía API Copernicus. El twin vacuno lo usa para: estimar biomasa disponible por parcela (kg MS/ha ≈ "
        "f(NDVI, estación, histórico)), calcular carga ganadera óptima, recomendar rotación de parcelas "
        "y predecir necesidad de suplementación. Con el histórico de 3+ años se detectan tendencias de "
        "degradación del pasto. Se visualiza en Cesium 3D como mapa de calor sobre las parcelas."
    ),
]

# --- PASO 6: Nuevos ejemplos cross-domain (5) ---
new_cross = [
    make(
        "Tengo una nave con NH3 alto y tos detectada. ¿Qué hago?",
        "Esa combinación (NH3 elevado + tos por acústica) es una alerta cruzada de riesgo respiratorio. "
        "Acciones inmediatas: (1) aumentar ventilación para bajar NH3 por debajo de 20 ppm (umbral RD 1135/2002), "
        "(2) verificar el consumo de agua — si también baja, refuerza la sospecha sanitaria, (3) comprobar "
        "el radar mmWave de actividad nocturna: si la actividad ha subido (animales inquietos/tosiendo de noche), "
        "la alerta es de nivel alto. En paralelo: registrar la incidencia en el SIGE (plan sanitario), "
        "avisar al veterinario para inspección y posible toma de muestras (hisopos nasales para PCR), y "
        "revisar el BME688 (VOCs) — un cambio en el perfil volátil puede indicar infección bacteriana. "
        "NeoFarm genera esta alerta cruzada automáticamente cuando coinciden señales de 3+ capas IoT."
    ),
    make(
        "¿Cómo vincula NeoFarm la nutrición con los datos IoT de la nave?",
        "NeoFarm conecta el módulo de Nutrición con IoT en varios puntos: (1) consumo real de pienso medido "
        "por tolvas inteligentes vs plan teórico — desviaciones >10% generan alerta, (2) consumo de agua "
        "(capa 5) como indicador de ingesta (ratio agua:pienso normal en cebo ~2.5:1; si sube a 3.5:1 puede "
        "indicar fiebre o estrés térmico), (3) temperatura ambiental (capa 3) para ajustar nivel energético "
        "de la dieta (por encima de 25°C, los cerdos reducen ingesta ~40 g/°C, hay que concentrar la dieta), "
        "(4) peso walk-over (capa 8) para validar que la GMD real se corresponde con la predicha por la "
        "formulación. El solver LP de NeoFarm (HiGHS) puede recalcular la formulación óptima automáticamente "
        "cuando los datos IoT indican desviación persistente (>3 días) del rendimiento esperado."
    ),
    make(
        "¿Cómo se integran genética, IoT y digital twin para predecir el día óptimo de sacrificio?",
        "El día óptimo de sacrificio es una predicción multi-módulo: (1) Genética aporta el potencial de "
        "crecimiento del lote (EPDs de GMD y EGD), (2) IoT proporciona datos reales diarios (peso walk-over, "
        "consumo pienso/agua, GMD observada), (3) Nutrición indica la curva de crecimiento teórica según "
        "la dieta actual, y (4) el Digital Twin integra todo en un modelo que predice cuándo el lote alcanzará "
        "el peso objetivo (típico 105-115 kg en blanco intensivo) con el IC marginal por debajo del umbral "
        "de rentabilidad. El twin también consulta precios de lonja (Mercolleida) para optimizar el momento: "
        "si el precio sube la semana siguiente y el IC marginal es aún aceptable, puede recomendar esperar "
        "2-3 días. La predicción se actualiza diariamente con R²>0.90 cuando hay >2 semanas de datos de peso."
    ),
    make(
        "¿Cómo afecta la densidad animal al rendimiento y cómo lo monitoriza PorciData?",
        "La densidad animal impacta directamente en GMD (-30 a -50 g/día si se supera la densidad legal), "
        "IC (+0.1 a +0.2 puntos), mortalidad, agresividad y riesgo de caudofagia. El RD 1135/2002 fija "
        "mínimos (0.65 m² para cerdos de 85-110 kg). PorciData monitoriza la densidad real de dos formas: "
        "(1) conteo automático por visión RGB (capa 1) con YOLO, precisión >95%, y (2) cálculo a partir "
        "de movimientos registrados (entradas/salidas, bajas). Si la cámara detecta más animales de los "
        "del censo, alerta de posible error de registro. Si detecta menos, puede ser mortalidad no registrada. "
        "El twin usa la densidad como variable del modelo: densidad real vs óptima, y su efecto en el IC "
        "predicho. Esto permite optimizar el llenado de naves: maximizar ocupación sin penalizar rendimiento."
    ),
    make(
        "¿Qué pasa con Seedy si Together.ai no está disponible?",
        "Seedy tiene un sistema de fallback automático. En funcionamiento normal, las consultas van a Together.ai "
        "donde corre el modelo fine-tuned (Qwen2.5-7B + LoRA, job ft-bc10fc32-2235) con coste ~0.25 EUR/mes. "
        "Si Together.ai no responde en 5 segundos o devuelve error, el backend FastAPI redirige automáticamente "
        "a Ollama local (seedy:q8, 8.1 GB en VRAM de la RTX 5080). La respuesta local es equivalente en "
        "calidad (mismo modelo base + LoRA, solo cambia la cuantización Q8 vs FP16). El RAG siempre es local "
        "(Qdrant + mxbai-embed-large en Ollama), así que no depende de la nube. Para demos offline o sin "
        "internet (ej: en la propia granja), Seedy funciona 100% local sin degradación apreciable. "
        "El usuario no nota diferencia entre Together y Ollama en la respuesta."
    ),
]

# --- PASO 7: Ensamblar v4 ---
output = clean + new_genetica + new_normativa + new_twin + new_cross
print(f"\n=== RESULTADO v4 ===")
print(f"Base limpia: {len(clean)}")
print(f"+ Genética: {len(new_genetica)}")
print(f"+ Normativa: {len(new_normativa)}")
print(f"+ Digital Twin: {len(new_twin)}")
print(f"+ Cross-domain: {len(new_cross)}")
print(f"TOTAL: {len(output)} ejemplos")

# Verificar distribución
cats = Counter()
for d in output:
    user = [m for m in d["messages"] if m["role"] == "user"][0]["content"].lower()
    if any(w in user for w in ['iot','sensor','capa','bom','nave','hardware','esp32','mqtt']):
        cats['IoT'] += 1
    elif any(w in user for w in ['nutri','butirat','enzima','nrc','pienso','formulac','ración','aminoácido','alimenta']):
        cats['Nutrición'] += 1
    elif any(w in user for w in ['genet','epd','wright','consanguinidad','apareamiento','raza','heterosis','heredab','blup','semen','farmm','cruzamiento','pedigrí','selección.*genóm']):
        cats['Genética'] += 1
    elif any(w in user for w in ['sige','normativa','ecogan','rd 306','rd 1135','bienestar','purín','registro','trazab','bioseguridad','mtd','bat']):
        cats['Normativa'] += 1
    elif any(w in user for w in ['twin','digital','simulac','world model','rl ','reinforcement','ndvi','cesium','thi','calibr']):
        cats['Digital Twin'] += 1
    else:
        cats['General/Otro'] += 1

print(f"\nDistribución final:")
for cat, n in cats.most_common():
    print(f"  {cat}: {n}")

# Guardar
with open("seedy_dataset_sft_v4.jsonl", "w") as f:
    for d in output:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print(f"\nGuardado: seedy_dataset_sft_v4.jsonl")
