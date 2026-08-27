from apps.worker.celery_app import celery_app

@celery_app.task
def run_netra_task(image_path: str):
    pass
