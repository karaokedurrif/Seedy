"""
Seedy Backend — Router /genetics

Motor de simulación genética multi-especie:
  - Predicción F1 (modelo aditivo + heterosis)
  - Simulación multi-generación F1→F5
  - Cruces óptimos (ranking por índice de selección)
  - BLUP / GBLUP para valores de cría
  - Índice de selección multi-rasgo
  - Base de datos de razas (avicultura, porcino, vacuno)

Conecta con capones.ovosfera.com, hub.porcidata.com, hub.vacasdata.com
"""

import sys
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query

# Añadir raíz del proyecto al path para importar genetics/
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from genetics.simulator import GeneticSimulator, CrossResult
from genetics.breeds import list_breeds, get_breed, ALL_BREEDS
from genetics.blup import BLUPEngine

from models.schemas import (
    PredictF1Request,
    PredictGenerationsRequest,
    OptimalMatingRequest,
    BLUPRequest,
    SelectionIndexRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/genetics", tags=["genetics"])

# Instancia compartida
_simulator = GeneticSimulator(seed=42)


# ─── Endpoints ────────────────────────────────────────


@router.get("/breeds")
async def get_breeds(species: str | None = Query(None, description="chicken, pig, cattle")):
    """
    Lista todas las razas disponibles, opcionalmente filtradas por especie.
    """
    breeds = list_breeds(species)
    if not breeds:
        raise HTTPException(404, f"No hay razas para especie '{species}'")
    return {"breeds": breeds, "total": len(breeds)}


@router.get("/breeds/{species}/{breed_id}")
async def get_breed_detail(species: str, breed_id: str):
    """
    Detalle completo de una raza: rasgos, heredabilidades, genotipo de color.
    """
    breed = get_breed(species, breed_id)
    if not breed:
        available = list(ALL_BREEDS.get(species, {}).keys())
        raise HTTPException(
            404,
            f"Raza '{breed_id}' no encontrada en {species}. "
            f"Disponibles: {available}",
        )
    
    return {
        "name": breed.name,
        "species": breed.species,
        "category": breed.category,
        "origin": breed.origin,
        "notes": breed.notes,
        "traits": {
            name: {
                "name": t.name,
                "value": t.value,
                "unit": t.unit,
                "heritability": t.heritability,
                "variance": t.variance,
            }
            for name, t in breed.traits.items()
        },
        "color_genotype": breed.color_genotype or None,
    }


@router.post("/predict-f1")
async def predict_f1(req: PredictF1Request):
    """
    Predice los rasgos de la descendencia F1 entre dos razas.
    
    Modelo: F1 = media parental + heterosis
    Incluye Capon Score (avicultura), consanguinidad, predicción de color.
    """
    try:
        result = _simulator.predict_f1(req.sire_breed, req.dam_breed, req.species)
    except ValueError as e:
        raise HTTPException(400, str(e))
    
    return _format_cross_result(result)


@router.post("/predict-generations")
async def predict_generations(req: PredictGenerationsRequest):
    """
    Simula N generaciones (F1→F5+) de un programa de cruce.
    
    Estrategias:
      - f1_inter_se: F1×F1, F2×F2...
      - backcross_sire: retrocruce hacia padre
      - backcross_dam: retrocruce hacia madre
      - rotational: alternancia de razas
    """
    try:
        results = _simulator.predict_generations(
            req.sire_breed, req.dam_breed, req.species,
            n_generations=req.n_generations,
            strategy=req.strategy,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    
    return {
        "cross": f"{req.sire_breed} × {req.dam_breed}",
        "species": req.species,
        "strategy": req.strategy,
        "generations": [_format_cross_result(r) for r in results],
    }


@router.post("/optimal-matings")
async def optimal_matings(req: OptimalMatingRequest):
    """
    Evalúa todos los cruces posibles entre razas de una especie
    y devuelve los mejores por índice de selección.
    """
    results = _simulator.optimal_matings(
        req.species,
        target_traits=req.target_traits or None,
        top_n=req.top_n,
    )
    
    if not results:
        raise HTTPException(404, f"No hay razas disponibles para especie '{req.species}'")
    
    return {
        "species": req.species,
        "matings": results,
        "total_evaluated": len(list(ALL_BREEDS.get(req.species, {}).keys())),
    }


@router.post("/breeding-values")
async def compute_breeding_values(req: BLUPRequest):
    """
    Calcula EBV (Estimated Breeding Values) mediante BLUP de Henderson.
    
    Requiere pedigrí + fenotipos observados.
    Devuelve ranking de animales por EBV.
    """
    engine = BLUPEngine()
    
    # Cargar pedigrí
    engine.add_pedigree(req.pedigree)
    
    # Cargar fenotipos
    for animal_id, value in req.phenotypes.items():
        engine.set_phenotype(animal_id, req.trait, value)
    
    # Resolver BLUP
    ebvs = engine.solve_blup(req.trait, req.heritability)
    
    if not ebvs:
        raise HTTPException(
            400,
            "No se pudo calcular EBV. Verificar que hay animales con fenotipo.",
        )
    
    # Ranking
    ranking = engine.rank_animals(req.trait, top_n=req.top_n)
    
    # Precisión
    n_phenotyped = len(req.phenotypes)
    accuracy = engine.breeding_accuracy(n_phenotyped, req.heritability)
    
    return {
        "trait": req.trait,
        "heritability": req.heritability,
        "n_animals": len(engine.animals),
        "n_phenotyped": n_phenotyped,
        "accuracy": round(accuracy, 3),
        "ranking": ranking,
        "all_ebvs": {k: round(v, 4) for k, v in ebvs.items()},
    }


@router.post("/selection-index")
async def compute_selection_index(req: SelectionIndexRequest):
    """
    Calcula el índice de selección multi-rasgo.
    
    Categorías: ÉLITE (≥85), BUENO (≥70), ACEPTABLE (≥50),
    MEDIO (≥30), DESCARTE (<30).
    """
    traits_dict = {k: {"value": v} for k, v in req.traits.items()}
    
    result = _simulator.selection_index(
        traits_dict, req.species, req.weights
    )
    
    return result


@router.get("/inbreeding-thresholds/{species}")
async def get_inbreeding_thresholds(species: str):
    """Devuelve los umbrales de consanguinidad para una especie."""
    from genetics.breeds import INBREEDING_THRESHOLDS
    
    key = species
    if species == "pig":
        key = "pig_white"
    
    thresholds = INBREEDING_THRESHOLDS.get(key)
    if not thresholds:
        raise HTTPException(404, f"Umbrales no definidos para '{species}'")
    
    return {
        "species": species,
        "thresholds": thresholds,
        "description": {
            "green": f"F < {thresholds['green']} — Seguro",
            "yellow": f"F < {thresholds['yellow']} — Vigilar",
            "red": f"F ≥ {thresholds['yellow']} — Riesgo alto",
        },
    }


@router.get("/heritabilities/{species}")
async def get_heritabilities(species: str):
    """Devuelve las heredabilidades de referencia para una especie."""
    from genetics.breeds import HERITABILITIES
    
    h2 = HERITABILITIES.get(species)
    if not h2:
        raise HTTPException(404, f"Heredabilidades no definidas para '{species}'")
    
    return {"species": species, "heritabilities": h2}


# ─── Helpers ──────────────────────────────────────────


def _format_cross_result(result: CrossResult) -> dict:
    """Serializa CrossResult para la API."""
    return {
        "generation": result.generation,
        "sire_breed": result.sire_breed,
        "dam_breed": result.dam_breed,
        "species": result.species,
        "predicted_traits": result.predicted_traits,
        "inbreeding_f": result.inbreeding_f,
        "inbreeding_status": result.inbreeding_status,
        "heterosis_level": result.heterosis_level,
        "color_prediction": result.color_prediction,
        "capon_score": result.capon_score,
        "notes": result.notes,
    }
