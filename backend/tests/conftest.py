import os

import pytest

# Testlər AYRI bazada işləyir ki, real məlumata toxunmasın
_base = os.environ["DATABASE_URL"]
_admin = _base.rsplit("/", 1)[0] + "/postgres"
TEST_URL = _base.rsplit("/", 1)[0] + "/qiymetradar_test"


def _ensure_test_db() -> None:
    import psycopg
    with psycopg.connect(_admin, autocommit=True) as c:
        if not c.execute("SELECT 1 FROM pg_database WHERE datname='qiymetradar_test'").fetchone():
            c.execute("CREATE DATABASE qiymetradar_test")


@pytest.fixture(scope="session", autouse=True)
def _test_db():
    _ensure_test_db()
    os.environ["DATABASE_URL"] = TEST_URL
    from app import db
    db.migrate()
    yield


@pytest.fixture
def clean_db():
    from app import db
    db.reset_all()
    yield db
    db.reset_all()


class FakeResp:
    def __init__(self, text="", status=200, url="http://x/", headers=None, content=b"", json_data=None):
        self.text, self.status_code, self.url, self.content = text, status, url, content
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self.encoding = "utf-8"
        self._json = json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(str(self.status_code))

    def json(self):
        return self._json


class FakeSession:
    """PoliteSession əvəzi: URL -> HTML lüğətindən cavab verir."""

    def __init__(self, pages):
        self.pages, self.calls = pages, []

    def get(self, url, **kw):
        self.calls.append(url)
        if url not in self.pages:
            return FakeResp(status=404, url=url)
        v = self.pages[url]
        return v if isinstance(v, FakeResp) else FakeResp(text=v, url=url)
