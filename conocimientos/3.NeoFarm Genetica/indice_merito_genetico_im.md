# Índice de Mérito Genético (IM) — NeoFarm / Seedy

## ¿Qué es el Índice de Mérito?

El **Índice de Mérito Genético (IM)** es un sistema de puntuación compuesta que evalúa cada ave del programa de selección con un score de **0.00 a 1.00**, combinando múltiples caracteres ponderados. Fue diseñado por Seedy basándose en principios de genética cuantitativa y BLUP, adaptado a avicultura heritage (capones, pulardas, razas autóctonas).

## Fórmula

```
IM = w₁ × P_norm + w₂ × M_norm + w₃ × C_norm + w₄ × V_norm + w₅ × D_norm
```

### Componentes

| Componente | Peso por defecto | Descripción | Normalización |
|-----------|-----------------|-------------|---------------|
| **Peso relativo (P)** | 35% | Peso actual vs peso objetivo Gompertz del cruce a esa edad | min(peso/objetivo, 1.0) |
| **Conformación (M)** | 25% | Evaluación visual + IA Vision de marmoleo/estructura, escala 1-5 | score / 5.0 |
| **Conversión alimentaria (C)** | 15% | kg pienso / kg peso ganado (invertido: menor = mejor) | 1.0 - min(ratio/max, 1.0) |
| **Viabilidad (V)** | 15% | Score de salud: antibióticos, cojeras, deformidades | Regla escalonada (ver abajo) |
| **Docilidad (D)** | 10% | Temperamento evaluado por IA Vision, escala 1-5 | score / 5.0 |

### Pesos por defecto (configurables por el usuario)

```python
peso=0.35, conformación=0.25, conversión=0.15, viabilidad=0.15, docilidad=0.10
```

Los pesos deben sumar 1.0 y son editables según la prioridad del programa de selección.

## Umbrales de selección

| IM | Categoría | Destino |
|----|-----------|---------|
| **≥ 0.85** | REPRODUCTOR | Candidato a padre/madre de siguiente generación. Reservar para clanes de cría. |
| **0.60 – 0.84** | PRODUCCIÓN | Capón (macho) o pularda/ponedora (hembra). Buen individuo pero no top genético. |
| **< 0.60** | DESCARTE | Vender como pollo campero o engorde. No aporta al programa genético. |

## Regla de viabilidad / locomoción (refinada)

La regla de cojeras fue consensuada con el criador para distinguir entre problemas graves y comunes:

- **Antibióticos alguna vez** → Viabilidad = 0.0 (descarte automático del programa reproductor)
- **Deformidad estructural** (tarsos, dedos, quilla) → Viabilidad = 0.0
- **Cojera crónica** (>72h + asimétrica o progresiva) → Viabilidad = 0.2
- **Cojera transitoria** (resuelta en <48h, simétrica) → Viabilidad = 0.7 (pollitos "torpones" de líneas pesadas como Orpington, Sussex, Malines o Barbezieux son normales)
- **Sin problemas** → Viabilidad = 1.0

## Peso objetivo dinámico (Gompertz)

El peso objetivo se calcula con el modelo de crecimiento de Gompertz específico para cada gallinero de selección:

```
W(t) = W_inf × exp(-exp(-k × (t - t_inflection)))
```

| Gallinero | Cruce | W_inf (g) | k | t_inflección (días) |
|-----------|-------|-----------|---|---------------------|
| G1 | Bresse × Sulmtaler | 3,500 | 0.028 | 70 |
| G2 | Sussex × Sussex | 4,200 | 0.025 | 75 |
| G3 | Orpington × mixed | 4,500 | 0.024 | 80 |
| G4 | Sussex × españolas | 3,800 | 0.026 | 73 |
| G5 | Vorwerk × Araucana | 2,800 | 0.032 | 60 |

Si no se indica gallinero, se usa la curva Gompertz de la raza del ave.

## Bonus por cata de hermano capón (Paladar como input)

Cuando se sacrifica y cata un capón de prueba, el resultado de la cata (score 1-5) se vincula a sus hermanos vivos. Los hermanos de los mejores capones reciben un bonus en conformación de hasta +0.5 puntos (máximo score 5.0 tras bonus).

## Relación con otros módulos genéticos

- El IM **NO sustituye** al COI de Wright. Ambos coexisten. Un ave con IM alto pero COI >0.25 con su pareja propuesta NO se aparea.
- El IM se calcula en momentos clave: semanas 4, 8, 12, 16, 20 (se guarda historial temporal).
- El IM alimenta al "Generational River" del frontend genético.
- Los modelos BLUP/GBLUP existentes calculan EBV (valores de cría estimados) que son complementarios al IM.

## API endpoints

| Endpoint | Método | Función |
|----------|--------|---------|
| `/genetics/merit/calculate` | POST | Calcular IM de un ave individual |
| `/genetics/merit/batch` | POST | Calcular IM de un lote (ordenado por score) |
| `/genetics/merit/ranking` | POST | Ranking completo con estadísticas |
| `/genetics/merit/history/{bird_id}` | GET | Historial temporal del IM de un ave |
| `/genetics/merit/gompertz-target` | GET | Peso objetivo Gompertz para edad/gallinero/raza |

## Ejemplo de uso

Para evaluar un Sussex macho de 20 semanas en G2, pesando 3800g, conformación 4, docilidad 4, sin problemas de salud, conversión 3.5:

```json
{
  "bird_id": "PAL-2626-0012",
  "gallinero": "G2",
  "age_weeks": 20,
  "weight_grams": 3800,
  "conformacion_score": 4.0,
  "conversion_ratio": 3.5,
  "docilidad_score": 4.0
}
```

Resultado: IM ≈ 0.79 → PRODUCCIÓN (buen capón, no top para reproducción).

---

*NeoFarm · Módulo implementado en seedy-backend · abril 2026*
