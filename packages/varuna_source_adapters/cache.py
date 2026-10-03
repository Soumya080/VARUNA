import hashlib
import os
from pathlib import Path
import shutil
import time

from varuna_source_adapters.protocol import SourceQuery

class FileCache:
    """Local filesystem cache with TTL."""

    def __init__(self, cache_dir: str = ".cache/adapters", ttl_seconds: int = 86400):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.ttl_seconds = ttl_seconds

    def get(self, key: str) -> str | None:
        """Return path if cached and fresh, None otherwise."""
        path = self.cache_dir / key
        if path.exists():
            if time.time() - path.stat().st_mtime < self.ttl_seconds:
                return str(path)
        return None

    def put(self, key: str, source_path: str) -> str:
        """Copy source_path into cache. Return cache path."""
        dest = self.cache_dir / key
        shutil.copy2(source_path, dest)
        return str(dest)

    def make_key(self, query: SourceQuery, ext: str = ".nc") -> str:
        """Deterministic cache key from query."""
        raw = f"{query.product_id}|{query.bbox.min_lon}|{query.bbox.min_lat}|{query.bbox.max_lon}|{query.bbox.max_lat}|{query.time_start.isoformat()}|{query.time_end.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest() + ext
