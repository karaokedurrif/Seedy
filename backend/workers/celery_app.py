"""Seedy Backend — Celery App Configuration.

Usa Redis como broker y backend para tasks async.
"""

from celery import Celery
from celery.schedules import crontab

celery_app = Celery(
    "seedy_workers",
    broker="redis://redis:6379/0",  # Redis container en ai_default network
    backend="redis://redis:6379/0",
    include=[
        "workers.behavior_analyzer",
        "workers.mating_confirmer",
        "workers.weekly_report",
    ],
)

# Configuración
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Europe/Madrid",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hora max por task
    task_soft_time_limit=3300,  # Warning a los 55 min
    worker_prefetch_multiplier=1,  # No prefetch tasks (importante para tasks lentos)
    worker_max_tasks_per_child=10,  # Restart worker cada 10 tasks (memory leak protection)
)

# Periodic tasks (Celery Beat)
celery_app.conf.beat_schedule = {
    # Análisis de comportamiento 7D cada noche a las 3 AM
    "analyze-behavior-7d-nightly": {
        "task": "workers.behavior_analyzer.analyze_bird_behavior_7d",
        "schedule": crontab(hour=3, minute=0),
        "args": ("gallinero_palacio",),  # Gallinero por defecto
    },
    # Confirmación de montas cada 6 horas
    "confirm-matings-6h": {
        "task": "workers.mating_confirmer.confirm_mating_batch",
        "schedule": crontab(minute=0, hour="*/6"),  # 00:00, 06:00, 12:00, 18:00
        "args": ("gallinero_palacio", 6),  # Últimas 6 horas
    },
    # Reporte semanal cada domingo a las 20:00
    "weekly-report-sunday": {
        "task": "workers.weekly_report.generate_weekly_report",
        "schedule": crontab(day_of_week=0, hour=20, minute=0),  # Domingo 20:00
        "args": ("gallinero_palacio",),
    },
}
