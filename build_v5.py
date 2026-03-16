#!/usr/bin/env python3
"""
Genera seedy_dataset_sft_v5.jsonl a partir del v4:
1. Carga v4 (187 ejemplos, porcino + vacuno)
2. Añade ~38 ejemplos nuevos:
   - 7  Avicultura: definiciones (capón, pularda, técnica, categorías)
   - 8  Avicultura: catálogo de razas reales (Bresse, Sulmtaler, Dorking…)
   - 8  Avicultura: cruces F0→F5, programa genético, evaluación fenotípica
   - 10 Anti-alucinación: respuestas honestas "no tengo ese dato"
   - 5  Cross-domain avícola + IoT/NeoFarm
3. Total esperado: ~225 ejemplos
"""
import json

# ──────────────────────────────────────────────────────────────────────
# SYSTEM PROMPT  (v5 — añade avícola + anti-alucinación)
# ──────────────────────────────────────────────────────────────────────
SYSTEM = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData), costes por nave, nutrición porcina, "
    "genética aplicada (porcino, vacuno y avícola), normativa SIGE, Digital Twins productivos "
    "y producción avícola de calidad (capones, pulardas, razas rústicas).\n\n"
    "Responde siempre en español, en prosa natural y profesional.\n"
    "No uses secciones tipo Notes, References o Explanation.\n"
    "No repitas la pregunta.\n"
    "No inventes cifras, normativa ni parámetros técnicos.\n"
    "Si no tienes información fiable sobre un tema, dilo claramente en lugar de inventar.\n"
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

# ──────────────────────────────────────────────────────────────────────
# PASO 1: Cargar v4 como base y actualizar system prompts
# ──────────────────────────────────────────────────────────────────────
with open("seedy_dataset_sft_v4.jsonl") as f:
    base = [json.loads(l) for l in f]

print(f"v4 base cargada: {len(base)} ejemplos")

# Actualizar system prompt en todos los ejemplos base
for d in base:
    for m in d["messages"]:
        if m["role"] == "system":
            m["content"] = SYSTEM

# ──────────────────────────────────────────────────────────────────────
# PASO 2: Nuevos ejemplos — Avicultura definiciones (7)
# ──────────────────────────────────────────────────────────────────────
new_avicultura_defs = [
    make(
        "¿Qué es un capón?",
        "Un capón es un gallo castrado quirúrgicamente antes de alcanzar la madurez sexual, "
        "normalmente entre las 8 y 12 semanas de vida. La castración elimina la producción de "
        "testosterona, lo que provoca varios cambios fisiológicos: el animal deja de desarrollar "
        "cresta y espolones, pierde agresividad territorial y, sobre todo, redistribuye el "
        "metabolismo hacia la acumulación de grasa intramuscular e intracavitaria. Esto produce "
        "una carne excepcionalmente tierna, jugosa y con un veteado de grasa infiltrada que le "
        "da un sabor muy superior al del pollo convencional. El capón se engorda durante un "
        "periodo largo (5-8 meses, frente a los 42 días del broiler industrial) con alimentación "
        "basada en cereales, lácteos y pastos. Es un producto gourmet con tradiciones centenarias "
        "en España (Capón de Villalba, Capón del Prat), Francia (Chapon de Bresse) e Italia. "
        "Un capón bien acabado pesa entre 3 y 5 kg en canal y se comercializa típicamente en "
        "Navidad, alcanzando precios de 15-30 EUR/kg según origen y certificación."
    ),
    make(
        "¿Qué es una pularda?",
        "Una pularda es una gallina joven que ha sido sometida a un régimen de engorde especial "
        "sin castración quirúrgica, aunque algunas tradiciones incluyen ovariectomía. A diferencia "
        "del capón (gallo castrado), la pularda es siempre hembra. Se seleccionan pollitas de razas "
        "pesadas o semipesadas (Bresse, Coucou de Malines, Sussex) a las 8-10 semanas y se las "
        "somete a un programa de engorde controlado: confinamiento parcial con luz tenue, "
        "alimentación rica en cereales (maíz, trigo) y lácteos (leche en polvo o suero), durante "
        "un mínimo de 5-7 meses. El resultado es un ave de 2.5 a 3.5 kg en canal con carne muy "
        "tierna y jugosa, con buena infiltración grasa pero perfil más delicado que el capón. "
        "La pularda tiene una tradición fuerte en la gastronomía francesa (Poularde de Bresse, "
        "única ave con AOC/AOP) y se consume como plato festivo de alta cocina. "
        "No debe confundirse con un pollo grande ni con una gallina de desvieje."
    ),
    make(
        "¿Cómo se realiza la castración de un gallo para obtener un capón?",
        "La caponización es una cirugía menor que se realiza entre las 6 y 12 semanas de vida del "
        "pollo, normalmente por la técnica de incisión intercostal. El procedimiento requiere:\n\n"
        "1. Ayuno previo de 12-24 horas para vaciar las vísceras y mejorar la visibilidad.\n"
        "2. Sujeción del ave sobre un soporte inclinado, con las alas extendidas para exponer "
        "el costado izquierdo (los dos testículos se extraen por el mismo lado o se repite en "
        "ambos costados según la técnica).\n"
        "3. Incisión de unos 2 cm entre las dos últimas costillas, cortando piel, músculo intercostal "
        "y membrana peritoneal.\n"
        "4. Separación del saco aéreo abdominal y localización del testículo, adherido dorsalmente "
        "junto al riñón, cerca de la aorta.\n"
        "5. Extracción del testículo con cauterio o pinza de torsión (nunca tirón directo) para "
        "evitar hemorragia de la arteria espermática.\n"
        "6. Repetición en el otro testículo (o por el mismo lado si la técnica lo permite).\n"
        "7. Cierre de la incisión con un punto de sutura o grapas quirúrgicas.\n\n"
        "La mortalidad en manos experimentadas es inferior al 5%. El riesgo principal es la "
        "hemorragia por rotura de vasos cercanos a la aorta. Tras la castración, el gallo pierde "
        "comportamiento sexual y territorial en 2-3 semanas y comienza la fase de engorde."
    ),
    make(
        "¿Se pueden cruzar capones con pulardas para obtener descendencia?",
        "No, es absolutamente imposible. Un capón es un gallo castrado (sin testículos) y por tanto "
        "estéril: no produce espermatozoides ni puede fecundar huevos. Una pularda, aunque es hembra, "
        "está sometida a un régimen de engorde que inhibe la puesta, y si fue ovariectomizada también "
        "es estéril. El objetivo del capón y la pularda es exclusivamente la producción de carne "
        "gourmet, no la reproducción.\n\n"
        "Para obtener pollos destinados a caponizar, necesitas un programa de cría con animales "
        "reproductores (gallos enteros y gallinas en puesta activa). El esquema habitual es:\n\n"
        "- Línea padre: gallos de raza pesada (Bresse, Dorking, Coucou de Malines) seleccionados "
        "por crecimiento y conformación.\n"
        "- Línea madre: gallinas de raza rústica con buena puesta y rusticidad (Castellana, "
        "Penedesenca, Sussex).\n"
        "- Los machos F1 se caponizán a las 8-12 semanas → capones.\n"
        "- Las hembras F1 se destinan a pulardas o a reposición de reproductoras.\n\n"
        "En ningún caso se utilizan capones o pulardas como reproductores."
    ),
    make(
        "¿Cuál es la diferencia entre pollo de engorde, capón, pularda y gallina campera?",
        "Son categorías muy distintas de producción avícola:\n\n"
        "• Pollo de engorde (broiler): línea genética industrial (Ross 308, Cobb 500), sacrificio "
        "a los 35-42 días con ~2.5 kg peso vivo, crecimiento acelerado, criado en naves intensivas. "
        "Carne bland, poca grasa intramuscular. Precio: 3-5 EUR/kg.\n\n"
        "• Capón: gallo castrado de raza pesada o cruce rústico, sacrificio a 5-8 meses con 3-5 kg "
        "canal. Carne con grasa infiltrada excepcional, sabor intenso. Producción estacional "
        "(sacrificio en Navidad). Precio: 15-30 EUR/kg.\n\n"
        "• Pularda: gallina joven engordada con programa especial, sacrificio a 5-7 meses con "
        "2.5-3.5 kg canal. Carne tierna y delicada, menos grasa infiltrada que el capón. "
        "También estacional. Precio: 12-25 EUR/kg.\n\n"
        "• Gallina/pollo campero: ave criada con acceso a exterior (mínimo 2 m²/ave según normativa EU), "
        "raza semipesada o rústica, sacrificio a 56-81 días mínimo según Label. Carne más firme y con "
        "más sabor que el broiler, pero sin la infiltración grasa del capón. Precio: 6-10 EUR/kg.\n\n"
        "Para producción gourmet en Segovia, lo más interesante son capones y pulardas de razas "
        "rústicas con engorde largo en régimen semiextensivo."
    ),
    make(
        "¿Cuándo se producen y comercializan los capones?",
        "La producción de capones es marcadamente estacional y está ligada al calendario festivo:\n\n"
        "• Nacimientos: los pollitos destinados a capón nacen entre mayo y julio.\n"
        "• Caponización: se realiza entre julio y septiembre (8-12 semanas de vida).\n"
        "• Engorde: de septiembre a diciembre, con alimentación progresiva de cereales y lácteos.\n"
        "• Acabado/cebado final: las 3-4 últimas semanas antes del sacrificio, en confinamiento "
        "con luz tenue y dieta concentrada en maíz y leche, para maximizar infiltración grasa.\n"
        "• Sacrificio: primera quincena de diciembre.\n"
        "• Comercialización: segunda quincena de diciembre (Navidad y fin de año).\n\n"
        "Este ciclo estacional es el motivo por el que el capón es un producto escaso y caro: "
        "solo hay una ventana de producción al año. Algunas explotaciones hacen dos lotes "
        "(el segundo para Semana Santa, naciendo en octubre-noviembre), pero es menos habitual "
        "y el resultado suele ser inferior porque el engorde coincide con meses fríos.\n\n"
        "En España, las principales zonas de producción son Galicia (Capón de Villalba, IGP), "
        "Cataluña (Capón del Prat), Navarra y Castilla y León."
    ),
    make(
        "¿Qué alimentación lleva un capón durante el engorde?",
        "La alimentación del capón es la clave de su calidad final y sigue un programa en fases:\n\n"
        "1. Fase de cría (0-8 semanas, pre-castración): pienso starter estándar para pollitos, "
        "20-22% proteína, con libre acceso a agua. En esta fase es un pollo normal.\n\n"
        "2. Fase de recría (8-16 semanas, post-castración): transición a una dieta más energética. "
        "Mezcla de cereales molidos (trigo, cebada, avena) complementada con verduras y acceso a "
        "pasto si el sistema es semiextensivo. Proteína ~16-18%.\n\n"
        "3. Fase de engorde (16 semanas hasta 3-4 semanas antes de sacrificio): dieta basada en "
        "cereales enteros o triturados gruesos (maíz principalmente, que aporta el color amarillo "
        "a la grasa), con complemento de leguminosas y acceso a pasto.\n\n"
        "4. Fase de acabado o cebado (últimas 3-4 semanas): confinamiento en jaula individual o "
        "cajón oscuro. Dieta exclusiva de harina de maíz cocida con leche entera o suero, en forma "
        "de papilla o pellets húmedos. Proporción aproximada: 70% maíz, 30% lácteos. Se administra "
        "2-3 veces al día ad libitum. Esta fase es la que produce la infiltración de grasa "
        "intramuscular característica.\n\n"
        "Un capón bien cebado consume unos 15-20 kg de alimento durante todo su ciclo. "
        "El coste de alimentación representa el 40-50% del coste total de producción."
    ),
]

# ──────────────────────────────────────────────────────────────────────
# PASO 3: Nuevos ejemplos — Catálogo de razas avícolas reales (8)
# ──────────────────────────────────────────────────────────────────────
new_avicultura_razas = [
    make(
        "¿Qué es la raza de gallina Bresse y por qué es especial para capones?",
        "La Bresse (o Poulet de Bresse) es una raza francesa originaria de la región de Bresse "
        "(Ain, Saône-et-Loire, Jura), y es la única ave del mundo con Denominación de Origen "
        "Protegida (AOP). Se reconoce por su plumaje blanco, patas azul-acero y cresta roja "
        "(los colores de la bandera francesa).\n\n"
        "Características productivas:\n"
        "• Peso adulto: gallos 3.0-3.5 kg, gallinas 2.0-2.5 kg.\n"
        "• Puesta: 160-200 huevos/año (moderada), huevos de cáscara blanca cremosa.\n"
        "• Crecimiento: moderado-lento, necesita 4-5 meses mínimo para sacrificio.\n"
        "• Conformación: pechuga amplia, muslos potentes, piel fina.\n"
        "• Calidad de carne: excepcional. La Bresse tiene una predisposición genética a infiltrar "
        "grasa intramuscular superior a cualquier otra raza, especialmente tras caponización.\n\n"
        "Para capones gourmet es la referencia mundial. El Chapon de Bresse se sacrifica con un "
        "mínimo de 8 meses y alcanza 3-4.5 kg canal. En las Glorieuses de Bresse (concurso anual "
        "desde 1862) los mejores ejemplares superan los 100 EUR/kg.\n\n"
        "En España se pueden adquirir reproductores Bresse de buena línea a través de criadores "
        "especializados franceses o de bancos de germoplasma avícola. El INIA-CSIC también "
        "conserva material genético de razas complementarias."
    ),
    make(
        "¿Qué es la Sulmtaler y de dónde viene?",
        "La Sulmtaler es una raza de gallina austriaca originaria del valle del Sulm, en Estiria "
        "(Steiermark, Austria). Es una de las razas centroeuropeas más valoradas para producción "
        "de carne de calidad y tiene una historia documentada desde el siglo XIV.\n\n"
        "Características:\n"
        "• Peso adulto: gallos 3.0-3.5 kg, gallinas 2.5-3.0 kg.\n"
        "• Plumaje: dorado-trigo con cola negra (variedad principal), existe también variedad blanca.\n"
        "• Cresta: pequeña tipo rosa (wickelkamm), lo que le da buena resistencia al frío.\n"
        "• Puesta: 150-180 huevos/año, huevo color crema.\n"
        "• Crecimiento: lento, conformación excelente con pechuga ancha.\n"
        "• Temperamento: dócil, buen pastoreo, adaptada a climas fríos.\n\n"
        "La Sulmtaler es muy interesante para programas de capones porque combina buen tamaño "
        "corporal (necesario para un capón rentable) con una calidad de carne e infiltración grasa "
        "que se acercan a la Bresse. Es más rústica y resistente al frío que la Bresse, lo que "
        "la hace más adecuada para sistemas extensivos en climas continentales "
        "como Castilla y León.\n\n"
        "No debe confundirse con la «Sultana de Tolosa» u otros nombres inventados: "
        "su único nombre correcto es Sulmtaler y su origen es Austria, no Francia ni España."
    ),
    make(
        "¿Qué es la Coucou de Malines y para qué se usa?",
        "La Coucou de Malines (también Mechelse Koekoek en flamenco) es una raza belga "
        "originaria de Malinas (Mechelen), considerada la «raza de mesa» por excelencia en "
        "Bélgica y Países Bajos. Es una de las razas más pesadas de Europa.\n\n"
        "Características:\n"
        "• Peso adulto: gallos 4.0-5.0 kg, gallinas 3.5-4.0 kg (de las más grandes).\n"
        "• Plumaje: barrado gris-blanco («coucou»), patrón autosexable (machos más claros).\n"
        "• Puesta: 140-160 huevos/año, huevo color crema.\n"
        "• Crecimiento: moderado-lento, pero alcanza pesos muy elevados.\n"
        "• Conformación: pechuga enorme, muslos muy anchos, hueso fino.\n\n"
        "Para producción de capones es una de las mejores opciones por su tamaño excepcional: "
        "un capón Coucou puede alcanzar 5-6 kg canal. La carne es tierna con buena infiltración, "
        "aunque algo inferior en finura a la Bresse. Es la raza ideal para la línea paterna "
        "en cruces destinados a capón, aportando tamaño y conformación. El cruce clásico belga "
        "para capones de alta gama es Coucou de Malines × Bresse."
    ),
    make(
        "¿Qué razas de gallinas autóctonas españolas son útiles para capones?",
        "España tiene varias razas autóctonas que pueden participar en programas de capones, "
        "principalmente como línea materna por su rusticidad y adaptación local:\n\n"
        "• Castellana Negra: originaria de Castilla. Plumaje negro brillante, cresta grande sencilla. "
        "Gallina de ~2.2 kg, excelente ponedora (220-240 huevos/año, blancos). Magra para capón puro, "
        "pero aporta vigor híbrido y puesta alta cuando se usa como madre cruzada con razas pesadas.\n\n"
        "• Penedesenca: originaria del Penedès (Cataluña). Famosa por sus huevos de cáscara marrón "
        "muy oscuro (casi chocolate). Peso ~2.3 kg, 160-200 huevos/año. Temperamento activo, "
        "excelente forrajeadora. Muy buena como línea materna en cruces para capón.\n\n"
        "• Empordanesa: de Girona. Similar a la Penedesenca pero más ligera. Interesante para "
        "cruces que busquen rusticidad extrema.\n\n"
        "• Euskal Oiloa: País Vasco. Raza de doble propósito, ~2.5 kg, 180 huevos/año. "
        "Buena rusticidad y adaptación a climas húmedos.\n\n"
        "Ninguna de estas razas tiene suficiente tamaño por sí sola para producir capones "
        "rentables (necesitas >3 kg canal), pero todas son líneas maternas excelentes en cruces "
        "F1 con gallos Bresse, Coucou de Malines o Dorking."
    ),
    make(
        "¿Qué es la raza Dorking y por qué es relevante para capones?",
        "La Dorking es una raza británica muy antigua, posiblemente introducida en Inglaterra por "
        "los romanos. Es notable por tener cinco dedos en cada pata (la mayoría de razas tienen "
        "cuatro), lo que la hace genéticamente única.\n\n"
        "Características:\n"
        "• Peso adulto: gallos 3.5-4.5 kg, gallinas 2.5-3.5 kg.\n"
        "• Variedades: plateada-gris, oscura, roja, blanca y cuco.\n"
        "• Puesta: 140-170 huevos/año, huevos blancos o crema.\n"
        "• Crecimiento: lento.\n"
        "• Conformación: cuerpo largo y profundo, pechuga muy desarrollada, quilla larga.\n"
        "• Calidad de carne: excelente, considerada una de las mejores razas de mesa.\n"
        "• Temperamento: muy dócil, ideal para confinamiento en fase de cebado.\n\n"
        "Para capones, la Dorking es muy interesante como línea paterna alternativa a la Coucou "
        "de Malines: aporta pechuga excepcional y calidad de carne, aunque algo menos de tamaño "
        "total. Los capones Dorking puros eran muy apreciados en la Inglaterra victoriana. "
        "Hoy es una raza en peligro (watch list de la Rare Breeds Survival Trust), pero hay "
        "criadores especializados en Reino Unido y Francia que venden huevos fértiles."
    ),
    make(
        "He leído que existe una raza de gallina llamada «La Mancha». ¿Es cierta?",
        "No. No existe ninguna raza de gallina reconocida como «La Mancha» en ningún catálogo "
        "oficial de razas avícolas (ni FAO, ni INIA, ni el British Poultry Standard, ni la "
        "APA americana). La Mancha es una denominación geográfica (Castilla-La Mancha, España) "
        "que a veces se confunde con la «LaMancha», que es una raza de CABRA californiana "
        "conocida por sus orejas muy cortas (American LaMancha).\n\n"
        "Las razas autóctonas españolas reconocidas son: Castellana Negra, Penedesenca, "
        "Empordanesa, Euskal Oiloa, Prat, Menorquina, Ibicenca, Andaluza Azul, Combatiente "
        "Español y alguna más según catálogos regionales. Si buscas una raza manchega para "
        "producción avícola, la más próxima geográficamente es la Castellana Negra, originaria "
        "de ambas Castillas."
    ),
    make(
        "¿La Andaluza Negra y la Retinta son razas de gallinas?",
        "No. Hay una confusión de especies:\n\n"
        "• Retinta: es una raza de VACUNO (Bos taurus) originaria del suroeste de España "
        "(Extremadura, Andalucía). Vaca rústica de capa retinta (rojiza), usada en extensivo "
        "para cría de terneros que luego se cruzan con razas cárnicas como Limusina o Charolesa. "
        "No tiene nada que ver con avicultura.\n\n"
        "• Andaluza Negra: no existe como raza reconocida ni en bovino ni en avícola con esa "
        "denominación exacta. En bovino existe la «Negra Andaluza» o «Negra de las Campiñas», "
        "una agrupación racial bovina en peligro de extinción. En avícola, la raza andaluza se "
        "llama «Andaluza Azul» (Blue Andalusian), y su plumaje es azul pizarra (no negro), "
        "resultado de un gen de dilución del color.\n\n"
        "Es importante no confundir especies: la genética bovina, porcina y avícola son campos "
        "completamente separados, con razas, parámetros reproductivos y sistemas de producción "
        "distintos. Las razas bovinas no pueden usarse en programas avícolas y viceversa."
    ),
    make(
        "¿Qué raza se llama Barbados Blackbelly?",
        "La Barbados Blackbelly es una raza de OVINO (Ovis aries), no de aves. Es una oveja "
        "de pelo (sin lana) originaria de la isla de Barbados, en el Caribe. Se caracteriza por "
        "su capa marrón rojiza con vientre negro, ausencia de lana, cola fina y alta resistencia "
        "parasitaria. Es una raza prolífica (partos gemelares frecuentes) adaptada a climas "
        "tropicales.\n\n"
        "La confusión puede surgir porque el nombre «Blackbelly» (barriga negra) podría evocar "
        "un patrón de plumaje aviar, pero es exclusivamente ovina. En avicultura no existe "
        "ninguna raza con ese nombre.\n\n"
        "Del mismo modo, la «Cotswold» es una raza de oveja inglesa de lana larga, no de gallina. "
        "Si estás buscando razas de gallinas para un programa de capones o producción avícola, "
        "las razas relevantes son Bresse, Coucou de Malines, Sulmtaler, Dorking, Castellana Negra, "
        "Penedesenca, etc. — todas ellas aves reales con estándares bien documentados."
    ),
]

# ──────────────────────────────────────────────────────────────────────
# PASO 4: Nuevos ejemplos — Cruces avícolas F0→F5 y programas genéticos (8)
# ──────────────────────────────────────────────────────────────────────
new_avicultura_cruces = [
    make(
        "¿Cómo funciona la lógica de cruces F0→F5 en avicultura para capones?",
        "La lógica de cruces generacionales en avicultura para capones sigue los mismos principios "
        "genéticos que en otras especies, pero adaptados al ciclo reproductivo de las aves:\n\n"
        "F0 (Generación fundadora): razas puras seleccionadas. Estableces tus líneas parentales:\n"
        "  - Línea paterna: raza pesada de alta conformación (Bresse, Coucou de Malines, Dorking)\n"
        "  - Línea materna: raza rústica con buena puesta y adaptación local (Castellana, Penedesenca)\n\n"
        "F1 (Primera generación de cruce): 100% vigor híbrido (heterosis). Los pollos F1 muestran "
        "superioridad sobre ambos padres en crecimiento, viabilidad y uniformidad. Es la generación "
        "IDEAL para caponizar machos y producir pulardas con hembras.\n\n"
        "F2 (Segunda generación, F1 × F1): se pierde el 50% de la heterosis y aparece segregación "
        "genética — los individuos son mucho más variables en tamaño, conformación y calidad de "
        "carne. NO recomendable para producción de capones uniformes.\n\n"
        "F3-F5 (Generaciones avanzadas): solo tienen sentido si estás creando una nueva línea "
        "sintética con selección dirigida. Requiere poblaciones grandes (>200 reproductores por "
        "generación) y evaluación fenotípica rigurosa.\n\n"
        "Recomendación práctica: para producción de capones gourmet, quédate en F1 y mantén "
        "líneas parentales puras separadas. Es más simple, más uniforme y maximiza la heterosis."
    ),
    make(
        "¿Qué cruces F1 recomiendas para producir capones gourmet en la zona de Segovia?",
        "Para la zona de Segovia, que tiene un clima continental seco con inviernos fríos "
        "(-5 a 5 °C en invierno) y veranos cálidos, te recomiendo estos cruces F1:\n\n"
        "1. ♂ Coucou de Malines × ♀ Castellana Negra:\n"
        "   Mejor opción global. El gallo Coucou aporta tamaño excepcional (4-5 kg) y conformación "
        "   cárnica. La gallina Castellana aporta rusticidad, adaptación al clima castellano y alta "
        "   tasa de puesta (más huevos fértiles = más pollos para caponizar). El F1 macho caponizado "
        "   debería alcanzar 3.5-4.5 kg canal a los 7 meses. Además, el cruce es autosexable "
        "   (machos más claros, hembras más oscuras) lo que facilita la separación temprana.\n\n"
        "2. ♂ Bresse × ♀ Penedesenca:\n"
        "   Orientado a calidad premium. El gallo Bresse aporta la mejor infiltración grasa "
        "   genética para capón. La Penedesenca aporta vigor, rusticidad y excelente capacidad "
        "   forrajera. El F1 macho caponizado será algo más ligero (3.0-3.8 kg canal) pero con "
        "   calidad de carne superior. Inconveniente: los reproductores Bresse son más caros.\n\n"
        "3. ♂ Dorking × ♀ Euskal Oiloa:\n"
        "   Opción para diferenciación. El Dorking aporta pechuga excepcional y carne premium. "
        "   La Euskal Oiloa es muy rústica y buena madre. El F1 dará capones de 3.0-3.5 kg canal "
        "   con calidad de pechuga sobresaliente. Inconveniente: el Dorking es difícil de conseguir.\n\n"
        "En los tres casos, los machos F1 se caponizán a las 8-12 semanas y las hembras F1 se "
        "destinan a pularda o se seleccionan las mejores como reproductoras de reposición (nunca "
        "entre ellas: siempre con gallos puros de la línea paterna para mantener F1)."
    ),
    make(
        "¿Qué problemas tiene usar F2 (F1 × F1) para capones?",
        "Usar una generación F2 (cruzar F1 entre sí) para producir capones tiene varios problemas "
        "importantes:\n\n"
        "1. Pérdida de heterosis: la F2 retiene solo ~50% del vigor híbrido de la F1. Esto se "
        "traduce en menor velocidad de crecimiento, peor conversión alimenticia y mayor mortalidad.\n\n"
        "2. Segregación genética: en F1, todos los individuos tienen la misma composición genética "
        "(50% padre + 50% madre). En F2, los genes se recombinan y cada individuo es diferente. "
        "Obtendrás pollos de 2 kg al lado de pollos de 4 kg, con conformaciones muy distintas. "
        "Esa variabilidad es un problema comercial: no puedes vender lotes uniformes.\n\n"
        "3. Segregación de calidad de carne: la infiltración grasa, la textura del músculo y el "
        "color de la piel (que depende de genes de pigmentación como el gen «Id» de xantofilas) "
        "también segregan. Algunos capones F2 tendrán carne excelente y otros mediocre.\n\n"
        "4. Reaparición de defectos recesivos: defectos genéticos que estaban ocultos en F1 "
        "(porque eran heterocigotos) pueden manifestarse en F2 con una frecuencia teórica de 1/4.\n\n"
        "La regla práctica en avicultura de calidad es: produce siempre en F1, mantén tus líneas "
        "parentales puras y compra o produce gallos puros para cada generación de producción."
    ),
    make(
        "¿Cómo diseño un programa de cría F0→F3 para capones en una explotación pequeña?",
        "Para una explotación pequeña (producción de 50-200 capones/año), el diseño práctico es:\n\n"
        "NÚCLEO F0 — Líneas puras (permanente):\n"
        "• Línea paterna: 2-3 gallos + 10-15 gallinas de la raza pesada elegida (ej. Coucou de "
        "Malines o Bresse). Objetivo: producir gallos puros para cruzar.\n"
        "• Línea materna: 1-2 gallos + 8-12 gallinas de la raza rústica (ej. Castellana Negra). "
        "Objetivo: producir gallinas puras para cruzar.\n"
        "• Gestionar consanguinidad: rotar gallos cada 2 generaciones comprando de otros criadores.\n\n"
        "PRODUCCIÓN F1 — Cruce terminal (cada año):\n"
        "• Apareamiento: gallos puros de línea paterna × gallinas puras de línea materna.\n"
        "• Incubación: recoger huevos fértiles durante 4-6 semanas (primavera), incubar 21 días.\n"
        "• Sexado a las 4-6 semanas (o al nacimiento si el cruce es autosexable).\n"
        "• Machos F1 → caponización a 8-12 semanas → engorde → sacrificio en diciembre.\n"
        "• Hembras F1 → pulardas (engorde 5-7 meses) o venta como pollitas camperas.\n\n"
        "NO necesitas F2 ni F3 en producción. Si algún día quieres crear tu propia línea sintética "
        "(F2, F3…), necesitarás al menos 100-200 reproductores por generación y un programa de "
        "evaluación fenotípica, lo cual solo tiene sentido a escala industrial.\n\n"
        "Consejo: invierte en buenos reproductores F0, no en complicar el esquema de cruces."
    ),
    make(
        "¿Qué criterios fenotípicos evalúo para seleccionar reproductores de capones?",
        "La selección de reproductores para un programa de capones debe evaluar estos criterios "
        "fenotípicos, priorizados por importancia:\n\n"
        "En GALLOS de línea paterna (aportan tamaño y conformación):\n"
        "1. Peso vivo a las 20 semanas: seleccionar los que superen la media de la raza en >10%.\n"
        "2. Conformación corporal: pechuga ancha y profunda, muslos gruesos, quilla larga.\n"
        "3. Ancho de pechuga (medido con calibre): correlaciona directamente con rendimiento canal.\n"
        "4. Longitud de quilla (esternón): indicador de capacidad de deposición muscular.\n"
        "5. Ausencia de defectos: dedos torcidos, quilla desviada, cresta caída (indica pobre vigor).\n"
        "6. Temperamento: seleccionar gallos activos pero no excesivamente agresivos.\n\n"
        "En GALLINAS de línea materna (aportan rusticidad y fertilidad):\n"
        "1. Tasa de puesta a 40 semanas: seleccionar las que superen 60% (>4 huevos/semana).\n"
        "2. Fertilidad de huevos: si incubas, medir tasa de eclosión por gallina (>80% deseable).\n"
        "3. Peso del huevo: >55 g para buena viabilidad del pollito.\n"
        "4. Rusticidad: supervivencia sin medicación durante la recría.\n"
        "5. Capacidad forrajera: las gallinas que pastorean activamente producen pollos más activos.\n"
        "6. Instinto maternal: relevante si usas incubación natural.\n\n"
        "Registra todo en fichas individuales (o en NeoFarm/FarmMatch si lo tienes disponible) "
        "y selecciona el 30-40% superior como reproductores."
    ),
    make(
        "¿Tiene sentido hacer triple cruce en avicultura para capones? Por ejemplo A × (B × C).",
        "Sí, el triple cruce (o cruce a tres vías) es una estrategia válida en avicultura para "
        "capones, aunque tiene ventajas e inconvenientes respecto al cruce simple F1:\n\n"
        "ESQUEMA: ♂ Raza A × ♀ (Raza B × Raza C)\n"
        "Ejemplo: ♂ Coucou de Malines × ♀ (Bresse × Castellana Negra)\n\n"
        "Ventajas:\n"
        "• Mayor heterosis total: el triple cruce retiene ~100% de heterosis individual (como F1) "
        "más heterosis materna de la madre cruzada.\n"
        "• Las madres cruzadas (B×C) son mejores productoras que las puras: más huevos fértiles, "
        "mayor viabilidad embrionaria, mejores madres.\n"
        "• Combinas tres pools genéticos: tamaño del Coucou + calidad de carne de la Bresse + "
        "rusticidad de la Castellana. Resultado potencialmente superior a cualquier F1 simple.\n\n"
        "Inconvenientes:\n"
        "• Más complejidad logística: necesitas mantener tres líneas puras (A, B, C) y producir "
        "las madres cruzadas (B×C) como paso intermedio antes de la producción final.\n"
        "• Más animales totales en el núcleo: al menos 3 lotes de reproductores puros.\n"
        "• Menos predecible: la composición genética del triple cruce (50% A + 25% B + 25% C) "
        "puede dar resultados variables si las razas B y C no combinan bien.\n\n"
        "Para explotaciones pequeñas (<200 capones/año), quédate con F1 simple: es más fácil de "
        "gestionar y los resultados son muy buenos. El triple cruce merece la pena a partir de "
        "500+ capones/año cuando puedes justificar el núcleo de reproductores ampliado."
    ),
    make(
        "¿Cómo evito la consanguinidad en un programa de capones con pocos reproductores?",
        "La consanguinidad es un riesgo real en explotaciones pequeñas avícolas. Aquí tienes "
        "estrategias prácticas:\n\n"
        "1. Rotación de gallos: el factor más crítico. Compra o intercambia gallos nuevos (de la "
        "misma raza pura) de otros criadores cada 2 años máximo. 2-3 gallos activos al mismo "
        "tiempo, sin parentesco entre ellos.\n\n"
        "2. Identificación individual: anilla a todos los reproductores con anillas numeradas "
        "en la pata. Lleva un registro de qué gallo cubre qué gallinas (sepáralos en lotes "
        "de apareamiento de 1 gallo + 5-8 gallinas durante 2-3 semanas).\n\n"
        "3. Evitar padre-hija y hermano-hermana: NUNCA usar pollitos nacidos en tu explotación "
        "como reproductores sin verificar que no comparten padre. Si usas 2 gallos alternos, "
        "solo las hijas del gallo A pueden emparejarse con el gallo B y viceversa.\n\n"
        "4. Red de criadores: establece una red de intercambio con 2-3 criadores de la misma raza. "
        "Cada año, intercambias huevos fértiles o pollitos de recría. Esto es equivalente a "
        "migración genética natural.\n\n"
        "5. Tamaño mínimo efectivo: intenta mantener al menos 3 gallos y 15 gallinas activos "
        "por raza pura. Eso da un tamaño efectivo de población Ne ≈ (4×3×15)/(3+15) = 10, "
        "que es bajo pero manejable con rotación de gallos externa.\n\n"
        "6. Registrar en FarmMatch/NeoFarm: si usas la plataforma, el módulo genético calcula "
        "automáticamente el coeficiente de consanguinidad y alerta si un apareamiento propuesto "
        "supera el umbral.\n\n"
        "En avicultura, los efectos de consanguinidad se notan rápido: menor eclosionabilidad, "
        "pollitos débiles, asimetrías (patas, dedos) y menor tasa de crecimiento."
    ),
    make(
        "Necesito un script en Python para generar un dataset de cruces avícolas para capones.",
        "Aquí tienes un script funcional que genera combinaciones de cruces avícolas con sus "
        "características esperadas:\n\n"
        "```python\n"
        "import json, itertools\n\n"
        "# Razas con sus atributos (peso, conformación, rusticidad, calidad carne, puesta)\n"
        "razas = {\n"
        "    'Bresse':            {'peso': 3.2, 'conf': 9, 'rust': 6, 'carne': 10, 'puesta': 180, 'tipo': 'pesada'},\n"
        "    'Coucou de Malines': {'peso': 4.5, 'conf': 10, 'rust': 7, 'carne': 8, 'puesta': 150, 'tipo': 'pesada'},\n"
        "    'Dorking':           {'peso': 4.0, 'conf': 9, 'rust': 5, 'carne': 9, 'puesta': 155, 'tipo': 'pesada'},\n"
        "    'Sulmtaler':         {'peso': 3.2, 'conf': 8, 'rust': 8, 'carne': 8, 'puesta': 165, 'tipo': 'pesada'},\n"
        "    'Castellana Negra':  {'peso': 2.2, 'conf': 5, 'rust': 9, 'carne': 6, 'puesta': 230, 'tipo': 'ligera'},\n"
        "    'Penedesenca':       {'peso': 2.3, 'conf': 5, 'rust': 9, 'carne': 6, 'puesta': 190, 'tipo': 'ligera'},\n"
        "    'Euskal Oiloa':      {'peso': 2.5, 'conf': 6, 'rust': 8, 'carne': 7, 'puesta': 180, 'tipo': 'semi'},\n"
        "    'Sussex':            {'peso': 3.5, 'conf': 8, 'rust': 7, 'carne': 8, 'puesta': 200, 'tipo': 'semi'},\n"
        "}\n\n"
        "HETEROSIS = 0.08  # ~8% vigor híbrido en peso\n"
        "dataset = []\n\n"
        "for padre, madre in itertools.product(razas, razas):\n"
        "    if padre == madre:\n"
        "        continue\n"
        "    rp, rm = razas[padre], razas[madre]\n"
        "    # Solo cruces padre pesada × madre ligera/semi (dirección correcta para capones)\n"
        "    if rp['tipo'] != 'pesada' or rm['tipo'] == 'pesada':\n"
        "        continue\n"
        "    peso_f1 = ((rp['peso'] + rm['peso']) / 2) * (1 + HETEROSIS)\n"
        "    conf_f1 = (rp['conf'] + rm['conf']) / 2\n"
        "    rust_f1 = max(rp['rust'], rm['rust'])  # dominancia del más rústico\n"
        "    carne_f1 = (rp['carne'] * 0.6 + rm['carne'] * 0.4)  # sesgo paterno\n"
        "    dataset.append({\n"
        "        'cruce': f'{padre} × {madre}',\n"
        "        'peso_capon_kg': round(peso_f1 * 0.90, 1),  # rendimiento canal ~90% del vivo\n"
        "        'conformacion': round(conf_f1, 1),\n"
        "        'rusticidad': round(rust_f1, 1),\n"
        "        'calidad_carne': round(carne_f1, 1),\n"
        "        'puesta_madre': rm['puesta'],\n"
        "    })\n\n"
        "dataset.sort(key=lambda x: x['calidad_carne'] * x['peso_capon_kg'], reverse=True)\n\n"
        "with open('cruces_avicolas_capones.json', 'w') as f:\n"
        "    json.dump(dataset, f, indent=2, ensure_ascii=False)\n\n"
        "print(f'Generados {len(dataset)} cruces avícolas')\n"
        "for c in dataset[:5]:\n"
        "    print(f\"  {c['cruce']}: {c['peso_capon_kg']}kg, carne={c['calidad_carne']}, rust={c['rusticidad']}\")\n"
        "```\n\n"
        "Este script genera todos los cruces lógicos (padre pesado × madre ligera/semi), calcula "
        "parámetros F1 esperados con heterosis del 8% en peso, y los ordena por un índice de "
        "calidad × peso. Los valores son orientativos, basados en datos de raza publicados."
    ),
]

# ──────────────────────────────────────────────────────────────────────
# PASO 5: Nuevos ejemplos — Anti-alucinación / honestidad (10)
# ──────────────────────────────────────────────────────────────────────
new_anti_hallucination = [
    make(
        "¿Cuál es el precio exacto del capón de Villalba este año?",
        "No tengo acceso a datos de precios en tiempo real ni de mercados específicos. "
        "El precio del Capón de Villalba varía cada temporada según oferta, demanda y calidad. "
        "Como referencia histórica, en años recientes se ha movido entre 18 y 35 EUR/kg en canal, "
        "pero para el precio de esta campaña te recomiendo consultar directamente la Feria del "
        "Capón de Villalba (que se celebra cada diciembre) o contactar con la asociación de "
        "productores de Villalba. También la Lonja Agropecuaria de Segovia publica precios de "
        "aves de calidad en temporada navideña."
    ),
    make(
        "¿Cuántos capones se producen al año en España?",
        "No dispongo de una cifra oficial actualizada de producción anual de capones en España. "
        "El capón es un producto de nicho que no aparece desglosado en las estadísticas del MAPA "
        "(Ministerio de Agricultura) como categoría separada — se incluye dentro de «otras aves» "
        "o «avicultura alternativa». Algunas estimaciones del sector hablan de menos de 100.000 "
        "capones/año en toda España, pero es un dato aproximado. Las principales zonas de "
        "producción (Villalba, El Prat, Navarra) podrían proporcionarte cifras locales. "
        "Si necesitas un dato preciso para un plan de negocio, te sugiero contactar con la "
        "Interprofesional Avícola (INTEROVIC no cubre aves, sería PROPOLLO o similar) o las "
        "Oficinas Comarcales Agrarias de tu zona."
    ),
    make(
        "¿Qué estudios científicos demuestran que la Bresse es mejor para capones que la Coucou?",
        "No puedo citarte estudios científicos específicos con doi y autores de memoria porque no "
        "tengo acceso a bases de datos de publicaciones científicas en tiempo real. Lo que sí puedo "
        "indicarte es que la comparación entre razas para producción de capones es un tema con "
        "poca literatura científica formal: la mayoría de la información proviene de registros "
        "históricos, concursos de calidad (como las Glorieuses de Bresse) y datos empíricos de "
        "productores. Si necesitas referencias académicas, te recomiendo buscar en Google Scholar "
        "o Scopus con términos como «capon meat quality breed comparison» o «poulet de Bresse "
        "carcass traits». Journals relevantes: Poultry Science, British Poultry Science, y "
        "World's Poultry Science Journal."
    ),
    make(
        "¿Qué dice exactamente la normativa europea sobre caponización?",
        "No tengo el texto legal exacto memorizado. Lo que sí te puedo indicar es el marco general: "
        "la caponización quirúrgica está permitida en la UE bajo la Directiva 2007/43/CE y "
        "regulaciones de bienestar animal, siempre que se realice por personal cualificado con "
        "analgesia/anestesia adecuada. Sin embargo, la regulación específica varía por país: "
        "en Francia está bien regulada y es rutinaria para la producción de chapons AOP; "
        "en España no hay una normativa específica que la prohíba pero tampoco un marco detallado "
        "que la regule como práctica zootécnica. Te recomiendo consultar con los Servicios "
        "Veterinarios Oficiales de tu comunidad autónoma para confirmar los requisitos exactos "
        "en tu zona."
    ),
    make(
        "¿Cuál será el rendimiento exacto de mis capones si uso Bresse × Castellana?",
        "No puedo darte una predicción exacta porque el rendimiento depende de muchos factores "
        "que no conozco de tu explotación: calidad genética de tus reproductores concretos, "
        "programa de alimentación, condiciones de alojamiento, habilidad en la caponización, "
        "sanidad general del lote, clima y época exacta de producción.\n\n"
        "Lo que sí puedo darte es un rango orientativo basado en los datos generales de ambas "
        "razas: un F1 ♂ Bresse × ♀ Castellana Negra caponizado, con un programa de engorde de "
        "7 meses y acabado de 3-4 semanas con maíz y leche, debería moverse en 3.0-3.8 kg canal, "
        "con rendimiento canal del 70-75% sobre peso vivo. Pero estos son rangos — tu resultado "
        "real dependerá de las condiciones específicas. Te recomiendo hacer un lote piloto de "
        "20-30 capones y medir los resultados antes de escalar."
    ),
    make(
        "¿NeoFarm tiene un módulo específico para gestión de capones?",
        "A fecha de mi último entrenamiento, NeoFarm tiene módulos de genética y gestión "
        "productiva para porcino y vacuno, pero no tengo constancia de un módulo específico "
        "para avicultura o gestión de capones. El módulo FarmMatch podría adaptarse para "
        "gestionar pedigrí y cruces avícolas, ya que la lógica genética (consanguinidad, "
        "heterosis, EPDs) es universal, pero habría que adaptar los parámetros y la interfaz "
        "para ave en lugar de cerdo/vacuno. Si estás interesado en esta funcionalidad, "
        "lo mejor sería comentarlo directamente con el equipo de desarrollo de NeoFarm para "
        "evaluar la viabilidad de una extensión avícola."
    ),
    make(
        "¿Cuánto cuesta montar una explotación de capones en Segovia?",
        "No puedo darte un presupuesto cerrado porque depende de muchas variables que no "
        "conozco: tamaño de la explotación, si ya tienes terreno e instalaciones, tipo de "
        "alojamiento (nave existente vs. construcción nueva), número de reproductores, "
        "si compras pollitos de un día o crías desde reproductores propios, etc.\n\n"
        "Lo que sí puedo orientarte son las partidas principales:\n"
        "• Reproductores F0: 20-50 EUR/ave según raza y calidad, necesitas al menos 15-20 aves.\n"
        "• Incubadora: 300-2.000 EUR según capacidad (50-500 huevos).\n"
        "• Alojamiento: desde 0 EUR (nave existente adaptada) hasta 20.000+ EUR (construcción nueva) .\n"
        "• Alimentación: 8-12 EUR por capón durante todo el ciclo (15-20 kg alimento × 0.5-0.6 EUR/kg).\n"
        "• Equipamiento caponización: 50-200 EUR (instrumental quirúrgico avícola).\n"
        "• Sacrificio: matadero autorizado, coste por ave variable.\n\n"
        "Para un presupuesto realista, te sugiero elaborar un plan de negocio con datos de tu "
        "situación concreta. Si me das más detalles (nº capones objetivo, instalaciones disponibles), "
        "puedo ayudarte a structurar las partidas."
    ),
    make(
        "¿Qué opinas de la raza Faverolles para capones?",
        "No tengo información detallada sobre el uso de la Faverolles específicamente para "
        "caponización en mis datos de entrenamiento. Lo que sé de la raza en general es que "
        "es una raza francesa de doble propósito, con barba y plumaje salmón en la variedad "
        "principal, peso de 3.0-3.5 kg en gallos y temperamento muy dócil. En teoría podría "
        "ser interesante para capones por su tamaño y docilidad, pero no tengo datos empíricos "
        "sobre rendimiento de capones Faverolles ni comparativas con razas como Bresse o Coucou "
        "de Malines. Si tienes experiencia con ella o encuentras datos de productores que la "
        "hayan usado, sería información valiosa para compartir."
    ),
    make(
        "¿Puedes diseñarme la dieta exacta día a día para un capón durante 7 meses?",
        "No puedo diseñarte una dieta día a día sin conocer los datos concretos: peso de los "
        "pollos al inicio, raza o cruce, temperatura media de tu zona, tipo de alojamiento "
        "(extensivo/intensivo/mixto), materias primas disponibles y sus precios locales, "
        "y objetivos de peso final.\n\n"
        "Lo que sí puedo darte es el marco general de las 4 fases de alimentación del capón "
        "(starter, recría, engorde, acabado) con rangos de proteína, energía y materias primas "
        "habituales. Si me proporcionas los datos de tu explotación, puedo ayudarte a ajustar "
        "esos rangos. Para una dieta de precisión, lo ideal sería trabajar con un nutricionista "
        "avícola que haga la formulación con análisis de tus materias primas."
    ),
    make(
        "¿Cuál es el índice de conversión alimenticia de un capón?",
        "No dispongo de un valor exacto validado con estudios, porque el IC del capón varía "
        "enormemente según la raza, el programa de alimentación y la duración del engorde. "
        "En broiler industrial es ~1.6-1.8 a 42 días. En capón, con un engorde de 5-8 meses, "
        "el IC global es mucho peor: estimaciones empíricas hablan de 5-8:1 (5 a 8 kg de "
        "alimento por kg de peso vivo ganado durante todo el ciclo). Esto es uno de los motivos "
        "por los que el capón es un producto caro: su eficiencia alimenticia es 3-4 veces peor "
        "que la del broiler. Sin embargo, no es un dato que deba evaluarse de la misma forma, "
        "porque el objetivo del capón no es la eficiencia sino la calidad de carne y grasa "
        "infiltrada. Si necesitas un IC preciso para tu plan de negocio, te recomiendo pesar "
        "alimento y animales semanalmente durante tu primer lote piloto."
    ),
]

# ──────────────────────────────────────────────────────────────────────
# PASO 6: Nuevos ejemplos — Cross-domain avícola + IoT/NeoFarm (5)
# ──────────────────────────────────────────────────────────────────────
new_cross_avi = [
    make(
        "¿Se pueden usar los sensores PorciData para monitorizar una nave de capones?",
        "Sí, muchas de las 7+1 capas de sensores PorciData son directamente aplicables a una "
        "nave de capones, con algunas adaptaciones:\n\n"
        "• Capa ambiental (T/HR/NH3/CO2): 100% compatible. Los capones requieren control "
        "ambiental similar al porcino, con rangos algo distintos (T óptima 15-20 °C en engorde, "
        "NH3 < 20 ppm, HR 60-70%). Los sensores Dragino + Renke funcionan igual.\n\n"
        "• Capa acústica (INMP441 + ESP32): adaptable. En avícola, el análisis de sonido puede "
        "detectar problemas respiratorios (CRD, bronquitis), estrés térmico (jadeo) y actividad "
        "general del lote. El modelo ML necesitaría reentrenarse con vocalizaciones de aves.\n\n"
        "• Capa de visión RGB (cámara IP): útil para conteo, detección de aves en suelo "
        "(indicador de enfermedad), y monitorización de actividad. Funciona directamente.\n\n"
        "• Capa térmica (Hikvision bi-espectro): excelente para detectar aves con fiebre "
        "o hipotermia en el lote. Aplicable directamente.\n\n"
        "• Capa de peso walk-over: necesita adaptación. Las básculas para cerdos no sirven "
        "para aves. Existen perchas-báscula (perching scales) que pesan aves automáticamente.\n\n"
        "• Capa de gases (BME688 nariz electrónica): útil para detectar deterioro de cama "
        "(yacija) y calidad del aire.\n\n"
        "• Radar mmWave: funciona para detección de movimiento pero es menos útil en aves "
        "que en cerdos.\n\n"
        "Con un coste adaptado estimado de ~1.200 EUR/nave (menos peso, sin caudalímetro), "
        "PorciData podría ofrecer una solución IoT para avicultura de calidad muy competitiva."
    ),
    make(
        "¿Cómo sería un Digital Twin para una explotación de capones?",
        "Un Digital Twin para producción de capones modelaría el ciclo completo del lote:\n\n"
        "1. Submodelo de crecimiento: curva de peso del capón desde pollito (40 g) hasta "
        "sacrificio (3.5-5 kg), parametrizada por raza/cruce, fase de alimentación y temperatura "
        "ambiental. A diferencia del broiler (curva de 42 días), el capón sigue una curva "
        "sigmoide de 5-8 meses con un punto de inflexión post-caponización donde el crecimiento "
        "se ralentiza y la deposición grasa aumenta.\n\n"
        "2. Submodelo de consumo: ingesta diaria de alimento y agua, vinculada a la fase "
        "de alimentación, temperatura y peso vivo. Alimenta predicciones de coste.\n\n"
        "3. Submodelo ambiental: temperatura, humedad, NH3, CO2 de la nave, alimentado por "
        "sensores IoT en tiempo real. El twin predice cuándo las condiciones saldrán de rango "
        "y sugiere ventilación o calefacción.\n\n"
        "4. Submodelo de calidad de carne: estimación de infiltración grasa basada en raza, "
        "duración del acabado, ratio maíz/leche en la dieta y peso vivo. Es el KPI diferencial "
        "respecto a un twin de broiler.\n\n"
        "5. Submodelo económico: coste acumulado vs. precio esperado de venta, con punto óptimo "
        "de sacrificio (el momento donde el margen bruto/capón es máximo).\n\n"
        "La integración con PorciData (adaptado a avícola) alimentaría los submodelos 1-3 "
        "con datos reales, y el twin alertaría sobre desviaciones."
    ),
    make(
        "¿Podría FarmMatch de NeoFarm gestionar el pedigrí de mis reproductores avícolas?",
        "En principio, FarmMatch está diseñado para porcino y vacuno, pero la lógica genética "
        "subyacente es universal y podría adaptarse para avicultura con estas consideraciones:\n\n"
        "Lo que funciona directamente:\n"
        "• Cálculo de consanguinidad (F de Wright): la fórmula es idéntica para cualquier especie.\n"
        "• Registro de pedigrí: padre, madre, abuelos — misma estructura.\n"
        "• Alertas de apareamiento: «este gallo × esta gallina daría F > umbral» = mismo cálculo.\n"
        "• Planificación de apareamientos: asignar gallos a lotes de gallinas minimizando F.\n\n"
        "Lo que necesitaría adaptación:\n"
        "• Parámetros reproductivos: en avícola se mide tasa de puesta (%), eclosionabilidad (%), "
        "y fertilidad de huevos, no tamaño de camada ni intervalo entre partos.\n"
        "• EPDs: los caracteres son distintos (peso vivo 20 sem., peso huevo, color cáscara) vs. "
        "porcino (GMD, espesor grasa dorsal, lechones vivos/parto).\n"
        "• Nº de crías por reproducción: una gallina puede producir 150+ descendientes/año "
        "(vs. ~25 en cerda), lo que cambia la intensidad de selección y el diseño del programa.\n\n"
        "Si la base de datos de FarmMatch es relacional estándar, la adaptación sería viable "
        "con un sprint de 2-3 semanas para ajustar los campos y recalibrar los modelos."
    ),
    make(
        "¿Qué normativa aplica en Castilla y León para una explotación de capones?",
        "No tengo el texto normativo específico de Castilla y León para avicultura de capones "
        "actualizado a hoy, pero el marco general incluye:\n\n"
        "1. Registro de explotación ganadera: obligatorio ante la Junta de Castilla y León "
        "(REGA avícola). Tipo: aves de corral para carne.\n\n"
        "2. Bienestar animal: Directiva 2007/43/CE (pollos de engorde) transpuesta al derecho "
        "español. Aplica densidades máximas según sistema: 33 kg/m² en estándar, hasta 39 kg/m² "
        "con ventilación ambiental controlada. Para capones extensivos con acceso a exterior, "
        "la densidad en el interior puede relajarse.\n\n"
        "3. Sanidad animal: programa de vigilancia de influenza aviar (obligatorio), bioseguridad "
        "básica, registro de tratamientos veterinarios.\n\n"
        "4. Matadero: sacrificio obligatorio en matadero autorizado para aves, con inspección "
        "ante-mortem y post-mortem.\n\n"
        "5. Etiquetado: si quieres comercializar como «capón», debes cumplir la normativa de "
        "comercialización de aves de corral (Reglamento UE 543/2008) que define requisitos para "
        "usar las menciones «capón» y «pularda».\n\n"
        "Para los requisitos exactos de tu caso, consulta con la Oficina Comarcal Agraria (OCA) "
        "de Segovia o los Servicios Veterinarios de la Junta. También el ITACYL puede asesorarte "
        "sobre aspectos técnicos y de calidad."
    ),
    make(
        "Tengo una explotación mixta de porcino y capones en Segovia. ¿Cómo integro ambas "
        "producciones con NeoFarm?",
        "Una explotación mixta porcino + capones tiene sinergias interesantes que NeoFarm puede "
        "ayudar a gestionar:\n\n"
        "Sinergias productivas:\n"
        "• Alimentación: el suero de leche de la industria local que uses para alimentar capones "
        "en fase de acabado también puede complementar dietas porcinas (fase de recría).\n"
        "• Residuos: la yacija (cama) de la nave de capones es excelente como fertilizante, "
        "y puede compostarse con purines porcinos para mejorar la relación C/N.\n"
        "• Estacionalidad complementaria: la producción de capones es estacional (mayo→diciembre), "
        "lo que permite compartir naves con otras fases de porcino.\n\n"
        "Integración en NeoFarm:\n"
        "• PorciData: un mismo gateway LoRa puede conectar sensores de la nave de cerdos Y de "
        "la nave de capones. Dashboard unificado para ambiente, consumo y alertas.\n"
        "• Módulo genético: FarmMatch para pedigrí porcino + extensión avícola (adaptación "
        "de los parámetros según lo comentado) en la misma plataforma.\n"
        "• Digital Twin dual: gemelo digital porcino (existente) + gemelo avícola (a desarrollar) "
        "alimentados ambos por los mismos sensores IoT.\n"
        "• Costes: SIGE unificado para gestión integrada de purines + yacija avícola.\n\n"
        "La clave es que la infraestructura IoT y de datos es común; lo que cambia son los modelos "
        "analíticos (curvas de crecimiento, parámetros ambientales), que son configurables por especie."
    ),
]

# ──────────────────────────────────────────────────────────────────────
# PASO 7: Ensamblar dataset v5
# ──────────────────────────────────────────────────────────────────────
all_new = (
    new_avicultura_defs
    + new_avicultura_razas
    + new_avicultura_cruces
    + new_anti_hallucination
    + new_cross_avi
)

dataset_v5 = base + all_new

output = "seedy_dataset_sft_v5.jsonl"
with open(output, "w", encoding="utf-8") as f:
    for d in dataset_v5:
        f.write(json.dumps(d, ensure_ascii=False) + "\n")

print(f"\n{'='*60}")
print(f"Dataset v5 generado: {output}")
print(f"  Base v4:                   {len(base):>4} ejemplos")
print(f"  + Avicultura definiciones: {len(new_avicultura_defs):>4}")
print(f"  + Avicultura razas:        {len(new_avicultura_razas):>4}")
print(f"  + Avicultura cruces/F0-F5: {len(new_avicultura_cruces):>4}")
print(f"  + Anti-alucinación:        {len(new_anti_hallucination):>4}")
print(f"  + Cross-domain avícola:    {len(new_cross_avi):>4}")
print(f"  = TOTAL:                   {len(dataset_v5):>4} ejemplos")
print(f"{'='*60}")

# Verificación de calidad
lens = []
for d in all_new:
    asst = [m for m in d["messages"] if m["role"] == "assistant"][0]["content"]
    lens.append(len(asst))
print(f"\nNuevos ejemplos — longitud respuesta:")
print(f"  Mín: {min(lens)} chars | Máx: {max(lens)} chars | Media: {sum(lens)//len(lens)} chars")

# Verificar que no hay respuestas copiadas
answers = [
    [m for m in d["messages"] if m["role"] == "assistant"][0]["content"]
    for d in dataset_v5
]
dupes = len(answers) - len(set(answers))
if dupes:
    print(f"\n⚠️  {dupes} respuestas duplicadas detectadas")
else:
    print("\n✅ Sin respuestas duplicadas")
