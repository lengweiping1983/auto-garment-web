"""Celery application configuration (optional, for future scaling).

Currently the project uses FastAPI BackgroundTasks for async processing.
Enable Celery + Redis when you need distributed workers.
"""
# from celery import Celery
# from app.config import settings
#
# celery_app = Celery(
#     "auto_garment",
#     broker=settings.redis_url,
#     backend=settings.redis_url,
#     include=["app.core.pipeline"],
# )
