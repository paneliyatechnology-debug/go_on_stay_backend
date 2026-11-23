import os
from django.conf import settings

# Set the default Django settings module for Celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    from celery import Celery
    app = Celery('goonstay')

    # Using a string here means the worker doesn't have to serialize
    # the configuration object to child processes.
    app.config_from_object('django.conf:settings', namespace='CELERY')

    # Celery Production Settings
    app.conf.update(
        broker_url=getattr(settings, 'CELERY_BROKER_URL', 'redis://localhost:6379/0'),
        result_backend=getattr(settings, 'CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
        task_serializer='json',
        accept_content=['json'],
        result_serializer='json',
        timezone=settings.TIME_ZONE,
        enable_utc=True,
        task_track_started=True,
        task_time_limit=300,  # 5 min hard limit
        task_soft_time_limit=240,  # 4 min soft limit
        worker_prefetch_multiplier=1,  # Fair distribution
        task_acks_late=True,  # Prevent lost tasks on worker crash
        task_reject_on_worker_lost=True,
    )

    # Load task modules from all registered Django apps.
    app.autodiscover_tasks()

except ImportError:
    # Graceful fallback when Celery package is not yet installed in local dev
    app = None
