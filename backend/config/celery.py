import os
from celery import Celery

# Set default Django settings module for celery program
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

# Load configuration from Django settings, using 'CELERY_' prefix
app.config_from_object("django.conf:settings", namespace="CELERY")

# Discover tasks from all registered Django apps
app.autodiscover_tasks()
