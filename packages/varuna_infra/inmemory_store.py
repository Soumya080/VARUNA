"""
VARUNA GRID — In-memory Object Store.
"""
from typing import Dict, List
from varuna_domain.ports import ObjectStore


class InMemoryObjectStore(ObjectStore):
    def __init__(self):
        self._data: Dict[str, bytes] = {}
        self._metadata: Dict[str, Dict[str, str]] = {}

    async def put(self, key: str, data: bytes, metadata: Dict[str, str]) -> str:
        self._data[key] = data
        self._metadata[key] = metadata
        return key

    async def get(self, key: str) -> bytes:
        if key not in self._data:
            raise KeyError(f"Object not found: {key}")
        return self._data[key]

    async def exists(self, key: str) -> bool:
        return key in self._data

    async def list_prefix(self, prefix: str) -> List[str]:
        return [k for k in self._data.keys() if k.startswith(prefix)]
