from apps.worker.celery_app import celery_app

@celery_app.task
def run_pravaah_task(region: str):
    pass
