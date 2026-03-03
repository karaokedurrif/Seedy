# 🧠 PROMPT — VacasData Hub: Plataforma Inteligente Unificada

> **Para**: VSCode Copilot (Claude Sonnet 4.5)
> **Fecha**: 15 Febrero 2026
> **Decisión arquitectónica**: VacasData Hub es UN SOLO PRODUCTO. No hay "PorciData" separado. El motor es uno, los módulos se activan según especie/tipo. El branding (colores, navbar, logo) se adapta al contexto del tenant, pero el código, la API, la BD y el deploy son únicos.
> **Estado actual**: Dashboard porcino ✅, Nave lista básica ✅, Lotes ✅. Faltan: detalle nave 404, trazabilidad 404, SIGE 404, y toda la inteligencia.

---

## 🏗️ PRINCIPIO FUNDAMENTAL

```
VacasData Hub = 1 producto, N módulos

El wizard configura qué módulos activar:
  ├── Especie: bovino | porcino | ovino | caprino
  ├── Tipo: extensivo | intensivo | mixto
  └── Módulos: IoT, Genética, Sanidad, ERP, Trazabilidad, Carbono, Purines...

La navbar, colores y terminología se adaptan al perfil.
Pero la URL siempre es hub.vacasdata.com
La API siempre es api-v2.vacasdata.com
El login es uno.
```

---

## 🔴 PASO 0: Arreglar 404s (ANTES de todo lo demás)

```bash
# Verificar qué páginas existen realmente:
find /srv/docker/apps/vacasdata-hub-v2/apps/web/src/app -name "page.tsx" | sort
```

**Crear las páginas que faltan** (archivos mínimos funcionales, no placeholders "en construcción"):

```
DEBE EXISTIR:                         ESTADO
app/barns/[id]/page.tsx               ← FALTA (404 al hacer click en "Ver detalles")
app/traceability/page.tsx             ← FALTA (404)
app/sige/page.tsx                     ← FALTA (404)
app/reproductoras/page.tsx            ← VERIFICAR
app/purines/page.tsx                  ← CREAR
app/erp/page.tsx                      ← CREAR (nuevo)
app/settings/branding/page.tsx        ← CREAR (nuevo)
```

**Para cada página nueva**, el mínimo funcional es:

```tsx
'use client';
import { useState, useEffect } from 'react';

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8002';

export default function PageName() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/endpoint`)
      .then(r => r.json())
      .then(d => { setData(d); setLoading(false); })
      .catch(e => { console.error(e); setLoading(false); });
  }, []);

  if (loading) return <div className="p-8">Cargando...</div>;
  
  return (
    <div className="max-w-7xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-6">Título</h1>
      {/* Contenido real */}
    </div>
  );
}
```

**Rebuild después de crear todas las páginas:**
```bash
cd /srv/docker/apps/vacasdata-hub-v2
docker compose build web --no-cache && docker compose up -d web
```

**NO avanzar hasta que TODAS las rutas de la navbar devuelvan 200.**

---

## BLOQUE A: Constructor de Nave con Dimensiones Reales

### A1. Formulario de dimensiones

En `/barns/[id]/edit` o como modal en `/barns`, el ganadero introduce las medidas reales de su nave:

```typescript
interface BarnDimensions {
  length_m: number;         // Largo (ej: 80m)
  width_m: number;          // Ancho (ej: 14m)
  height_eaves_m: number;   // Altura al alero (ej: 3.5m)
  height_ridge_m: number;   // Altura cumbrera (ej: 5.5m)
  roof_type: "dos_aguas" | "plano" | "shed";
  orientation_degrees: number;  // 0=Norte
  
  // Layout interior
  corridor_width_m: number;     // Pasillo central
  corridor_position: "center" | "side";
  pen_rows: 1 | 2;
  pens_per_row: number;
  pen_width_m: number;
  pen_depth_m: number;
  
  // Instalaciones
  slat_type: "emparrillado_total" | "emparrillado_parcial" | "cama";
  feed_system: "tolva_seca" | "pipeline_líquido" | "comedero_lineal";
  ventilation: "chimenea" | "túnel" | "pared" | "cruzada";
  fosa_purin_m3: number;
  silos_count: number;
  doors: { x: number; y: number; type: string }[];
}
```

### A2. Vista 2D a escala (SVG) con dispositivos IoT

En vez de intentar Three.js complejo, hacer una **vista SVG a escala real** que sea práctica:

```tsx
// app/barns/[id]/page.tsx — Vista de planta de la nave

function BarnFloorPlan({ barn }: { barn: BarnWithDimensions }) {
  const SCALE = 8; // 1 metro = 8 píxeles
  const svgWidth = barn.dimensions.length_m * SCALE;
  const svgHeight = barn.dimensions.width_m * SCALE;
  const [editMode, setEditMode] = useState(false);
  const [selectedPen, setSelectedPen] = useState(null);

  return (
    <div>
      {/* Toolbar */}
      <div className="flex items-center justify-between mb-4">
        <div>
          <h1 className="text-xl font-bold">{barn.name}</h1>
          <p className="text-sm text-gray-500">
            {barn.dimensions.length_m}m × {barn.dimensions.width_m}m · 
            Altura: {barn.dimensions.height_eaves_m}m
          </p>
        </div>
        <div className="flex gap-2">
          <button onClick={() => setEditMode(!editMode)} 
            className="px-4 py-2 rounded-xl border text-sm">
            {editMode ? '✅ Guardar posiciones' : '📐 Editar dispositivos'}
          </button>
          <LayerToggles />
        </div>
      </div>

      {/* Indicadores ambientales en tiempo real */}
      <div className="grid grid-cols-4 gap-3 mb-4">
        <EnvironmentCard icon="🌡️" label="Temperatura" 
          value={`${barn.environment.temperature}°C`}
          status={barn.environment.temperature > 28 ? 'danger' : 'ok'} />
        <EnvironmentCard icon="💧" label="Humedad" 
          value={`${barn.environment.humidity}%`} />
        <EnvironmentCard icon="⚗️" label="NH₃" 
          value={`${barn.environment.nh3_ppm} ppm`}
          status={barn.environment.nh3_ppm > 20 ? 'danger' : 'ok'} />
        <EnvironmentCard icon="💨" label="CO₂" 
          value={`${barn.environment.co2_ppm} ppm`}
          status={barn.environment.co2_ppm > 3000 ? 'warning' : 'ok'} />
      </div>

      {/* SVG a escala */}
      <div className="overflow-auto border rounded-2xl bg-gray-50 p-2">
        <svg viewBox={`-20 -20 ${svgWidth + 40} ${svgHeight + 40}`} 
          className="w-full" style={{ minHeight: 400 }}>
          
          {/* Perímetro de la nave */}
          <rect x={0} y={0} width={svgWidth} height={svgHeight}
            fill="#F9FAFB" stroke="#374151" strokeWidth={3} rx={4} />
          
          {/* Techo (indicativo) */}
          <line x1={0} y1={svgHeight/2} x2={svgWidth} y2={svgHeight/2}
            stroke="#D1D5DB" strokeWidth={1} strokeDasharray="8,4" />
          
          {/* Pasillo central */}
          {barn.dimensions.corridor_position === 'center' && (
            <rect 
              x={0} 
              y={(svgHeight - barn.dimensions.corridor_width_m * SCALE) / 2}
              width={svgWidth}
              height={barn.dimensions.corridor_width_m * SCALE}
              fill="#E5E7EB" />
          )}
          
          {/* Corrales */}
          {barn.pens.map((pen, i) => {
            const pos = calculatePenPosition(pen, i, barn, SCALE);
            return (
              <g key={pen.id} onClick={() => setSelectedPen(pen)} 
                className="cursor-pointer">
                <rect {...pos} 
                  fill={getPenColor(pen.status)}
                  stroke="#6B7280" strokeWidth={1} rx={2}
                  className="hover:stroke-2 hover:stroke-blue-500 transition-all" />
                <text x={pos.x + 8} y={pos.y + 16} fontSize={11} fontWeight="bold" 
                  fill="#111827">
                  C{pen.number}
                </text>
                <text x={pos.x + 8} y={pos.y + 30} fontSize={9} fill="#4B5563">
                  🐷×{pen.current_count} · {pen.avg_weight_kg?.toFixed(0)}kg
                </text>
                <text x={pos.x + 8} y={pos.y + 42} fontSize={9} fill="#6B7280">
                  IC:{pen.feed_conversion?.toFixed(2)}
                </text>
              </g>
            );
          })}
          
          {/* Sensores IoT */}
          {barn.sensors?.map(sensor => (
            <g key={sensor.id} className={editMode ? 'cursor-move' : 'cursor-pointer'}>
              <circle 
                cx={sensor.position.x * SCALE} cy={sensor.position.y * SCALE}
                r={8} fill={getSensorColor(sensor.type)} stroke="white" strokeWidth={2} />
              <text x={sensor.position.x * SCALE} y={sensor.position.y * SCALE + 4}
                fontSize={10} textAnchor="middle" fill="white">
                {getSensorIcon(sensor.type)}
              </text>
            </g>
          ))}

          {/* Cámaras IA con campo de visión */}
          {barn.cameras?.map(cam => (
            <g key={cam.id}>
              <polygon 
                points={calculateCameraFOV(cam, SCALE)}
                fill="rgba(59,130,246,0.08)" stroke="#3B82F6" strokeWidth={1} />
              <text x={cam.position.x * SCALE} y={cam.position.y * SCALE}
                fontSize={14}>📷</text>
            </g>
          ))}

          {/* Silos (fuera de la nave) */}
          {barn.silos?.map((silo, i) => (
            <g key={silo.id}>
              <circle cx={svgWidth + 30} cy={30 + i * 50} r={18}
                fill={silo.level_pct > 20 ? '#22C55E' : '#EF4444'} 
                stroke="#374151" strokeWidth={2} />
              <text x={svgWidth + 30} y={30 + i * 50 + 4}
                fontSize={9} textAnchor="middle" fill="white" fontWeight="bold">
                {silo.level_pct}%
              </text>
              <text x={svgWidth + 55} y={30 + i * 50 + 4}
                fontSize={9} fill="#6B7280">{silo.name}</text>
            </g>
          ))}

          {/* Escala */}
          <line x1={10} y1={svgHeight + 15} x2={10 + 10 * SCALE} y2={svgHeight + 15}
            stroke="#9CA3AF" strokeWidth={2} />
          <text x={10} y={svgHeight + 28} fontSize={9} fill="#9CA3AF">10m</text>
        </svg>
      </div>

      {/* Panel lateral de corral seleccionado */}
      {selectedPen && <PenDetailPanel pen={selectedPen} onClose={() => setSelectedPen(null)} />}
    </div>
  );
}
```

### A3. Sugerencia automática de colocación de dispositivos

```python
# backend/services/device_placement.py

def suggest_device_placement(barn_dimensions: dict) -> dict:
    """
    Dado las dimensiones de una nave, sugiere dónde colocar sensores,
    cámaras IA y bridges Meshtastic.
    """
    L = barn_dimensions["length_m"]
    W = barn_dimensions["width_m"]
    H = barn_dimensions["height_eaves_m"]
    
    suggestions = []
    
    # Sensores Temp/HR: 1 cada 15m, a 60% de altura
    for i in range(max(2, int(L / 15))):
        x = (i + 0.5) * (L / max(2, int(L / 15)))
        suggestions.append({
            "type": "temp_humidity", "icon": "🌡️",
            "position": {"x": round(x, 1), "y": round(W / 2, 1), "z": round(H * 0.6, 1)},
            "reason": "1 sensor cada 15m de largo, a 60% de altura",
            "cost_eur": 25,
        })
    
    # NH3/CO2: cerca del suelo, 1 cada 25m
    for i in range(max(1, int(L / 25))):
        x = (i + 0.5) * (L / max(1, int(L / 25)))
        suggestions.append({
            "type": "nh3_co2", "icon": "⚗️",
            "position": {"x": round(x, 1), "y": round(W / 4, 1), "z": 0.3},
            "reason": "NH₃ a 30cm del suelo (zona de respiración animal)",
            "cost_eur": 85,
        })
    
    # Cámaras IA: 1 cada 20m, cenital en pasillo
    for i in range(max(2, int(L / 20))):
        x = (i + 0.5) * (L / max(2, int(L / 20)))
        suggestions.append({
            "type": "ai_camera", "icon": "📷",
            "position": {"x": round(x, 1), "y": round(W / 2, 1), "z": round(H - 0.5, 1)},
            "fov_degrees": 120,
            "covers_pens": 4,
            "reason": "Cámara IA cenital — cubre ~4 corrales",
            "capabilities": ["conteo", "caudofagia", "cojeras", "animal_caído", "actividad"],
            "cost_eur": 150,
        })
    
    # Bridges Meshtastic: 1 cada 30m
    for i in range(max(1, int(L / 30))):
        x = (i + 0.5) * (L / max(1, int(L / 30)))
        suggestions.append({
            "type": "meshtastic_bridge", "icon": "📡",
            "position": {"x": round(x, 1), "y": 0.5, "z": round(H - 0.3, 1)},
            "coverage_m": 35,
            "reason": "Gateway LoRa mesh — cobertura indoor 30-50m",
            "cost_eur": 35,
        })
    
    # Caudalímetro agua
    suggestions.append({
        "type": "water_flow", "icon": "💧",
        "position": {"x": 2, "y": round(W / 2, 1), "z": 1.0},
        "reason": "Consumo de agua por nave — indicador precoz de enfermedad",
        "cost_eur": 45,
    })
    
    total_cost = sum(s["cost_eur"] for s in suggestions)
    
    return {
        "suggestions": suggestions,
        "total_devices": len(suggestions),
        "estimated_cost_eur": total_cost,
        "barn_dimensions": barn_dimensions,
        "note": "Posiciones sugeridas automáticamente. Puedes arrastrarlas en el plano.",
    }
```

**Endpoint**: `POST /api/v1/barns/{id}/suggest-devices`

---

## BLOQUE B: IA Vision

### B1. Capacidades que ofrece cada cámara

No necesitamos entrenar modelos ahora. Lo que necesitamos es el **framework** en el frontend y backend que muestre QUÉ detecta cada cámara y genere las alertas.

```python
# backend/services/ai_vision.py

AI_VISION_CAPABILITIES = [
    {
        "id": "pig_counting",
        "name": "Conteo automático",
        "description": "Cuenta cerdos por corral. Detecta discrepancias con el censo.",
        "accuracy": "95%",
        "alert_examples": ["Corral 3: detectados 22 cerdos, censo dice 25 → revisar"],
        "value_proposition": "Ahorra 30 min/día de recuento manual",
    },
    {
        "id": "tail_biting",
        "name": "Detección de caudofagia",
        "description": "Detecta mordedura de colas por postura y movimiento.",
        "accuracy": "87%",
        "alert_examples": ["Corral 7: actividad de mordedura detectada, intervenir"],
        "value_proposition": "Intervención 24-48h antes de lesiones. Evita decomisos en matadero.",
    },
    {
        "id": "lameness",
        "name": "Detección de cojeras",
        "description": "Analiza marcha por pose estimation. Detecta asimetrías.",
        "accuracy": "82%",
        "value_proposition": "Tratamiento precoz. Reduce sacrificios por problemas locomotores.",
    },
    {
        "id": "activity_level",
        "name": "Nivel de actividad grupal",
        "description": "Inactividad prolongada = posible enfermedad. Hiperactividad = estrés o pelea.",
        "accuracy": "90%",
        "value_proposition": "Detección precoz de enfermedad respiratoria, 1-3 días antes de síntomas.",
    },
    {
        "id": "dead_animal",
        "name": "Animal caído o muerto",
        "description": "Detecta animal inmóvil en posición anormal >30 minutos.",
        "accuracy": "93%",
        "value_proposition": "Retirada inmediata. Cumplimiento SANDACH. Registro automático de baja.",
    },
    {
        "id": "feed_hopper_level",
        "name": "Nivel de tolvas de pienso",
        "description": "Estima nivel de pienso por análisis visual, sin sensor físico.",
        "accuracy": "88%",
        "value_proposition": "Complementa lectura de silos. Detecta tolvas vacías o atascadas.",
    },
]
```

### B2. Dashboard de cámaras

```
/barns/{id}/cameras → Vista de todas las cámaras de la nave
Cada cámara muestra:
- Imagen placeholder (o stream si hay URL RTSP)
- Estado: online/offline
- Último evento detectado
- Lista de capacidades IA activas
- Nº de alertas en las últimas 24h
```

---

## BLOQUE C: ERP Completo — Ganadero NO necesita gestoría

### C1. Módulos del ERP

El ERP integrado convierte VacasData en la ÚNICA herramienta que necesita el ganadero:

```
/erp
├── /erp/rrhh          → Gestión de personal
├── /erp/inventory     → Mercaderías (pienso, medicamentos, material)
├── /erp/sales         → Ventas (animales, leche, créditos carbono)
├── /erp/purchases     → Compras (lechones, pienso, suministros)
├── /erp/accounting    → Contabilidad básica (ingresos/gastos por categoría)
├── /erp/taxes         → Formularios fiscales (IVA, IRPF, REA)
└── /erp/reports       → Informes para la gestoría (exportable PDF/Excel)
```

### C2. RRHH

```python
# backend/models/erp.py

class Employee(Base):
    __tablename__ = "employees"
    
    id = Column(UUID, primary_key=True)
    tenant_id = Column(String, index=True)
    name = Column(String)
    dni = Column(String)
    role = Column(String)  # "encargado" | "peón" | "veterinario" | "administrativo"
    contract_type = Column(String)  # "indefinido" | "temporal" | "fijo_discontinuo"
    start_date = Column(Date)
    salary_gross_monthly = Column(Float)
    ss_number = Column(String)  # Seguridad Social
    
    # Formación obligatoria (RD 306/2020: 20h mínimo)
    training_hours = Column(Float, default=0)
    training_records = Column(JSON)  # [{date, topic, hours, provider}]
    training_compliant = Column(Boolean, default=False)  # ≥20h
    
    # Horario
    schedule = Column(JSON)  # Turnos semanales
    
    status = Column(String, default="active")
```

### C3. Inventario / Mercaderías

```python
class InventoryItem(Base):
    __tablename__ = "inventory"
    
    id = Column(UUID, primary_key=True)
    tenant_id = Column(String, index=True)
    name = Column(String)
    category = Column(String)  # "pienso" | "medicamento" | "material" | "repuesto"
    
    # Stock
    current_stock = Column(Float)
    unit = Column(String)  # "kg" | "litros" | "unidades" | "dosis"
    min_stock_alert = Column(Float)  # Alerta de stock bajo
    
    # Para medicamentos
    is_medication = Column(Boolean, default=False)
    requires_prescription = Column(Boolean, default=False)
    withdrawal_days = Column(Integer)  # Periodo de supresión
    lot_number = Column(String)
    expiry_date = Column(Date)
    
    # Coste
    unit_cost_eur = Column(Float)
    supplier = Column(String)
    last_purchase_date = Column(Date)
```

### C4. Ventas y Compras

```python
class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(UUID, primary_key=True)
    tenant_id = Column(String, index=True)
    type = Column(String)  # "sale" | "purchase"
    date = Column(Date)
    
    # Contraparte
    counterpart_name = Column(String)  # Matadero, proveedor, etc.
    counterpart_nif = Column(String)
    
    # Detalle
    concept = Column(String)  # "Venta 200 cerdos cebo", "Compra pienso starter"
    category = Column(String)  # "venta_animales" | "compra_pienso" | "subvención" | ...
    
    # Importes
    base_amount_eur = Column(Float)
    vat_pct = Column(Float)           # 10% (animales vivos) o 21% (general)
    vat_amount_eur = Column(Float)
    total_amount_eur = Column(Float)
    
    # Para ventas de animales
    animal_count = Column(Integer)
    avg_weight_kg = Column(Float)
    price_per_kg = Column(Float)
    batch_id = Column(String)  # Vincular con lote
    
    # Factura
    invoice_number = Column(String)
    invoice_pdf_url = Column(String)
    
    # Pago
    payment_status = Column(String)  # "pendiente" | "cobrado" | "pagado"
    payment_date = Column(Date)
    payment_method = Column(String)  # "transferencia" | "pagaré" | "efectivo"
```

### C5. Fiscalidad — Formularios automáticos

```python
# backend/services/tax_service.py

"""
Generación automática de formularios fiscales para ganaderos.
El Régimen Especial Agrario (REA) tiene particularidades que las gestorías
cobran por conocer. VacasData las automatiza.
"""

def generate_quarterly_vat(tenant_id: str, quarter: int, year: int, db: Session):
    """
    Genera datos para el Modelo 303 (IVA trimestral).
    Particularidades ganaderas:
    - Ventas animales vivos: IVA 10% (tipo reducido)
    - Compras pienso: IVA 10%
    - Compras maquinaria: IVA 21%
    - REA: compensación forfait del 12% en compras a agricultores en REA
    """
    sales = db.query(Transaction).filter(
        Transaction.tenant_id == tenant_id,
        Transaction.type == "sale",
        extract('quarter', Transaction.date) == quarter,
        extract('year', Transaction.date) == year,
    ).all()
    
    purchases = db.query(Transaction).filter(
        Transaction.tenant_id == tenant_id,
        Transaction.type == "purchase",
        extract('quarter', Transaction.date) == quarter,
        extract('year', Transaction.date) == year,
    ).all()
    
    # IVA repercutido (ventas)
    vat_collected_10 = sum(t.vat_amount_eur for t in sales if t.vat_pct == 10)
    vat_collected_21 = sum(t.vat_amount_eur for t in sales if t.vat_pct == 21)
    
    # IVA soportado (compras)
    vat_paid_10 = sum(t.vat_amount_eur for t in purchases if t.vat_pct == 10)
    vat_paid_21 = sum(t.vat_amount_eur for t in purchases if t.vat_pct == 21)
    
    # Compensaciones REA
    rea_compensation = sum(
        t.base_amount_eur * 0.12 
        for t in purchases 
        if t.category == "compra_rea"
    )
    
    total_collected = vat_collected_10 + vat_collected_21
    total_paid = vat_paid_10 + vat_paid_21 + rea_compensation
    result = total_collected - total_paid
    
    return {
        "model": "303",
        "quarter": f"{quarter}T {year}",
        "sales_summary": {
            "base_10pct": sum(t.base_amount_eur for t in sales if t.vat_pct == 10),
            "vat_10pct": vat_collected_10,
            "base_21pct": sum(t.base_amount_eur for t in sales if t.vat_pct == 21),
            "vat_21pct": vat_collected_21,
        },
        "purchases_summary": {
            "base_10pct": sum(t.base_amount_eur for t in purchases if t.vat_pct == 10),
            "vat_10pct": vat_paid_10,
            "base_21pct": sum(t.base_amount_eur for t in purchases if t.vat_pct == 21),
            "vat_21pct": vat_paid_21,
            "rea_compensation": rea_compensation,
        },
        "result": {
            "total_collected": round(total_collected, 2),
            "total_deductible": round(total_paid, 2),
            "to_pay_or_refund": round(result, 2),
            "status": "a_ingresar" if result > 0 else "a_devolver",
        },
        "exportable": True,
        "note": "Datos preparados para el Modelo 303. Exporta en PDF para tu gestoría o presenta directamente.",
    }


def generate_annual_summary(tenant_id: str, year: int, db: Session):
    """
    Resumen anual para IRPF (Modelo 130 trimestral + Modelo 100 anual).
    Incluye: ingresos por categoría, gastos deducibles, amortizaciones,
    subvenciones PAC, y cálculo de base imponible.
    """
    # ... cálculo completo
    pass
```

---

## BLOQUE D: Trazabilidad + SIGE (las páginas que dan 404)

### D1. Página `/traceability`

```
/traceability
├── Libro de registro digital (movimientos de lotes, entradas, salidas)
├── ICA digital — generar y enviar al matadero con 1 click
├── Retorno matadero — pesos canal, clasificación SEUROP, decomisos
├── Historial de movimientos REMO
└── Documentos generados (ICAs enviadas, guías de transporte)
```

Contenido mínimo funcional:

```tsx
// app/traceability/page.tsx
export default function TraceabilityPage() {
  return (
    <div className="max-w-7xl mx-auto p-6">
      <h1 className="text-2xl font-bold mb-2">Trazabilidad</h1>
      <p className="text-gray-500 mb-8">
        Desde la entrada de lechones hasta el retorno de datos del matadero
      </p>

      {/* Tabs */}
      <Tabs items={[
        { id: "movements", label: "📋 Libro de Registro", content: <MovementLog /> },
        { id: "ica", label: "📄 ICA Digital", content: <ICAManager /> },
        { id: "slaughterhouse", label: "🏭 Retorno Matadero", content: <SlaughterhouseData /> },
        { id: "documents", label: "📂 Documentos", content: <DocumentsArchive /> },
      ]} />
    </div>
  );
}
```

### D2. Página `/sige`

El SIGE digital vivo con los 11 planes del RD 306/2020:

```tsx
// app/sige/page.tsx
const SIGE_PLANS = [
  { id: 1, name: "Veterinario de explotación", auto: true, icon: "🩺",
    description: "Datos del veterinario responsable" },
  { id: 2, name: "Plan de LDD", auto: "partial", icon: "🧹",
    description: "Limpieza, desinfección, desinsectación y desratización" },
  { id: 3, name: "Plan de mantenimiento", auto: false, icon: "🔧",
    description: "Mantenimiento de instalaciones y equipos" },
  { id: 4, name: "Plan de formación", auto: true, icon: "🎓",
    description: "20h mínimo por trabajador. Se alimenta del módulo RRHH.",
    source: "erp.employees.training_hours" },
  { id: 5, name: "Cadáveres y SANDACH", auto: "partial", icon: "⚰️",
    description: "Recogida y almacenamiento. Se registra con IA Vision (animal caído)." },
  { id: 6, name: "Gestión de residuos", auto: true, icon: "♻️",
    description: "Conectado con módulo SmartPurín." },
  { id: 7, name: "Gestión ambiental y cambio climático", auto: true, icon: "🌍",
    description: "Auto-generado con datos de sensores + calculadora carbono.",
    source: "sensors + carbon_calculator" },
  { id: 8, name: "Plan de bioseguridad", auto: "partial", icon: "🛡️",
    description: "Protocolo de visitas, vallado, control de acceso." },
  { id: 9, name: "Plan sanitario", auto: true, icon: "💊",
    description: "Cada tratamiento registrado actualiza este plan automáticamente.",
    source: "health.treatments" },
  { id: 10, name: "Uso racional de antibióticos", auto: true, icon: "💉",
    description: "DDDvet calculado automáticamente. Indicadores REDUCE.",
    source: "health.treatments.where(type=antibiotic)" },
  { id: 11, name: "Plan de bienestar animal", auto: true, icon: "🐷",
    description: "Monitorizado en tiempo real con sensores IoT y cámaras IA.",
    source: "sensors.environment + ai_vision" },
];

// Para cada plan mostrar:
// - Estado: ✅ Completo | ⚠️ Requiere revisión | ❌ Pendiente
// - Fuente de datos: "Auto (sensores)" | "Manual" | "Mixto"
// - Última actualización
// - Botón "Ver detalle" → expande con el contenido del plan
// - Botón "Exportar PDF" → genera documento para inspección
```

---

## BLOQUE E: SmartPurín (módulo innovador)

Crear `/purines` con:

1. **Indicador visual de fosa** — tanque con nivel animado y color (verde→amarillo→rojo)
2. **Predicción**: "La fosa se llena en X días" basado en producción diaria
3. **Composición estimada**: N, P, K calculados sin analítica (por tipo de pienso)
4. **Potencial biogás**: kWh/año y €/año que podría generar
5. **Valor como fertilizante**: €/m³ equivalente en abono mineral
6. **Plan de abonado**: qué parcelas, cuánto por hectárea, calendario (zonas vulnerables)
7. **Alertas**: nivel alto, periodo prohibido de aplicación, proximidad a cauces
8. **Reporting ECOGAN**: auto-generado para declaración de MTDs

---

## BLOQUE F: Rediseño UX/UI

### F1. Problemas actuales de diseño

Mirando las capturas, el diseño es funcional pero genérico. Para ser competitivo necesita personalidad.

### F2. Sistema de diseño mejorado

```css
/* Design tokens — adaptativos por especie */

:root {
  /* Cuando es bovino extensivo */
  --color-primary: #1B4332;     /* Forest green */
  --color-secondary: #40C057;   /* Electric green */
  --color-accent: #339AF0;      /* Sky blue */
  --color-surface: #F0FFF4;     /* Green tint */
  
  /* Cuando es porcino intensivo */
  --color-primary: #7C2D12;     /* Terracotta oscuro */
  --color-secondary: #F59E0B;   /* Amber */
  --color-accent: #EC4899;      /* Pink */
  --color-surface: #FFFBEB;     /* Warm cream */
}
```

### F3. Mejoras concretas de UI

```
1. CARDS más grandes y visuales — no solo texto, añadir sparklines y mini-gráficos
2. ICONOS consistentes — usar Lucide React en vez de emojis en producción
3. SIDEBAR colapsable — en vez de solo navbar top, añadir sidebar para la sección activa
4. DARK MODE — esencial para ganaderos que revisan el móvil a las 5am
5. EMPTY STATES con ilustración — cuando no hay datos, no solo texto "no hay datos"
6. LOADING SKELETONS — en vez de "Cargando...", usar skeleton animado
7. TOAST NOTIFICATIONS — confirmaciones de acciones en la esquina
8. BREADCRUMBS — para saber dónde estás: Dashboard > Naves > Nave 1 > Corral 3
9. RESPONSIVE — las naves se ven en tablet en el campo, no solo desktop
10. ACCESIBILIDAD — botones grandes (min 44px), contraste alto para uso con guantes/sol
```

### F4. Dashboard adaptativo por especie

```
BOVINO EXTENSIVO:
┌─────────────────────────────────────────────────────┐
│ [🐄 156 Animales] [📡 6 IoT] [🌿 -12t CO₂] [€2.4k]│
│                                                      │
│ ┌─────────── MAPA GPS ──────────────┐  ┌─ Clima ──┐│
│ │  (Leaflet con posición de vacas)  │  │ 8°C ⛅   ││
│ │  en la sierra en tiempo real      │  │ Viento 15││
│ └───────────────────────────────────┘  └──────────┘│
│                                                      │
│ ┌─ Actividad reciente ─────────────────────────────┐│
│ │ 🔴 COLLAR-001 telemetría · Hace 5 min           ││
│ │ 💉 Vacuna antiparasitaria × 12 · Hace 2h        ││
│ └──────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────┘

PORCINO INTENSIVO:
┌─────────────────────────────────────────────────────┐
│ [🐷 2400 Plazas] [📊 IC 2.38] [📦 4 Lotes] [€18k] │
│                                                      │
│ ┌──── VISTA NAVE ─────────────────┐  ┌─ Ambiente ─┐│
│ │  (SVG plano con corrales)       │  │ 🌡️ 22.3°C ││
│ │  coloreados por estado          │  │ NH₃ 12ppm ││
│ │  + sensores + cámaras           │  │ 💧 65%    ││
│ └─────────────────────────────────┘  └────────────┘│
│                                                      │
│ ┌─ Alertas ──────────┐  ┌─ Silos ────────────────┐│
│ │ 🔴 Corral 7: act.  │  │ Starter: 28% ██░░░░░ ││
│ │    baja 6h          │  │ Crecim.: 62% █████░░░ ││
│ │ 🟡 Silo 1: <30%    │  │ Acabado: 89% ████████░││
│ └────────────────────┘  └────────────────────────┘│
└─────────────────────────────────────────────────────┘
```

---

## ⚠️ REGLAS

1. **Arreglar TODOS los 404 antes de crear funcionalidad nueva**
2. **Un solo producto**: VacasData Hub. Los colores/navbar/terminología se adaptan, el código no se duplica
3. **`NEXT_PUBLIC_API_URL`** en todos los fetch, nunca rutas relativas
4. **No usar `docker exec`** para editar archivos — editar en el host directamente
5. **Rebuild después de cada tanda de cambios**: `docker compose build web --no-cache && docker compose up -d web`
6. **Registrar routers nuevos** en main.py: erp, tax, purines, traceability, sige
7. **Migraciones Alembic** para tablas nuevas: employees, inventory, transactions
8. **SVG para la vista de nave** (pragmático) en vez de Three.js (complejo)
9. **Datos demo** para cada módulo nuevo — no dejar páginas vacías
10. **Responsive** — mínimo 44px en botones, funcional en tablet

---

## ✅ CHECKLIST COMPLETO

### Infraestructura
```
[ ] Todas las rutas de la navbar devuelven 200 (cero 404s)
[ ] F12 Console: 0 errores de fetch
[ ] api-v2.vacasdata.com/docs muestra todos los endpoints nuevos
```

### Nave inteligente
```
[ ] /barns/{id}: Vista SVG a escala con corrales coloreados por estado
[ ] Formulario de dimensiones (largo, ancho, altura, layout)
[ ] Sensores y cámaras visibles en el plano
[ ] POST /api/v1/barns/{id}/suggest-devices: sugiere colocación automática
[ ] Click en corral → panel lateral con datos del lote
```

### IA Vision
```
[ ] /barns/{id}: Cámaras con campo de visión dibujado en SVG
[ ] Lista de capacidades IA por cámara (conteo, caudofagia, cojeras, etc.)
[ ] Dashboard de alertas IA (aunque sean simuladas para la demo)
```

### ERP
```
[ ] /erp/rrhh: Lista empleados, formación obligatoria (20h), contratos
[ ] /erp/inventory: Stock de pienso, medicamentos, materiales con alertas
[ ] /erp/sales: Ventas de animales vinculadas a lotes
[ ] /erp/purchases: Compras con categorías y IVA
[ ] /erp/taxes: Modelo 303 trimestral auto-calculado
[ ] /erp/reports: Export PDF/Excel para gestoría
```

### Trazabilidad
```
[ ] /traceability: Libro de registro, ICA digital, retorno matadero
[ ] Generar ICA con 1 click → PDF con datos automáticos del lote
```

### SIGE
```
[ ] /sige: 11 planes del RD 306/2020 con estado y fuente de datos
[ ] Planes auto-actualizados marcados como "Auto (sensores)"
[ ] Exportar SIGE completo como PDF para inspección
```

### SmartPurín
```
[ ] /purines: Indicador de nivel, predicción, composición, biogás
[ ] Plan de abonado con calendario de zonas vulnerables
```

### UX/UI
```
[ ] Colores adaptativos por especie (verde=bovino, terracota=porcino)
[ ] Loading skeletons en todas las páginas
[ ] Breadcrumbs en páginas de detalle
[ ] Empty states con mensaje útil (no solo "no hay datos")
[ ] Responsive funcional en tablet
```

---

*Prompt VacasData Hub — Plataforma Inteligente Unificada*
*15 Febrero 2026*
