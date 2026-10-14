import os

from celery import Celery  # type: ignore[import-untyped]

celery = Celery(
    "career-intelligence", broker=os.environ.get("REDIS_URL", "redis://127.0.0.1:6379/0")
)
celery.conf.update(
    accept_content=["json"],
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 900, "global_keyprefix": "career:"},
    result_backend=None,
    task_acks_late=True,
    task_default_queue="discovery",
    task_ignore_result=True,
    task_publish_retry=True,
    task_publish_retry_policy={
        "max_retries": 2,
        "interval_start": 0,
        "interval_step": 1,
        "interval_max": 2,
    },
    task_reject_on_worker_lost=True,
    task_serializer="json",
    task_soft_time_limit=70,
    task_time_limit=75,
    worker_prefetch_multiplier=1,
)
celery.autodiscover_tasks(["app.workers"])
