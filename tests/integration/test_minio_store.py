import pytest
import os
import asyncio
from varuna_infra.minio_store import MinioObjectStore

@pytest.fixture
def minio_store():
    # Attempt to connect to local minio; skip if unavailable
    endpoint = os.environ.get("MINIO_ENDPOINT", "localhost:9000")
    access_key = os.environ.get("MINIO_ACCESS_KEY", "minioadmin")
    secret_key = os.environ.get("MINIO_SECRET_KEY", "minioadmin")
    bucket = "test-varuna"
    
    import socket
    host, port = endpoint.split(":")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        try:
            s.connect((host, int(port)))
        except Exception:
            pytest.skip(f"MinIO not available at {endpoint}")

    try:
        store = MinioObjectStore(endpoint, access_key, secret_key, bucket, secure=False)
        return store
    except Exception as e:
        pytest.skip(f"MinIO not available for testing: {e}")

@pytest.mark.asyncio
async def test_minio_store_put_get(minio_store):
    data = b"test_scientific_data_123"
    metadata = {"content-type": "application/octet-stream", "case_id": "CASE-MINIO"}
    key = "test_case/phi_field.npy"
    
    # Put
    res_key = await minio_store.put(key, data, metadata)
    assert res_key == key
    
    # Exists
    exists = await minio_store.exists(key)
    assert exists is True
    
    # Get
    fetched_data = await minio_store.get(key)
    assert fetched_data == data
    
    # List
    keys = await minio_store.list_prefix("test_case/")
    assert key in keys
    
    # Delete
    await minio_store.delete(key)
    exists = await minio_store.exists(key)
    assert exists is False
