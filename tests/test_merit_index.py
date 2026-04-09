"""Tests para el Índice de Mérito Genético (IM)."""

import sys
from pathlib import Path

# Añadir backend al path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from models.merit_index import MeritInput, MeritWeights, SelectionCategory
from services.merit_index import (
    calculate_merit_index,
    calculate_viability,
    get_target_weight,
    gompertz_weight,
    evaluate_pairing,
)


def test_perfect_bird():
    """Ave perfecta: IM cercano a 1.0."""
    inp = MeritInput(
        bird_id="TEST-001",
        age_weeks=20,
        weight_grams=3500,
        target_weight_grams=3500,
        conformacion_score=5.0,
        conversion_ratio=3.0,
        docilidad_score=5.0,
    )
    result = calculate_merit_index(inp)
    assert result.im_score >= 0.90, f"Ave perfecta debería tener IM≥0.90, got {result.im_score}"
    assert result.category == SelectionCategory.REPRODUCTOR


def test_antibiotics_kills_viability():
    """Antibióticos = viabilidad 0.0, baja significativamente el IM."""
    inp = MeritInput(
        bird_id="TEST-002",
        age_weeks=16,
        weight_grams=3000,
        target_weight_grams=3500,
        conformacion_score=4.0,
        has_antibiotics=True,
        docilidad_score=4.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["viabilidad"] == 0.0
    assert result.im_score < 0.85, "Ave con antibióticos no puede ser reproductor"


def test_deformity_kills_viability():
    """Deformidad estructural = viabilidad 0.0."""
    inp = MeritInput(
        bird_id="TEST-DEF",
        age_weeks=12,
        weight_grams=2000,
        target_weight_grams=2500,
        conformacion_score=3.0,
        has_deformity=True,
        docilidad_score=4.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["viabilidad"] == 0.0


def test_transient_lameness_is_mild():
    """Cojera transitoria solo penaliza parcialmente (0.7)."""
    inp = MeritInput(
        bird_id="TEST-003",
        age_weeks=8,
        weight_grams=800,
        target_weight_grams=900,
        conformacion_score=3.5,
        has_transient_lameness=True,
        docilidad_score=4.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["viabilidad"] == 0.7
    assert result.im_score > 0.50


def test_chronic_lameness_severe():
    """Cojera crónica penaliza severamente (0.2)."""
    inp = MeritInput(
        bird_id="TEST-CRON",
        age_weeks=16,
        weight_grams=3000,
        target_weight_grams=3500,
        conformacion_score=4.0,
        has_chronic_lameness=True,
        docilidad_score=4.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["viabilidad"] == 0.2


def test_aggressive_bird_penalized():
    """Ave agresiva (docilidad 1) baja el componente de docilidad."""
    inp = MeritInput(
        bird_id="TEST-004",
        age_weeks=20,
        weight_grams=4000,
        target_weight_grams=3800,
        conformacion_score=5.0,
        docilidad_score=1.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["docilidad"] == 0.2


def test_no_conversion_data_gets_neutral():
    """Sin datos de conversión → 0.5 neutral."""
    inp = MeritInput(
        bird_id="TEST-NOCONV",
        age_weeks=12,
        weight_grams=2000,
        target_weight_grams=2500,
        conformacion_score=3.0,
        conversion_ratio=None,
        docilidad_score=3.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["conversion"] == 0.5


def test_weight_overcap():
    """Peso mayor al objetivo se capea a 1.0."""
    inp = MeritInput(
        bird_id="TEST-OVER",
        age_weeks=20,
        weight_grams=5000,
        target_weight_grams=3500,
        conformacion_score=4.0,
        docilidad_score=4.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["peso"] == 1.0


def test_weights_must_sum_to_one():
    """Pesos que no suman 1.0 deben fallar."""
    try:
        MeritWeights(peso=0.5, conformacion=0.5, conversion=0.5, viabilidad=0.5, docilidad=0.5)
        assert False, "Debería haber lanzado error"
    except Exception:
        pass


def test_custom_weights():
    """Pesos personalizados se aplican correctamente."""
    w = MeritWeights(peso=0.50, conformacion=0.20, conversion=0.10, viabilidad=0.10, docilidad=0.10)
    inp = MeritInput(
        bird_id="TEST-CW",
        age_weeks=20,
        weight_grams=3500,
        target_weight_grams=3500,
        conformacion_score=5.0,
        docilidad_score=5.0,
    )
    result = calculate_merit_index(inp, w)
    # Con peso al 50% y peso perfecto, peso_weighted debe ser 0.50
    assert result.weighted_components["peso"] == 0.50


def test_categories():
    """Verificar los 3 umbrales de categorización."""
    # Reproductor (IM ≥ 0.85)
    perfect = MeritInput(
        bird_id="CAT-R", age_weeks=20, weight_grams=3500,
        target_weight_grams=3500, conformacion_score=5.0, docilidad_score=5.0,
    )
    assert calculate_merit_index(perfect).category == SelectionCategory.REPRODUCTOR

    # Descarte (IM < 0.60)
    poor = MeritInput(
        bird_id="CAT-D", age_weeks=20, weight_grams=1000,
        target_weight_grams=3500, conformacion_score=1.0, docilidad_score=1.0,
        has_antibiotics=True,
    )
    assert calculate_merit_index(poor).category == SelectionCategory.DESCARTE


def test_sibling_tasting_bonus():
    """Bonus por cata de hermano capón se aplica a conformación."""
    base = MeritInput(
        bird_id="TASTE-A", age_weeks=20, weight_grams=3500,
        target_weight_grams=3500, conformacion_score=4.0, docilidad_score=4.0,
    )
    with_bonus = MeritInput(
        bird_id="TASTE-B", age_weeks=20, weight_grams=3500,
        target_weight_grams=3500, conformacion_score=4.0, docilidad_score=4.0,
        sibling_tasting_bonus=0.5,
    )
    r_base = calculate_merit_index(base)
    r_bonus = calculate_merit_index(with_bonus)
    assert r_bonus.components["conformacion"] > r_base.components["conformacion"]


def test_gompertz_weight():
    """El modelo Gompertz produce valores razonables."""
    # A 20 semanas (140 días), un Sussex debería estar ~3500-4000g
    w = gompertz_weight(140, 4200, 0.025, 75)
    assert 3000 < w < 4200, f"Gompertz Sussex 20w = {w}g"


def test_gompertz_target_by_gallinero():
    """get_target_weight funciona por gallinero."""
    t = get_target_weight(20, gallinero="G2")
    assert t > 0


def test_gompertz_target_by_breed():
    """get_target_weight funciona por raza."""
    t = get_target_weight(20, breed="sussex")
    assert t > 0


def test_auto_gompertz_when_no_target():
    """Si no se pasa target_weight_grams, se calcula por gallinero."""
    inp = MeritInput(
        bird_id="AUTO-G", gallinero="G2", age_weeks=20,
        weight_grams=3800, conformacion_score=4.0, docilidad_score=4.0,
    )
    result = calculate_merit_index(inp)
    assert result.components["peso"] > 0


def test_sex_in_recommendation():
    """El sexo aparece en la recomendación cuando se proporciona."""
    inp_male = MeritInput(
        bird_id="SEX-M", sex="male", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=4.0, docilidad_score=4.0,
    )
    inp_female = MeritInput(
        bird_id="SEX-F", sex="female", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=4.0, docilidad_score=4.0,
    )
    r_m = calculate_merit_index(inp_male)
    r_f = calculate_merit_index(inp_female)
    assert "(macho)" in r_m.recommendation
    assert "(hembra)" in r_f.recommendation


def test_sex_female_produccion_destino():
    """Hembra en PRODUCCIÓN recomienda pularda, no capón."""
    inp = MeritInput(
        bird_id="DEST-F", sex="female", age_weeks=20,
        weight_grams=2800, target_weight_grams=3500,
        conformacion_score=3.5, docilidad_score=3.5,
    )
    result = calculate_merit_index(inp)
    if result.category == SelectionCategory.PRODUCCION:
        assert "pularda" in result.recommendation
        assert "capón" not in result.recommendation


def test_calculate_with_custom_weights():
    """El endpoint /calculate ahora acepta weights custom."""
    w = MeritWeights(peso=0.50, conformacion=0.20, conversion=0.10, viabilidad=0.10, docilidad=0.10)
    inp = MeritInput(
        bird_id="CW-CALC", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    result = calculate_merit_index(inp, w)
    assert result.weighted_components["peso"] == 0.50


def test_pairing_approved_low_coi():
    """Apareamiento con COI bajo y buenos IM → APPROVED."""
    sire = MeritInput(
        bird_id="SIRE-01", sex="male", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    dam = MeritInput(
        bird_id="DAM-01", sex="female", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    result = evaluate_pairing(sire, dam, expected_coi=0.05)
    assert result["decision"] == "APPROVED"
    assert len(result["warnings"]) == 0


def test_pairing_blocked_high_coi():
    """Apareamiento con COI > 0.25 → BLOCKED aunque IM sea alto."""
    sire = MeritInput(
        bird_id="SIRE-02", sex="male", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    dam = MeritInput(
        bird_id="DAM-02", sex="female", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    result = evaluate_pairing(sire, dam, expected_coi=0.30)
    assert result["decision"] == "BLOCKED"
    assert any("BLOQUEADO" in w for w in result["warnings"])


def test_pairing_warns_medium_coi():
    """COI entre 0.125 y 0.25 → APPROVED con warning."""
    sire = MeritInput(
        bird_id="SIRE-03", sex="male", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    dam = MeritInput(
        bird_id="DAM-03", sex="female", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    result = evaluate_pairing(sire, dam, expected_coi=0.20)
    assert result["decision"] == "APPROVED"
    assert any("primos hermanos" in w for w in result["warnings"])


def test_pairing_warns_non_reproductor():
    """Apareamiento con ave no-reproductora genera warning."""
    sire = MeritInput(
        bird_id="SIRE-04", sex="male", age_weeks=20,
        weight_grams=1000, target_weight_grams=3500,
        conformacion_score=2.0, docilidad_score=2.0,
        has_antibiotics=True,
    )
    dam = MeritInput(
        bird_id="DAM-04", sex="female", age_weeks=20,
        weight_grams=3500, target_weight_grams=3500,
        conformacion_score=5.0, docilidad_score=5.0,
    )
    result = evaluate_pairing(sire, dam, expected_coi=0.05)
    assert any("No es reproductor" in w for w in result["warnings"])


if __name__ == "__main__":
    tests = [v for k, v in globals().items() if k.startswith("test_")]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  ✅ {t.__name__}")
            passed += 1
        except Exception as e:
            print(f"  ❌ {t.__name__}: {e}")
            failed += 1
    print(f"\n{'='*40}")
    print(f"Total: {passed + failed} | ✅ {passed} | ❌ {failed}")
