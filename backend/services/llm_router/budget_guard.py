"""
Budget Guard — Control de gasto diario/mensual con degradación a local.
Evita sorpresas de facturación de Together.ai.
"""

import logging
from datetime import datetime, date
from typing import Dict
import os
import json
from pathlib import Path

log = logging.getLogger(__name__)


class BudgetGuard:
    """
    Guarda del presupuesto. Cap diario y mensual configurable.
    Cuando se alcanza 80%, emite warnings. Al 95%, bloquea Together.
    """
    
    # Configuración desde .env o defaults
    DAILY_CAP_USD = float(os.getenv("TOGETHER_DAILY_CAP_USD", "7.50"))
    MONTHLY_CAP_USD = float(os.getenv("TOGETHER_MONTHLY_CAP_USD", "175.0"))
    
    def __init__(self, state_file: str = "/app/data/llm_budget_state.json"):
        self.state_file = Path(state_file)
        self.state = self._load_state()
    
    def _load_state(self) -> Dict:
        """Carga estado de gasto del día/mes actual."""
        if not self.state_file.exists():
            return self._init_state()
        
        try:
            with open(self.state_file, "r") as f:
                state = json.load(f)
            
            # Reset si cambió el día o mes
            today = date.today().isoformat()
            month = date.today().strftime("%Y-%m")
            
            if state.get("date") != today:
                state["daily_usd"] = 0.0
                state["date"] = today
            
            if state.get("month") != month:
                state["monthly_usd"] = 0.0
                state["month"] = month
            
            return state
        
        except Exception as exc:
            log.warning(f"Failed to load budget state: {exc}. Resetting.")
            return self._init_state()
    
    def _init_state(self) -> Dict:
        """Estado inicial."""
        today = date.today()
        return {
            "date": today.isoformat(),
            "month": today.strftime("%Y-%m"),
            "daily_usd": 0.0,
            "monthly_usd": 0.0,
            "daily_calls": 0,
            "monthly_calls": 0,
        }
    
    def _save_state(self):
        """Persiste estado."""
        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            with open(self.state_file, "w") as f:
                json.dump(self.state, f, indent=2)
        except Exception as exc:
            log.error(f"Failed to save budget state: {exc}")
    
    def record(self, model_id: str, cost_usd: float):
        """Registra un gasto."""
        if cost_usd <= 0:
            return  # Local, no cost
        
        self.state["daily_usd"] += cost_usd
        self.state["monthly_usd"] += cost_usd
        self.state["daily_calls"] += 1
        self.state["monthly_calls"] += 1
        
        self._save_state()
        
        # Warn si superamos umbrales
        if self.warn_threshold():
            log.warning(
                f"⚠️ Budget warning: daily ${self.state['daily_usd']:.2f} "
                f"(cap ${self.DAILY_CAP_USD:.2f}), "
                f"monthly ${self.state['monthly_usd']:.2f} "
                f"(cap ${self.MONTHLY_CAP_USD:.2f})"
            )
    
    def is_capped(self) -> bool:
        """¿Hemos alcanzado el cap? Bloquea Together.ai."""
        daily_pct = self.state["daily_usd"] / self.DAILY_CAP_USD
        monthly_pct = self.state["monthly_usd"] / self.MONTHLY_CAP_USD
        
        return daily_pct >= 0.95 or monthly_pct >= 0.95
    
    def warn_threshold(self) -> bool:
        """¿Estamos cerca del cap? (80%)"""
        daily_pct = self.state["daily_usd"] / self.DAILY_CAP_USD
        monthly_pct = self.state["monthly_usd"] / self.MONTHLY_CAP_USD
        
        return daily_pct >= 0.80 or monthly_pct >= 0.80
    
    def usage_today(self) -> float:
        """Gasto hoy en USD."""
        return self.state["daily_usd"]
    
    def usage_month(self) -> float:
        """Gasto este mes en USD."""
        return self.state["monthly_usd"]
    
    def get_summary(self) -> Dict:
        """Resumen del estado actual."""
        return {
            "daily": {
                "usd": self.state["daily_usd"],
                "cap": self.DAILY_CAP_USD,
                "pct": (self.state["daily_usd"] / self.DAILY_CAP_USD) * 100,
                "calls": self.state["daily_calls"],
            },
            "monthly": {
                "usd": self.state["monthly_usd"],
                "cap": self.MONTHLY_CAP_USD,
                "pct": (self.state["monthly_usd"] / self.MONTHLY_CAP_USD) * 100,
                "calls": self.state["monthly_calls"],
            },
            "is_capped": self.is_capped(),
            "warn_threshold": self.warn_threshold(),
        }


# Singleton global
_budget_guard = None


def get_budget_guard() -> BudgetGuard:
    """Obtiene instancia singleton del BudgetGuard."""
    global _budget_guard
    if _budget_guard is None:
        _budget_guard = BudgetGuard()
    return _budget_guard
