"""Tiny in-memory stand-ins for MongoDB and S3 so endpoint tests need no network."""


from app.local import MemoryCollection as FakeCollection  # noqa: F401
from app.local import MemoryDB as FakeDB  # noqa: F401


class FakeS3:
    """Replaces app.storage: uploads are a dict of key -> bytes."""
    def __init__(self):
        self.objects = {}

    def presign_put(self, key):
        return f"https://fake-s3.invalid/{key}?sig=x"

    def presign_get(self, key, ttl_s=300):
        return f"https://fake-s3.invalid/{key}?get=1"

    def get_bytes(self, key):
        from app import storage
        if key not in self.objects:
            raise storage.NotFound(key)
        return self.objects[key]
