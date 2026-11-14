"""Tiny in-memory stand-ins for MongoDB and S3 so endpoint tests need no network."""
import copy


class FakeCollection:
    def __init__(self, docs=()):
        self.docs = [dict(d) for d in docs]

    def _match(self, doc, query):
        return all(doc.get(k) == v for k, v in (query or {}).items())

    def find_one(self, query=None, projection=None):
        return next((copy.deepcopy(d) for d in self.docs if self._match(d, query)), None)

    def find(self, query=None, projection=None):
        return [copy.deepcopy(d) for d in self.docs if self._match(d, query)]

    def insert_one(self, doc):
        self.docs.append(copy.deepcopy(doc))

    def insert_many(self, docs):
        for d in docs:
            self.insert_one(d)

    def delete_many(self, query):
        self.docs = [d for d in self.docs if not self._match(d, query)]

    def update_one(self, query, update):
        for d in self.docs:
            if self._match(d, query):
                d.update(copy.deepcopy(update["$set"]))
                return

    def find_one_and_update(self, query, update):
        for d in self.docs:
            if self._match(d, query):
                before = copy.deepcopy(d)
                d.update(copy.deepcopy(update["$set"]))
                return before
        return None

    def create_index(self, *a, **kw):
        pass


class FakeDB(dict):
    def __missing__(self, name):
        self[name] = FakeCollection()
        return self[name]

    __getattr__ = dict.__getitem__


class FakeS3:
    """Replaces app.storage: uploads are a dict of key -> bytes."""
    def __init__(self):
        self.objects = {}

    def presign_put(self, key):
        return f"https://fake-s3.invalid/{key}?sig=x"

    def get_bytes(self, key):
        from app import storage
        if key not in self.objects:
            raise storage.NotFound(key)
        return self.objects[key]
