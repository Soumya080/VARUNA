"""
VARUNA GRID — MinIO Object Store.
"""
import io
import json
import asyncio
from typing import Dict, List, Optional
from minio import Minio
from minio.error import S3Error

from varuna_domain.ports import ObjectStore

class MinioObjectStore(ObjectStore):
    def __init__(self, endpoint: str, access_key: str, secret_key: str, bucket_name: str, secure: bool = False):
        self.client = Minio(
            endpoint,
            access_key=access_key,
            secret_key=secret_key,
            secure=secure
        )
        self.bucket_name = bucket_name
        self._ensure_bucket()

    def _ensure_bucket(self):
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)

    async def put(self, key: str, data: bytes, metadata: Dict[str, str]) -> str:
        # Convert metadata values to strings as S3 headers only support strings
        str_metadata = {k: str(v) for k, v in metadata.items()}
        
        def _put():
            self.client.put_object(
                self.bucket_name,
                key,
                data=io.BytesIO(data),
                length=len(data),
                metadata=str_metadata
            )
        await asyncio.to_thread(_put)
        return key

    async def get(self, key: str) -> bytes:
        def _get():
            try:
                response = self.client.get_object(self.bucket_name, key)
                data = response.read()
                response.close()
                response.release_conn()
                return data
            except S3Error as e:
                if e.code == "NoSuchKey":
                    raise KeyError(f"Object not found: {key}")
                raise
        return await asyncio.to_thread(_get)

    async def exists(self, key: str) -> bool:
        def _exists():
            try:
                self.client.stat_object(self.bucket_name, key)
                return True
            except S3Error as e:
                if e.code == "NoSuchKey":
                    return False
                raise
        return await asyncio.to_thread(_exists)

    async def list_prefix(self, prefix: str) -> List[str]:
        def _list():
            objects = self.client.list_objects(self.bucket_name, prefix=prefix, recursive=True)
            return [obj.object_name for obj in objects]
        return await asyncio.to_thread(_list)
