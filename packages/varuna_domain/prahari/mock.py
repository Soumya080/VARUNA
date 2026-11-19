import threading
import uuid
from typing import Callable, Dict, List
from varuna_contracts.schemas import BBox
from varuna_domain.prahari.protocol import PrahariProvider

class MockPrahariProvider(PrahariProvider):
    def __init__(self):
        self._stop_event = threading.Event()
        self._running = False
        self._scheduled_jobs: Dict[str, str] = {}

    def watch(self, region: BBox, callback: Callable[[str], None]) -> None:
        """Mock watch: just replay the test fixtures."""
        fixture_scenes = ["tests/fixtures/scene_mock_01.tif",
                          "tests/fixtures/scene_mock_02.tif"]
        self.replay(fixture_scenes, callback)

    def replay(self, scene_paths: List[str], callback: Callable[[str], None], delay_seconds: float = 5.0) -> None:
        self._running = True
        self._stop_event.clear()
        for path in scene_paths:
            if self._stop_event.is_set():
                break
            callback(path)
            self._stop_event.wait(timeout=delay_seconds)
        self._running = False

    def stop(self) -> None:
        self._stop_event.set()

    @property
    def is_running(self) -> bool:
        return self._running

    def schedule(self, cron_expr: str, callback: Callable[[], None]) -> str:
        """Mock schedule: records the job and returns a job ID without
        actually running `callback` on a cron. Deterministic, no threads.
        """
        job_id = f"job-{uuid.uuid4().hex[:8]}"
        self._scheduled_jobs[job_id] = cron_expr
        return job_id

    def cancel(self, job_id: str) -> None:
        self._scheduled_jobs.pop(job_id, None)
