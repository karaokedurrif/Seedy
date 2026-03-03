# PorciData — Resumen IoT Hardware y BOM#
# Sinónimos y términos de búsqueda
BOM, Bill of Materials, presupuesto, coste total, precio hardware, 
cuánto cuesta, inversión por nave, coste sensores, coste IoT nave

## Documento índice para RAG — Colección "PorciData IoT & Hardware"

---

## COSTE TOTAL HARDWARE IoT POR NAVE: ~1.420 EUR

Esto es 10x más barato que alternativas comerciales (Fancom, Nedap, SoundTalks que cuestan >14.500 EUR equivalente).

---

## Las 7+1 Capas de Sensores IoT PorciData

### CAPA 1: Acústica — Detección de Tos Respiratoria
- **Hardware**: Micrófono MEMS INMP441 + ESP32-S3
- **Coste por nave**: ~15 EUR
- **Función**: Detectar tos respiratoria porcina (PRRS, Mycoplasma hyopneumoniae, Influenza A)
- **Modelo IA**: Random Forest con MFCC (cabe en ESP32) o CNN con espectrogramas Mel (Jetson)
- **Entrenamiento**: 500+ clips de tos + 1500 no-tos, etiquetados con Audacity o Label Studio
- **Métrica de salida**: Índice ReHS (Respiratory Health Status) — verde >60%, ámbar 40-60%, rojo <40%
- **Inferencia edge**: <5ms por ventana de 1 segundo en ESP32
- **Alternativa comercial**: SoundTalks (Boehringer Ingelheim) = ~1.000 EUR/nave/año
- **Ventaja PorciData**: 15 EUR una vez vs 1.000 EUR/año recurrente. Open source.
- **Impacto demostrado**: SoundTalks reportó intervención 2.6 días más rápida, -28% antibióticos, +12.7g/día ganancia media diaria

### CAPA 2: Visión RGB — Peso Estimado, Conteo, Cojera, Caudofagia
- **Hardware**: Cámara IP 4MP + Jetson Nano/Orin Nano con YOLO
- **Coste por nave**: ~150 EUR
- **Función**: Estimación de peso por imagen, conteo automático, detección de cojeras y mordedura de cola
- **Alternativa comercial**: Fancom iGrow, Nedap = >3.000 EUR

### CAPA 3: Visión Térmica — Fiebre, Estrés Calor
- **Hardware**: Hikvision bi-espectro (RGB + térmica integrada)
- **Coste por nave**: ~550 EUR
- **Función**: Temperatura oreja/cuerpo sin contacto, estrés térmico, verificación ventilación
- **Alternativa comercial**: FLIR T1020 + software = >5.000 EUR

### CAPA 4: Ambiental Core — Temperatura, Humedad, NH3, CO2
- **Hardware**: Dragino LoRa + sensores Renke industriales
- **Coste por nave**: ~200 EUR
- **Protocolo**: LoRaWAN estándar
- **Alternativa comercial**: Big Dutchman clima = ~1.500 EUR

### CAPA 5: Agua — Consumo, pH, Calidad
- **Hardware**: Caudalímetro + sensor pH + ESP32
- **Coste por nave**: ~80 EUR
- **Función**: Consumo diario por nave/corral, pH del agua, detección anomalías
- **Alternativa comercial**: NO EXISTE integrado (INNOVACIÓN ÚNICA PorciData)

### CAPA 6: Gases Avanzado — Nariz Electrónica
- **Hardware**: BME688 (Bosch, nariz electrónica) + SPS30 (Sensirion, partículas) + ESP32
- **Coste por nave**: ~50 EUR
- **Mide**: H2S, PM2.5, VOCs (compuestos orgánicos volátiles)
- **Burn-in**: BME688 requiere 48h de burn-in + 4-8 semanas de datos etiquetados
- **Alternativa comercial**: NO EXISTE en porcino (INNOVACIÓN ÚNICA PorciData — primera aplicación mundial)
- **Potencial**: Detección precoz de enfermedades por perfil de VOCs. Cero publicaciones científicas previas en granjas porcinas.

### CAPA 7: Radar Actividad — Actividad Nocturna, Respiración Grupal
- **Hardware**: Seeed MR60BHA1 (radar mmWave 60GHz)
- **Coste por nave**: ~25 EUR
- **Función**: Actividad nocturna, patrón respiratorio grupal, detección aplastamiento
- **Alternativa comercial**: NO EXISTE en porcino (INNOVACIÓN ÚNICA PorciData)
- **Alternativas evaluadas**: HLK-LD2410 (24GHz, 5 EUR, solo presencia), Infineon BGT60TR13C (40 EUR, signos vitales)

### CAPA 8: Peso Walk-Over — Peso Individual Real
- **Hardware**: Células de carga DIY + lector RFID + ESP32
- **Coste por nave**: ~350 EUR
- **Función**: Peso individual automático cuando el animal pasa por el comedero/bebedero
- **Alternativa comercial**: Fancom/Nedap = >3.000 EUR

---

## BOM PILOTO: 3 Naves (datos reales)

Granja intensiva de 10 naves. Piloto en 3 naves:
- 1 nave de madres/maternidad (~100 plazas madres)
- 2 naves de engorde (~500 plazas cada una, total 1.000 plazas engorde)

**Coste hardware por nave**: ~1.420 EUR
**Coste hardware piloto 3 naves**: ~4.260 EUR
**Coste SaaS mensual**: 99 EUR/mes
**ROI estimado**: 2.3 meses
**Equivalente comercial**: >14.500 EUR por nave = >43.500 EUR las 3 naves

---

## Arquitectura IoT PorciData

```
ESP32 (edge) → LoRaWAN/WiFi → Mosquitto (MQTT broker)
  → Node-RED (ETL/reglas) → InfluxDB (time-series)
  → Grafana (dashboards) → Alertas (push/Telegram)
  → FastAPI (twin/IA) → hub.vacasdata.com (frontend)
```

**Topics MQTT**: neofarm/{farm_id}/{barn_id}/{layer}/{sensor_type}
**Ejemplo**: neofarm/granja01/nave02/acoustic/cough_index

---

## Posicionamiento Competitivo

PorciData NO compite con ERPs (AgroVision PigVision, CloudFarms, PigExpert).
PorciData es la CAPA IoT + IA que se conecta ENCIMA de cualquier ERP existente vía API.

- vs Fancom/Nedap: 10x más barato, más capas, open source
- vs SoundTalks: ~15 EUR vs ~1.000 EUR/año, misma función
- vs AgroVision: Complemento, no competidor. PorciData añade inteligencia predictiva
- vs CloudFarms: Extensión IoT del "pasaporte digital" del cerdo
- Moat defensivo: 7 capas integradas, datasets propios, nariz electrónica BME688 sin precedente
