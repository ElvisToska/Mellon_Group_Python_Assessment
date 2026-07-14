import db.cache as cache


class BrokenRedis:
    def get(self, key):
        raise RuntimeError("redis is down")

    def set(self, key, value, ex=None):
        raise RuntimeError("redis is down")

    def flushdb(self):
        raise RuntimeError("redis is down")


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.flushed = False

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ex=None):
        self.values[key] = value
        self.last_ttl = ex

    def flushdb(self):
        self.flushed = True


def test_cache_get_returns_none_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "redis_client", BrokenRedis())

    assert cache.cache_get("terminals:list") is None


def test_cache_set_does_not_raise_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "redis_client", BrokenRedis())

    cache.cache_set("terminals:list", [{"tid": "T0101001"}], ttl=30)


def test_cache_clear_all_does_not_raise_when_redis_is_unavailable(monkeypatch):
    monkeypatch.setattr(cache, "redis_client", BrokenRedis())

    cache.cache_clear_all()


def test_cache_set_and_get_json_round_trip(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake_redis)

    payload = [{"tid": "T0101001", "enabled": True}]
    cache.cache_set("terminals:list", payload, ttl=30)

    assert cache.cache_get("terminals:list") == payload
    assert fake_redis.last_ttl == 30


def test_cache_clear_all_calls_flushdb(monkeypatch):
    fake_redis = FakeRedis()
    monkeypatch.setattr(cache, "redis_client", fake_redis)

    cache.cache_clear_all()

    assert fake_redis.flushed is True
