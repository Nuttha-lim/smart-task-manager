import os
from celery import Celery

# Broker URL can be overridden with env var CELERY_BROKER_URL
broker = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/0')

app = Celery('smart_task_manager', broker=broker)

# Basic beat schedule: run the notification processor every minute
app.conf.beat_schedule = {
    'process-notifications-every-minute': {
        'task': 'celery_tasks.process_notifications',
        'schedule': 60.0,
        'args': (),
    },
}

app.conf.timezone = 'UTC'

# Ensure task modules are imported so Celery registers tasks at startup.
import celery_tasks  # noqa: F401
