"""
Seedy Genetics — Motor BLUP / GBLUP

Implementación de Henderson's Mixed Model Equations para
calcular Estimated Breeding Values (EBV) por pedigrí y
Genomic EBV (GEBV) con matriz de relaciones genómicas.

Referencias:
  Henderson (1984) — Applications of Linear Models in Animal Breeding
  VanRaden (2008) — Efficient Methods to Compute Genomic Predictions
"""

import numpy as np
from dataclasses import dataclass, field


@dataclass
class Animal:
    """Animal con pedigrí y fenotipos."""
    id: str
    sire_id: str | None = None  # Padre
    dam_id: str | None = None   # Madre
    sex: str = "unknown"        # male, female
    breed: str = ""
    generation: int = 0
    phenotypes: dict[str, float] = field(default_factory=dict)
    ebv: dict[str, float] = field(default_factory=dict)
    gebv: dict[str, float] = field(default_factory=dict)
    inbreeding_f: float = 0.0
    genotype: np.ndarray | None = None  # SNP markers (0, 1, 2)


class BLUPEngine:
    """
    Motor BLUP de Henderson para cálculo de EBV.
    
    Modelo animal mixto: y = Xb + Zu + e
      y: vector de fenotipos
      X: matriz de diseño para efectos fijos
      b: efectos fijos (media de grupo, sexo, etc.)
      Z: matriz de incidencia para efectos aleatorios
      u: valores genéticos aditivos (EBV)
      e: residuales
    
    Henderson's MME:
      [X'X    X'Z  ] [b̂]   [X'y]
      [Z'X  Z'Z+A⁻¹λ] [û] = [Z'y]
    
    donde λ = σ²e / σ²a = (1 - h²) / h²
    """
    
    def __init__(self):
        self.animals: dict[str, Animal] = {}
        self._id_to_idx: dict[str, int] = {}
    
    def add_animal(self, animal: Animal):
        """Registra un animal en el motor."""
        self.animals[animal.id] = animal
    
    def add_pedigree(self, records: list[dict]):
        """
        Carga pedigrí masivo.
        Cada record: {"id": str, "sire": str|None, "dam": str|None,
                       "sex": str, "breed": str, "generation": int}
        """
        for rec in records:
            animal = Animal(
                id=rec["id"],
                sire_id=rec.get("sire"),
                dam_id=rec.get("dam"),
                sex=rec.get("sex", "unknown"),
                breed=rec.get("breed", ""),
                generation=rec.get("generation", 0),
            )
            self.animals[animal.id] = animal
    
    def set_phenotype(self, animal_id: str, trait: str, value: float):
        """Registra un fenotipo observado."""
        if animal_id in self.animals:
            self.animals[animal_id].phenotypes[trait] = value
    
    # ── Matriz de parentesco (A) ──
    
    def build_relationship_matrix(self) -> np.ndarray:
        """
        Construye la Numerator Relationship Matrix (A) de Wright.
        A(i,j) = 2 × parentesco entre i y j.
        A(i,i) = 1 + F(i), donde F(i) es el coeficiente de consanguinidad.
        
        Algoritmo tabular de Meuwissen & Luo (1992).
        """
        ids = sorted(self.animals.keys())
        n = len(ids)
        self._id_to_idx = {aid: i for i, aid in enumerate(ids)}
        
        A = np.zeros((n, n))
        
        for i, aid in enumerate(ids):
            animal = self.animals[aid]
            
            sire_idx = self._id_to_idx.get(animal.sire_id) if animal.sire_id else None
            dam_idx = self._id_to_idx.get(animal.dam_id) if animal.dam_id else None
            
            if sire_idx is not None and dam_idx is not None:
                # A(i,i) = 1 + F(i) = 1 + 0.5 * A(sire, dam)
                A[i, i] = 1.0 + 0.5 * A[sire_idx, dam_idx]
            else:
                A[i, i] = 1.0
            
            for j in range(i):
                jid = ids[j]
                j_animal = self.animals[jid]
                
                j_sire_idx = self._id_to_idx.get(j_animal.sire_id) if j_animal.sire_id else None
                j_dam_idx = self._id_to_idx.get(j_animal.dam_id) if j_animal.dam_id else None
                
                val = 0.0
                if sire_idx is not None:
                    if j == sire_idx:
                        val += 0.5 * A[sire_idx, sire_idx]
                    else:
                        val += 0.5 * A[min(sire_idx, j), max(sire_idx, j)] if sire_idx != j else 0.5 * A[sire_idx, sire_idx]
                if dam_idx is not None:
                    if j == dam_idx:
                        val += 0.5 * A[dam_idx, dam_idx]
                    else:
                        val += 0.5 * A[min(dam_idx, j), max(dam_idx, j)] if dam_idx != j else 0.5 * A[dam_idx, dam_idx]
                
                # Corrección: usar tabular method
                if sire_idx is not None and dam_idx is not None:
                    val = 0.5 * (A[j, sire_idx] + A[j, dam_idx])
                elif sire_idx is not None:
                    val = 0.5 * A[j, sire_idx]
                elif dam_idx is not None:
                    val = 0.5 * A[j, dam_idx]
                else:
                    val = 0.0
                
                A[i, j] = val
                A[j, i] = val
        
        # Actualizar F de cada animal
        for aid, idx in self._id_to_idx.items():
            self.animals[aid].inbreeding_f = A[idx, idx] - 1.0
        
        return A
    
    def compute_inbreeding(self, animal_id: str) -> float:
        """Calcula F de Wright para un animal específico."""
        if not self._id_to_idx:
            self.build_relationship_matrix()
        return self.animals.get(animal_id, Animal(id="")).inbreeding_f
    
    # ── BLUP Henderson's MME ──
    
    def solve_blup(self, trait: str, heritability: float,
                   fixed_effects: dict[str, list[str]] | None = None
                   ) -> dict[str, float]:
        """
        Resuelve las Henderson's Mixed Model Equations para un rasgo.
        
        Args:
            trait: Nombre del rasgo
            heritability: Heredabilidad (h²)
            fixed_effects: {nombre_efecto: [niveles]} → e.g. {"sex": ["male", "female"]}
        
        Returns: {animal_id: EBV}
        """
        # Step 1: Identificar animales con fenotipo
        ids = sorted(self.animals.keys())
        n_animals = len(ids)
        id_map = {aid: i for i, aid in enumerate(ids)}
        
        # Animales con datos
        phenotyped = [
            (aid, self.animals[aid].phenotypes[trait])
            for aid in ids
            if trait in self.animals[aid].phenotypes
        ]
        
        if not phenotyped:
            return {}
        
        n_obs = len(phenotyped)
        y = np.array([p[1] for p in phenotyped])
        obs_ids = [p[0] for p in phenotyped]
        
        # Step 2: Matrices de diseño
        # Efecto fijo: solo media general (intercepto)
        n_fixed = 1
        X = np.ones((n_obs, n_fixed))
        
        # Z: incidencia animales
        Z = np.zeros((n_obs, n_animals))
        for i, aid in enumerate(obs_ids):
            Z[i, id_map[aid]] = 1.0
        
        # Step 3: Relationship matrix A
        A = self.build_relationship_matrix()
        
        # Step 4: lambda = σ²e / σ²a
        lam = (1.0 - heritability) / heritability
        
        # Step 5: Construir MME
        # [X'X    X'Z        ] [b̂]   [X'y]
        # [Z'X  Z'Z + A⁻¹·λ ] [û] = [Z'y]
        
        try:
            A_inv = np.linalg.inv(A)
        except np.linalg.LinAlgError:
            # Si A es singular, usar pseudoinversa
            A_inv = np.linalg.pinv(A)
        
        XtX = X.T @ X
        XtZ = X.T @ Z
        ZtX = Z.T @ X
        ZtZ = Z.T @ Z
        Xty = X.T @ y
        Zty = Z.T @ y
        
        # Ensamblar sistema
        dim = n_fixed + n_animals
        LHS = np.zeros((dim, dim))
        RHS = np.zeros(dim)
        
        LHS[:n_fixed, :n_fixed] = XtX
        LHS[:n_fixed, n_fixed:] = XtZ
        LHS[n_fixed:, :n_fixed] = ZtX
        LHS[n_fixed:, n_fixed:] = ZtZ + A_inv * lam
        
        RHS[:n_fixed] = Xty
        RHS[n_fixed:] = Zty
        
        # Step 6: Resolver
        try:
            solution = np.linalg.solve(LHS, RHS)
        except np.linalg.LinAlgError:
            solution = np.linalg.lstsq(LHS, RHS, rcond=None)[0]
        
        # Extraer EBVs
        ebvs = solution[n_fixed:]
        result = {}
        for aid, idx in id_map.items():
            ebv_val = float(ebvs[idx])
            self.animals[aid].ebv[trait] = ebv_val
            result[aid] = ebv_val
        
        return result
    
    # ── GBLUP ──
    
    def solve_gblup(self, trait: str, heritability: float) -> dict[str, float]:
        """
        GBLUP: BLUP genómico usando la Genomic Relationship Matrix (G).
        G = ZZ' / Σ(2p(1-p))  (VanRaden, 2008)
        
        Requiere que los animales tengan genotype (array de SNP 0/1/2).
        """
        # Animales con genotipo
        genotyped = [
            (aid, self.animals[aid])
            for aid in sorted(self.animals.keys())
            if self.animals[aid].genotype is not None
        ]
        
        if len(genotyped) < 2:
            return self.solve_blup(trait, heritability)
        
        ids = [g[0] for g in genotyped]
        n = len(ids)
        
        # Construir matriz M de genotipos
        M = np.array([self.animals[aid].genotype for aid in ids], dtype=float)
        n_snp = M.shape[1]
        
        # Frecuencias alélicas
        p = M.mean(axis=0) / 2.0
        p = np.clip(p, 0.01, 0.99)
        
        # Centrar: Z = M - 2p
        Z_mat = M - 2.0 * p
        
        # G = ZZ' / sum(2pq)
        scaling = np.sum(2.0 * p * (1.0 - p))
        if scaling < 1e-10:
            scaling = 1.0
        G = (Z_mat @ Z_mat.T) / scaling
        
        # Resolver con G en vez de A
        phenotyped = [
            (aid, self.animals[aid].phenotypes[trait])
            for aid in ids
            if trait in self.animals[aid].phenotypes
        ]
        
        if not phenotyped:
            return {}
        
        n_obs = len(phenotyped)
        y = np.array([p[1] for p in phenotyped])
        obs_ids = [p[0] for p in phenotyped]
        id_map = {aid: i for i, aid in enumerate(ids)}
        
        X = np.ones((n_obs, 1))
        Z_inc = np.zeros((n_obs, n))
        for i, aid in enumerate(obs_ids):
            if aid in id_map:
                Z_inc[i, id_map[aid]] = 1.0
        
        lam = (1.0 - heritability) / heritability
        
        try:
            G_inv = np.linalg.inv(G)
        except np.linalg.LinAlgError:
            G_inv = np.linalg.pinv(G)
        
        XtX = X.T @ X
        XtZ = X.T @ Z_inc
        ZtX = Z_inc.T @ X
        ZtZ = Z_inc.T @ Z_inc
        Xty = X.T @ y
        Zty = Z_inc.T @ y
        
        dim = 1 + n
        LHS = np.zeros((dim, dim))
        RHS = np.zeros(dim)
        
        LHS[0, 0] = XtX[0, 0]
        LHS[0, 1:] = XtZ[0]
        LHS[1:, 0] = ZtX[:, 0]
        LHS[1:, 1:] = ZtZ + G_inv * lam
        
        RHS[0] = Xty[0]
        RHS[1:] = Zty
        
        try:
            solution = np.linalg.solve(LHS, RHS)
        except np.linalg.LinAlgError:
            solution = np.linalg.lstsq(LHS, RHS, rcond=None)[0]
        
        gebvs = solution[1:]
        result = {}
        for aid, idx in id_map.items():
            val = float(gebvs[idx])
            self.animals[aid].gebv[trait] = val
            result[aid] = val
        
        return result
    
    # ── Precisión de cría ──
    
    @staticmethod
    def breeding_accuracy(n_progeny: int, heritability: float) -> float:
        """
        Precisión del EBV basada en número de descendientes.
        r = sqrt(n × h² / (1 + (n-1) × h²/4))
        """
        if n_progeny <= 0 or heritability <= 0:
            return 0.0
        num = n_progeny * heritability
        den = 1.0 + (n_progeny - 1) * heritability / 4.0
        return float(np.sqrt(num / den))
    
    # ── Ranking por EBV ──
    
    def rank_animals(self, trait: str, top_n: int = 10,
                     use_gebv: bool = False) -> list[dict]:
        """
        Ranking de animales por EBV (o GEBV) para un rasgo.
        """
        values = []
        for aid, animal in self.animals.items():
            source = animal.gebv if use_gebv else animal.ebv
            if trait in source:
                values.append({
                    "id": aid,
                    "breed": animal.breed,
                    "sex": animal.sex,
                    "generation": animal.generation,
                    "ebv": source[trait],
                    "inbreeding_f": animal.inbreeding_f,
                    "type": "GEBV" if use_gebv else "EBV",
                })
        
        values.sort(key=lambda x: x["ebv"], reverse=True)
        return values[:top_n]
