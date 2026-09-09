from celery import Celery

from services.api.app.config.settings import get_worker_settings

settings = get_worker_settings()

celery_app = Celery(
    "strayhub",
    broker=settings.celery_broker_url,
    include=[
        "services.worker.app.tasks.adoption",
        "services.worker.app.tasks.care_report",
        "services.worker.app.tasks.growth_diary",
        "services.worker.app.tasks.reconciliation",
    ],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    enable_utc=True,
    timezone="UTC",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_connection_timeout=5,
    task_publish_retry=False,
    broker_transport_options={
        "visibility_timeout": settings.celery_visibility_timeout,
        # Jobs are persisted before publish. Fail fast and let reconciliation
        # retry from PostgreSQL instead of blocking an API/webhook request.
        "max_retries": 0,
        "socket_connect_timeout": 1,
        "socket_timeout": 5,
    },
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    task_time_limit=settings.celery_task_time_limit,
    task_routes={
        "adoption.*": {"queue": settings.celery_queue_ai},
        "growth_diary.*": {"queue": settings.celery_queue_ai},
        "care_report.*": {"queue": settings.celery_queue_ai},
        "system.*": {"queue": settings.celery_queue_system},
    },
    beat_schedule={
        "reconcile-ai-dispatch": {
            "task": "system.reconcile_ai_dispatch",
            "schedule": settings.celery_reconcile_interval_seconds,
            "options": {"queue": settings.celery_queue_system},
        }
    },
)

__all__ = ["celery_app"]
