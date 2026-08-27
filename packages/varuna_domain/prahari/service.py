from typing import List
from varuna_contracts.schemas import BBox
from varuna_domain.prahari.protocol import PrahariProvider

class PrahariService:
    """Orchestrates: scene arrival -> NETRA -> case creation -> pipeline trigger."""

    def __init__(self, provider: PrahariProvider, netra_service, workflow):
        self._provider = provider
        self._netra = netra_service
        self._workflow = workflow

    def start_watch(self, region: BBox):
        def on_scene(scene_path: str):
            pass # Hook to create envelope, trigger netra, etc.
        self._provider.watch(region, on_scene)

    def start_replay(self, scene_paths: List[str], delay: float = 5.0):
        def on_scene(scene_path: str):
            pass # Same as watch
        self._provider.replay(scene_paths, on_scene, delay)

    def stop(self):
        self._provider.stop()

    @property
    def is_running(self) -> bool:
        return self._provider.is_running
        
    def schedule_task(self, cron_expr: str, callback: callable) -> str:
        return self._provider.schedule(cron_expr, callback)
        
    def cancel_task(self, job_id: str) -> None:
        self._provider.cancel(job_id)
