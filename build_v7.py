#!/usr/bin/env python3
"""
build_v7.py — Genera seedy_dataset_sft_v7.jsonl
  1. Copia todos los 302 ejemplos de v6
  2. Añade ~200 ejemplos nuevos basados en datos REALES de /conocimientos/
  3. Refuerza: VISION (0→30), Malines/Avicultura (+15), Genética cruzada (+20),
     GeoTwin (+15), Digital Twins (+15), Nutrición (+15), Normativa (+15),
     cross-domain (+20), meta-Seedy (+10), seguridad alimentaria (+10)
  4. Deduplica por pregunta (normalizada)
  5. Audita distribución final
"""
import json
from collections import Counter

SYSTEM = (
    "Eres Seedy, asistente técnico especializado en agrotech para NeoFarm.\n"
    "Dominios principales: IoT ganadero (PorciData 7 capas), nutrición animal (NRC 2012), "
    "genética aplicada (EPDs, FarmMatch, heterosis), normativa SIGE (RD 306/2020), "
    "Digital Twins productivos, GIS/GeoTwin (Cesium 3D, PNOA), "
    "Computer Vision ganadera (YOLO, TensorRT) y economía agropecuaria.\n\n"
    "Responde siempre en español, en prosa natural y profesional.\n"
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

# --- Cargar v6 ---
with open("seedy_dataset_sft_v6.jsonl") as f:
    base = [json.loads(l) for l in f]

print(f"v6 base: {len(base)} ejemplos")

# --- Nuevos ejemplos ---
new_examples = []

# ============================================================
# VISION / Computer Vision (~30 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué modelo de detección de objetos usa NeoFarm para monitorizar ganado?",
        "NeoFarm utiliza YOLOv8m (variante medium) como detector principal, con la opción de migrar a YOLOv11 cuando esté maduro. El modelo se entrena con imágenes de 640×640 px, 100 epochs, batch 16 y patience 20. Las augmentaciones incluyen mosaic (1.0), mixup (0.15) y copy_paste (0.1). Se definen 6 clases unificadas: chicken, pig, cattle, chick, piglet y calf. La inferencia se ejecuta en la RTX 5080 para entrenamiento y en Jetson Orin Nano 8GB para edge, exportando a TensorRT FP16/INT8 para máximo rendimiento."
    ),
    make(
        "¿Qué precisión tiene la IA de visión para detectar caudofagia en cerdos?",
        "Según las pruebas internas de NeoFarm, la detección de caudofagia (tail biting) alcanza un 87% de precisión. Es una de las métricas más complicadas porque requiere detectar comportamientos sutiles. Para contexto, el conteo automático de cerdos llega al 95%, la detección de animales caídos/muertos (>30 min inmóviles) al 93%, el nivel de actividad grupal al 90%, el nivel de tolvas al 88%, y la detección de cojeras al 82%. Todas estas métricas se obtienen con cámaras IP 4MP + inferencia en Jetson Orin Nano."
    ),
    make(
        "¿Cuánto cuesta la capa de visión RGB por nave en PorciData?",
        "La capa 2 (Visión RGB) tiene un coste aproximado de 150 EUR por nave. Incluye una cámara IP 4MP y un edge compute (Jetson Nano/Orin Nano) que ejecuta YOLO para conteo automático, estimación de peso, detección de cojeras y caudofagia. En comparación, soluciones comerciales como Fancom iGrow o Nedap cuestan más de 3.000 EUR por nave solo para la parte de visión. La cámara térmica Hikvision bi-espectro (capa 3) cuesta ~550 EUR adicionales y detecta temperatura corporal sin contacto (oreja/cuerpo) para estrés térmico."
    ),
    make(
        "¿Cómo funciona la estimación de peso por visión artificial en NeoFarm?",
        "El pipeline de estimación de peso usa un enfoque en dos etapas: primero, YOLOv8 detecta el animal y extrae la región de interés (ROI). Después, un backbone EfficientNet-B0 (alternativa: ConvNeXt-Tiny) extrae features de la imagen redimensionada a 224×224 px. Estas features pasan por un MLP de regresión: Linear(features + 1 extra, 256) → ReLU → Dropout(0.3) → Linear(256, 64) → ReLU → Dropout(0.2) → Linear(64, 1) que predice el peso en kg. El '+1' extra es el área normalizada del animal obtenida por segmentación mask, que mejora la predicción. El sistema se calibra contra una báscula walk-over (~350 EUR/nave) para ground truth."
    ),
    make(
        "¿Qué algoritmo de tracking usa NeoFarm para seguir animales individuales?",
        "NeoFarm utiliza BoT-SORT como algoritmo de tracking por defecto, con ByteTrack como alternativa, ambos integrados en Ultralytics. Los umbrales de velocidad (en unidades normalizadas/segundo) son: en reposo (<0.005), caminando (<0.05) y corriendo (>0.15). Para detectar estereotipias, se exige una duración mínima de 30 segundos del comportamiento repetitivo. La ventana de tracking es de 300 frames (~10 s a 30 fps) y un animal se da por perdido después de 5.0 segundos sin detección. Esto permite analizar patrones de comportamiento por individuo a lo largo del día."
    ),
    make(
        "¿Cómo se optimiza YOLO para Jetson Orin Nano en edge?",
        "La pipeline de optimización para edge es: PyTorch (.pt) → ONNX (.onnx) → TensorRT FP16 → TensorRT INT8. Para INT8 se necesita un set de calibración de ~500 imágenes representativas. El benchmark usa 50 iteraciones de warmup + 200 de medición, reportando avg_ms, P50, P95, P99, FPS y memoria GPU en MB. El workspace de TensorRT se configura a 4 GB por defecto. En Jetson Orin Nano 8GB, los umbrales por defecto son confianza 0.4 e IoU 0.5. El sistema codifica por colores según especie: gallinas en naranja, cerdos en rosa y vacuno en verde."
    ),
    make(
        "¿Qué hardware piloto tiene NeoFarm para visión en granja?",
        "El piloto de visión de NeoFarm incluye 2 cámaras RGB 8K de alta resolución, 1 cámara térmica Hikvision bi-espectro, micrófonos INMP441, radar mmWave 60 GHz (Seeed MR60BHA1), báscula walk-over con celdas de carga + RFID, y un Jetson Orin Nano 8GB como edge compute. El coste total de todo el stack de visión + sensores es significativamente menor que la alternativa comercial de FLIR T1020 + software (>5.000 EUR). Para detección se usa YOLOv8/YOLOv11, para segmentación YOLO-seg, para pose ViTPose o MediaPipe, y para comportamiento temporal un transformer con tracking."
    ),
    make(
        "¿Cuál es la diferencia entre YOLO, ViTPose y un transformer temporal en el pipeline de visión?",
        "Cada modelo tiene un rol distinto en el pipeline: YOLO (detección/segmentación) localiza animales en cada frame con bounding boxes y máscaras — funciona frame a frame, es rápido y se exporta a TensorRT. ViTPose/MediaPipe (estimación de pose) identifica puntos clave del esqueleto del animal (articulaciones), útil para detectar cojeras por asimetría de movimiento. El transformer temporal analiza secuencias de frames para detectar comportamientos complejos que no se ven en un solo frame: estereotipias, agresiones sostenidas, patrones de alimentación. BoT-SORT une las detecciones frame a frame para seguir individuos a lo largo del tiempo."
    ),
    make(
        "¿Qué métricas usa el benchmark de TensorRT para evaluar modelos en edge?",
        "El benchmark de TensorRT mide: latencia promedio (avg_ms), percentiles P50/P95/P99 (para detectar jitter), FPS (frames por segundo) y memoria GPU ocupada en MB. Se configura con 50 iteraciones de warmup para estabilizar la GPU y 200 iteraciones de medición. Compara automáticamente las variantes PyTorch, ONNX, TensorRT FP16 y TensorRT INT8, generando una tabla comparativa. Para la RTX 5080 se espera >100 FPS en FP16 con YOLOv8m a 640px. En Jetson Orin Nano, el target es >15 FPS en INT8 para procesamiento en tiempo real."
    ),
    make(
        "¿Cómo se detectan animales caídos o muertos con visión artificial?",
        "La detección de animales caídos/muertos se basa en la combinación de detección + tracking temporal. YOLO detecta al animal en cada frame y BoT-SORT lo rastrea. Si un animal permanece inmóvil (velocidad <0.005 unidades normalizadas/segundo) durante más de 30 minutos, se genera una alerta de prioridad alta. Esta métrica alcanza un 93% de precisión en las pruebas internas. La alerta se envía vía MQTT al topic neofarm/{farm_id}/{barn_id}/vision/alert y se registra en InfluxDB para trazabilidad. Es una de las detecciones más críticas porque permite intervención temprana reduciendo la mortalidad."
    ),
    make(
        "¿Puede NeoFarm detectar el nivel de las tolvas de pienso con visión?",
        "Sí, la detección del nivel de tolvas (feed hopper level) alcanza un 88% de precisión. Se utiliza una cámara cenital que captura la vista superior de la tolva, y YOLO segmenta el área visible de pienso versus el área vacía. El ratio proporciona una estimación del porcentaje de llenado. Cuando baja del 20%, se genera una alerta automática vía MQTT para reposición. Esto evita periodos sin pienso que afectan al índice de conversión (IC) y al bienestar animal. Es una aplicación secundaria de las mismas cámaras que monitorizan a los animales, sin coste adicional de hardware."
    ),
    make(
        "¿Cómo entrena NeoFarm modelos de visión para diferentes especies?",
        "NeoFarm usa un dataset unificado con 6 clases: chicken, pig, cattle, chick, piglet y calf. El entrenamiento se ejecuta en la RTX 5080 16GB con YOLOv8m a 640px, 100 epochs, batch 16 y patience 20 (early stopping). Las augmentaciones son mosaic (1.0), mixup (0.15) y copy_paste (0.1). Los modelos entrenados se exportan a ONNX y luego a TensorRT FP16/INT8 para despliegue en Jetson Orin Nano. Cada especie tiene umbrales de confianza ajustados y codificación visual diferente (gallinas naranja, cerdos rosa, vacuno verde). Los datos de validación incluyen escenas de granja real con variaciones de luz, ángulo y densidad."
    ),
    make(
        "¿Qué es DeepStream y para qué lo usa NeoFarm?",
        "DeepStream es el framework de NVIDIA para procesamiento de vídeo en edge. NeoFarm lo utiliza en Jetson Orin Nano para ejecutar pipelines multi-stream: múltiples cámaras se decodifican en paralelo por hardware (NVDEC), las imágenes pasan por el modelo TensorRT (detección + tracking), y los resultados se envían al backend vía MQTT. DeepStream gestiona automáticamente el pipeline de GPU (decode → preprocess → inference → postprocess → output) sin que cada frame toque la CPU. Esto permite procesar 2-4 streams de cámaras simultáneamente en un Orin Nano 8GB manteniendo >15 FPS por stream."
    ),
    make(
        "¿Cómo se detectan cojeras en cerdos con visión artificial?",
        "La detección de cojeras alcanza un 82% de precisión y es una de las más complejas. Combina dos enfoques: 1) Análisis de pose con ViTPose, que identifica puntos clave del esqueleto del cerdo y detecta asimetrías en el movimiento de las extremidades durante la marcha. 2) Análisis temporal con el tracker BoT-SORT, que calcula la velocidad y regularidad del movimiento individual. Un cerdo con cojera muestra patrones irregulares de velocidad (aceleración-frenado-aceleración) y asimetría lateral. La ventana de análisis es de 300 frames (~10 s a 30 fps). Las alertas tempranas de cojera permiten intervención antes de que se conviertan en un problema de bienestar animal serio."
    ),
    make(
        "¿Cuánto cuesta la cámara térmica de PorciData y qué detecta?",
        "La cámara térmica Hikvision bi-espectro cuesta aproximadamente 550 EUR por nave (capa 3 de PorciData). Detecta temperatura corporal del animal sin contacto, midiendo la temperatura de la oreja y el cuerpo. Permite identificar estrés térmico (cuando la temperatura ambiente supera el THI de confort), fiebre individual temprana (>0.5°C sobre la media del grupo), y patrones de distribución térmica en la nave. La alternativa comercial (FLIR T1020 + software) cuesta más de 5.000 EUR. La cámara bi-espectro combina imagen visible (RGB) e infrarroja en un solo dispositivo, lo que facilita la correspondencia entre el animal detectado visualmente y su temperatura."
    ),
    make(
        "¿Qué diferencia hay entre la detección de BCS visual y la estimación de peso?",
        "Son dos métricas diferentes que usan pipelines similares pero con objetivos distintos. La estimación de peso usa EfficientNet-B0 → MLP de regresión para predecir kg directamente, calibrada contra báscula walk-over. El BCS (Body Condition Score) evalúa la condición corporal del animal en una escala (1-5 en vacuno, 1-5 en porcino) analizando la visibilidad de huesos (costillas, espina dorsal, caderas). El BCS se obtiene por clasificación (categorías discretas), no regresión continua. Para vacuno extensivo, el BCS se evalúa visualmente desde drones o cámaras en abrevadero. Para porcinas gestantes, el BCS óptimo al parto es 3.0-3.5 y se mide semanalmente. Ambos modelos comparten el backbone YOLO para la detección del animal."
    ),
    make(
        "¿Cómo gestiona NeoFarm la inferencia de IA cuando no hay conexión a internet en la granja?",
        "NeoFarm sigue un diseño offline-first. La inferencia de visión se ejecuta 100% localmente en Jetson Orin Nano con modelos TensorRT, sin necesidad de conexión. Los resultados (detecciones, alertas, métricas) se almacenan en un buffer local en la caseta con retries automáticos. Cuando hay conexión, se sincronizan vía MQTT o HTTP con el backend central. El gateway local tiene buffer con retries para garantizar que no se pierden datos. Incluso el GeoTwin usa localStorage para persistencia offline. Esto es crítico en explotaciones rurales donde la conectividad puede ser intermitente o inexistente."
    ),
    make(
        "¿Se puede usar visión artificial para detectar el celo en vacas?",
        "Sí, aunque en NeoFarm para vacuno extensivo se prioriza el enfoque con GPS + acelerómetro (collares/crotales) por la dispersión de los animales en dehesa. Para explotaciones intensivas o semi-intensivas, la detección visual del celo se basa en identificar monta (una vaca montando a otra) y comportamiento de seguimiento, usando el tracking temporal con BoT-SORT. La estrategia de centinelas (10-20 animales representativos instrumentados) proporciona datos complementarios. La detección combinada GPS + visión + acelerómetro mejora significativamente la tasa de detección frente a cualquiera de los métodos por separado."
    ),
    make(
        "¿Qué formato de anotación usa NeoFarm para los datasets de visión?",
        "NeoFarm usa el formato YOLO nativo (archivos .txt con clase + coordenadas normalizadas x_center, y_center, width, height) para detección, y formato COCO JSON para segmentación y pose. Las anotaciones se organizan siguiendo la estructura estándar de Ultralytics: un directorio images/ con las imágenes y un directorio labels/ paralelo con las etiquetas. El dataset YAML define las 6 clases (chicken, pig, cattle, chick, piglet, calf), las rutas de train/val/test, y los hiperparámetros de augmentación. Para la construcción del dataset se usa un builder específico que gestiona avícola, porcino y vacuno de forma unificada."
    ),
    make(
        "¿Cuántas imágenes necesita NeoFarm para calibrar TensorRT INT8?",
        "Para la calibración de TensorRT INT8 se recomiendan ~500 imágenes representativas del dominio de despliegue. Estas imágenes deben cubrir las condiciones reales de la granja: diferentes horarios (día/noche), niveles de iluminación, densidades de animales, y posiciones de cámara. La calibración INT8 reduce la latencia significativamente respecto a FP16 (típicamente 1.5-2× más rápido) con una pérdida de precisión mínima (<1% mAP). El proceso genera una tabla de rangos de activación por capa que el engine TensorRT usa para cuantizar los pesos de FP32 a INT8."
    ),
]

# ============================================================
# AVICULTURA / MALINES / CAPONES (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué es el Coucou de Malines y por qué es importante para la producción de capones?",
        "El Coucou de Malines (Mechelse Koekoek, en español 'Cuco de Malinas') es una raza avícola belga considerada la raza más pesada de Europa. Los machos alcanzan 5.0 kg y las hembras 3.8 kg, con un rendimiento canal del 72% — superior al de la Bresse (70%). Su índice de sabor es 90/100 y tiene un temperamento muy dócil, lo que es crucial para la caponización porque los animales dóciles sufren menos estrés post-operatorio. Tiene piel blanca y se clasifica en el Grupo 2 ('Estructura — El chasis del capón'). Es ideal para producir capones gigantes cuando se cruza con otras razas mejoradoras."
    ),
    make(
        "¿Cuál es la diferencia entre la Bresse y el Coucou de Malines para capones?",
        "Son dos estrategias diferentes: la Bresse (Gauloise Blanche de Bresse) es la referencia mundial en calidad de carne — índice sabor 95/100, FCR 2.8:1, única AOP para aves en Europa, con sus características patas azules ('tricolor francés'). Pesa 4.5/3.5 kg (♂/♀) y tiene un rendimiento canal del 70%. El Coucou de Malines aporta más peso (5.0/3.8 kg, rendimiento 72%) y docilidad extrema, pero con un sabor ligeramente inferior (90/100). El cruce de ambas razas es una estrategia real para combinar la calidad organoléptica de la Bresse con la estructura corporal del Malines. En la práctica, para capones gigantes se prefiere el Malines como línea padre por su masa muscular."
    ),
    make(
        "¿A qué edad se caponizan los pollos y qué tasa de éxito tiene?",
        "La caponización se realiza entre las 6-8 semanas de edad, cuando el pollo pesa 600-800 g. Nunca debe hacerse después de las 12 semanas — la regla práctica es que debe hacerse ANTES de que el gallo cante por primera vez. Con un operador experimentado, la tasa de éxito es del 95-98%, y la mortalidad post-operatoria es del 2-5%. Los 'falsos capones' (caponización incompleta) se detectan porque la cresta reaparece a las 4-6 semanas post-operación. Solo se acepta caponización quirúrgica para obtener la certificación Label Rouge; métodos químicos o hormonales están prohibidos en la UE."
    ),
    make(
        "¿Qué es el cruce 'Majestic' en avicultura y qué resultados da?",
        "El cruce 'Majestic' es una combinación diseñada para maximizar el peso del capón: se cruza ♂ Coucou de Malines × ♀ Faverolles. El resultado es un capón gigante de 4.5-5.5 kg con un Capon Score de ~80/100 (calificación 'Muy Bueno') y un FCR de ~3.1:1. El Malines aporta estructura corporal y docilidad, mientras que la Faverolles aporta rusticidad y adaptación al frío. Es un cruce orientado a mercado premium donde el peso del ave es el factor diferencial principal, como ferias y mercados de Navidad donde los capones gigantes alcanzan los precios más altos."
    ),
    make(
        "¿Qué es el Capon Score y cómo se calcula?",
        "El Capon Score es un índice compuesto de 100 puntos que evalúa la aptitud de una raza o cruce para producir capones de calidad. Se calcula con 5 componentes ponderados: rendimiento canal (35% del peso total del score), peso corporal del macho (25%), docilidad (15%), velocidad de crecimiento (15%) y rusticidad (10%). Por ejemplo, un cruce Malines × Faverolles ('Majestic') obtiene ~80/100, mientras que la Bresse pura obtiene mayor puntuación en sabor pero menor en peso. El Capon Score es una herramienta interna de NeoFarm para comparar razas y cruces de forma objetiva."
    ),
    make(
        "¿Qué es una épinette y cómo se usa en la producción de capones?",
        "La épinette es una jaula individual de engorde final (acabado) que se usa en la fase de cebado de capones y pulardas. Las dimensiones son 30×40 cm por ave, con 45-50 cm de altura. La duración del acabado es de 4 semanas para pulardas y 4-5 semanas para capones. Durante esta fase, los animales reciben una dieta especial llamada 'pâtée': 70-80% de maíz amarillo/blanco + 15-20% de trigo + 1.5-2 litros de leche por kg de grano. Este método tradicional permite un engrasamiento intramuscular que mejora enormemente el sabor y la textura de la carne. Es una práctica obligatoria para obtener la Appellation d'Origine Protégée (AOP) Bresse."
    ),
    make(
        "¿Cuáles son los requisitos del Label Rouge para capones?",
        "El Label Rouge exige para capones: edad mínima de sacrificio de 200+ días (vs 150 días para pollos), densidad máxima de 11 aves/m² en interior y mínimo 10 m²/ave en exterior con acceso obligatorio a pastos, y una alimentación con mínimo 70% de cereales. La caponización debe ser exclusivamente quirúrgica — ningún método químico u hormonal está permitido. Para comparar: un pollo industrial se sacrifica a los 35-42 días con 2.5 kg, mientras que un capón extensivo necesita 210-300 días y alcanza 3.5-5.5 kg. El precio de mercado refleja esta diferencia: industrial 3-5 €/kg frente a capón Label Rouge 12-25 €/kg."
    ),
    make(
        "¿Qué heterosis se espera en cruces F1 de aves para capones?",
        "Los valores de heterosis esperados en cruces F1 avícolas son: velocidad de crecimiento +15%, eficiencia alimentaria (FCR) +12%, resistencia a enfermedades +20%, tolerancia al estrés +18%, calidad de carne +10%, pero fertilidad -5% (reducción). Estos valores se calculan con la fórmula: F1 = media_parental + |EBV_a - EBV_b| × factor_heterosis, donde el factor es 0.15 para peso y 0.10 para otros caracteres. La mayor distancia genética entre razas parentales produce mayor efecto heterótico. Por eso los cruces más productivos son entre razas de grupos diferentes: Grupo 1 (Sabor, ej. Bresse) × Grupo 2 (Estructura, ej. Malines)."
    ),
    make(
        "¿Cuáles son las heredabilidades de los caracteres avícolas?",
        "En avicultura, las heredabilidades (h²) de los caracteres principales son: rendimiento canal h²=0.50 (alta, responde bien a selección), peso corporal h²=0.50 (alta), velocidad de crecimiento h²=0.40 (media-alta), puesta/huevos por año h²=0.30 (media), docilidad h²=0.30 (media, seleccionable), y rusticidad h²=0.25 (media-baja). Para cruces de capones, la selección más efectiva se centra en rendimiento canal y peso corporal (h² altas), mientras que la rusticidad se mejora más eficazmente por heterosis (cruzando razas rústicas). NeoFarm calcula los GEBV (valores genómicos estimados) con la fórmula VanRaden 2008: G = ZZ'/Σ(2p(1-p))."
    ),
    make(
        "¿Cuáles son las 4 fases de alimentación del capón extensivo?",
        "Las 4 fases de alimentación del capón extensivo son: 1) Arranque (0-4 semanas): pienso starter alto en proteína (~22% PB) para desarrollo esquelético. 2) Crecimiento (4-12 semanas): período pre/post caponización, reducción gradual de PB a ~18%, la caponización se hace a las 6-8 semanas (600-800 g). 3) Pastoreo/desarrollo (12-30 semanas): acceso a pastos con 10 m²/ave mínimo, pienso complementario con 70%+ cereales según Label Rouge, el ave desarrolla músculo y estructura. 4) Acabado/épinette (últimas 4-5 semanas): en jaula individual 30×40 cm, dieta de pâtée (maíz + leche) para engrasamiento intramuscular que da la calidad organoléptica premium. Total: 210-300 días vs 35-42 días de un pollo industrial."
    ),
    make(
        "¿Cuál es el umbral de consanguinidad para descarte automático en avicultura?",
        "En avicultura, cuando el coeficiente de consanguinidad (F de Wright) supera 0.15 (15%), se aplica un descarte automático del cruce propuesto. Este umbral es más estricto que en otras especies porque las aves son más sensibles a la depresión consanguínea, especialmente en fertilidad (que ya pierde un -5% por el efecto del cruce F1). Para porcino industrial el umbral rojo es >12.5%, para ibérico puro >20%. NeoFarm calcula F usando el algoritmo tabular de Meuwissen & Luo (1992) con complejidad O(n²) sobre la matriz de parentesco, exigiendo un mínimo de 3 generaciones de pedigree (5 ideal)."
    ),
    make(
        "¿Qué diferencia hay entre un capón y una pularda?",
        "El capón es un gallo castrado quirúrgicamente entre las 6-8 semanas de vida. Se sacrifica a los 210-300 días con 3.5-5.5 kg. La pularda es una gallina joven que no ha puesto huevos, engordada en épinette durante 4 semanas (1 semana menos que el capón). La pularda es típicamente más pequeña (2.5-3.5 kg) pero con carne muy tierna y un infiltrado graso más delicado. Ambos productos son premium (12-25 €/kg) frente al pollo industrial (3-5 €/kg). La diferencia clave: el capón no produce hormonas masculinas tras la caponización, lo que permite un engrasamiento intramuscular superior y un temperamento dócil que reduce el estrés y mejora la calidad de la carne."
    ),
]

# ============================================================
# GENÉTICA CRUZADA / EPDs / FarmMatch (~20 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cómo calcula NeoFarm el coeficiente de consanguinidad de Wright?",
        "NeoFarm implementa el algoritmo tabular de Meuwissen & Luo (1992) para calcular el coeficiente de consanguinidad F de Wright. La fórmula base es F = Σ(1/2)^(n1+n2+1) × (1 + FA), donde n1 y n2 son las generaciones desde cada padre al ancestro común, y FA es la consanguinidad de ese ancestro. La complejidad es O(n²) sobre la matriz de parentesco. Se exige un mínimo de 3 generaciones de pedigree (5 ideal) para resultados fiables. Los umbrales de alerta son: porcino industrial (<6.25% verde, 6.25-12.5% amarillo, >12.5% rojo), ibérico puro (<10% verde, 10-20% amarillo, >20% rojo), vacuno extensivo (<8% verde)."
    ),
    make(
        "¿Cómo calcula NeoFarm los EPDs simplificados?",
        "El cálculo simplificado de EPD (Expected Progeny Differences) en NeoFarm usa la fórmula: EPD_r = h² × (P_i − μ_grupo) / 2, donde h² es la heredabilidad del carácter, P_i es el fenotipo individual y μ_grupo es la media del grupo contemporáneo. Para vacuno, las heredabilidades clave son: peso nacimiento h²=0.40, peso destete h²=0.25, fertilidad h²=0.05-0.10, facilidad de parto h²=0.12. Para porcino: GMD h²=0.30, FCR h²=0.25, prolificidad h²=0.10, robustez inmune h²=0.15. Si hay datos genómicos (SNP >50K), se integra con: EPD_final = EPD_fenotípico × w1 + GE-EPD × w2, dando más peso (w2) al genómico."
    ),
    make(
        "¿Qué es el Índice de Mérito Económico (IME) en genética ganadera?",
        "El Índice de Mérito Económico (IME) pondera los EPDs según el valor económico de cada carácter. Los pesos varían por sistema productivo: para vacuno extensivo: fertilidad 30%, facilidad parto 20%, peso destete 25%, resiliencia 15%, longevidad 10%. Para porcino intensivo: FCR 35%, GMD 25%, prolificidad 15%, robustez inmune 15%, uniformidad 10%. NeoFarm calcula el IME automáticamente para cada animal y lo usa en el solver de apareamiento (FarmMatch) para maximizar el progreso genético. El objetivo del solver es: Max Σ(IndiceGenetico_cría) − λ × Σ(F_cría), donde λ controla la penalización por consanguinidad."
    ),
    make(
        "¿Cómo funciona el solver de apareamiento FarmMatch?",
        "FarmMatch es el motor de optimización de apareamientos de NeoFarm. Para poblaciones pequeñas usa el Algoritmo Húngaro (asignación óptima en O(n³)), y para cooperativas grandes usa MILP (programación lineal mixta entera) con el solver HiGHS (open source). La función objetivo es: Max Σ(IndiceGenetico_cría) − λ × Σ(F_cría), que maximiza el progreso genético (suma de IME de la descendencia esperada) penalizado por la consanguinidad esperada. Las restricciones incluyen: un macho máximo N hembras, evitar cruces con F > umbral (variable por especie), respetar fechas de disponibilidad, y opcionalmente priorizar rasgos específicos."
    ),
    make(
        "¿Qué rendimiento canal da el cruce Avileña × Limusina comparado con Avileña pura?",
        "El cruce Avileña × Limusina alcanza un rendimiento canal del 60-63%, significativamente superior al 55-58% de la Avileña pura. Esto se debe a que la Limusina aporta conformación muscular superior (típicamente clasificación EUROP 'U'). En términos económicos, la diferencia de clasificación EUROP es sustancial: categoría U = 7.5 €/kg canal, R = 7.2 €/kg, O = 6.5 €/kg. Para un añojo de 250 kg canal, pasar de O a U supone ~250 EUR más por animal. Los añojos (<24 meses) se pagan 7.0-7.5 €/kg canal, mientras que los novillos (>24 meses) caen a ~5.0 €/kg, una penalización fuerte que determina la edad óptima de sacrificio."
    ),
    make(
        "¿Qué paneles genómicos usa NeoFarm para selección?",
        "NeoFarm integra varios paneles de SNPs según especie: para bovino, GGP-9K (panel económico de screening), GGP-100K (panel estándar para selección) e Igenity Beef (panel orientado a valor comercial). Para porcino, SNP 60K (panel estándar de industria) y Neogen (alternativa competitiva). La integración genómica sigue la fórmula: EPD_final = EPD_fenotípico × w1 + GE-EPD × w2, donde si hay >50K SNPs, el peso genómico (w2) domina sobre el fenotípico (w1). Para avicultura se calcula GEBV con la fórmula VanRaden 2008: G = ZZ'/Σ(2p(1-p)), y la exactitud del valor de cría se estima como: r = sqrt(n × h² / (1 + (n-1) × h²/4))."
    ),
    make(
        "¿Qué es la heterosis y cómo la calcula NeoFarm?",
        "La heterosis (o vigor híbrido) es la superioridad del cruce F1 respecto a la media de los padres. NeoFarm la calcula con: Heterosis_trait = H_base_trait × DistanciaGenética(R1, R2), donde mayor distancia genética produce mayor efecto heterótico. En avicultura, los valores base son: crecimiento +15%, FCR +12%, resistencia a enfermedades +20%, tolerancia al estrés +18%, calidad de carne +10%, pero fertilidad -5% (excepción negativa). La fórmula F1 específica es: F1 = media_parental + |EBV_a - EBV_b| × factor_heterosis, con factor 0.15 para peso y 0.10 para otros caracteres. Por eso en capones se cruzan razas de grupos diferentes (Sabor × Estructura) para maximizar el efecto."
    ),
    make(
        "¿Cuál es la estrategia de centinelas en vacuno extensivo?",
        "En vacuno extensivo, NeoFarm no instrumenta todo el rebaño — usa la estrategia de centinelas: 10-20 animales representativos equipados con collares/crotales GPS + acelerómetro. Estos centinelas transmiten posición GPS cada 5-30 minutos, datos de actividad por acelerómetro, rumiación (si el hardware lo soporta), y opcionalmente temperatura corporal. La infraestructura de comunicación usa 2-3 gateways LoRa solares con baterías LiFePO4, backhaul por satélite de baja banda ancha, y diseño offline-first (si no hay cobertura, los datos se bufferizan localmente). El coste de instrumentar 15 centinelas es muy inferior a equipar un rebaño de 200 animales."
    ),
    make(
        "¿Qué diferencia hay entre el Algoritmo Húngaro y MILP para apareamientos?",
        "Son dos solvers para el mismo problema (asignación óptima de apareamientos), pero para escalas diferentes. El Algoritmo Húngaro resuelve asignación bipartita en O(n³) — óptimo para rebaños pequeños (<100 animales) donde cada macho se asigna a un grupo definido de hembras. MILP (Mixed Integer Linear Programming) con HiGHS permite restricciones complejas: un macho con N hembras máximo, restricciones temporales, priorización de rasgos, límites de consanguinidad por subgrupo. Es mejor para cooperativas con múltiples rebaños (>500 animales). NeoFarm usa HiGHS porque es open source, rápido, y el mismo solver se usa en formulación de raciones (LP nutricional con 20-40 restricciones por fase)."
    ),
    make(
        "Tengo un rebaño Avileña-Negra Ibérica puro. ¿Merece la pena cruzar con Limusina?",
        "La decisión depende de tu objetivo. El cruce Avileña × Limusina sube el rendimiento canal de 55-58% a 60-63%, lo que mejora la clasificación EUROP (de O/R a R/U) y el precio de canal: categoría U paga 7.5 €/kg vs O a 6.5 €/kg. Para un añojo de 250 kg canal, eso son ~250 EUR más por animal. Sin embargo, perderás rusticidad y adaptación a la dehesa de la Avileña pura. Mi recomendación: mantén un núcleo de Avileña pura para reposición (hembras reproductoras) y cruza los machos Limusina sobre hembras Avileña comerciales para producir añojos de cebo con mejor conformación. Sacrifícalos antes de 24 meses — los novillos (>24 meses) caen a ~5.0 €/kg, una penalización severa. NeoFarm puede calcular el IME y la consanguinidad esperada para optimizar estos cruces con FarmMatch."
    ),
    make(
        "¿Cuáles son las diferencias de heredabilidad entre porcino y vacuno?",
        "Las heredabilidades difieren significativamente entre especies. Vacuno: peso nacimiento h²=0.40 (alta), peso destete h²=0.25 (media), facilidad de parto h²=0.12 (baja), fertilidad h²=0.05-0.10 (muy baja). Porcino: ganancia media diaria h²=0.30 (media), índice de conversión h²=0.25 (media), prolificidad h²=0.10 (baja), robustez inmune h²=0.15 (baja). La implicación práctica: en vacuno, seleccionar por peso al nacimiento es muy efectivo (h² alta), pero seleccionar por fertilidad es casi inútil por selección individual — requiere evaluación de progenie con muchas hijas. En porcino, el progreso más rápido se obtiene en FCR y GMD. Para caracteres con h² baja, la heterosis por cruzamiento es más efectiva que la selección pura."
    ),
]

# ============================================================
# GeoTwin / GIS / Cesium (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué stack tecnológico usa GeoTwin de NeoFarm?",
        "GeoTwin usa: frontend Next.js 14 + CesiumJS 1.113 + React 18 + Tailwind CSS 3, backend Fastify 4 + Turf.js 6 + fast-xml-parser. Para terreno usa MDT02 del CNIG con resolución de 2 metros (fallback: Cesium World Terrain a ~30 m). Imágenes de satélite: PNOA ortofoto del IGN España como capa principal, Bing Maps como alternativa. Índices de vegetación: Copernicus Sentinel-2 L2A con NDVI a 10 m de resolución y revisita cada 5 días (combinando Sentinel-2A/B). La cadena de fallback de terreno es: MDT02 (12s timeout) → Cesium World Terrain (12s timeout) → Elipsoide (siempre funciona)."
    ),
    make(
        "¿Qué sistema de coordenadas usa NeoFarm en España?",
        "NeoFarm utiliza el sistema UTM ETRS89 con el huso correspondiente a cada zona de España: EPSG:25828 (UTM 28N) para Canarias, EPSG:25829 (UTM 29N) para Galicia y Portugal, EPSG:25830 (UTM 30N) para España central — el más común —, y EPSG:25831 (UTM 31N) para Cataluña y Baleares. CesiumJS trabaja internamente en WGS84 (EPSG:4326), así que las conversiones son automáticas. GeoTwin incluye una heurística de auto-detección: si X > 100,000 y Y > 4,000,000, asume UTM y calcula el huso. Todas las geometrías se almacenan en coordenadas UTM para operaciones métricas (áreas, distancias) y se proyectan a WGS84 solo para visualización."
    ),
    make(
        "¿Cómo calcula GeoTwin el NDVI de una parcela?",
        "GeoTwin calcula el NDVI a partir de las bandas de Copernicus Sentinel-2 L2A con la fórmula: NDVI = (B08 - B04) / (B08 + B04), donde B08 es el infrarrojo cercano (NIR) y B04 es el rojo, ambos con 10 m de resolución. El resultado se genera como PNG de 512×512 px con una rampa de colores. Los filtros de calidad exigen >70% de cobertura útil y ≤30% de nubes. La interpretación: <0.0 = agua/suelo desnudo/nieve, 0.0-0.2 = suelo desnudo/roca, 0.2-0.4 = vegetación dispersa/pasto seco, 0.4-0.6 = vegetación moderada/pasto verde, 0.6-0.8 = vegetación densa/cultivos activos, >0.8 = vegetación muy densa/bosque. GeoTwin también soporta EVI, NDWI, SAVI y BSI para análisis más específicos."
    ),
    make(
        "¿Qué índices de vegetación soporta GeoTwin además del NDVI?",
        "GeoTwin calcula 5 índices espectrales: 1) NDVI = (NIR-RED)/(NIR+RED) — vegetación general. 2) NDWI = (GREEN-NIR)/(GREEN+NIR) — contenido hídrico de la vegetación, útil para detectar estrés hídrico. 3) EVI = 2.5×(NIR-RED)/(NIR+6×RED-7.5×BLUE+1) — vegetación mejorada, corrige saturación del NDVI en zonas muy verdes. 4) SAVI = ((NIR-RED)/(NIR+RED+L))×(1+L) — ajustado al suelo, mejor en zonas con suelo visible (L=0.5 típico). 5) BSI = ((SWIR+RED)-(NIR+BLUE))/((SWIR+RED)+(NIR+BLUE)) — índice de suelo desnudo, detecta erosión. Todos se calculan desde Sentinel-2 L2A con revisita de 5 días."
    ),
    make(
        "¿Cómo se configuran las cámaras 3D en CesiumJS para GeoTwin?",
        "La configuración estándar de cámara en GeoTwin es: heading 315° (vista isométrica), pitch -38°, rango de zoom 50 m – 80,000 m. El movimiento flyTo usa easing sinusoidal con duración de 2.8 s por defecto. Anti-aliasing: FXAA + MSAA 4×. Screen space error: 1.0 (máximo detalle). Sombras suaves habilitadas. Depth testing contra terreno activado. El tiempo está congelado en 2026-06-15T09:30:00Z (iluminación matinal ~45° para buenas sombras). Para explotaciones de montaña se usa exageración de terreno 2.0×, dehesa 1.0× (sin exageración), Mediterráneo 1.2×."
    ),
    make(
        "¿Cómo gestiona GeoTwin los assets 3D?",
        "GeoTwin usa un pipeline BlenderGIS para assets 3D con convenciones estrictas: nomenclatura {tipo}_{subtipo}_{lod}.glb, escala 1 unidad Blender = 1 metro, origen en el centro de la base del modelo. Tres niveles de detalle: LOD0 = 50K polígonos máximo (vista cercana), LOD1 = 10K (vista media), LOD2 = 2K (vista lejana). Materiales PBR Principled BSDF con máximo 2 texturas por asset. Compresión: Draco (reduce geometría ~70%) o meshopt. Los assets incluyen naves ganaderas, silos, cercas, puntos de agua, caminos y vegetación. Se cargan en CesiumJS posicionados en UTM y convertidos a Cartesian3 para renderizado."
    ),
    make(
        "¿Qué es el THI y cómo lo calcula GeoTwin?",
        "El THI (Temperature-Humidity Index) es un índice de estrés térmico calculado como: THI = (1.8 × T + 32) − (0.55 − 0.0055 × HR) × (1.8 × T − 26), donde T es temperatura en °C y HR es humedad relativa en %. Las zonas de alerta son: confort (THI <72), alerta (72-79), peligro (79-89), y emergencia (≥89). GeoTwin calcula el THI en tiempo real a partir de los sensores IoT ambientales y lo visualiza como un mapa de calor sobre el terreno 3D. Cuando el THI entra en zona de peligro, se activan alertas automáticas vía MQTT para ajustar ventilación, refrigeración o activar sistemas de spray."
    ),
    make(
        "¿Cómo simula GeoTwin la propagación de incendios?",
        "GeoTwin incluye un simulador de incendios basado en autómata celular de propagación. El modelo toma como inputs: dirección y velocidad del viento, pendiente del terreno (del MDT02), y NDVI (vegetación seca = más combustible). El resultado es un perímetro temporal de propagación que se renderiza como raster/isolíneas en CesiumJS. Sirve como herramienta de planificación preventiva: el ganadero ve cómo se propagaría un incendio desde cualquier punto de ignición y puede diseñar cortafuegos, rutas de evacuación del ganado, y ubicaciones seguras. Para explotaciones extensivas en dehesa, esto es crítico en los meses de verano."
    ),
    make(
        "¿Qué simulaciones de dispersión de gases incluye GeoTwin?",
        "GeoTwin incluye un simulador de dispersión de gases atmosféricos basado en el modelo de pluma gaussiana (Gaussian plume). Los inputs son: fuentes de emisión (fosas de purines, naves ganaderas), velocidad y dirección del viento, y estabilidad atmosférica. El output es un mapa de calor direccional + isolíneas de concentración renderizados en CesiumJS sobre el terreno 3D. Esto permite evaluar el impacto de las emisiones de NH3, H2S y CH4 en parcelas vecinas y zonas habitadas, cumpliendo con los requisitos del plan de Emisiones del SIGE (RD 306/2020). También permite planificar la ubicación óptima de nuevas naves minimizando el impacto ambiental."
    ),
    make(
        "¿Qué métricas ESG calcula GeoTwin?",
        "GeoTwin calcula las siguientes métricas ESG (Environmental, Social, Governance): CH4 (entérico + purines) en CO2 equivalente, N2O del suelo y purines, consumo energético por plaza, huella hídrica por kg producido, y secuestro de carbono (pastizales + arbolado). Además, modela escenarios de mejora: el aditivo 3-NOP reduce CH4 entérico un -30%, un biodigestor anaerobio reduce CH4 de purines un -60%, paneles solares reducen CO2 energético un -40%, y el pastoreo rotacional secuestra +200 kg CO2/ha/año. Estas métricas permiten al ganadero cuantificar su huella y acceder a créditos de carbono o certificaciones de sostenibilidad."
    ),
    make(
        "¿Cómo funciona GeoTwin sin conexión a internet?",
        "GeoTwin sigue un diseño offline-first. El twin store (twinStore.ts) persiste datos en localStorage del navegador. Se puede importar/exportar la configuración completa como JSON drag-and-drop. En la caseta de la explotación, el procesamiento edge se ejecuta localmente con un buffer + retries automáticos en el gateway. Las capas de mapa base se pre-cachean y los cálculos de NDVI se almacenan localmente. Cuando se recupera conectividad, se sincronizan las novedades. El fallback de terreno (MDT02 → Cesium WT → Elipsoide) garantiza que siempre hay un terreno 3D disponible, aunque con menor resolución. Los assets de Cesium Ion (Bing Maps ID 2, MDT02 Spain ID 4475569) se cachean agresivamente en el navegador."
    ),
]

# ============================================================
# Digital Twins / IoT avanzado (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cómo calcula el Digital Twin Porcino el riesgo respiratorio?",
        "El Digital Twin Porcino calcula el riesgo respiratorio combinando señales de múltiples capas IoT: NH3 (ppm), actividad respiratoria acústica (ReHS — Respiratory Health Status), consumo de agua, temperatura/humedad ambiente, y PM2.5 (partículas finas). La función del twin es: Twin_Productivo_Nave = f(numero_animales, edad_lote, temperatura, humedad, NH3, consumo_agua, consumo_pienso, actividad, mortalidad_acumulada). El output incluye IC estimado en tiempo real, peso proyectado, fecha óptima de envío a matadero, riesgo respiratorio en %, impacto económico en €/lote, e índice de bienestar dinámico. Un ejemplo: caída de consumo de agua del -18% activa una alerta con probabilidad de brote respiratorio del 63% e impacto estimado de -3.200€ si no se interviene."
    ),
    make(
        "¿Qué es el ReHS y cómo funciona la detección acústica de tos?",
        "El ReHS (Respiratory Health Status) es la métrica de salud respiratoria basada en la capa acústica de PorciData. Usa un micrófono INMP441 + ESP32-S3 (~15 EUR/nave) que analiza ventanas de audio de 1-5 segundos, clasificando eventos de tos y los agrega por hora. Los umbrales son: verde (ReHS >60%, nave sana), ámbar (40-60%, vigilar), rojo (<40%, intervenir). La referencia comercial es SoundTalks (>3.000 EUR): sus datos muestran que la detección acústica permite intervención 2.6 días más rápida, reduce antibióticos un -28%, y mejora la ganancia media diaria en +12.7 g/día. PorciData ofrece funcionalidad similar a 15 EUR/nave, un factor 200× más barato."
    ),
    make(
        "¿Qué es la nariz electrónica BME688 y por qué es innovadora en porcino?",
        "La nariz electrónica (e-nose) de PorciData usa el sensor BME688 + SPS30 + ESP32 (~50 EUR/nave) para medir H2S, PM2.5, VOCs y otros compuestos volátiles. Es innovadora porque NO existen publicaciones científicas anteriores del uso de BME688 en granjas porcinas — NeoFarm es la primera. El sensor requiere un burn-in de 48 horas y 4-8 semanas de datos etiquetados para calibración. Detecta patrones de VOCs que se correlacionan con problemas de salud antes que los síntomas visibles. Se combina con NH3 ambiental (ideal 10-25 ppm) para el plan de Emisiones del SIGE. Es una de las 3 capas exclusivas de PorciData que no ofrece ningún competidor comercial."
    ),
    make(
        "¿Qué capas IoT son exclusivas de PorciData frente a la competencia?",
        "PorciData tiene 3 capas que son primera mundial en porcino comercial: 1) Capa 5 — Agua: caudalímetro + pH + ESP32 (~80 EUR/nave), monitorizando consumo y calidad de agua por nave/corral, sin equivalente comercial a este precio. 2) Capa 6 — Nariz electrónica: BME688 + SPS30 (~50 EUR/nave), primera aplicación científica de e-nose BME688 en porcino. 3) Capa 7 — Radar mmWave: Seeed MR60BHA1 60 GHz (~25 EUR/nave), primera vez que se usa radar milimétrico para monitorizar respiración y actividad en cerdos. En total, las 7+1 capas cuestan ~1.420 EUR/nave, 10× más barato que soluciones comerciales de Fancom/Nedap (>14.500 EUR/nave)."
    ),
    make(
        "¿Cómo funciona el Digital Twin Vacuno de NeoFarm?",
        "El Digital Twin Vacuno modela el territorio completo de la explotación extensiva: Twin_Extensivo = f(clima, actividad_centinelas, agua_abrevaderos, uso_parcelas, reproduccion). Usa la estrategia de centinelas: 10-20 animales representativos con GPS (lectura cada 5-30 min) + acelerómetro + rumiación. La infraestructura son 2-3 gateways LoRa solares con baterías LiFePO4 y backhaul por satélite. A diferencia del twin porcino (que modela la nave), el twin vacuno modela el uso del territorio: qué parcelas están sobrepastoreadas (NDVI bajando), dónde se concentra el ganado, tiempos de rumiación por zona, y estrés térmico por THI. Todo con diseño offline-first para dehesas sin cobertura móvil."
    ),
    make(
        "¿Qué anomalías detecta el Digital Twin con los datos de agua?",
        "La detección de anomalías en consumo de agua usa CUSUM (Cumulative Sum) y STL (Seasonal and Trend decomposition using Loess) + z-score por corral/lote. El agua es el indicador más temprano de problemas de salud: una caída de -15% a -20% en el consumo de agua precede a síntomas visibles en 24-48 horas. El twin combina esta señal con NH3, tos (ReHS), y temperatura. Ejemplo real del sistema de alertas: 'Evento: Caída consumo agua -18%. Probabilidad brote respiratorio: 63%. Impacto estimado si no intervenir: -3.200€. Recomendación: Revisión calidad agua + ajuste ventilación.' La prioridad de implementación es alta: agua + T/RH + NH3 son los primeros 14 días del despliegue."
    ),
    make(
        "¿Cuál es la hoja de ruta de implementación IoT de 0 a 90 días?",
        "La implementación IoT de NeoFarm sigue 3 fases: Días 0-14 (mínimo viable): instalar sensores de T/RH + NH3 ambiental + caudalímetro de agua, definir topics MQTT (neofarm/{farm_id}/{barn_id}/{layer}/{sensor_type}), conexión a InfluxDB. Días 15-45 (dashboards): crear dashboards en Grafana para ambiente, agua y energía, configurar alertas por umbral (NH3 >25 ppm, agua -15%, T fuera de rango). Días 46-90 (primer modelo de anomalía): entrenar el primer modelo CUSUM/STL sobre agua o tos, crear playbooks de actuación (alerta → diagnóstico → acción → verificación). No intentar hacerlo todo a la vez: cada capa se añade incrementalmente después de validar la anterior."
    ),
    make(
        "¿Cómo se estructura un topic MQTT en NeoFarm?",
        "El patrón estándar de topics MQTT en NeoFarm es: neofarm/{farm_id}/{barn_id}/{layer}/{sensor_type}. Ejemplo: neofarm/granja01/nave03/environmental/temperature para la temperatura de la nave 3 de la granja 01. Las capas (layer) corresponden a las 7+1 capas de PorciData: acoustic, vision_rgb, vision_thermal, environmental, water, enose, radar, weight. Los mensajes se publican en JSON con timestamp, valor, unidad y metadata del sensor. El broker es Mosquitto (:1883) en Docker. Node-RED (:1880) se encarga de las transformaciones y reglas de negocio antes de escribir en InfluxDB. El patrón permite filtrar por granja, nave o tipo de sensor usando wildcards MQTT: neofarm/granja01/+/environmental/#."
    ),
    make(
        "¿Qué ventajas tiene Mioty sobre LoRa para IoT ganadero?",
        "Mioty supera a LoRa en varios aspectos críticos para ganadería: capacidad de 44.000 paquetes/min/MHz al 10% PER, superando a LoRa SF12 por >1.000× en capacidad. Soporta >1.5 millones de telegramas/día/estación base (vs miles en LoRaWAN/Sigfox). La vida de batería es 3× superior a LoRa. Bajo interferencia, LoRa pierde >20% de paquetes mientras Mioty mantiene integridad total gracias a su FEC que reconstruye el mensaje con solo la mitad de los bursts transmitidos. Seguridad: AES-128 + CMAC 32-bit + contador anti-replay de 24-bit. En un piloto real con Duroc × Ibérico en Extremadura (2.354 cerdos), el sistema IoT con Mioty demostró mejoras de +5-10% en GMD (de 0.375 a 0.413 kg/día) y un aumento de beneficio del +6.36%."
    ),
    make(
        "¿Qué resultados dio el piloto IoT de Mioty en Extremadura?",
        "El piloto IoT con tecnología Mioty se realizó en una explotación de Duroc × Ibérico en Extremadura con un lote de 2.354 cerdos. Tras 35 días, quedaron 2.319 animales con una ganancia media diaria de 0.375 kg/día y un índice de procesamiento de 1.5123 kg pienso/kg carne. Los ingresos brutos fueron 124.709-129.562€ (a 2.56-2.66 €/kg, referencia septiembre 2024). Con las mejoras IoT (ajuste de ventilación, alimentación precisa, detección temprana), se estima una mejora de +5-10% en GMD hasta 0.413 kg/día, con un total de 51.609 kg de peso vivo e ingresos de 132.636-137.797€ — un incremento de beneficio del 6.36%. Esto demuestra el ROI directo de la monitorización IoT."
    ),
]

# ============================================================
# Nutrición avanzada (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué es el butirato sódico y por qué se usa en nutrición porcina?",
        "El butirato sódico (C₄H₇NaO₂) es un ácido graso de cadena corta con solubilidad >330 g/L y punto de fusión 250-253°C. En nutrición porcina actúa como promotor de la salud intestinal: refuerza las tight junctions (uniones estrechas) del epitelio, estimula la producción de IgA (inmunoglobulina A), y modula citoquinas proinflamatorias como TNF-α y IL-6. Su uso se integra con la capa 6 de PorciData (nariz electrónica BME688): si el score de VOCs es alto y el NH3 también está elevado, el sistema sugiere considerar suplementación con butirato para mejorar la salud intestinal y reducir las emisiones amoniacales."
    ),
    make(
        "¿Cuánto ahorra usar enzimas NSP en piensos y cuándo se recomienda?",
        "Las enzimas NSP (Non-Starch Polysaccharide) generan un ahorro del 3-5% en el coste de formulación del pienso cuando las dietas contienen más de un 15% de ingredientes fibrosos (salvado de trigo, DDGS, pulpa de remolacha, etc.). Estas enzimas degradan los polisacáridos no amiláceos que reducen la digestibilidad del alimento. El solver LP de NeoFarm (HiGHS open source) incorpora automáticamente el efecto de las enzimas NSP como restricción: si se activa la variable 'enzimas_nsp = true', se corrige la matriz de energía digestible de los ingredientes fibrosos, permitiendo incluir más materia prima barata sin sacrificar el rendimiento productivo del animal."
    ),
    make(
        "¿Cómo funciona la auto-reformulación de dieta por señal IoT?",
        "NeoFarm integra los datos IoT con la formulación nutricional mediante reglas automáticas. Cuando los sensores detectan temperatura alta (estrés calórico, THI >72), el sistema recomienda aumentar la energía neta +10% y la lisina +15% en la ración, porque los animales reducen consumo voluntario pero sus necesidades proteicas se mantienen. El solver LP (HiGHS) recalcula la formulación óptima con las nuevas restricciones, respetando los 20-40 constraints nutricionales por fase (aminoácidos, energía, minerales, fibra, calcio/fósforo). La nueva formulación se envía como recomendación al sistema de alimentación o directamente al ganadero vía app."
    ),
    make(
        "¿Qué solver usa NeoFarm para formular raciones y cuántas restricciones maneja?",
        "NeoFarm utiliza HiGHS como solver de programación lineal (LP), que es open source y soporta LP, MIP y QP. También tiene la opción de javascript-lp-solver vía WASM para cálculos en el navegador. Una formulación típica tiene 20-40 restricciones nutricionales por fase: energía neta/metabolizable, aminoácidos esenciales (lisina, metionina, treonina, triptófano), calcio, fósforo disponible, sodio, cloro, fibra bruta máxima, grasa máxima, etc. El mismo solver HiGHS se usa también en el motor genético FarmMatch para optimización de apareamientos con MILP. Las referencias de precios de materias primas se obtienen de la Lonja del Ebro (cereales), Mercolleida (porcino) y Lonja de Segovia (vacuno/ovino)."
    ),
    make(
        "¿Qué niveles de NH3 son aceptables en una nave porcina?",
        "El rango óptimo de NH3 en una nave porcina es 10-25 ppm. Por debajo de 10 ppm es excelente (buena ventilación). Entre 10-25 ppm es aceptable según la normativa. Por encima de 25 ppm se activa una alerta y se debe aumentar la ventilación. Por encima de 50 ppm hay riesgo grave para salud animal y humana. El RD 1135/2002 establece el nivel máximo legal en 25 ppm. PorciData monitoriza NH3 continuamente con la capa 4 (Dragino LoRa + Renke, ~200 EUR/nave) y la capa 6 (BME688 e-nose, ~50 EUR). Cuando NH3 supera el umbral + tos acústica (ReHS <60%) + caída de agua >15%, el Digital Twin calcula la probabilidad de brote respiratorio."
    ),
    make(
        "¿De dónde obtiene NeoFarm los precios de referencia de materias primas?",
        "NeoFarm obtiene precios de referencia de 3 lonjas principales: Mercolleida para referencia nacional porcina (cotización semanal del cerdo de cebo, lechón, etc.), Lonja de Segovia para vacuno y ovino (cotización semanal de terneros, añojos, corderos), y Lonja del Ebro para cereales y materias primas (trigo, cebada, maíz, soja, etc.). Los datos se capturan automáticamente vía el Worker Web/Automation usando APIs cuando están disponibles o Playwright para web scraping ético. Los precios alimentan tanto el solver de formulación (coste mínimo de la ración) como el módulo económico del Digital Twin (cálculo de margen por lote)."
    ),
]

# ============================================================
# Normativa / SIGE / Bienestar (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cuáles son los 11 planes obligatorios del SIGE según RD 306/2020?",
        "Los 11 planes obligatorios del Sistema Integral de Gestión de Explotaciones (SIGE) según el RD 306/2020 son: 1) Plan Sanitario, 2) Plan de Bioseguridad, 3) Plan de Limpieza, Desinfección y Desinsectación (LDD), 4) Plan de Gestión de Purines y Estiércol, 5) Plan de Bienestar Animal, 6) Plan de Alimentación, 7) Plan de Eficiencia Energética, 8) Plan de Gestión de Residuos, 9) Plan de Emisiones y Medio Ambiente, 10) Plan de Formación (mínimo 20 horas/año), y 11) Plan de Trazabilidad. NeoFarm puede auto-actualizar 7 de estos 11 planes usando los datos de los sensores IoT, reduciendo significativamente la carga administrativa del ganadero."
    ),
    make(
        "¿Cuántos m² por cerdo exige la normativa según peso?",
        "El RD 1135/2002 establece las superficies mínimas por cerdo según peso vivo: ≤10 kg = 0.15 m², 10-20 kg = 0.20 m², 20-30 kg = 0.30 m², 30-50 kg = 0.40 m², 50-85 kg = 0.55 m², 85-110 kg = 0.65 m², >110 kg = 1.00 m². Para cerdas gestantes en grupo (obligatorio desde la 4ª semana post-cubrición hasta 7 días antes del parto): grupos de ≥40 animales = 2.025 m²/cerda y 1.476 m²/primeriza; grupos de 6-39 animales = 2.250 m²/cerda y 1.640 m²/primeriza. El verraco necesita mínimo 6 m² (10 m² si hace monta natural). PorciData verifica automáticamente la densidad usando conteo por visión + área del corral."
    ),
    make(
        "¿Qué requisitos ambientales exige el RD 1135/2002 para naves porcinas?",
        "El RD 1135/2002 establece: ruido máximo 85 dB (continuo, no picos), iluminación mínima 40 lux durante 8 horas al día, NH3 máximo 25 ppm. La edad mínima de destete es 28 días (excepcionalmente 21 días si existe un problema sanitario justificado). PorciData monitoriza todas estas métricas automáticamente: la capa acústica (INMP441) mide nivel de ruido continuo, la capa ambiental (Dragino LoRa + Renke, ~200 EUR/nave) mide T/RH/NH3/CO2/luz, y la capa de agua (caudalímetro, ~80 EUR/nave) registra consumo. Los datos se comparan contra los umbrales legales y generan alertas automáticas + registros para inspección SIGE."
    ),
    make(
        "¿Qué es ECOGAN y cómo se aplica?",
        "ECOGAN es la herramienta oficial del MAPA (Ministerio de Agricultura, Pesca y Alimentación) para calcular emisiones de NH3 y gases de efecto invernadero en explotaciones ganaderas. Se implementa en 8 pasos: 1) Selección del tipo de explotación, 2) Censo animal, 3) Caracterización de naves, 4) Sistemas de alojamiento, 5) Gestión de estiércol/purines, 6) Alimentación, 7) Otras fuentes de emisión, 8) Resumen de emisiones y medidas de mitigación. NeoFarm integra ECOGAN en el plan 9 (Emisiones) del SIGE, alimentándolo automáticamente con datos IoT reales en lugar de los valores por defecto que normalmente se usan. Esto proporciona un cálculo de emisiones mucho más preciso y permite demostrar mejoras medibles."
    ),
    make(
        "¿Cuántos planes SIGE puede auto-actualizar NeoFarm con IoT?",
        "NeoFarm puede auto-actualizar 7 de los 11 planes SIGE obligatorios usando datos IoT: Plan Sanitario (ReHS acústico + alertas de salud del Twin), Bioseguridad (registros de acceso), LDD (programación automática), Bienestar (T/RH/NH3/luz/densidad monitorizadas en continuo), Alimentación (consumo de pienso y agua registrado), Eficiencia Energética (medidores de consumo eléctrico), y Emisiones (NH3/VOCs reales vs ECOGAN). Los 4 restantes requieren intervención humana parcial: Purines (requiere registro de vaciados), Residuos (parte administrativa), Formación (horas presenciales), y Trazabilidad (entradas/salidas de animales, aunque NeoFarm puede automatizar parte con RFID). El resultado: el ganadero ahorra horas de papeleo y tiene registros objetivos para inspecciones."
    ),
]

# ============================================================
# Cross-domain / Integración / Casos de uso reales (~20 ejemplos)
# ============================================================
new_examples += [
    make(
        "NH3 a 30 ppm, consumo de agua -20% y ReHS en 35%. ¿Qué hago?",
        "Esto es una alerta roja de posible brote respiratorio. El NH3 supera el máximo legal (25 ppm), el agua ha caído significativamente (-20%), y la salud respiratoria es crítica (ReHS <40%). Acciones inmediatas: 1) Aumentar ventilación para bajar NH3 por debajo de 25 ppm — verificar que los ventiladores estén al máximo y las entradas de aire libres. 2) Revisar calidad de agua — pH, caudal, posible obstrucción de bebederos. 3) Contactar al veterinario — con estos 3 indicadores simultáneos, la probabilidad de brote respiratorio es alta (~63% según datos históricos). 4) Según el Digital Twin de NeoFarm, no intervenir costaría ~3.200€/lote en mortalidad + retraso de crecimiento. 5) Registrar todo en el SIGE para cumplir con el Plan Sanitario (RD 306/2020). SoundTalks demostró que la intervención temprana basada en acústica reduce antibióticos un -28% y mejora la GMD en +12.7 g/día."
    ),
    make(
        "¿Cómo combina NeoFarm la genética con el IoT para mejorar el rendimiento?",
        "NeoFarm integra genética + IoT en un ciclo cerrado: 1) FarmMatch optimiza apareamientos según IME (Índice de Mérito Económico) y consanguinidad. 2) Los lechones nacen y IoT monitoriza su ambiente desde el primer día (T/RH/NH3/agua/peso). 3) El Digital Twin ajusta la predicción de IC (índice de conversión) y peso proyectado en tiempo real según los datos IoT. 4) Al sacrificio, los datos reales de canal (peso, clasificación EUROP, rendimiento) retroalimentan los EPDs de los padres. 5) El ciclo se cierra: los EPDs actualizados mejoran la próxima generación de apareamientos. Para vacuno: GPS centinelas + NDVI por parcela + datos de fertilidad retroalimentan los EPDs de facilidad de parto y peso destete. En un lote test con Mioty en Extremadura (2.354 cerdos Duroc × Ibérico), la integración IoT mejoró la GMD un +5-10%."
    ),
    make(
        "¿Cómo puede NeoFarm ayudarme a cumplir con el SIGE sin tanto papeleo?",
        "NeoFarm auto-actualiza 7 de los 11 planes SIGE obligatorios usando los sensores IoT. En lugar de registrar manualmente temperatura, humedad, NH3, consumo de agua, etc., los sensores de PorciData (~1.420 EUR/nave) capturan todo en continuo. Los datos se almacenan en InfluxDB, se visualizan en Grafana, y se exportan en formato compatible con SIGE. Para las inspecciones, puedes mostrar dashboards con datos reales en vez de hojas de cálculo rellenadas a mano. Además, el Digital Twin genera alertas automáticas cuando algún parámetro sale de norma (NH3 >25 ppm, ruido >85 dB, luz <40 lux, densidad excesiva), permitiendo que corrijas antes de la inspección. El plan de Formación (20h/año) y el de Residuos requieren registro manual, pero el resto es automatizable."
    ),
    make(
        "¿Cuánto cuesta PorciData frente a Fancom o Nedap?",
        "PorciData cuesta ~1.420 EUR por nave incluyendo las 7+1 capas de sensores IoT: acústica 15€, visión RGB 150€, térmica 550€, ambiental 200€, agua 80€, e-nose 50€, radar 25€, y peso walk-over 350€. Las alternativas comerciales cuestan 10× más: solo la capa de visión de Fancom iGrow supera los 3.000 EUR/nave, y la cámara térmica FLIR T1020 + software cuesta >5.000 EUR/nave. El stack completo de Fancom/Nedap supera los 14.500 EUR/nave. Además, PorciData incluye 3 capas exclusivas (agua inteligente, e-nose BME688, radar mmWave) que no ofrece ningún competidor. La estrategia de NeoFarm es posicionarse como capa IoT+IA que complementa los ERPs existentes (AgroVision, CloudFarms), no los reemplaza."
    ),
    make(
        "¿Puedo usar NeoFarm para una explotación mixta porcino + vacuno?",
        "Sí, NeoFarm está diseñado para explotaciones multi-especie. Para porcino intensivo usas PorciData (7+1 capas IoT, ~1.420 EUR/nave) con Digital Twin de nave: T/RH/NH3/agua/peso/visión → riesgo respiratorio, IC estimado, fecha óptima de envío. Para vacuno extensivo usas VacasData con centinelas GPS (10-20 animales) + GeoTwin (Cesium 3D + NDVI + THI) → uso de parcelas, estrés térmico, reproducción. Los módulos transversales sirven para ambas especies: Genética (FarmMatch calcula IME y consanguinidad por especie), Nutrición (HiGHS formula raciones con restricciones específicas), SIGE (los 11 planes aplican a ambas), y Trazabilidad. Todo se gestiona desde una sola interfaz en hub.vacasdata.com o la app móvil React Native."
    ),
    make(
        "¿Cuál es la arquitectura de 3 capas de NeoFarm?",
        "NeoFarm se estructura en 3 capas: 1) Capa Usuario: Next.js 14 + Tailwind + shadcn/ui (web app en hub.vacasdata.com) y React Native + Expo (app móvil). 2) Capa Inteligencia: FastAPI + PostgreSQL (backend), RAG con Qdrant + mxbai-embed-large (embeddings), LLM Seedy (fine-tuned Qwen2.5 via Together.ai producción / Ollama local fallback), motor genético FarmMatch, solver nutricional HiGHS, y 6 workers especializados en Open WebUI. 3) Capa IoT: ESP32/LoRa → MQTT (Mosquitto) → Node-RED → InfluxDB → Grafana. Los datos fluyen de abajo hacia arriba: sensores capturan → MQTT transporta → InfluxDB almacena → Digital Twin analiza → LLM explica → usuario actúa. La API es api-v2.vacasdata.com. NeoFarm se posiciona como capa de IoT+IA ENCIMA de ERPs existentes."
    ),
    make(
        "Quiero montar una explotación de capones extensivos con 500 aves. ¿Qué me recomiendas?",
        "Para 500 capones extensivos te recomiendo: 1) Raza: cruce ♂ Coucou de Malines × ♀ Faverolles ('Majestic') → capones de 4.5-5.5 kg, Capon Score ~80/100. 2) Instalación: nave con 11 aves/m² interior = ~46 m², parcela exterior mínimo 10 m²/ave = 5.000 m² (con rotación de parcelas). 3) Alimentación: 4 fases (arranque 22% PB, crecimiento 18%, pastoreo con 70%+ cereales, acabado en épinette con pâtée de maíz + leche). 4) Caponización: semanas 6-8, necesitas un operador con experiencia (tasa éxito 95-98%). 5) IoT NeoFarm (recomendado): cámara RGB para conteo + peso visual (~150 EUR), sensor ambiental (~200 EUR). 6) Comercialización: capones premium a 12-25 €/kg = ingresos brutos de 27.000-68.750€ (500 capones × 4.5 kg × 12-25 €/kg). Calendario: 210-300 días de ciclo, ideal para Navidad."
    ),
    make(
        "¿Cómo puede NeoFarm detectar estrés calórico antes de que afecte al ganado?",
        "NeoFarm detecta estrés calórico con múltiples capas: 1) Sensores ambientales (T/RH, ~200 EUR/nave) calculan el THI = (1.8×T+32) − (0.55−0.0055×HR) × (1.8×T−26). Zonas: confort (<72), alerta (72-79), peligro (79-89), emergencia (≥89). 2) Cámara térmica bi-espectro (~550 EUR/nave) detecta temperatura corporal individual sin contacto. 3) Radar mmWave (25 EUR/nave) detecta cambios en frecuencia respiratoria. 4) Consumo de agua (caudalímetro, 80 EUR/nave): el aumento de bebida es el primer síntoma. 5) Para vacuno extensivo, GeoTwin calcula THI por zona geoespacial combinando datos meteorológicos con NDVI (sombra de arbolado). El Digital Twin genera alertas proactivas ANTES de entrar en zona de peligro: 'THI previsto 78 en 3 horas → activar ventilación/spray a las 11:00'."
    ),
    make(
        "¿Qué datos necesita NeoFarm para empezar con el mínimo?",
        "El mínimo viable para empezar con NeoFarm en porcino es: 1) Sensor de T/RH + NH3 (capa ambiental, ~200 EUR/nave) → monitoriza las 3 variables más críticas del bienestar. 2) Caudalímetro de agua (~80 EUR/nave) → el indicador más temprano de problemas de salud. 3) Conexión: un ESP32 + WiFi o LoRa hacia un gateway con acceso a internet. Total: ~280 EUR/nave. Con estos 2 sensores ya puedes: monitorizar cumplimiento de NH3 <25 ppm (SIGE), detectar caídas de consumo de agua (alerta temprana), y tener un dashboard Grafana con datos reales para inspecciones. Después añades incrementalmente: acústica (15€), e-nose (50€), radar (25€), visión RGB (150€), térmica (550€), peso (350€). No hace falta instalar todo el BOM de 1.420 EUR desde el primer día."
    ),
    make(
        "¿Cómo se integra GeoTwin con el Digital Twin Porcino y Vacuno?",
        "GeoTwin es la capa geoespacial 3D que integra los digital twins específicos de cada especie. Para vacuno extensivo: GeoTwin visualiza en Cesium 3D las parcelas con NDVI (Sentinel-2, 10 m resolución), superpone las posiciones GPS de los centinelas (cada 5-30 min), calcula THI por zona, y muestra el uso real del territorio vs la capacidad de carga. Para porcino intensivo: GeoTwin posiciona las naves en el terreno 3D (MDT02, 2 m resolución), muestra indicadores de cada nave (semáforo ReHS, NH3, agua), y permite drill-down al Digital Twin de nave con datos en tiempo real. Los assets 3D (naves, silos, cercas) siguen el pipeline BlenderGIS con LOD0/LOD1/LOD2. También incluye simulaciones de impacto ambiental: dispersión de gases (pluma gaussiana) y propagación de incendios (autómata celular)."
    ),
    make(
        "¿Cómo puede NeoFarm ayudar a reducir la huella de carbono de una explotación?",
        "GeoTwin calcula las emisiones ESG y modela escenarios de mitigación concretos: 1) El aditivo 3-NOP reduce CH4 entérico un -30% (aplicable a vacuno). 2) Un biodigestor anaerobio reduce CH4 de purines un -60% (aplicable a porcino). 3) Paneles solares reducen CO2 de energía un -40%. 4) El pastoreo rotacional secuestra +200 kg CO2/ha/año (vacuno extensivo, medido por NDVI). NeoFarm cuantifica cada mejora en CO2 equivalente y €, permitiendo al ganadero: demostrar mejoras para inspecciones ambientales, acceder a créditos de carbono, cumplir requisitos de sostenibilidad de distribuidores, y solicitar ayudas de la PAC vinculadas a eco-esquemas. Todo basado en datos IoT reales, no estimaciones genéricas de ECOGAN."
    ),
]

# ============================================================
# Meta-Seedy / Infraestructura / Docker (~10 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué es Seedy y cómo se relaciona con NeoFarm?",
        "Seedy es el sistema de inteligencia artificial de NeoFarm. Es un LLM fine-tuned (basado en Qwen2.5 + LoRA) con RAG (Qdrant + mxbai-embed-large) y 6 workers especializados en Open WebUI. Seedy NO es NeoFarm: NeoFarm es la plataforma IoT + SaaS (sensores, hub.vacasdata.com, app móvil). Seedy es el cerebro de IA que asiste a NeoFarm. Los dominios de Seedy son: IoT ganadero (PorciData), nutrición animal (NRC 2012, HiGHS), genética aplicada (EPDs, FarmMatch), normativa SIGE (RD 306/2020), Digital Twins, GIS/GeoTwin (Cesium 3D), Computer Vision (YOLO, TensorRT) y economía agropecuaria. Seedy corre en una MSI Vector 16 HX (RTX 5080 16GB, 64GB RAM) con Docker y está accesible en seedy.neofarm.io."
    ),
    make(
        "¿Qué hardware necesita Seedy para funcionar?",
        "Seedy funciona en una MSI Vector 16 HX con RTX 5080 16GB VRAM, 64GB RAM, Ubuntu 24.04. Todo corre en Docker (red ai_default): Ollama (:11434) con GPU para el modelo LLM (~8.5 GB en VRAM con Q4_K_M 14B), Open WebUI (:3000) como interfaz web, Qdrant (:6333) para vectores RAG, FastAPI backend (:8000), InfluxDB (:8086), Mosquitto (:1883), Node-RED (:1880), Grafana (:3001), y un tunnel Cloudflare para acceso remoto. La producción usa Together.ai para inference 24/7 (~0.25 EUR/mes), con Ollama local como fallback. Los embeddings (mxbai-embed-large, 669 MB) y el reranker (bge-reranker-v2-m3) son 100% locales. Con 16GB de VRAM, Seedy puede ejecutar un 14B Q4_K_M y mxbai-embed-large simultáneamente."
    ),
    make(
        "¿Cuántas colecciones RAG tiene Seedy y qué contienen?",
        "Seedy tiene 8 colecciones de conocimiento en Qdrant/Open WebUI: 1) PorciData — IoT & Hardware: BOM 7+1 capas, sensores, firmware ESP32. 2) Nutrición & Formulación: butirato, enzimas NSP, NRC 2012, solver LP HiGHS, lonjas. 3) Genética: Wright, EPDs, FarmMatch, razas autóctonas. 4) Estrategia & Competencia: Fancom vs Nedap, posicionamiento. 5) Digital Twins & IoT: twins porcino/vacuno, Mioty vs LoRa, playbooks. 6) Normativa & SIGE: RD 306/2020 (11 planes), ECOGAN, RD 1135/2002. 7) Avicultura & Capones: Coucou de Malines, Bresse, caponización, Label Rouge, cruces. 8) GeoTwin & GIS 3D: Cesium, PNOA, MDT02, NDVI, THI, simulaciones. Los parámetros RAG son: chunk 1500/300, Top K=8, búsqueda híbrida con BM25 weight 0.7, relevance threshold 0.25."
    ),
    make(
        "¿Cómo puedo acceder a Seedy desde fuera de la red local?",
        "Seedy está expuesto a internet mediante un tunnel Cloudflare con autenticación: seedy.neofarm.io para Open WebUI (interfaz de chat con los 6 workers), seedy-api.neofarm.io para la API FastAPI (endpoint /chat SSE + /health), y seedy-grafana.neofarm.io para los dashboards IoT de Grafana. El tunnel se ejecuta en Docker y usa un token (variable TUNNEL_TOKEN en .env). También puedes acceder desde la app móvil React Native (que apunta a seedy-api.neofarm.io por defecto). Nota: el wildcard DNS *.neofarm.io solo cubre un nivel de subdominio, por eso se usan guiones (seedy-api, seedy-grafana) en vez de puntos (api.seedy). Tailscale también está activo para acceso directo a IPs internas en desarrollo."
    ),
    make(
        "¿Qué modelo LLM usa Seedy y cómo se actualizó?",
        "Seedy usa Qwen2.5-7B-Instruct como modelo base, fine-tuned con LoRA en Together.ai. Lleva 6 versiones: v3 (200 ej., job ft-bc10fc32-2235), v4 (187 ej., ft-o1bf79da-6ofa), v5 (267 ej., ft-e0f71c8c-45d3), v6 (302 ej., ft-1f0c7e89-525d). El proceso de actualización es: crear dataset JSONL → subir a Together.ai → fine-tune LoRA (r=64, alpha=128, 4 epochs, lr=2e-5) → descargar adapter → merge con modelo base (transformers + peft) → convertir a GGUF con llama.cpp (Q4_K_M para 14B, Q8_0 para 7B) → cargar en Ollama. El modelo de producción corre en Together.ai para inference 24/7, y Ollama local es fallback. La próxima versión (v7) migrará a Qwen2.5-14B-Instruct con ~500 ejemplos SFT para reducir alucinaciones."
    ),
]

# ============================================================
# BATCH 2 — Porcino práctico (~20 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cuál es el índice de conversión típico en porcino de cebo?",
        "El índice de conversión (IC) típico en porcino de cebo blanco intensivo es: en la fase de inicio (20-40 kg) IC = 1.6-1.8:1, en crecimiento (40-70 kg) IC = 2.0-2.3:1, en acabado (70-110 kg) IC = 2.5-3.0:1. La media global del ciclo de cebo (20-110 kg) suele estar en 2.3-2.6:1 para genéticas modernas (Pietrain × Large White/Landrace). En ibérico puro en extensivo (montanera + cebo), el IC es mucho peor: 3.5-4.5:1. Cada 0.1 puntos de mejora en IC supone ~2-3€/cerdo de ahorro en pienso. PorciData monitoriza el peso estimado (visión + báscula walk-over) y el consumo de pienso para calcular el IC real del lote en tiempo real."
    ),
    make(
        "¿Cuántos lechones por camada es normal en porcino blanco?",
        "Las cerdas híbridas modernas (Large White × Landrace) producen 14-16 lechones nacidos vivos por parto, con programas hiperprolíficos (Danbred, Topigs Norsvin TN70) llegando a 16-18. La tasa de mortalidad pre-destete es 8-12%, así que los destetados por camada son 12-14. El objetivo es ≥30 lechones destetados/cerda/año (2.3-2.5 partos/año × 13-14 destetados). En ibérico puro, la prolificidad es mucho menor: 6-8 nacidos vivos. La heredabilidad de la prolificidad es baja (h²=0.10), por lo que la mejora genética es lenta — la heterosis del cruce F1 es más efectiva que la selección pura para este carácter."
    ),
    make(
        "¿Cuál es la ganancia media diaria esperada en cerdo de cebo?",
        "La ganancia media diaria (GMD) en porcino de cebo blanco intensivo varía por fase: inicio (20-40 kg) GMD = 650-750 g/día, crecimiento (40-70 kg) GMD = 800-900 g/día, acabado (70-110 kg) GMD = 750-850 g/día. Con genéticas top y nutrición optimizada se pueden superar 900 g/día de media global (20-110 kg). En ibérico × Duroc, la GMD típica es 350-500 g/día en cebo, y en ibérico puro de montanera baja a 300-400 g/día. En el piloto Mioty con 2.354 cerdos Duroc × Ibérico, la GMD fue 0.375 kg/día y con IoT se proyectó mejorar a 0.413 kg/día (+10%). La heredabilidad de la GMD es h²=0.30 (media), respondiendo bien a selección."
    ),
    make(
        "¿Cuánto vale un cerdo de cebo en lonja y cuándo se envía a matadero?",
        "El precio de referencia del cerdo de cebo en Mercolleida oscila entre 1.20-1.80 €/kg vivo, con picos estacionales en verano y Navidad. El peso óptimo de envío a matadero es 105-115 kg de peso vivo para cerdo blanco (canal 80-85 kg, rendimiento ~78%). Enviar antes de 100 kg penaliza el rendimiento canal; enviar después de 120 kg aumenta la grasa dorsal y empeora la clasificación EUROP. El Digital Twin de NeoFarm calcula la fecha óptima de envío cruzando: peso proyectado (visión + báscula), precio de pienso, cotización de lonja, y el IC de la fase final (que empeora progresivamente). Cada día extra en el cebadero tiene un coste de pienso (~0.70-0.90 €/cerdo/día)."
    ),
    make(
        "¿Qué temperatura y humedad óptima necesita una nave de cebo porcino?",
        "Las temperaturas óptimas en porcino varían por fase: lechones recién nacidos 28-32°C (con foco de calor), transición (6-20 kg) 24-28°C, cebo inicio (20-40 kg) 22-24°C, cebo acabado (70-110 kg) 18-22°C, gestantes 16-20°C. La humedad relativa ideal es 60-70% en todas las fases. Cuando T>26°C para cerdos de cebo, hay estrés calórico: caída del consumo voluntario -10 a -20%, aumento de la mortalidad, y empeoramiento del IC. El THI calcula el estrés combinado: THI = (1.8×T+32) − (0.55−0.0055×HR) × (1.8×T−26). PorciData monitoriza T/RH con la capa ambiental (Dragino LoRa + Renke, ~200 EUR/nave) y genera alertas automáticas."
    ),
    make(
        "¿Cómo afecta la ventilación al NH3 en una nave porcina?",
        "La ventilación es el factor más importante para controlar el NH3. En invierno, la tentación es reducir ventilación para ahorrar calefacción, pero esto sube el NH3 rápidamente. El objetivo es mantener NH3 <25 ppm (máximo legal RD 1135/2002) idealmente <10 ppm. Una ventilación mínima de 3-5 renovaciones/hora en invierno suele ser suficiente para mantener NH3 en rango. En verano se necesitan 40-60 renovaciones/hora para control térmico. PorciData monitoriza NH3 continuamente y puede alertar cuando sube, pero la causa raíz suele ser: ventilación insuficiente, foso de purines lleno, o mala calidad de cama. La correlación NH3 alto + ReHS bajo (<40%) = alerta roja de brote respiratorio."
    ),
    make(
        "¿Qué es la clasificación SEUROP en canales porcinas?",
        "La clasificación SEUROP (también S-EUROP) categoriza las canales porcinas por porcentaje de magro estimado: S = ≥60% (Súper), E = 55-60%, U = 50-55%, R = 45-50%, O = 40-45%, P = <40%. En España, la mayoría de canales blancas están en E/U. Cada categoría tiene un precio diferente en matadero — la diferencia entre E y R puede ser 5-10 céntimos/kg canal. Con 85 kg de canal media, eso son ~5-8€/cerdo. La genética es el factor principal: cruzar con Pietrain mejora la conformación (más magro). El IC y la nutrición en acabado (ratio lisina/energía) también afectan. NeoFarm retroalimenta los datos de clasificación del matadero a los EPDs genéticos para mejorar la selección."
    ),
    make(
        "¿Cuál es la diferencia entre el cerdo ibérico puro y el cruce ibérico × Duroc?",
        "El cerdo ibérico puro (100% ibérico) es más lento (GMD 300-400 g/día), más graso, con IC alto (3.5-4.5:1), pero produce jamones de máxima calidad con certificación DOP (Guijuelo, Los Pedroches, etc.) y alcanza precios premium: jamón ibérico de bellota 100% puede superar 250 €/pieza. El cruce ibérico × Duroc (50% ibérico) crece más rápido (GMD 400-500 g/día), tiene mejor IC (3.0-3.5:1), y es el producto más común del mercado ibérico. Se etiqueta como 'ibérico' pero no '100% ibérico'. En montanera, el puro necesita más tiempo (14-18 meses) que el cruce (12-14 meses). El real decreto de calidad del ibérico (RD 4/2014) regula las categorías: bellota, cebo de campo, cebo."
    ),
    make(
        "¿Qué es la montanera y cuándo se realiza?",
        "La montanera es el período de engorde final del cerdo ibérico en la dehesa, alimentándose de bellotas (de encina y alcornoque) y pastos naturales. Se realiza de octubre/noviembre a febrero/marzo — coincidiendo con la caída de la bellota. Cada cerdo necesita 0.5-1 hectárea de dehesa. Durante la montanera, el cerdo ibérico come 6-10 kg de bellota/día y engorda 46 kg mínimo (reposición mínima) para obtener la categoría 'de bellota'. El cerdo entra con ~100-115 kg y sale con ~160-180 kg. La infiltración de grasa intramuscular producida por la bellota (rica en ácido oleico) es lo que da al jamón ibérico de bellota su sabor único. NeoFarm puede monitorizar centinelas GPS en la dehesa para verificar el acceso real a las zonas de arbolado."
    ),
    make(
        "¿Qué son los purines y cómo los gestiona la normativa?",
        "Los purines son la mezcla de heces, orina y agua de lavado de las naves porcinas. Su gestión es obligatoria bajo el Plan 4 del SIGE (RD 306/2020). Las opciones son: 1) Aplicación agrícola como fertilizante — respetando las dosis de nitrógeno máximas según zona vulnerable (170 kg N/ha/año en zonas vulnerables a nitratos). 2) Balsa de almacenamiento — capacidad mínima para 3-4 meses de producción. 3) Tratamiento: separación sólido/líquido, compostaje, biodigestor anaerobio (reduce CH4 -60%). 4) Exportación a otra explotación o gestor autorizado. NeoFarm monitoriza el nivel de foso con sensores de ultrasonidos y calcula la producción estimada por censo, alertando cuando la capacidad se acerca al límite."
    ),
]

# ============================================================
# BATCH 2 — Vacuno práctico (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué razas autóctonas de vacuno extensivo hay en España?",
        "Las principales razas autóctonas de vacuno extensivo en España son: Avileña-Negra Ibérica (dehesas del centro/oeste, 550-600 kg ♂, rústica, buena materna), Retinta (Extremadura/Andalucía, 800-900 kg ♂, adaptada al calor), Morucha (Salamanca, 700-800 kg ♂, mucha rusticidad), Rubia Gallega (Galicia, 900-1.000 kg ♂, excelente calidad de carne, ternera IGP Galicia), Pirenaica (País Vasco/Navarra/Aragón, 800-900 kg ♂, buena conformación), y Asturiana de los Valles (Asturias, 900-1.000 kg ♂, hipermuscularidad culón). Cada una está adaptada a su ecosistema. El cruce con Limusina o Charolais mejora la conformación canal pero reduce la adaptación al medio."
    ),
    make(
        "¿Cómo calcula NeoFarm la carga ganadera óptima con NDVI?",
        "NeoFarm usa el NDVI de Sentinel-2 (10 m resolución, cada 5 días) para estimar la biomasa disponible por parcela. La relación es: NDVI 0.2-0.4 = pasto seco con baja disponibilidad (<1.000 kg MS/ha), NDVI 0.4-0.6 = pasto verde con disponibilidad media (1.000-3.000 kg MS/ha), NDVI >0.6 = pasto abundante (>3.000 kg MS/ha). Una UGM (Unidad de Ganado Mayor = vaca adulta de ~600 kg) consume 10-12 kg de materia seca/día. Cruzando la biomasa estimada por NDVI con el consumo por UGM, GeoTwin calcula los días de pastoreo disponible por parcela y la carga ganadera sostenible (UGM/ha). En dehesa, la carga típica es 0.3-0.5 UGM/ha, en praderas atlánticas 1.0-2.0 UGM/ha."
    ),
    make(
        "¿Cuánto vale un ternero de cría en lonja?",
        "En la Lonja de Segovia (referencia para vacuno en España), los precios de ternero de 6-7 meses oscilan: machos cruzados 800-1.200€/cabeza, hembras cruzadas 600-900€/cabeza. Los precios varían por raza, peso, conformación, y estación. Los terneros de razas cárnicas puras (Avileña, Limusina) y sus cruces se pagan mejor que los de razas mixtas. Factores que suben el precio: buen estado sanitario, desparasitados, con IBR/BVD negativos, peso homogéneo en el lote. NeoFarm captura automáticamente las cotizaciones de Segovia para alimentar el módulo económico del Digital Twin Vacuno, calculando el margen bruto por ternero producido."
    ),
    make(
        "¿Qué es un añojo y cuánto rinde en canal?",
        "Un añojo es un bovino sacrificado antes de los 14 meses de edad (en la práctica, 12-14 meses, 400-500 kg vivo). Es la categoría de sacrificio más rentable en cebo vacuno por la relación velocidad de engorde / calidad de canal. El rendimiento canal típico es 55-60% para razas rústicas (Avileña, Retinta) y 58-63% para cruces con Limusina/Charolais. La clasificación EUROP marca el precio: U = 7.0-7.5 €/kg canal, R = 6.5-7.2 €/kg, O = 6.0-6.5 €/kg. Para un añojo de 250 kg canal en categoría R: 250 × 7.0 = 1.750€ de ingreso. El ternero costó ~1.000€ y el cebo (~6 meses × ~3€/día pienso) ~550€, dejando un margen bruto de ~200€/animal antes de otros costes."
    ),
    make(
        "¿Cómo funciona el pastoreo rotacional y qué ventajas tiene?",
        "El pastoreo rotacional divide la superficie en 4-8 parcelas y rota el ganado cada 3-7 días, dejando que cada parcela descanse 21-35 días. Ventajas: 1) Mejora la producción de pasto +20-40% vs pastoreo continuo, porque evita el sobrepastoreo. 2) Secuestra +200 kg CO2/ha/año (métrica ESG que calcula GeoTwin). 3) Reduce parásitos internos porque los ciclos de reposo rompen el ciclo vital de los helmintos. NeoFarm gestiona el rotacional con GeoTwin: el NDVI por parcela indica cuándo hay pasto suficiente para devolver al ganado, los GPS de los centinelas verifican que están en la parcela correcta, y el twin calcula los días de pastoreo restantes. La PAC premia el pastoreo rotacional dentro de los eco-esquemas."
    ),
    make(
        "¿Cómo detecta NeoFarm problemas reproductivos en vacuno extensivo?",
        "NeoFarm monitoriza la reproducción en extensivo mediante: 1) Centinelas GPS + acelerómetro: detectan monta (animal inmóvil con movimiento rítmico encima) y cambios de actividad asociados al celo. 2) Calendario reproductivo en el twin: fecha de cubrición → diagnóstico de gestación a 30-45 días (ecógrafo manual) → fecha prevista de parto. 3) Alertas de parto: aumento de actividad + aislamiento del grupo + posición GPS fuera de la zona habitual. 4) Control post-parto: si la vaca no aparece con el ternero cerca en 24-48 horas, alerta de posible aborto o ternero perdido. La tasa de fertilidad objetivo es >85% (vaquillas >50%). La heredabilidad de la fertilidad es muy baja (h²=0.05-0.10), por eso la mejora viene más por manejo (condición corporal al parto BCS 3.0-3.5) que por selección genética."
    ),
    make(
        "¿Cómo gestiona NeoFarm una dehesa con vacas de cría?",
        "NeoFarm gestiona la dehesa con VacasData + GeoTwin: 1) Mapeo de la finca: parcelas con geometrias UTM, NDVI por parcela cada 5 días (Sentinel-2), arbolado (encina/alcornoque) mapeado por ortofoto PNOA. 2) Centinelas GPS (10-20 vacas representativas): posición cada 5-30 min, actividad por acelerómetro, rumiación. 3) Infraestructura: puntos de agua mapeados con caudal monitorizado, cercados electrónicos (opcionales) para pastoreo rotacional virtual, comederos con sensor de nivel. 4) Reproducción: calendario de cubriciones, control de partos, peso del ternero al destete para EPDs. 5) Economía: margen por vaca = (ingresos ternero + subvenciones PAC) − (costes alimentación + veterinario + tasas). Todo visualizado en Cesium 3D, con assets del pipeline BlenderGIS."
    ),
    make(
        "¿Qué subvenciones de PAC puede cobrar un ganadero extensivo?",
        "La PAC 2023-2027 incluye varios pagos para ganadería extensiva: 1) Pago básico por hectárea (derecho de pago base, ~100-200 €/ha según región). 2) Eco-esquemas: pastoreo extensivo (~50-80 €/ha), rotación de pastos, mantenimiento de dehesa con arbolado. 3) Ayudas asociadas: prima por vaca nodriza (70-100 €/cabeza), prima al vacuno de cebo (40-60 €/cabeza). 4) Agroambientales: mantenimiento de razas autóctonas en peligro (200-300 €/UGM), biodiversidad en dehesas. GeoTwin de NeoFarm puede verificar el cumplimiento de eco-esquemas con datos objetivos: carga ganadera real (GPS centinelas / hectárea), pastoreo rotacional demostrable, y NDVI que acredita la cobertura vegetal."
    ),
]

# ============================================================
# BATCH 2 — IoT avanzado / casos edge (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Qué es LoRa y por qué la usa NeoFarm para sensores?",
        "LoRa (Long Range) es una tecnología de radio de bajo consumo que opera en la banda ISM 868 MHz (Europa) con alcance de 2-15 km en zonas rurales. NeoFarm la usa porque las granjas suelen estar lejos de redes WiFi/4G y los sensores necesitan funcionar con baterías durante meses. Los nodos LoRa envían datos pequeños (temperatura, humedad, NH3) a un gateway (concentrador) que los reenvía por internet al backend. NeoFarm usa gateways Dragino LPS8N o RAK7289 (~200-300 EUR). En extensivo, los gateways son solares con baterías LiFePO4. La limitación de LoRa es la capacidad: en granjas grandes con muchos sensores, Mioty (44.000 paquetes/min/MHz) supera ampliamente a LoRa."
    ),
    make(
        "¿Cómo funciona Node-RED en la arquitectura de NeoFarm?",
        "Node-RED (:1880 en Docker) actúa como el motor de reglas y transformación de datos entre los sensores y el almacenamiento. Los flujos típicos son: 1) MQTT In (suscripción a topics Mosquitto) → Parseo JSON → Validación de rango → Escribir en InfluxDB. 2) MQTT In → Detección de umbral (NH3 >25 ppm) → Generar alerta → Publicar en MQTT Out (topic de alertas) + Escribir en InfluxDB. 3) Timer (cada 5 min) → Consultar InfluxDB (últimas lecturas) → Calcular media/tendencia → Actualizar dashboard. Node-RED permite crear reglas sin programar código, con una interfaz visual drag-and-drop. Las reglas del Digital Twin (correlación agua + NH3 + ReHS → probabilidad de brote) se pueden implementar como flujos Node-RED."
    ),
    make(
        "¿Cómo se configura Mosquitto MQTT en NeoFarm?",
        "Mosquitto es el broker MQTT que corre en Docker (:1883 para MQTT, :9001 para WebSockets). La configuración básica: listener 1883 para comunicación entre sensores y backend, allow_anonymous true en desarrollo (con ACL en producción), persistence true para mantener mensajes retenidos, persistence_file /mosquitto/data/mosquitto.db. Los topics siguen el patrón: neofarm/{farm_id}/{barn_id}/{layer}/{sensor_type}. Los sensores publican con QoS 1 (at least once) para garantizar entrega. Node-RED se suscribe con wildcards: neofarm/+/+/environmental/# para recibir todos los datos ambientales de todas las granjas/naves. Para producción, se activa TLS (:8883) y autenticación por usuario/password o certificado cliente."
    ),
    make(
        "¿Qué pasa si un sensor IoT deja de enviar datos?",
        "NeoFarm detecta la ausencia de datos con un watchdog configurable por sensor. Si un sensor no envía datos durante 3× su intervalo normal (ejemplo: si envía cada 5 min, el watchdog se activa a los 15 min), se genera una alerta de tipo 'sensor offline'. Node-RED implementa este watchdog con un nodo 'trigger' en modo timeout. La alerta incluye: sensor_id, última lectura, duración del silencio, y posible causa (batería baja si el último RSSI era débil, o fallo de gateway si múltiples sensores de la misma nave se caen). Las baterías de los ESP32 + LoRa duran 6-12 meses con una lectura cada 5 min. Mioty extiende esto a 3× más (18-36 meses). Los gateways solares con LiFePO4 tienen autonomía de 3-5 días sin sol."
    ),
    make(
        "¿Cómo almacena NeoFarm los datos de series temporales?",
        "NeoFarm usa InfluxDB (:8086 en Docker) como base de datos de series temporales. Los datos de sensores se organizan en measurements (tablas): environment (T, RH, NH3, CO2, lux), water (flow_rate, pH, total_liters), acoustic (rehs_score, cough_count), weight (estimated_kg), etc. Cada punto tiene tags (farm_id, barn_id, sensor_id) y fields (valor numérico). InfluxDB es ideal para este caso: ingesta rápida, compresión eficiente de datos temporales, y queries con ventanas temporales (mean(temperature) por hora/día). La retención por defecto es 1 año sin downsampling, con políticas de continuous query para crear resúmenes horarios/diarios que se mantienen indefinidamente. Grafana (:3001) se conecta directamente como datasource."
    ),
    make(
        "¿Cómo se programa un ESP32 para enviar datos LoRa en NeoFarm?",
        "El firmware ESP32 para PorciData sigue un patrón estándar: 1) Setup: inicializar sensor (BME688, SHT31, etc.), configurar módulo LoRa (RFM95/SX1276), establecer spreading factor y potencia. 2) Loop: despertar del deep sleep → leer sensor → construir payload compacto (CayenneLPP o similar, <51 bytes) → transmitir vía LoRa → dormir N minutos. 3) Gestión de energía: deep sleep entre lecturas (4-20 μA), lectura + transmisión dura <2 s. El intervalo típico es 5 min para ambiente y agua, 1 min para acústica (pre-procesada en el ESP32-S3 con INMP441). El firmware se flashea por OTA (Over-the-Air) cuando hay WiFi disponible, o por USB en campo. Los logs se envían por LoRa con baja prioridad."
    ),
    make(
        "¿Cómo se configura Grafana para monitorizar una nave porcina?",
        "Grafana (:3001 en Docker, accesible en seedy-grafana.neofarm.io) se configura con InfluxDB como datasource. Un dashboard típico de nave porcina incluye: 1) Panel de Temperatura/Humedad con umbrales (líneas rojas en T>26°C y RH>80%). 2) Panel de NH3 con umbral legal a 25 ppm. 3) Panel de consumo de agua (litros/hora con media móvil 24h). 4) Panel de ReHS acústico (semáforo verde/ámbar/rojo). 5) Panel de peso estimado (distribución del lote). 6) Tabla de alertas activas. Variables de template: $farm (selector de granja) y $barn (selector de nave). Las alertas se configuran en Grafana: si NH3 >25 ppm durante >15 min → notificación por webhook a MQTT → la app móvil recoge la alerta."
    ),
]

# ============================================================
# BATCH 2 — Economía / Mercados / Negocio (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cuánto cuesta producir un cerdo de cebo y cuál es el margen?",
        "Costes típicos de producir un cerdo blanco de cebo (20-110 kg): pienso = 75-85€ (70% del coste total), lechón 20 kg = 30-45€, veterinario/medicamentos = 3-5€, mano de obra = 5-8€, energía/agua/otros = 3-5€. Total: 116-148€/cerdo. Con un cerdo de 110 kg vivo a 1.40€/kg (cotización Mercolleida media), los ingresos son 154€. Margen bruto: 6-38€/cerdo. Los márgenes son muy ajustados y variables — el principal driver es el precio del pienso (maíz + soja) y la cotización de lonja. PorciData mejora el margen reduciendo mortalidad (-2-3 cerdos/1.000, ~2-4€ más/cerdo), mejorando IC (-0.1 punto, ~2-3€/cerdo), y optimizando la fecha de envío (+1-3€/cerdo). ROI del IoT estimado: 7-10€/cerdo de mejora."
    ),
    make(
        "¿Cómo calcula el Digital Twin el impacto económico de un brote respiratorio?",
        "El Digital Twin cruza 4 fuentes para el cálculo económico: 1) Mortalidad extra: si el brote mata un 3% del lote de 1.000 cerdos = 30 animales × ~150€ = 4.500€ de pérdida. 2) Retraso de crecimiento: los supervivientes crecen 10-15% menos durante 2-3 semanas → 7-10 días extra en cebadero × 0.80€/día/cerdo × 970 cerdos = 5.500-7.700€. 3) Medicamentos: antibióticos + antiinflamatorios = 1-3€/cerdo × 970 = 970-2.910€. 4) Peor IC: el IC sube 0.1-0.2 puntos → +2-4€/cerdo × 970 = 1.940-3.880€. Total estimado: 12.900-19.000€/lote. Con detección temprana IoT (ReHS <40% + agua -15% + NH3 >25 ppm), se puede intervenir 2.6 días antes (dato SoundTalks) y reducir el impacto un 40-60%: ahorro de 5.000-11.000€."
    ),
    make(
        "¿Cuánto cuesta montar una granja de cebo porcino completa?",
        "Inversión aproximada para una granja de cebo porcino nueva de 2.000 plazas: nave + instalaciones = 400.000-600.000€ (200-300€/plaza), equipamiento (comederos, bebederos, ventilación, calefacción, slat) = 100.000-150.000€, fosa de purines = 30.000-50.000€, oficina + vestuarios + vado sanitario = 20.000-30.000€. Total: 550.000-830.000€. A esto se añade PorciData IoT: 1.420€/nave × 4-6 naves = 5.680-8.520€ (<2% de la inversión). El período de amortización es 8-12 años. Con 2.000 plazas y 2.5 rotaciones/año = 5.000 cerdos/año × 20-30€ margen bruto = 100.000-150.000€/año de margen bruto antes de amortización. La viabilidad depende críticamente del ciclo de precios del pienso y la cotización de lonja."
    ),
    make(
        "¿Qué es Mercolleida y para qué la usa NeoFarm?",
        "Mercolleida es la Lonja de Referencia Nacional para porcino, ubicada en Lleida. Publica semanalmente la cotización del cerdo de cebo (€/kg vivo), lechones, y otros productos porcinos. Es la referencia que usan mataderos, integradoras y ganaderos para negociar precios. NeoFarm captura automáticamente estas cotizaciones vía web scraping (Worker Web/Automation con Playwright) y las integra en: 1) El Digital Twin — para calcular el valor del lote y la fecha óptima de envío a matadero. 2) El solver de formulación — para optimizar el coste de la ración según precios de materias primas. 3) Informes económicos — para que el ganadero vea su margen en tiempo real. Otras lonjas relevantes: Segovia (vacuno/ovino), Lonja del Ebro (cereales)."
    ),
    make(
        "¿Cómo calcula NeoFarm el ROI de la monitorización IoT?",
        "NeoFarm calcula el ROI del IoT comparando el coste de los sensores (~1.420 EUR/nave de PorciData) con los ahorros proyectados: 1) Reducción de mortalidad: detección temprana de brotes → -2-3 muertes/1.000 → ahorro 300-450€/1.000 cerdos. 2) Mejora de IC: alimentación optimizada + confort térmico → -0.05-0.10 IC → ahorro 1-3€/cerdo. 3) Optimización de envío a matadero: ±2-3 días → ahorro 1-2€/cerdo. 4) Ahorro en antibióticos: intervención temprana → -28% uso (dato SoundTalks) → ahorro 0.5-1€/cerdo. Total estimado: 7-10€/cerdo × 500-2.000 cerdos/nave/año = 3.500-20.000€/año de ahorro. Con coste de 1.420€/nave, el payback es de 1-4 meses. En el piloto Mioty (2.354 cerdos Duroc × Ibérico), el beneficio aumentó un 6.36%."
    ),
    make(
        "¿Cómo compite NeoFarm contra AgroVision y CloudFarms?",
        "NeoFarm NO compite directamente contra AgroVision, CloudFarms, iFarming o Agrogi — esos son ERPs de gestión (censo, trazabilidad, contabilidad). NeoFarm se posiciona como capa de IoT + IA ENCIMA de estos ERPs. La estrategia es: el ganadero mantiene su ERP favorito y añade NeoFarm para: sensores IoT a coste 10× menor (PorciData ~1.420 EUR/nave vs 14.500+ EUR de Fancom/Nedap), IA asistente (Seedy) para consultas técnicas, Digital Twin predictivo, genética optimizada (FarmMatch), y GeoTwin 3D para extensivo. La integración con ERPs se hace por API REST. Los competidores directos de NeoFarm son Fancom, Nedap, y SoundTalks en la capa IoT, no los ERPs."
    ),
]

# ============================================================
# BATCH 2 — Más Visión / Edge AI (~10 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Puede NeoFarm contar automáticamente los cerdos de una nave?",
        "Sí, el conteo automático de cerdos por visión artificial es una de las funcionalidades más maduras, con un 95% de precisión. Usa YOLOv8m para detectar cada cerdo visible en el frame, BoT-SORT para tracking temporal (evitar contar el mismo cerdo dos veces), y un algoritmo de reconciliación que combina múltiples frames para dar un conteo consolidado. Con una cámara cenital por corral (4MP, IP, ~50€), se obtiene un conteo actualizado cada 15 min. El beneficio principal: detectar bajas (muertes) automáticamente — si el conteo cae en 1, se genera una alerta. Para grupos de >50 cerdos, la precisión del conteo manual humano también es ~95%, pero requiere entrar al corral y genera estrés."
    ),
    make(
        "¿Qué resolución de cámara necesita NeoFarm para detección en granja?",
        "Para la detección estándar con YOLO, la inferencia se ejecuta a 640×640 px — por lo que una cámara de 2-4 MP es suficiente para resolución directa. Sin embargo, NeoFarm usa cámaras de 4 MP (2560×1440) por varias razones: 1) Zoom digital: se pueden recortar ROIs de animales lejanos manteniendo buena resolución. 2) Múltiples corrales: una cámara de 4 MP cenital puede cubrir 2-3 corrales con tiling (dividir la imagen en tiles de 640×640). 3) Calidad de la estimación de peso: más píxeles por animal = mejor precisión de EfficientNet-B0. Las cámaras 8K del piloto de visión son para investigación y entrenamiento de modelos; en producción, 4 MP es el estándar con coste ~50-80€/cámara."
    ),
    make(
        "¿Se pueden usar drones con cámara para monitorizar vacuno extensivo?",
        "Sí, los drones son una herramienta complementaria viable para vacuno extensivo, especialmente para rebaños sin centinelas GPS. Se usan para: 1) Conteo aéreo del rebaño (vuelo periódico, YOLO detecta y cuenta desde ortofoto). 2) Evaluación de BCS (condición corporal) desde vista dorsal — se ve la prominencia de huesos en la espalda/cadera. 3) Detección de animales aislados o en apuros (heridos, atrapados en cercados). 4) Mapeo NDVI de parcelas con cámara multiespectral. Limitaciones: dependen del clima (no vuelan con viento >30 km/h o lluvia), requieren piloto con licencia A2/STS, autonomía limitada (20-30 min), y no son monitorización continua. Por eso NeoFarm prioriza centinelas GPS para monitorización 24/7, y drones como complemento periódico."
    ),
    make(
        "¿Cómo funciona el radar mmWave de PorciData?",
        "El radar mmWave de PorciData usa el módulo Seeed MR60BHA1 a 60 GHz (~25 EUR/nave), primera aplicación en porcino comercial. Opera sin contacto y sin cámara — detecta: frecuencia respiratoria, presencia/actividad/inactividad, y cambios de comportamiento grupal. Ventajas sobre visión: funciona en oscuridad total, no se contamina (no tiene lente), no hay preocupaciones de privacidad del trabajador, y el hardware es muy barato. Limitaciones: no distingue individuos, cobertura limitada (~3-5 m), y la precisión de la frecuencia respiratoria en un grupo denso aún está en validación. Se usa como complemento de la capa de visión y acústica, no como sustituto. La combinación radar + acústica + acelerómetro da una monitorización de actividad redundante y robusta."
    ),
    make(
        "¿Qué diferencias hay entre utilizar cámaras IP y el sistema de visión de Fancom iGrow?",
        "Fancom iGrow es un sistema comercial cerrado que cuesta >3.000 EUR/nave solo para la parte de visión. Incluye cámara propietaria, software cerrado, y requiere suscripción anual. Mide peso estimado y actividad. PorciData de NeoFarm usa cámaras IP estándar (~50-80 EUR cada una) con inferencia open source (Ultralytics YOLOv8/v11) en Jetson Orin Nano. Ventajas de NeoFarm: coste 40× menor, algoritmos actualizables (nuevo modelo = nuevo firmware), modelo 100% propio (no dependes de proveedor cerrado), integrado con el resto de capas IoT (acústica, agua, radar). Desventaja: requiere integración técnica (no es plug-and-play como Fancom). Por eso NeoFarm se dirige inicialmente a integradores y cooperativas con soporte técnico, no a ganaderos individuales sin soporte."
    ),
]

# ============================================================
# BATCH 2 — Nutrición / Formulación extra (~10 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cuántas fases de alimentación tiene un cerdo de cebo y qué caracteriza cada una?",
        "Típicamente 3-4 fases: 1) Pre-starter/Starter (5-10 kg, post-destete): pienso altamente digestible, 22-24% PB, lisina >1.4%, lactosa, plasma sanguíneo. Es el pienso más caro (>500€/t) pero crítico para el arranque. 2) Crecimiento 1 (20-40 kg): 18-20% PB, lisina 1.1-1.2%, energía 2.350-2.400 kcal EN/kg. 3) Crecimiento 2/Acabado (40-80 kg): 16-18% PB, lisina 0.9-1.0%. 4) Retirada/Acabado final (80-110 kg): 14-16% PB, lisina 0.7-0.8%, se limita la proteína para evitar exceso de grasa dorsal. El solver HiGHS de NeoFarm formula cada fase con 20-40 restricciones (aminoácidos, energía, minerales, fibra, palatabilidad) minimizando coste por kg de pienso. Cada fase dura 3-5 semanas en cebo intensivo."
    ),
    make(
        "¿Qué aminoácidos son limitantes en la nutrición porcina?",
        "Los aminoácidos limitantes en porcino (en orden de limitación) son: 1) Lisina — el primer limitante, refencia para el perfil de proteína ideal. 2) Metionina + Cisteína (azufrados) — 55-60% de la lisina. 3) Treonina — 62-65% de la lisina. 4) Triptófano — 17-19% de la lisina. La formulación se basa en el concepto de 'proteína ideal': todos los aminoácidos se expresan como ratio respecto a la lisina. NRC 2012 define los perfiles por fase. Los aminoácidos sintéticos (L-lisina HCl, DL-metionina, L-treonina, L-triptófano) permiten reducir la proteína bruta total del pienso (-2-3 pp) manteniendo el perfil ideal, lo que reduce las emisiones de N (menos nitrógeno excretado en purines = menos NH3)."
    ),
    make(
        "¿Cómo se calcula el coste de la ración con el solver LP?",
        "El solver LP (programación lineal) minimiza la función objetivo: Coste = Σ(precio_i × proporción_i) para i materias primas, sujeto a restricciones lineales: cada nutriente (energía, lisina, metionina, etc.) debe estar entre un mínimo y un máximo, cada materia prima tiene un mínimo y máximo de inclusión (ej: soja máximo 30%, caliza 0-2%), y la suma de proporciones = 100%. HiGHS resuelve esto en milisegundos para 20-40 ingredientes y 20-40 restricciones. Los precios de ingredientes vienen de la Lonja del Ebro (cereales) y proveedores locales. NeoFarm optimiza semanalmente según variaciones de precio, y alerta cuando un cambio de precio de >5% justifica reformular. El ahorro de una formulación LP vs empírica es típicamente 3-8€/tonelada."
    ),
    make(
        "¿Qué efecto tiene añadir fitasa al pienso porcino?",
        "La fitasa libera fósforo atrapado en el ácido fítico de los granos (>60% del fósforo total de cereales y soja es fítico). Añadiendo 500-1.000 FTU/kg de fitasa, se liberan 0.8-1.2 g de fósforo disponible/kg de pienso. Esto permite: 1) Reducir la adición de fosfato dicálcico/monocálcico (ahorro ~3-5€/t de pienso). 2) Reducir la excreción de fósforo en purines -25 a -30% (menor contaminación, cumplimiento de zonas vulnerables). 3) Mejorar la digestibilidad de aminoácidos y energía (efecto 'extra-phosphoric'). Las superdosis de fitasa (1.500-2.500 FTU/kg) dan beneficios adicionales pero con rendimientos decrecientes. El solver LP de NeoFarm incluye la fitasa como variable binaria: si se activa, modifica la matriz nutricional del pienso."
    ),
    make(
        "¿Cómo afecta el estrés calórico al consumo de pienso?",
        "Cuando la temperatura supera el umbral de confort (22-24°C para cerdos de cebo), el consumo voluntario de pienso cae linealmente: -10% a 26°C, -20% a 30°C, -30% a 33°C. Esto reduce la ganancia media diaria y empeora el IC porque las necesidades de mantenimiento aumentan (jadeo, termorregulación). La respuesta nutricional es: aumentar la concentración de energía neta (+10%) y lisina digestible (+15%) en el pienso, para que con menos kg ingeridos el cerdo reciba los mismos nutrientes. También se puede añadir betaína (1-2 kg/t) como osmorregulador y electrolitos (bicarbonato sódico). PorciData detecta estrés calórico con THI >72 y activa auto-reformulación: el solver HiGHS recalcula la ración con restricciones ajustadas al estrés."
    ),
]

# ============================================================
# BATCH 2 — Preguntas prácticas del ganadero (~15 ejemplos)
# ============================================================
new_examples += [
    make(
        "El veterinario recomienda antibiótico para un brote respiratorio. ¿Puedo reducir el uso con IoT?",
        "Sí. SoundTalks demostró con datos que la detección acústica temprana  reduce el uso de antibióticos un -28% y mejora la GMD en +12.7 g/día, porque permite intervenir 2.6 días antes de que un brote se extienda. Con PorciData: 1) El ReHS acústico detecta toses antes de síntomas visibles. 2) Si ReHS cae a <60% (ámbar) se revisa la nave sin medicar. 3) Si ReHS <40% (rojo) + NH3 >25 ppm + agua -15%, se actúa (ventilación + revisión veterinaria). 4) Se puede medicar solo los corrales afectados, no toda la nave (metafilaxis selectiva vs metafilaxis masiva). El coste de PorciData acústica es 15€/nave — si evita medicar 1.000 cerdos innecesariamente a 1-2€/cerdo, se amortiza en un solo evento."
    ),
    make(
        "¿Cómo sé si mis cerdos están creciendo bien sin pesarlos manualmente?",
        "NeoFarm ofrece 2 opciones: 1) Báscula walk-over (~350 EUR/nave): los cerdos pasan por una báscula incorporada al comedero o bebedero, registrando peso individual vía RFID + celda de carga. Precisión: ±1-2 kg. Frecuencia: varias veces al día por cada cerdo. 2) Estimación por visión (~150 EUR/nave): la cámara cenital + EfficientNet-B0 estima el peso visual usando el área del animal y features de imagen. Precisión: ±3-5 kg (menos precisa pero sin hardware mecánico). El Digital Twin combina ambas fuentes con los datos de consumo de pienso para calcular el IC en tiempo real y proyectar la fecha de envío a matadero. El peso grupal también se detecta: si hay mucha dispersión (CV >10%), indica un problema de uniformidad."
    ),
    make(
        "¿Qué hago si mis vacas no quedan preñadas?",
        "La infertilidad en vacuno extensivo tiene causas múltiples que NeoFarm ayuda a diagnosticar: 1) Condición corporal (BCS): si las vacas están por debajo de BCS 2.5 al inicio de la temporada de cubrición, la fertilidad cae drásticamente. GeoTwin + centinelas GPS verifican que las vacas tengan acceso a pasto de calidad (NDVI >0.4). 2) Estrés calórico: THI >72 reduce la fertilidad un -20-30%. 3) Mineral deficiency: en suelos ácidos la deficiencia de selenio y cobre es frecuente. 4) Toro subfértil: verificar ratio toro:vacas (1:25-30 máximo). 5) Enfermedades venéreas (tricomonosis, campylobacter). La heredabilidad de la fertilidad es muy baja (h²=0.05-0.10), así que la mejora principal viene por manejo: BCS >3.0 al parto, suplementación mineral, y control sanitario del toro."
    ),
    make(
        "Tengo una alerta de THI 82 en mi nave de cebo. ¿Qué pasos sigo?",
        "THI 82 está en zona de PELIGRO (79-89). Acciones inmediatas: 1) Maximizar ventilación: todos los ventiladores al 100%, abrir todas las entradas de aire. 2) Activar sistema de refrigeración: cooling-pad, spray de agua (1 min ON / 5 min OFF), o nebulización. 3) Asegurar agua ad libitum: verificar que todos los bebederos funcionan — los cerdos beben 2-3× más con calor. 4) No alimentar en horas de máximo calor (12-17h): mover la alimentación a la madrugada y la noche. 5) Reducir densidad si es posible (sacar los cerdos más pesados). 6) Monitorizar estrechamente: si THI sube a >89 (emergencia) o se detectan cerdos jadeando intensamente, contactar veterinario. PorciData debió haber generado la alerta proactivamente a THI 72 (zona de alerta). Revisa los umbrales de alerta de Grafana."
    ),
    make(
        "¿Cuánta agua bebe un cerdo de cebo al día?",
        "El consumo de agua en porcino de cebo varía por peso y temperatura: 20-40 kg = 2-4 L/día, 40-70 kg = 4-6 L/día, 70-110 kg = 6-10 L/día. Con estrés calórico (T>26°C), el consumo puede duplicarse hasta 12-15 L/día. La ratio agua:pienso es normalmente 2-3:1 (2-3 litros de agua por cada kg de pienso). El caudal mínimo del bebedero es 0.5-1.0 L/min. PorciData monitoriza el consumo de agua con caudalímetro (~80 EUR/nave) y detecta: caídas súbitas (-15% = alerta temprana de enfermedad), consumo excesivo (posible estrés calórico o fuga), y consumo cero (bebedero obstruido o avería). El agua es el primer indicador de problemas: un cerdo deja de beber 24-48 horas antes de mostrar síntomas visibles."
    ),
    make(
        "¿Cómo puedo mejorar la clasificación EUROP de mis terneros?",
        "Para mejorar la clasificación EUROP (más músculo, menos grasa): 1) Genética: cruzar con razas de conformación superior (Limusina, Charolais, Rubia Gallega, Asturiana de los Valles). El cruce Avileña × Limusina sube de O/R a R/U (diferencia de 0.5-1.0 €/kg canal). 2) Alimentación en cebo: ratio lisina/energía adecuado, proteína suficiente (14-16% PB en acabado vacuno). 3) Edad de sacrificio: añojo (<14 meses) se paga mejor que novillo (>24 meses). 4) Manejo: minimizar estrés previo al sacrificio (transporte, espera en matadero). NeoFarm usa los datos de clasificación del matadero como retroalimentación genética: los terneros de los mejores toros (mayor % de canales en U/E) reciben un EPD de conformación más alto, mejorando la selección futura con FarmMatch."
    ),
    make(
        "¿Qué mantenimiento necesitan los sensores de PorciData?",
        "El mantenimiento de PorciData es mínimo: 1) Micrófono INMP441: limpieza mensual de la carcasa (polvo), sin calibración. Duración: indefinida. 2) Cámara IP 4MP: limpieza de lente mensual (spray anti-polvo), verificar ángulo. Duración: 5-10 años. 3) Sensor ambiental (T/RH/NH3): limpieza trimestral de la sonda, verificación con medidor portátil cada 6 meses. El sensor de NH3 puede necesitar reemplazo cada 2-3 años. 4) Caudalímetro: limpieza anual del filtro. Duración: 10+ años. 5) BME688 (e-nose): re-burn-in de 48h si se corta la alimentación >30 días. 6) ESP32/gateway: firmware OTA, batería LiFePO4 cada 5-8 años. 7) Báscula walk-over: calibración trimestral con peso conocido, limpieza de la celda de carga. Total: ~2-4 horas/mes de mantenimiento por nave."
    ),
    make(
        "¿Cómo sé cuándo vaciar el foso de purines?",
        "NeoFarm puede monitorizar el nivel de foso con un sensor de ultrasonidos (~30-50 EUR) que mide la distancia a la superficie del purín. La alerta se configura: ámbar al 70% de capacidad, rojo al 85%. Adicionalmente, el Digital Twin estima la producción diaria de purines basándose en el censo de animales, peso medio, y consumo de agua (más agua = más purines). La capacidad mínima legal de almacenamiento es 3-4 meses de producción. Para dimensionar: un cerdo de cebo (20-110 kg) produce ~5-7 litros de purín/día. 1.000 plazas × 6 L/día × 120 días = ~720 m³ de capacidad mínima de fosa. NeoFarm genera un informe mensual de producción de purines para el plan de Gestión de Purines del SIGE (RD 306/2020)."
    ),
]

# ============================================================
# BATCH 3 — Visión + Avicultura + Cross-domain (~65 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Puede la visión artificial detectar peleas entre cerdos?",
        "Sí, la detección de agresiones entre cerdos se basa en el análisis temporal del tracker BoT-SORT. El algoritmo detecta: 1) Dos animales con velocidad alta (>0.15 unidades normalizadas/s) que se mueven hacia el mismo punto. 2) Contacto repetido entre bounding boxes en un patrón de empuje-retroceso-empuje. 3) Duración del evento >10 segundos (para distinguir de juego normal). Precisión actual: ~75-80%, menor que el conteo (95%) porque es un comportamiento complejo. Las agresiones son frecuentes post-mezcla de lotes, y su detección temprana permite separar animales agresores o añadir material de enriquecimiento (cadenas, juguetes). El RD 1135/2002 exige medidas contra agresiones entre cerdos."
    ),
    make(
        "¿Cómo se usa Sentinel-2 para monitorizar la bellota en dehesa?",
        "Sentinel-2 no detecta directamente la producción de bellota, pero el NDVI temporal revela información indirecta: 1) El NDVI de las copas de encinas/alcornoques es estable (~0.5-0.7) durante el verano (perennifolias), pero un NDVI anormalmente bajo en octubre-noviembre puede indicar estrés hídrico que reduce la fructificación. 2) El NDVI del pasto bajo el arbolado en septiembre-octubre indica disponibilidad de pasto complementario. Para cuantificar la bellota directamente, NeoFarm usaría drones con cámara multiespectral o muestreo manual (kg bellota/m² bajo copa × n° encinas). GeoTwin combina el mapa de arbolado (ortofoto PNOA) con NDVI para estimar zonas con mayor potencial de montanera."
    ),
    make(
        "¿Cómo puede NeoFarm ayudar a gestionar una integradora porcina con 50 granjas?",
        "Para una integradora con 50 granjas, NeoFarm escala con: 1) Dashboard centralizado en Grafana con variables $farm (50 granjas) × $barn (150-300 naves), alarmas agregadas por prioridad. 2) FarmMatch a nivel de cooperativa: MILP con HiGHS (no el Algoritmo Húngaro, que no escala) para optimizar apareamientos en >5.000 animales con restricciones de distancia entre granjas. 3) Digital Twin multi-nave: ranking de naves por rendimiento (IC, mortalidad, ReHS), benchmarking entre granjas para identificar best practices. 4) Formulación centralizada: un solver LP por fase × por granja, adaptado a la disponibilidad local de materias primas. 5) SIGE centralizado: reporting automatizado para las 50 explotaciones. Mioty es clave para este escenario: soporta >1.5 millones de telegramas/día vs miles de LoRa."
    ),
    make(
        "¿Es posible detectar la sarna sarcóptica en cerdos con visión artificial?",
        "La detección directa de sarna por visión artificial está en investigación pero no es fiable aún — las lesiones cutáneas tempranas son difíciles de distinguir en resolución 640×640 px. Sin embargo, NeoFarm detecta indicadores indirectos: 1) Rascado excesivo: el tracker BoT-SORT detecta movimientos repetitivos contra barrotes o paredes (estereotipia de rascado). 2) Zonas de alopecia: si el modelo de segmentación detecta cambios significativos en el patrón de color/textura del animal en la serie temporal. 3) Reducción de actividad: los animales con picor intenso descansan menos. La combinación de rascado frecuente + caída de GMD + sin alerta respiratoria sugiere un problema dermatológico. La confirmación requiere inspección veterinaria visual."
    ),
    make(
        "¿Qué es una Faverolles y por qué se cruza con Malines?",
        "La Faverolles (Saumon Faverolles) es una raza avícola francesa del Grupo 3 ('Rusticidad y Adaptación'), con pesos de 4.0/3.2 kg (♂/♀), buena rusticidad, tolerancia al frío, y un temperamento dócil. Su rendimiento canal es modesto (67%) y su índice de sabor medio (82/100). Se cruza con el Coucou de Malines para producir el 'Majestic' porque: 1) El Malines aporta peso y estructura (5.0 kg ♂, rendimiento 72%). 2) La Faverolles aporta rusticidad para condiciones extensivas y adaptación al frío. 3) La distancia genética entre el Grupo 2 (Estructura) y el Grupo 3 (Rusticidad) maximiza la heterosis: crecimiento +15%, FCR +12%, resistencia a enfermedades +20%. El resultado: capones de 4.5-5.5 kg con buena adaptación al exterior."
    ),
    make(
        "¿Puede NeoFarm monitorizar gallinas ponedoras en sistema campero?",
        "Sí, aunque el foco actual de NeoFarm es carne/capones, las mismas tecnologías sirven para ponedoras: 1) Visión (YOLO): conteo de gallinas en nave/parque, detección de picaje (plumofagia), distribución espacial. Las 6 clases del modelo incluyen 'chicken'. 2) Acústica (INMP441): detección de patrones de cacareo asociados a estrés o puesta. 3) Ambiental (T/RH/NH3): las ponedoras camperas tienen umbrales similares (NH3 <20 ppm idealmente). 4) Para huevos: un sensor de conteo en nido podría estimar la tasa de puesta por nave. La regulación de gallinas camperas exige 4 m²/ave en exterior + enriquecimiento. NeoFarm verifica la densidad con visión y los parámetros ambientales con IoT. La heredabilidad de la puesta es h²=0.30 (media), respondiendo bien a selección."
    ),
    make(
        "¿Cuánto espacio necesita un capón en exterior según la normativa?",
        "Para capones extensivos bajo Label Rouge, el espacio mínimo es: interior 11 aves/m² (equivalente a 0.09 m²/ave), exterior mínimo 10 m²/ave con acceso obligatorio a pastos. Para la AOP Bresse los requisitos son más estrictos: exterior mínimo 10 m²/ave en parcelas rotadas, y la fase de épinette en jaula individual de 30×40 cm durante 4-5 semanas. En la práctica, para 500 capones necesitas: nave de ~46 m² interior + parcela de 5.000 m² exterior. Si aplicas rotación de parcelas (recomendado para descanso parasitario), necesitas 2-3 parcelas de 5.000 m² cada una = 10.000-15.000 m² totales. NeoFarm verifica la densidad interior con conteo por visión (YOLOv8, 95% precisión) y el uso de parcelas exteriores con GPS/visión."
    ),
    make(
        "¿Qué sensores mínimos necesita una nave avícola?",
        "Para una nave avícola (pollos de carne, capones o ponedoras), los sensores mínimos son: 1) Temperatura + Humedad (BME280 o SHT31, ~5-10 EUR): T óptima varía por edad (35°C día 1, bajando 3°C/semana hasta 21°C a las 4 semanas). 2) NH3 (sensor electroquímico, ~50-100 EUR): máximo 20-25 ppm. 3) Luz (luxómetro integrado, <5 EUR): las aves requieren fotoperiodo controlado (16h luz / 8h oscuridad para engorde, 14-16h para puesta). 4) CO2 (<10 EUR): máximo 3.000 ppm. Total: ~70-125 EUR/nave + ESP32 + LoRa/WiFi = ~100-170 EUR. Es mucho más barato que en porcino porque las naves son más pequeñas y hay menos capas necesarias. La cámara de visión (~50-80 EUR) es opcional pero recomendada para vigilar mortalidad."
    ),
    make(
        "¿Qué diferencia hay entre el modelo de PorciData para porcino y el de VacasData para vacuno?",
        "PorciData y VacasData son dos módulos IoT de NeoFarm optimizados para contextos muy diferentes. PorciData es intensivo (naves cerradas): 7+1 capas de sensores fijos por nave (~1.420 EUR/nave), alta densidad de datos, monitorización 24/7, Digital Twin de nave con predicción de IC y fecha de envío. VacasData es extensivo (dehesa/pradera): centinelas GPS móviles (10-20 animales), comunicación LoRa/Mioty con gateways solares, GeoTwin 3D para visualización del territorio, NDVI satelital para biomasa, THI para estrés térmico. La frecuencia de datos también difiere: PorciData envía datos cada 1-5 min, VacasData cada 5-30 min. El modelo económico es diferente: PorciData opera en márgenes estrechos (~20-30€/cerdo) optimizando IC, VacasData en ciclos largos (~12-18 meses) optimizando fertilidad y peso destete."
    ),
    make(
        "¿Cómo puede NeoFarm ayudar durante una inspección del SIGE?",
        "Durante una inspección SIGE, NeoFarm proporciona: 1) Histórico completo de datos ambientales: gráficas de T/RH/NH3/luz de los últimos 12 meses almacenadas en InfluxDB, demostrando cumplimiento continuo del RD 1135/2002. 2) Registro de alertas y acciones: cada vez que NH3 superó 25 ppm, cuándo se detectó, cuándo se corrigió, y qué acción se tomó. 3) Plan de Bienestar Animal auto-actualizado: densidad verificada por visión, iluminación >40 lux durante 8h/día, ruido <85 dB. 4) Plan de Alimentación: registro de consumo de pienso y agua por nave/día. 5) Plan de Emisiones: datos reales de NH3/VOCs vs ECOGAN. 6) Dashboard accesible en seedy-grafana.neofarm.io que el inspector puede consultar en tiempo real. Todo exportable en PDF/CSV para el expediente."
    ),
    make(
        "¿Qué es Tailscale y para qué lo usa NeoFarm?",
        "Tailscale es una red privada virtual (VPN mesh) basada en WireGuard que NeoFarm usa para acceso remoto seguro durante el desarrollo. Cada dispositivo (portátil de David, servidor, gateways en campo) se une a la red Tailscale y recibe una IP estable (100.x.y.z). Esto permite: acceder al Ollama, Open WebUI, InfluxDB, y Grafana directamente por IP interna sin exponer puertos. En producción, el acceso público usa Cloudflare Tunnel (seedy.neofarm.io, seedy-api.neofarm.io, seedy-grafana.neofarm.io). Tailscale se mantiene activo como backdoor de emergencia: si el tunnel Cloudflare falla, se puede acceder a todo vía Tailscale. No sustituye al firewall del servidor — solo proporciona conectividad cifrada entre dispositivos autorizados."
    ),
    make(
        "¿Cómo se evalúa la calidad de respuesta de Seedy?",
        "Seedy se evalúa con un set de 'golden questions' — preguntas con respuesta conocida que cubren todos los dominios: IoT, nutrición, genética, normativa, visión, GeoTwin, avicultura. Las métricas son: 1) Exactitud técnica: ¿las cifras, fórmulas y normativas son correctas? (cero alucinaciones). 2) Completitud: ¿incluye toda la info relevante sin omitir datos críticos? 3) Coherencia: ¿es consistente con respuestas anteriores? 4) Naturalidad: ¿suena como un técnico agrario experto, no como un chatbot genérico? Después de cada fine-tune se pasa el set de golden questions y se compara con la versión anterior. La versión v7 migra a Qwen2.5-14B-Instruct para reducir alucinaciones como la que ocurrió con el 'Cuco de Malines' (datos inventados sobre una raza real)."
    ),
    make(
        "¿Cuántos workers tiene Seedy en Open WebUI y qué hace cada uno?",
        "Seedy tiene 6 workers especializados en Open WebUI: 1) Worker General: respuestas técnicas estándar sobre IoT, nutrición, genética, normativa. Es el que usa 90% del tráfico. 2) Worker Nutrición: formulación de raciones con HiGHS, análisis de ingredientes, tablas NRC 2012. 3) Worker Genética: cálculo de EPDs, consanguinidad, FarmMatch, heterosis. 4) Worker GeoTwin: consultas geoespaciales, NDVI, THI, parcelas. 5) Worker IoT/Digital Twin: alertas, playbooks de actuación, configuración de sensores. 6) Worker Coder & Data: asistencia técnica para el desarrollo de NeoFarm (Docker, Together.ai, LoRA merge, dataset creation). Cada worker tiene un system prompt especializado que guía al LLM hacia el dominio correcto."
    ),
    make(
        "¿Puedo usar NeoFarm para ovino o caprino?",
        "Actualmente, NeoFarm está optimizado para porcino (PorciData) y vacuno (VacasData), con módulo de avicultura emergente. El ovino y caprino son técnicamente posibles con adaptaciones: 1) Extensivo (ovino/caprino en pasto): el stack de VacasData (centinelas GPS, GeoTwin, NDVI) aplica directamente. Las colleras GPS para ovejas son más pequeñas y baratas. 2) Intensivo (cebo de corderos): el concepto de PorciData aplica (T/RH/NH3/agua), pero los umbrales son diferentes. 3) Genética: FarmMatch soporta cualquier especie parametrizando heredabilidades y umbral de consanguinidad. 4) Visión: YOLO necesitaría reentrenamiento con imágenes de ovejas (nueva clase 'sheep'). El mercado ovino en España es grande (Lonja de Segovia cotiza cordero lechal y pascual), pero NeoFarm prioriza porcino + vacuno antes de expandir a ovino."
    ),
    make(
        "¿Cómo gestiona NeoFarm las actualizaciones de firmware IoT en campo?",
        "Las actualizaciones de firmware de los ESP32 se hacen por OTA (Over-the-Air) cuando el dispositivo tiene conexión WiFi. El proceso: 1) El nuevo firmware se compila con PlatformIO/Arduino IDE y se sube a un servidor OTA (puede ser el propio backend NeoFarm). 2) El ESP32, en cada ciclo de despertar, verifica si hay una versión nueva disponible. 3) Si la descarga y verifica el checksum, flashea la nueva imagen y reinicia. Si falla, mantiene la versión anterior (partición dual A/B). 4) Para dispositivos sin WiFi (LoRa-only en campo), la actualización se hace por USB con un técnico en visita. Los gateways LoRa (Dragino, RAK) también soportan OTA vía su interfaz web. Las actualizaciones típicas son: corrección de bugs, cambio de intervalo de lectura, y adición de nuevos tipos de sensor."
    ),
    make(
        "¿Cómo sé si la calidad del agua es buena para mis cerdos?",
        "NeoFarm mide la calidad de agua con la capa 5 de PorciData (~80 EUR/nave): caudalímetro (consumo) + pH + temperatura del agua. Los rangos óptimos son: pH 6.5-8.0, temperatura <20°C (agua fría estimula consumo), conductividad eléctrica <3.000 μS/cm, nitratos <50 mg/L, coliformes totales 0 UFC/100 mL (análisis periódico en laboratorio). PorciData monitoriza pH y caudal en continuo; los análisis microbiológicos y mineralógicos se hacen 2-4 veces/año en laboratorio. La primera señal de problema de calidad de agua es: consumo anormal (excesivo si hay sal/sales minerales altas, reducido si hay sabor/olor malo). Si el consumo baja un -15% sin causa ambiental (T/RH normal), revisar primero la calidad del agua."
    ),
    make(
        "¿Cuál es la velocidad de crecimiento esperada en capones Malines?",
        "El Coucou de Malines puro crece más lento que un pollo industrial pero más rápido que la Bresse: alcanza 3.5-4.0 kg a las 16-18 semanas (vs 2.5 kg a las 6 semanas del industrial). Tras la caponización a las 6-8 semanas, la velocidad de crecimiento se reduce temporalmente (1-2 semanas de recuperación) y luego se normaliza. El capón Malines puro alcanza 4.5-5.0 kg a las 28-32 semanas. El cruce Majestic (Malines × Faverolles) puede llegar a 4.5-5.5 kg en el mismo período. Durante la fase de épinette (últimas 4-5 semanas), la ganancia es mayor por el engrasamiento con la dieta de pâtée (maíz + leche): +400-600 g/semana. FCR global del capón: ~3.0-3.5:1 (eficiente para extensivo, pero 2× peor que el industrial a 1.6-1.8:1)."
    ),
    make(
        "¿Qué protocolo sigue NeoFarm para la bioseguridad digital?",
        "NeoFarm aplica bioseguridad digital en varias capas: 1) Autenticación: Open WebUI usa usuarios con contraseña, los endpoints API usan tokens JWT. 2) Red: Docker con red interna ai_default (los contenedores no exponen puertos al exterior excepto los publicados). 3) Acceso externo: Cloudflare Tunnel con cifrado TLS de extremo a extremo (el tráfico nunca toca internet sin cifrar). 4) MQTT: en producción, TLS + autenticación por usuario/password. 5) Together.ai: API key enviada solo por HTTPS. 6) Datos sensibles: los datos de producción real (censo, mortalidad, pesos) nunca se envían al LLM en producción — Seedy tiene su conocimiento en RAG y SFT, no necesita datos reales del ganadero para responder preguntas técnicas. 7) Backups: volúmenes Docker con backup semanal."
    ),
    make(
        "¿Cómo se calibra la báscula walk-over de PorciData?",
        "La báscula walk-over (~350 EUR/nave) se calibra trimestralmente: 1) Colocar 3 pesos conocidos (ej. 25 kg, 50 kg, 100 kg) sobre la plataforma. 2) Verificar que la lectura coincide ±0.5 kg con el peso conocido. 3) Si hay desviación, ajustar el offset y la pendiente (ganancia) en el firmware del Arduino/ESP32 que lee la celda de carga (HX711). La fórmula es: peso_real = (lectura_ADC - offset) × ganancia. La celda de carga debe limpiarse de restos (purín, pienso) porque la corrosión afecta la precisión. En la práctica, la báscula walk-over se instala en un paso obligado (corredor hacia bebedero) para que todos los cerdos pasen al menos 1-2 veces al día. Los datos se envían vía LoRa con el RFID del animal para identificación individual."
    ),
    make(
        "¿Cómo NeoFarm asegura que los datos de IoT son fiables?",
        "La fiabilidad de los datos IoT se garantiza con: 1) Validación de rango: Node-RED descarta lecturas imposibles (T <-10°C o >60°C, NH3 <0 o >200 ppm). 2) Filtrado de outliers: media móvil de 5 lecturas, se descarta si desviación >3σ. 3) Cross-validation: si T ambiental sube bruscamente pero T de agua se mantiene, es probable un fallo del sensor ambiental. 4) Watchdog: alerta si un sensor no envía datos en 3× su intervalo. 5) Calibración periódica: sensores de NH3 se verifican con tubo Dräger cada 6 meses, báscula con pesos conocidos trimestralmente. 6) Redundancia: en naves críticas, 2 sensores de T/RH por nave. Los datos se marcan con quality_flag (good/suspect/bad) en InfluxDB."
    ),
    make(
        "¿Qué sucede cuando un lote de cerdos termina el cebo y se envía a matadero?",
        "Cuando el Digital Twin proyecta que el lote ha alcanzado el peso objetivo (105-115 kg) o la cotización de lonja es favorable, NeoFarm genera un informe de fin de lote: 1) Resumen productivo: GMD media, IC medio, peso estimado, mortalidad %, consumo total de pienso y agua. 2) Resumen económico: ingresos (n° cerdos × peso × cotización Mercolleida) − costes (pienso, lechón, veterinario, energía) = margen bruto/cerdo. 3) Resumen sanitario: eventos de alerta, uso de antibióticos, incidencias. 4) Datos para retroalimentación genética: peso canal y clasificación EUROP del matadero → actualizan los EPDs de los padres. 5) Limpieza: se registra fechas de vaciado sanitario y LDD para el SIGE. El informe se exporta en PDF y se compara con lotes anteriores para detectar tendencias."
    ),
    make(
        "¿Cómo funciona la detección de mastitis en vacuno con IoT?",
        "En vacuno lechero (no es el foco principal de NeoFarm, pero es técnicamente posible), la mastitis se detecta por: 1) Conductividad eléctrica de la leche: aumenta >6 mS/cm por la inflamación. Se mide en el robot o en la sala de ordeño. 2) Actividad individual: las vacas con mastitis caminan menos y rumiación disminuye — detectable por acelerómetro del collar centinela. 3) Flujo de leche: reducción de producción >15% respecto a la curva de lactación esperada. 4) Temperatura de ubre: detectable por cámara térmica (capa 3 de PorciData adaptada). Para vacuno de carne extensivo (foco de NeoFarm), la mastitis es menos frecuente pero cuando ocurre, el ternero pierde peso — detectable por la báscula walk-over si existe."
    ),
    make(
        "¿Qué pasa si se cae el WiFi o internet en la granja?",
        "NeoFarm está diseñado para ser resiliente a cortes de internet: 1) Los sensores ESP32 + LoRa NO dependen de WiFi/internet — transmiten por radio LoRa al gateway local. 2) El gateway almacena datos en buffer local (SD card o flash) con retries automáticos. 3) Los datos se acumulan hasta que vuelve la conexión y se sincronizan automáticamente. 4) El Jetson Orin Nano (visión) funciona 100% offline — la inferencia YOLO/TensorRT es local, las alertas se almacenan y se envían cuando hay conexión. 5) Grafana local (en la red LAN de la granja) funciona sin internet si InfluxDB es local. Lo que NO funciona sin internet: Seedy (LLM en Together.ai o Ollama en servidor remoto), CloudflareTunnel (acceso externo), y sincronización con hub.vacasdata.com. Pero las alertas críticas se re-envían automáticamente."
    ),
    make(
        "Quiero preparar capones para Navidad. ¿Cuándo debo empezar?",
        "Para tener capones listos en Navidad (sacrificio primera quincena de diciembre), el calendario retrospectivo es: 1) Nacimiento de pollitos: abril-mayo (necesitas 210-240 días de ciclo). 2) Caponización: junio (6-8 semanas de vida, 600-800 g). 3) Pastoreo/crecimiento: julio-octubre (acceso a exterior, 10 m²/ave). 4) Entrada en épinette: noviembre (~4-5 semanas antes del sacrificio). 5) Sacrificio: primera quincena de diciembre. 6) Comercialización: semanas del 15-31 de diciembre. Para 500 capones, pide 550-570 pollitos machos (margen para mortalidad pre-caponización 5-8% + caponización 2-5%). Precios de venta en Navidad: capón entero 12-25 €/kg (vs 5-8 €/kg fuera de temporada). Razas recomendadas: Malines puro o cruce Majestic (Malines × Faverolles) para capones de 4.5-5.5 kg."
    ),
    make(
        "¿Qué métricas nos valen para la PAC 2023-2027 con eco-esquemas ganaderos?",
        "NeoFarm documenta objetivamente varias métricas exigidas por los eco-esquemas de la PAC 2023-2027: 1) Pastoreo extensivo: GPS centinelas demuestran que el ganado pasta X días/año, con carga ganadera real (UGM/ha). 2) Rotación de pastos: GeoTwin registra las parcelas usadas por período, evidenciando rotación. 3) Biodiversidad en dehesa: NDVI periódico muestra mantenimiento de cobertura vegetal. 4) Bienestar animal: IoT documenta condiciones ambientales continuas (T/RH/NH3) + densidad + consumo de agua. 5) Reducción de emisiones: datos reales de NH3/CO2 vs ECOGAN genérico. 6) Mantenimiento de razas autóctonas: pedigree + EPDs documentan la pureza racial. Todo exportable en informes PDF estandarizados para la solicitud PAC."
    ),
    make(
        "¿Cuáles son las 7+1 capas IoT de PorciData y cuánto cuesta cada una?",
        "Las 7+1 capas de PorciData con su coste por nave son: Capa 1 — Acústica: micrófono INMP441 + ESP32-S3 = ~15 EUR. Detección de tos, ReHS. Capa 2 — Visión RGB: cámara IP 4MP + Jetson Nano = ~150 EUR. Conteo, peso visual, cojeras. Capa 3 — Visión Térmica: Hikvision bi-espectro = ~550 EUR. Temperatura corporal sin contacto. Capa 4 — Ambiental: Dragino LoRa + Renke T/RH/NH3/CO2/luz = ~200 EUR. Capa 5 — Agua: caudalímetro + pH + ESP32 = ~80 EUR. Primera mundial en porcino a este precio. Capa 6 — Nariz electrónica: BME688 + SPS30 + ESP32 = ~50 EUR. Primera publicación con BME688 en porcino. Capa 7 — Radar: Seeed MR60BHA1 60 GHz = ~25 EUR. Primera aplicación en porcino. Capa +1 — Peso: walk-over con celdas de carga + RFID + HX711 = ~350 EUR. Total: ~1.420 EUR/nave, 10× menos que Fancom/Nedap (>14.500 EUR/nave)."
    ),
    make(
        "¿Cuál es el plan de formación mínimo del SIGE y cómo ayuda NeoFarm?",
        "El Plan de Formación del SIGE (Plan 10) exige un mínimo de 20 horas de formación anual para el personal de la explotación. Debe incluir: bienestar animal, bioseguridad, manejo sanitario, gestión ambiental, y seguridad laboral. NeoFarm NO sustituye la formación presencial obligatoria, pero ayuda de dos formas: 1) Seedy actúa como tutor técnico 24/7 — el ganadero puede preguntar sobre normativa, manejo, nutrición, genética, etc. y recibir respuestas actualizadas basadas en sus propios datos. 2) NeoFarm puede generar material de formación personalizado: informes con las incidencias reales de la explotación (ej: 'este año tuvimos 3 alertas de NH3 >25 ppm, así es cómo las gestionamos') que se documentan como formación práctica. Las 20 horas se acreditan con certificado del organismo formador."
    ),
    make(
        "¿Cómo se conecta NeoFarm con el matadero para cerrar el ciclo de datos?",
        "NeoFarm recibe datos del matadero para retroalimentar la genética y la economía: 1) Peso canal: se compara con el peso estimado por IoT para validar la calibración de la báscula walk-over / visión. 2) Clasificación EUROP: se asigna al animal y retroalimenta los EPDs de los padres (mejorar selección de conformación). 3) Grasa dorsal: correlaciona con la nutrición de acabado. 4) Decomisos: identifica problemas sanitarios post-mortem que no se detectaron ante-mortem. La integración es por fichero CSV/EDI que el matadero genera automáticamente, o manualmente si el matadero es pequeño. En España, los mataderos generan la información de clasificación EUROP por ley. El ganadero solo necesita pedir que le envíen el fichero de resultados vinculado a los crotales RFID de sus animales."
    ),
    make(
        "¿Cómo se dimensiona un biodigestor anaerobio para una granja de 2.000 cerdos?",
        "Un biodigestor para 2.000 plazas de cebo procesa ~12.000 L/día de purín (6 L/cerdo/día). El volumen del digestor es 25-35 días de retención hidráulica × 12 m³/día = 300-420 m³. Produce ~300-450 m³ de biogás/día (~60% CH4), equivalente a ~180-270 m³ CH4 → 630-950 kWh térmicos o 250-380 kWh eléctricos con un CHP. Inversión: 150.000-300.000€ para una planta de esta escala. ROI: 5-8 años sin subvenciones. GeoTwin calcula que el biodigestor reduce las emisiones de CH4 de purines un -60%, lo que equivale a ~X toneladas de CO2eq/año (dependiente del censo). El digestato resultante contiene el mismo nitrógeno pero en forma amoniacal (más disponible para cultivos), mejorando su valor como fertilizante."
    ),
]

# ============================================================
# BATCH 4 — Relleno final para llegar a ~500 (~33 ejemplos)
# ============================================================
new_examples += [
    make(
        "¿Cuál es la temperatura crítica inferior del lechón recién nacido?",
        "El lechón recién nacido tiene una temperatura crítica inferior (TCI) de ~34°C, lo que significa que por debajo de esa temperatura ambiental empieza a gastar energía en termorregulación. Nace sin grasa subcutánea significativa, sin pelaje denso, y con reservas de glucógeno para solo 12-18 horas. Por eso se necesita un foco de calor (lámpara o placa calefactora) a 32-35°C en la zona de descanso del lechón durante las primeras 48 horas, reduciéndose gradualmente 2-3°C por semana. La nave de maternidad se mantiene a 20-22°C para confort de la cerda, creando un microclima diferenciado. PorciData monitoriza T del foco con un sensor dedicado y alerta si cae por debajo de 30°C."
    ),
    make(
        "¿Cuánto CO2 emite una plaza de cerdo de cebo al año?",
        "Las emisiones por plaza de cebo porcino (2.5 rotaciones/año, 90 kg media) son aproximadamente: CH4 entérico = 1.5 kg CH4/año (=42 kg CO2eq × GWP=28), CH4 de purines = 3-6 kg CH4/año (=84-168 kg CO2eq), N2O del estiércol = 0.05-0.1 kg N2O/año (=15-30 kg CO2eq × GWP=298), CO2 directo (respiración) = no se contabiliza (biogénico). Total: ~140-240 kg CO2eq/plaza/año. Con un biodigestor (-60% CH4 purines) y aditivo 3-NOP (-30% CH4 entérico), se puede reducir a ~70-130 kg CO2eq/plaza/año. ECOGAN calcula estas emisiones automáticamente. GeoTwin de NeoFarm puede alimentar ECOGAN con datos reales de IoT en vez de estimaciones."
    ),
    make(
        "¿Cómo gestiona NeoFarm la trazabilidad animal?",
        "La trazabilidad en NeoFarm se integra en el Plan 11 del SIGE (Trazabilidad). Para porcino: cada animal tiene un crotal (identificación individual) o el lote tiene un código. PorciData registra: fecha de entrada, origen (integradora/proveedor), peso de entrada, fecha de salida, peso de salida, destino (matadero), guía de transporte. Los datos de movimiento están en PostgreSQL y son consultables por la API desde la app. Para vacuno: cada animal tiene DIB (Documento de Identificación Bovina), pasaporte individual, y crotal oficial — NeoFarm lo mapea al ID del collar GPS centinela. Los cambios de censo se reportan automáticamente a SITRAN (Sistema Integral de Trazabilidad Animal) cuando la integración está configurada."
    ),
    make(
        "¿Qué ventajas tiene un LLM fine-tuned frente a ChatGPT genérico para el ganadero?",
        "Seedy (LLM fine-tuned) tiene 3 ventajas clave frente a ChatGPT o similar: 1) Precisión especializada: Seedy está entrenado con datos técnicos verificados de NeoFarm (normativa española, BOM PorciData con precios exactos, razas autóctonas españolas, lonjas locales). ChatGPT puede inventar cifras o mezclar normativa de otros países. 2) RAG actualizado: Seedy accede a 8 colecciones de conocimiento en Qdrant con los documentos técnicos reales de NeoFarm, siempre actualizados. 3) Integración: Seedy se conecta con los datos IoT del ganadero (futuro) para dar respuestas contextuales: 'tu NH3 está a 28 ppm, baja la ventilación'. ChatGPT no tiene acceso a tus sensores. La desventaja: Seedy es 14B parámetros vs GPT-4 ~1T, así que en preguntas muy generales ChatGPT será mejor."
    ),
    make(
        "¿Qué es SITRAN y cómo se conecta con NeoFarm?",
        "SITRAN (Sistema Integral de Trazabilidad Animal) es la plataforma oficial del MAPA para la gestión de la trazabilidad ganadera en España. Registra: explotaciones (REGA), censos, movimientos (guías), alertas sanitarias, y sacrificios. Cada comunidad autónoma tiene su portal SITRAN. NeoFarm puede automatizar parcialmente la comunicación con SITRAN: 1) Al dar de alta/baja animales en NeoFarm, se genera el formato de comunicación compatible con SITRAN. 2) Los movimientos (entrada/salida de animales) se registran con fecha, origen, destino, y guía. 3) Para vacuno, el DIB + pasaporte se vincula al ID interno de NeoFarm. La integración completa vía API de SITRAN depende de la CCAA — algunas ofrecen webservices, otras solo formulario web."
    ),
    make(
        "¿Qué es la fórmula Meuwissen & Luo 1992 y por qué se usa?",
        "Meuwissen & Luo (1992) describieron un algoritmo tabular eficiente para calcular el coeficiente de consanguinidad F de Wright de todos los individuos de un pedigrí en una sola pasada. La complejidad es O(n²) donde n es el número de individuos. Antes de este algoritmo, calcular F requería recorrer el pedigrí por caminos (path coefficient method) con complejidad exponencial. NeoFarm implementa este algoritmo para calcular F de todos los animales de una explotación o cooperativa: con 5.000 animales y 5 generaciones de pedigrí, se ejecuta en milisegundos. El resultado alimenta al solver FarmMatch: apareamientos que producirían F > umbral (6.25% porcino industrial, 8% vacuno extensivo, 15% avicultura) se descartan automáticamente."
    ),
    make(
        "¿Cómo calcula NeoFarm el GEBV con la fórmula VanRaden 2008?",
        "El GEBV (Genomic Estimated Breeding Value) se calcula con la fórmula de VanRaden (2008): G = ZZ'/Σ(2p(1-p)), donde Z es la matriz de genotipos centrada (0/1/2 por SNP, centrada por la frecuencia alélica), Z' es su transpuesta, y Σ(2p(1-p)) es un factor de escala basado en las frecuencias alélicas. La matriz G resultante es la matriz de relación genómica, que reemplaza la matriz A (relación basada en pedigrí) en la evaluación genética. La exactitud del valor de cría se estima como: r = √(n × h² / (1 + (n-1) × h²/4)), donde n es el número de mediciones y h² la heredabilidad. Con paneles de >50K SNPs, el GEBV es más preciso que el EPD fenotípico, especialmente para caracteres con h² baja."
    ),
    make(
        "¿Para qué necesita NeoFarm un reranker en el RAG?",
        "El reranker (bge-reranker-v2-m3) mejora la calidad de los documentos recuperados por RAG. El flujo es: 1) La pregunta del usuario se convierte en embedding con mxbai-embed-large. 2) Qdrant busca los Top K=8 chunks más similares por distancia coseno (búsqueda híbrida con BM25 weight 0.7). 3) El reranker re-ordena esos 8 chunks por relevancia real (modelo cross-encoder que ve pregunta + chunk juntos). 4) Los top 3-5 chunks rerankeados se pasan al LLM como contexto. Sin reranker, el embedding puede recuperar chunks superficialmente similares pero no relevantes. Con reranker, la precisión sube significativamente. El reranker corre localmente (~300 MB) y añade ~200 ms de latencia, aceptable para calidad. El umbral de relevancia es 0.25 — chunks con score <0.25 se descartan."
    ),
    make(
        "¿Cómo importa NeoFarm los datos PNOA para ortofoto en GeoTwin?",
        "El PNOA (Plan Nacional de Ortofotografía Aérea) del IGN España proporciona ortofotografías de alta resolución (25-50 cm/px) de todo el territorio español. GeoTwin accede a las ortofotos vía WMTS (Web Map Tile Service) del IGN: https://www.ign.es/wmts/pnoa-ma. No se descargan los datos completos — se cargan tiles bajo demanda según la vista de cámara en CesiumJS. La alternativa (fallback) es Bing Maps. Para análisis offline o zonas con mala conectividad, se pueden pre-cachear tiles en un rango geográfico. Las ortofotos PNOA se usan para: identificar naves, caminos, punting de agua, lindes de parcelas, y como textura base del terreno 3D (MDT02). La combinación MDT02 (2 m resolución terreno) + PNOA (25 cm ortofoto) da un gemelo digital geoespacial de alta fidelidad."
    ),
    make(
        "¿Qué es el solver HiGHS y por qué lo eligió NeoFarm?",
        "HiGHS es un solver open source de programación lineal (LP), programación lineal mixta entera (MIP) y programación cuadrática (QP), desarrollado en la Universidad de Edimburgo. NeoFarm lo eligió por: 1) Open source (licencia MIT) — sin costes de licencia vs CPLEX o Gurobi (miles de €/año). 2) Rendimiento competitivo — para los tamaños de problema de NeoFarm (20-40 variables × 20-40 restricciones en nutrición, ≤500 variables en FarmMatch) es más que suficiente. 3) Soporte multi-lenguaje: Python, C, C++, JavaScript/WASM. 4) Se usa tanto en formulación de raciones (LP mínimo coste) como en optimización de apareamientos (MILP). La alternativa javascript-lp-solver vía WASM permite ejecutar formulaciones directamente en el navegador sin backend."
    ),
    make(
        "¿Cuántos litros de agua por día necesita una vaca de cría en dehesa?",
        "Una vaca de cría en dehesa (500-600 kg) necesita 40-60 litros de agua al día en condiciones normales, y hasta 80-100 L/día en verano con estrés calórico. En lactación, la demanda sube a 60-90 L/día. Para un rebaño de 100 vacas en verano: 100 × 80 L = 8.000 L/día mínimo de capacidad en abrevaderos. NeoFarm monitoriza los puntos de agua con caudalímetro o sensor de nivel de depósito, mapeados en GeoTwin. Si un abrevadero se seca o el consumo total baja >15%, es alerta (puede indicar avería, contaminación del agua, o que las vacas están concentradas en otro punto). En dehesas extensas con múltiples puntos de agua, los GPS centinelas muestran qué puntos de agua usa el ganado realmente."
    ),
    make(
        "¿Cómo evalúa NeoFarm la rentabilidad de una explotación extensiva?",
        "NeoFarm calcula la rentabilidad extensiva con el módulo económico del Digital Twin Vacuno: Ingresos = (n° terneros destetados × peso destete × cotización lonja Segovia) + subvenciones PAC + venta de desvieje. Costes = alimentación suplementaria + veterinario + mano de obra + amortización de instalaciones + IBI + seguros + agua + vallados. Margen bruto por vaca = Ingresos − Costes variables. Para una explotación de 100 Avileñas en dehesa: 85 terneros destetados (85% fertilidad) × 230 kg × 3.0 €/kg = 58.650€ ingresos + 15.000€ PAC = 73.650€. Costes: 35.000-45.000€. Margen bruto: 28.650-38.650€, es decir 286-386€/vaca. NeoFarm calcula esto mensualmente con datos reales para detectar tendencias."
    ),
    make(
        "¿Qué es Cesium Ion y qué assets de NeoFarm se alojan ahí?",
        "Cesium Ion es el servicio cloud de Cesium para alojar assets 3D, tilesets y terrenos. NeoFarm usa Cesium Ion para: 1) Cesium World Terrain (asset Cesium): terreno global a ~30 m de resolución, fallback cuando MDT02 no está disponible. 2) Bing Maps (asset ID 2): capa de imagen satelital alternativa a PNOA. 3) MDT02 Spain (asset ID 4475569): terreno de alta resolución 2 m del CNIG, subido como Quantized Mesh Terrain a Cesium Ion para servir tiles bajo demanda. Los assets 3D propios (naves, silos, animales) se sirven desde el servidor local de NeoFarm como glTF/GLB, no desde Ion, para control total y offline-first. Cesium Ion requiere un API token en la configuración de GeoTwin."
    ),
    make(
        "¿Cómo mejora la detección temprana la tasa de mortalidad?",
        "La detección temprana IoT reduce la mortalidad significativamente: 1) Acústica (ReHS): detecta tos 2.6 días antes de síntomas visibles (dato SoundTalks), permitiendo medicación selectiva (solo corrales afectados, -28% antibióticos). 2) Agua: caída >15% precede a problemas en 24-48h — tiempo para diagnosticar antes de que se extienda. 3) Visión: animal caído >30 min = alerta inmediata de urgencia (93% precisión). 4) Térmica: fiebre individual detectada por cámara bi-espectro antes de que el animal deje de comer. En datos agregados: una reducción del 2% en mortalidad en una granja de 5.000 cerdos/año × 150€/cerdo = 15.000€/año de ahorro, vs coste de PorciData (~8.500€ total para 6 naves). El payback es de ~6 meses."
    ),
    make(
        "¿Puede NeoFarm predecir la producción de carne por lote?",
        "Sí, el Digital Twin proyecta el peso total del lote en tiempo real: peso_total_proyectado = Σ(peso_individual_estimado_i + GMD_i × días_restantes_i) para cada animal i. Los inputs son: peso estimado por visión/báscula, GMD calculada por la pendiente del peso en los últimos 7 días, y consumo de pienso. El twin también proyecta: rendimiento canal esperado (78-80% para cerdo blanco), clasificación EUROP probable (según genética + grasa dorsal), e ingresos esperados (peso canal × cotización Mercolleida). Si la GMD del lote cae >5% respecto a la curva esperada, se genera una alerta para investigar causas (enfermedad, estrés, problema nutricional). Esto permite al ganadero planificar con el matadero la fecha de envío óptima."
    ),
    make(
        "¿Cuál es la huella hídrica de producir 1 kg de carne de cerdo?",
        "La huella hídrica de 1 kg de carne porcina es ~6.000 litros de agua, considerando agua verde (lluvia para cultivos de pienso: 4.800 L), agua azul (riego + bebida: 600 L), y agua gris (contaminación/depuración: 600 L). En comparación: vacuno 15.000 L/kg, pollo 4.300 L/kg, huevos 3.300 L docena. NeoFarm reduce la huella hídrica optimizando: 1) IC (menos pienso necesario = menos agua verde). 2) Detección de fugas de agua (caudalímetro IoT). 3) Reciclaje de agua de lavado para fosas. GeoTwin calcula la huella hídrica por plaza como métrica ESG, que es útil para: reporting de sostenibilidad, acceso a mercados con requisitos ambientales (grandes distribuidores), y créditos de carbono."
    ),
    make(
        "¿Qué diferencias hay entre LoRaWAN, Sigfox y Mioty para ganadería?",
        "Las 3 son tecnologías LPWAN (Low Power Wide Area Network), pero con diferencias clave: LoRaWAN es la más extendida en agro — frecuencia 868 MHz, buena cobertura rural (2-15 km), gateway propio (~200-300€), batería ~12 meses, pero capacidad limitada (miles de paquetes/día). Sigfox es operado (infraestructura del operador, sin gateway propio), más barato por dispositivo, pero menor flexibilidad y cobertura rural irregular en España. Mioty es la tecnología emergente: 44.000 paquetes/min/MHz (>1.000× más que LoRa), batería 3× más que LoRa (hasta 36 meses), FEC que tolera colisiones e interferencias. Para ganadería, Mioty es ideal para explotaciones grandes (>2.000 plazas con muchos sensores), LoRaWAN para explotaciones medianas (500-2.000), y Sigfox ya no se recomienda por la incertidumbre de la empresa."
    ),
    make(
        "¿Puedo usar Seedy sin IoT, solo como consultor técnico?",
        "Sí, Seedy funciona como consultor técnico independiente sin necesitar datos IoT. Puedes acceder a Seedy vía seedy.neofarm.io (chat web) o desde la app móvil y hacerle preguntas sobre: normativa SIGE (los 11 planes, RD 306/2020, RD 1135/2002), genética (calcular consanguinidad, comparar cruces, EPDs), nutrición (principios de formulación, aminoácidos limitantes, fases de alimentación), sanidad (interpretar síntomas, protocolos), economía (cotizaciones de lonja, costes de producción). Seedy responde con datos técnicos verificados, no inventa cifras. El valor completo se obtiene cuando IoT + Seedy trabajan juntos (el twin proporciona contexto real), pero Seedy solo ya supera a ChatGPT genérico en calidad de respuestas agrarias."
    ),
    make(
        "¿Cómo funciona la exportación de datos de NeoFarm para compliance?",
        "NeoFarm exporta datos en múltiples formatos para compliance: 1) CSV: tablas de lecturas de sensores, alertas, movimientos de animales — compatible con Excel, SITRAN, y auditores. 2) PDF: informes mensuales/anuales con gráficas, KPIs, resumen de incidencias, cumplimiento de umbrales legales. 3) JSON/API: para integración con ERPs (AgroVision, CloudFarms) y servicios gubernamentales (SITRAN, veterinario oficial). Los informes de bienestar animal incluyen: horas de cumplimiento de NH3 <25 ppm, T en rango, iluminación >40 lux, densidad correcta. Para inspecciones ambientales: emisiones reales vs ECOGAN. Para PAC: carga ganadera, rotación de pastos, eco-esquemas. Todo con timestamp trazable desde el sensor hasta el informe."
    ),
    make(
        "¿Cómo se configura el RAG de Seedy con BM25 y búsqueda híbrida?",
        "El RAG de Seedy usa búsqueda híbrida: combina embeddings semánticos (mxbai-embed-large, 1024 dims) con BM25 (búsqueda por palabras clave). La configuración en Open WebUI/Qdrant es: chunk_size=1500 caracteres, overlap=300, Top K=8 documentos recuperados, BM25_weight=0.7 (peso relativo del BM25 sobre el embedding). El flujo completo: pregunta → embedding con mxbai-embed-large → consulta a Qdrant (semántica + BM25 con peso 0.7) → Top 8 chunks → reranking con bge-reranker-v2-m3 → filtrado por relevance_threshold 0.25 → top 3-5 chunks relevantes → se inyectan como contexto al LLM (Seedy fine-tuned) → respuesta. La búsqueda híbrida es mejor que puramente semántica porque respeta términos técnicos exactos (ej: 'RD 306/2020' o 'BME688')."
    ),
    make(
        "¿Cuánto cuesta el fine-tune de Seedy en Together.ai?",
        "El fine-tune de Seedy en Together.ai cuesta ~3-8 USD por job para modelos 7B con ~300-500 ejemplos y 4 epochs. Para el 14B el coste es ~6-15 USD por job. La configuración estándar es: LoRA r=64, alpha=128, 4 epochs, learning rate=2e-5, batch_size=auto. El tiempo de entrenamiento es ~15-30 min para 7B y ~30-60 min para 14B. El inference en producción con modelo fine-tuned en Together.ai cuesta ~0.20 USD/millón de tokens input y ~0.60 USD/millón tokens output para 7B. Con ~500 consultas/día × 500 tokens/consulta de media, el coste mensual de inference es ~5-15 USD. Es extremadamente barato comparado con GPT-4 (~30 USD/millón tokens input). El modelo local en Ollama (fallback) tiene coste 0 de inference pero consume VRAM."
    ),
    make(
        "¿Cómo se mide el graso infiltrado del capón y por qué importa?",
        "El graso infiltrado (intramuscular) es la grasa depositada dentro del músculo, entre las fibras musculares. Es lo que da la 'textura fundente' y el sabor al capón premium. Se mide post-mortem por: 1) Análisis químico (extracción Soxhlet): método de referencia, da % de grasa exacto. 2) Espectroscopia NIR (Near Infrared): rápido y no destructivo, ~2% de error. Un capón de calidad tiene 8-15% de grasa intramuscular vs 2-4% de un pollo industrial. El engrasamiento se logra en la fase de épinette: la dieta de pâtée (maíz + leche) durante 4-5 semanas promueve la deposición grasa intramuscular. La caponización es clave: sin testosterona, el metabolismo del capón favorece la deposición de grasa en vez de músculo magro, produciendo carne más tierna y sabrosa."
    ),
]

# --- Merge v6 + nuevos, dedup ---
all_examples = base + new_examples

# Dedup by user question (normalized)
seen = set()
deduped = []
dupes = 0
for ex in all_examples:
    q = ex["messages"][1]["content"].strip().lower()
    if q not in seen:
        seen.add(q)
        deduped.append(ex)
    else:
        dupes += 1

print(f"\nBase v6: {len(base)}")
print(f"Nuevos: {len(new_examples)}")
print(f"Total antes de dedup: {len(all_examples)}")
print(f"Duplicados eliminados: {dupes}")
print(f"Dataset v7 final: {len(deduped)}")

# --- Update system prompt for ALL examples ---
for ex in deduped:
    ex["messages"][0]["content"] = SYSTEM

# --- Save ---
with open("seedy_dataset_sft_v7.jsonl", "w") as f:
    for ex in deduped:
        f.write(json.dumps(ex, ensure_ascii=False) + "\n")

print(f"\n✅ Guardado: seedy_dataset_sft_v7.jsonl ({len(deduped)} ejemplos)")

# --- Audit final ---
KEYWORDS = {
    "IOT": ["iot", "sensor", "esp32", "mqtt", "porcidata", "influx", "grafana", "bom", "firmware", "lora", "meshtastic", "mioty"],
    "NUTRICION": ["nutri", "butirato", "nrc", "aminoácido", "lisina", "pienso", "dieta", "formulación", "ración", "highs"],
    "GENETICA": ["genétic", "epd", "consanguinidad", "heterosis", "cruce", "raza", "wright", "farmmatch", "apareamiento", "heredabilidad"],
    "NORMATIVA": ["sige", "rd 306", "rd 1135", "ecogan", "normativ", "bienestar animal"],
    "PORCINO": ["cerdo", "porcin", "lechón", "cebo", "gestación", "nave ", "maternidad", "ibérico"],
    "VACUNO": ["vacun", "bovin", "ternero", "vaca", "extensiv", "pastizal", "dehesa", "centinela"],
    "AVICULTURA": ["capón", "gallina", "pularda", "bresse", "avícola", "avicultura", "pollo", "malines", "coucou"],
    "TWINS": ["digital twin", "gemelo digital", "world model", "simulación", "centinela"],
    "GEOTWIN": ["geotwin", "gis", "cesium", "pnoa", "catastro", "ndvi", "parcela", "geoespacial", "thi "],
    "VISION": ["yolo", "visión artificial", "computer vision", "tensorrt", "opencv", "detección visual", "cámara ia", "yolov8", "bot-sort", "edge ai", "jetson", "deepstream"],
}

cats = Counter()
for ex in deduped:
    text = ' '.join(m['content'] for m in ex['messages'] if m['role'] != 'system').lower()
    for cat, kws in KEYWORDS.items():
        if any(kw in text for kw in kws):
            cats[cat] += 1

print(f"\nDistribución final v7 (sin system prompt):")
for cat, n in sorted(cats.items(), key=lambda x: -x[1]):
    print(f"  {cat:15s} {n:4d}")
