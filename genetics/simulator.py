"""
Seedy Genetics — Simulador de Cruces F1→F5

Predice rasgos de descendencia multi-generacional usando:
  - Modelo aditivo medio-parental
  - Heterosis (vigor híbrido)
  - Control de consanguinidad (Wright F)
  - Genética mendeliana de color (avicultura)
  - Depresión endogámica

Soporta 3 especies: chicken, pig, cattle.
"""

import random
import math
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from genetics.breeds import (
    Breed, Trait, get_breed, ALL_BREEDS,
    HERITABILITIES, HETEROSIS_FACTORS, INBREEDING_THRESHOLDS,
)


# ─────────────────────────────────────────────────────
# Resultado de simulación
# ─────────────────────────────────────────────────────

@dataclass
class CrossResult:
    """Resultado de un cruce predicho."""
    generation: str                   # "F1", "F2", etc.
    sire_breed: str
    dam_breed: str
    species: str
    predicted_traits: dict[str, dict] = field(default_factory=dict)
    # {trait: {"value": float, "unit": str, "heterosis_pct": float, "h2": float}}
    inbreeding_f: float = 0.0
    inbreeding_status: str = "green"  # green, yellow, red
    heterosis_level: str = "high"     # high, medium, low, none
    color_prediction: dict | None = None  # Solo avicultura
    capon_score: float | None = None  # Solo avicultura
    notes: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────
# Simulador multi-generación
# ─────────────────────────────────────────────────────

class GeneticSimulator:
    """
    Simulador de cruces genéticos multi-generación.
    """
    
    def __init__(self, seed: int | None = None):
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
    
    def predict_f1(self, sire_breed_id: str, dam_breed_id: str,
                   species: str) -> CrossResult:
        """
        Predice rasgos F1 del cruce entre dos razas.
        
        Modelo: F1_trait = media_parental + heterosis_boost
        Heterosis: |EBV_a - EBV_b| × factor_heterosis
        """
        sire = get_breed(species, sire_breed_id)
        dam = get_breed(species, dam_breed_id)
        
        if not sire or not dam:
            raise ValueError(
                f"Raza no encontrada: sire={sire_breed_id}, dam={dam_breed_id} "
                f"en especie={species}"
            )
        
        result = CrossResult(
            generation="F1",
            sire_breed=sire.name,
            dam_breed=dam.name,
            species=species,
        )
        
        het_factors = HETEROSIS_FACTORS.get(species, {})
        is_same_breed = (sire_breed_id == dam_breed_id)
        
        # Calcular distancia genética (heurística basada en divergencia de rasgos)
        genetic_distance = self._estimate_genetic_distance(sire, dam)
        
        # Traits compartidos
        common_traits = set(sire.traits.keys()) & set(dam.traits.keys())
        
        for trait_name in common_traits:
            sire_trait = sire.traits[trait_name]
            dam_trait = dam.traits[trait_name]
            
            # Media parental
            midparent = (sire_trait.value + dam_trait.value) / 2.0
            
            # Heterosis
            het_factor = het_factors.get(trait_name, 0.0)
            if is_same_breed:
                het_boost_pct = 0.0
            else:
                # La heterosis escala con distancia genética
                divergence = abs(sire_trait.value - dam_trait.value)
                het_boost_pct = het_factor * genetic_distance * 100
            
            het_boost_abs = midparent * (het_boost_pct / 100.0)
            predicted_value = midparent + het_boost_abs
            
            # Varianza del F1 (reducida respecto a padres por uniformidad híbrida)
            f1_variance = (sire_trait.variance + dam_trait.variance) / 4.0
            
            # Para FCR, menor es mejor → heterosis negativa es positiva
            if trait_name in ("feed_conversion",):
                predicted_value = midparent - abs(het_boost_abs)
            
            result.predicted_traits[trait_name] = {
                "value": round(predicted_value, 2),
                "unit": sire_trait.unit,
                "sire_value": sire_trait.value,
                "dam_value": dam_trait.value,
                "midparent": round(midparent, 2),
                "heterosis_pct": round(het_boost_pct, 1),
                "h2": sire_trait.heritability,
                "variance": round(f1_variance, 3),
            }
        
        # Heterosis level
        if is_same_breed:
            result.heterosis_level = "none"
        elif genetic_distance > 0.7:
            result.heterosis_level = "high"
        elif genetic_distance > 0.4:
            result.heterosis_level = "medium"
        else:
            result.heterosis_level = "low"
        
        # Inbreeding F = 0 para cruce entre razas puras distintas
        if is_same_breed:
            result.inbreeding_f = 0.0625  # Simular algo de F en puros
            result.notes.append(
                "⚠️ Cruce intra-raza: sin heterosis. Controlar consanguinidad."
            )
        else:
            result.inbreeding_f = 0.0
        
        result.inbreeding_status = self._inbreeding_status(
            result.inbreeding_f, species
        )
        
        # Color prediction (solo avicultura)
        if species == "chicken" and sire.color_genotype and dam.color_genotype:
            result.color_prediction = self._predict_color_f1(
                sire.color_genotype, dam.color_genotype
            )
        
        # Capon Score (solo avicultura)
        if species == "chicken":
            result.capon_score = self._calculate_capon_score(
                result.predicted_traits
            )
        
        # Origin distance note
        if sire.origin and dam.origin and not is_same_breed:
            result.notes.append(
                f"Cruce {sire.origin} × {dam.origin} "
                f"(distancia genética estimada: {genetic_distance:.2f})"
            )
        
        return result
    
    def predict_generations(self, sire_breed_id: str, dam_breed_id: str,
                            species: str,
                            n_generations: int = 5,
                            strategy: str = "f1_inter_se"
                            ) -> list[CrossResult]:
        """
        Simula N generaciones de un programa de cruce.
        
        Strategies:
          - "f1_inter_se": F1×F1 para crear F2, F2×F2→F3, etc.
          - "backcross_sire": F1 × Sire breed → BC1, BC1 × Sire → BC2...
          - "backcross_dam": F1 × Dam breed
          - "rotational": Alternar razas cada generación
        """
        results = []
        
        # F1
        f1 = self.predict_f1(sire_breed_id, dam_breed_id, species)
        results.append(f1)
        
        if n_generations <= 1:
            return results
        
        sire = get_breed(species, sire_breed_id)
        dam = get_breed(species, dam_breed_id)
        if not sire or not dam:
            return results
        
        prev_result = f1
        
        for gen in range(2, n_generations + 1):
            gen_label = f"F{gen}"
            gen_result = CrossResult(
                generation=gen_label,
                species=species,
                sire_breed=prev_result.sire_breed,
                dam_breed=prev_result.dam_breed,
            )
            
            # Heterosis decay: en F2+ se pierde 50% por generación
            # F2 retiene 50%, F3 retiene 25%, etc.
            heterosis_retention = 0.5 ** (gen - 1)
            
            # Inbreeding increases
            if strategy == "f1_inter_se":
                # F intra-generación: F2 = 0.25, F3 = 0.375...
                f_coef = 1.0 - (0.5 ** (gen - 1))
                f_coef *= 0.25  # Scaled for practical populations
                gen_result.inbreeding_f = round(f_coef, 4)
                gen_result.notes.append(
                    f"Inter se: retiene {heterosis_retention*100:.0f}% de heterosis F1"
                )
            
            elif strategy == "backcross_sire":
                # Backcross: proporción de raza paterna aumenta
                sire_proportion = 1.0 - 0.5 ** gen
                gen_result.notes.append(
                    f"Backcross: {sire_proportion*100:.0f}% genoma {sire.name}"
                )
                gen_result.inbreeding_f = 0.5 ** gen * 0.0625
            
            elif strategy == "backcross_dam":
                dam_proportion = 1.0 - 0.5 ** gen
                gen_result.notes.append(
                    f"Backcross: {dam_proportion*100:.0f}% genoma {dam.name}"
                )
                gen_result.inbreeding_f = 0.5 ** gen * 0.0625
            
            elif strategy == "rotational":
                # Heterosis mantenida al ~67%
                heterosis_retention = 2.0 / 3.0
                gen_result.inbreeding_f = 0.03
                gen_result.notes.append(
                    "Rotacional: mantiene ~67% de heterosis"
                )
            
            gen_result.inbreeding_status = self._inbreeding_status(
                gen_result.inbreeding_f, species
            )
            
            # Predecir rasgos
            for trait_name, f1_data in f1.predicted_traits.items():
                midparent = f1_data["midparent"]
                het_pct_f1 = f1_data["heterosis_pct"]
                
                # Heterosis reducida
                het_pct_gen = het_pct_f1 * heterosis_retention
                het_boost = midparent * (het_pct_gen / 100.0)
                
                # Depresión endogámica
                inbreeding_penalty = gen_result.inbreeding_f * 0.1 * midparent
                
                if trait_name in ("feed_conversion",):
                    predicted = midparent - abs(het_boost) + inbreeding_penalty
                else:
                    predicted = midparent + het_boost - inbreeding_penalty
                
                # Varianza aumenta en generaciones avanzadas (segregación)
                variance = f1_data["variance"] * (1.0 + 0.5 * (gen - 1))
                
                gen_result.predicted_traits[trait_name] = {
                    "value": round(predicted, 2),
                    "unit": f1_data["unit"],
                    "midparent": midparent,
                    "heterosis_pct": round(het_pct_gen, 1),
                    "h2": f1_data["h2"],
                    "variance": round(variance, 3),
                    "inbreeding_penalty_pct": round(
                        gen_result.inbreeding_f * 10, 1
                    ),
                }
            
            # Capon score
            if species == "chicken":
                gen_result.capon_score = self._calculate_capon_score(
                    gen_result.predicted_traits
                )
            
            results.append(gen_result)
            prev_result = gen_result
        
        return results
    
    # ── Índice de selección ──
    
    def selection_index(self, traits: dict[str, dict],
                        species: str,
                        weights: dict[str, float] | None = None
                        ) -> dict:
        """
        Calcula índice de selección multi-rasgo.
        
        Para avicultura (capones):
          Sabor proxy (canal): 40%, Rendimiento canal: 35%, Rusticidad: 25%
        
        Para porcino:
          GMD: 25%, FCR: 25%, % magro: 20%, Litter size: 15%, Robustez: 15%
        
        Para vacuno:
          Peso destete: 25%, Facilidad parto: 20%, Fertilidad: 20%,
          Rusticidad: 15%, GMD: 20%
        """
        if weights is None:
            weights = self._default_selection_weights(species)
        
        score = 0.0
        max_score = 0.0
        details = {}
        
        for trait_name, w in weights.items():
            if trait_name in traits:
                t = traits[trait_name]
                value = t["value"] if isinstance(t, dict) else t
                
                # Normalizar a 0-100
                normalized = self._normalize_trait(
                    trait_name, value, species
                )
                
                contribution = normalized * w
                score += contribution
                max_score += 100 * w
                
                details[trait_name] = {
                    "raw_value": value,
                    "normalized": round(normalized, 1),
                    "weight": w,
                    "contribution": round(contribution, 2),
                }
        
        # Penalización por consanguinidad
        # (no aplicable directamente aquí, se añade en predict_f1)
        
        final_score = (score / max_score * 100) if max_score > 0 else 0
        
        # Categoría
        if final_score >= 85:
            category = "ÉLITE"
            recommendation = "Candidato reproductor prioritario"
        elif final_score >= 70:
            category = "BUENO"
            recommendation = "Candidato reproductor secundario"
        elif final_score >= 50:
            category = "ACEPTABLE"
            recommendation = "Producción comercial"
        elif final_score >= 30:
            category = "MEDIO"
            recommendation = "Producción comercial (considerar otros cruces)"
        else:
            category = "DESCARTE"
            recommendation = "Bajo índice de selección"
        
        return {
            "score": round(final_score, 1),
            "category": category,
            "recommendation": recommendation,
            "details": details,
        }
    
    # ── Optimización de apareamiento ──
    
    def optimal_matings(self, species: str,
                        target_traits: list[str] | None = None,
                        top_n: int = 5) -> list[dict]:
        """
        Evalúa todos los cruces posibles entre razas y devuelve
        los top_n mejores por índice de selección.
        """
        breeds = ALL_BREEDS.get(species, {})
        breed_ids = list(breeds.keys())
        
        if not target_traits:
            target_traits = list(
                self._default_selection_weights(species).keys()
            )
        
        results = []
        
        for i, sire_id in enumerate(breed_ids):
            for dam_id in breed_ids[i:]:  # Incluir mismo × mismo
                try:
                    f1 = self.predict_f1(sire_id, dam_id, species)
                    idx = self.selection_index(
                        f1.predicted_traits, species
                    )
                    
                    results.append({
                        "sire": breeds[sire_id].name,
                        "dam": breeds[dam_id].name,
                        "sire_id": sire_id,
                        "dam_id": dam_id,
                        "score": idx["score"],
                        "category": idx["category"],
                        "heterosis": f1.heterosis_level,
                        "inbreeding_f": f1.inbreeding_f,
                        "capon_score": f1.capon_score,
                        "key_traits": {
                            k: v["value"]
                            for k, v in f1.predicted_traits.items()
                            if k in target_traits
                        },
                    })
                except Exception:
                    continue
        
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:top_n]
    
    # ── Helpers privados ──
    
    def _estimate_genetic_distance(self, breed_a: Breed,
                                    breed_b: Breed) -> float:
        """
        Estima distancia genética entre dos razas basándose en
        la divergencia fenotípica normalizada (proxy de Fst).
        Rango: 0 (idénticas) a 1 (máxima distancia).
        """
        if breed_a.name == breed_b.name:
            return 0.0
        
        common = set(breed_a.traits.keys()) & set(breed_b.traits.keys())
        if not common:
            return 0.5
        
        divergences = []
        for trait_name in common:
            a_val = breed_a.traits[trait_name].value
            b_val = breed_b.traits[trait_name].value
            mean_val = (abs(a_val) + abs(b_val)) / 2.0
            if mean_val > 0:
                divergences.append(abs(a_val - b_val) / mean_val)
        
        if not divergences:
            return 0.5
        
        # Normalizar a [0, 1]
        raw = np.mean(divergences)
        return min(1.0, raw * 2.0)
    
    def _inbreeding_status(self, f: float, species: str) -> str:
        """Clasifica F de Wright en green/yellow/red."""
        key = species
        if species == "pig":
            key = "pig_white"  # Default
        
        thresholds = INBREEDING_THRESHOLDS.get(key, {"green": 0.0625, "yellow": 0.125, "red": 0.25})
        
        if f < thresholds["green"]:
            return "green"
        elif f < thresholds["yellow"]:
            return "yellow"
        else:
            return "red"
    
    def _predict_color_f1(self, sire_geno: dict[str, str],
                           dam_geno: dict[str, str]) -> dict:
        """
        Predicción de color F1 basada en genética mendeliana.
        Simplificada a los 5 loci principales.
        """
        predictions = {}
        
        for locus in ["E", "Co", "S", "Ml", "Bl"]:
            s_alleles = sire_geno.get(locus, "")
            d_alleles = dam_geno.get(locus, "")
            
            if s_alleles and d_alleles:
                predictions[locus] = {
                    "sire": s_alleles,
                    "dam": d_alleles,
                    "f1_possible": self._cross_alleles(
                        locus, s_alleles, d_alleles
                    ),
                }
        
        return predictions
    
    def _cross_alleles(self, locus: str, sire: str, dam: str) -> list[str]:
        """Simplificación de cruces mendelianos para loci avícolas."""
        # Para el locus Blue (dominancia incompleta)
        if locus == "Bl":
            if "Bl" in sire and "Bl" in dam:
                if "bl+" in sire and "bl+" in dam:
                    return ["25% Bl/Bl (splash)", "50% Bl/bl+ (azul)", "25% bl+/bl+ (negro)"]
                elif "bl+" not in sire and "bl+" not in dam:
                    return ["100% Bl/Bl (splash)"]
                else:
                    return ["50% Bl/Bl (splash)", "50% Bl/bl+ (azul)"]
            elif "Bl" in sire or "Bl" in dam:
                return ["50% Bl/bl+ (azul)", "50% bl+/bl+ (negro)"]
            else:
                return ["100% bl+/bl+ (negro o color base)"]
        
        # Simplificación general
        if sire == dam:
            return [f"100% {sire}"]
        else:
            return [f"Variable: {sire} × {dam}"]
    
    def _calculate_capon_score(self, traits: dict[str, dict]) -> float | None:
        """
        Capon Score NeoFarm: ponderación para aptitud capón.
          - Rendimiento canal: 35%
          - Peso corporal: 25%
          - Docilidad: 15%
          - Velocidad crecimiento: 15%
          - Rusticidad: 10%
        """
        weights = {
            "carcass_yield_pct": 0.35,
            "body_weight_kg": 0.25,
            "docility": 0.15,
            "growth_rate": 0.15,
            "rusticity": 0.10,
        }
        
        score = 0.0
        total_weight = 0.0
        
        for trait_name, w in weights.items():
            if trait_name in traits:
                t = traits[trait_name]
                value = t["value"] if isinstance(t, dict) else t
                normalized = self._normalize_trait(
                    trait_name, value, "chicken"
                )
                score += normalized * w
                total_weight += w
        
        if total_weight < 0.5:  # Faltan demasiados rasgos
            return None
        
        return round(score / total_weight, 1)
    
    def _normalize_trait(self, trait_name: str, value: float,
                          species: str) -> float:
        """Normaliza un rasgo a escala 0-100."""
        # Rangos de normalización por rasgo y especie
        ranges = {
            "chicken": {
                "body_weight_kg": (2.0, 6.0),
                "carcass_yield_pct": (55, 80),
                "growth_rate": (40, 100),
                "docility": (40, 100),
                "rusticity": (40, 100),
                "eggs_per_year": (100, 300),
                "feed_conversion": (4.5, 2.5),  # Invertido: menor = mejor
                "breast_width_cm": (7, 12),
            },
            "pig": {
                "daily_gain_g": (500, 1000),
                "feed_conversion": (4.0, 2.0),  # Invertido
                "backfat_mm": (35, 5),           # Invertido
                "lean_pct": (35, 70),
                "litter_size": (7, 16),
                "born_alive": (6, 15),
                "weaned_per_litter": (5, 13),
                "carcass_index": (60, 95),
                "respiratory_resistance": (40, 100),
            },
            "cattle": {
                "weaning_weight_kg": (150, 300),
                "yearling_weight_kg": (280, 550),
                "daily_gain_g": (600, 1400),
                "calving_ease": (50, 95),
                "fertility_pct": (70, 95),
                "calving_interval_days": (450, 360),  # Invertido: menor = mejor
                "docility": (50, 95),
                "heat_tolerance": (40, 100),
                "parasite_resistance": (40, 100),
            },
        }
        
        sp_ranges = ranges.get(species, {})
        if trait_name not in sp_ranges:
            return min(100, max(0, value))
        
        lo, hi = sp_ranges[trait_name]
        if lo == hi:
            return 50.0
        
        normalized = (value - lo) / (hi - lo) * 100.0
        return max(0.0, min(100.0, normalized))
    
    def _default_selection_weights(self, species: str) -> dict[str, float]:
        """Pesos por defecto del índice de selección por especie."""
        if species == "chicken":
            return {
                "carcass_yield_pct": 0.35,
                "body_weight_kg": 0.25,
                "docility": 0.15,
                "growth_rate": 0.15,
                "rusticity": 0.10,
            }
        elif species == "pig":
            return {
                "daily_gain_g": 0.25,
                "feed_conversion": 0.25,
                "lean_pct": 0.20,
                "litter_size": 0.15,
                "respiratory_resistance": 0.15,
            }
        elif species == "cattle":
            return {
                "weaning_weight_kg": 0.25,
                "calving_ease": 0.20,
                "fertility_pct": 0.20,
                "daily_gain_g": 0.20,
                "heat_tolerance": 0.15,
            }
        return {}
