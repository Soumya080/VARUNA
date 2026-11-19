from apps.worker.celery_app import celery_app

@celery_app.task
def run_abhiyan_task(case_id: str):
    pass
