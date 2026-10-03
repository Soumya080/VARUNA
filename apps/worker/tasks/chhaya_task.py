from apps.worker.celery_app import celery_app

@celery_app.task
def run_chhaya_task(slick_id: str):
    pass
