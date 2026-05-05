"""Seedy Backend — Workers Celery para tareas asíncronas batch."""

from .celery_app import celery_app

__all__ = ["celery_app"]
