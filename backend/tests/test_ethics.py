import requests

from app.ethics import PoliteSession, RobotsDisallowed, RobotsGuard
from tests.conftest import FakeResp

ROBOTS = "User-agent: *\nDisallow: /private/\nCrawl-delay: 2\n"


def guard(status=200, text=ROBOTS, exc=None):
    def get(url, **kw):
        if exc:
            raise exc
        return FakeResp(text=text, status=status)
    return RobotsGuard(http_get=get)


def test_robots_disallows_private_path():
    g = guard()
    assert g.allowed("http://shop/") is True
    assert g.allowed("http://shop/private/prices") is False
    assert g.crawl_delay("http://shop/") == 2.0


def test_missing_robots_means_allowed():
    g = guard(status=404, text="")
    assert g.allowed("http://shop/anything") is True and g.crawl_delay("http://shop/") is None


def test_robots_server_error_or_unreachable_blocks_conservatively():
    assert guard(status=503, text="").allowed("http://shop/") is False
    assert guard(exc=requests.ConnectionError()).allowed("http://shop/") is False


def test_robots_cached_per_origin():
    calls = []
    g = RobotsGuard(http_get=lambda url, **kw: calls.append(url) or FakeResp(text=ROBOTS))
    g.allowed("http://shop/a"); g.allowed("http://shop/b"); g.allowed("http://other/a")
    assert calls == ["http://shop/robots.txt", "http://other/robots.txt"]


class Clock:
    def __init__(self):
        self.t, self.slept = 100.0, []

    def now(self):
        return self.t

    def sleep(self, s):
        self.slept.append(round(s, 2)); self.t += s


class Sess:
    def __init__(self, responses):
        self.responses, self.n = list(responses), 0

    def get(self, url, **kw):
        self.n += 1
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def polite(sess, clock, **kw):
    return PoliteSession(session=sess, sleep=clock.sleep, clock=clock.now, guard=guard(), min_interval=1.0, **kw)


def test_rate_limit_uses_crawl_delay_between_requests_to_same_host():
    clock = Clock()
    p = polite(Sess([FakeResp(), FakeResp(), FakeResp()]), clock)
    p.get("http://shop/a"); p.get("http://shop/b"); p.get("http://shop/c")
    assert clock.slept == [2.0, 2.0]            # robots Crawl-delay 2 > min_interval 1


def test_disallowed_url_is_never_requested():
    clock, sess = Clock(), Sess([FakeResp()])
    p = polite(sess, clock)
    try:
        p.get("http://shop/private/prices")
        assert False, "RobotsDisallowed gözlənilirdi"
    except RobotsDisallowed:
        pass
    assert sess.n == 0


def test_retries_server_errors_then_succeeds():
    clock = Clock()
    sess = Sess([FakeResp(status=503), requests.ConnectionError("x"), FakeResp(text="ok")])
    r = polite(sess, clock, retries=2).get("http://shop/a")
    assert r.text == "ok" and sess.n == 3


def test_gives_up_after_retries():
    clock = Clock()
    p = polite(Sess([requests.Timeout(), requests.Timeout()]), clock, retries=1)
    try:
        p.get("http://shop/a")
        assert False
    except requests.Timeout:
        pass


def test_utf8_forced_when_charset_missing():
    clock = Clock()
    resp = FakeResp(text="£", headers={"content-type": "text/html"})
    resp.encoding = "ISO-8859-1"
    r = polite(Sess([resp]), clock).get("http://shop/a")
    assert r.encoding == "utf-8"
