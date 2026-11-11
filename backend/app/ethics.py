"""Scraping etikası (dərs, bölmə 11): robots.txt-ə hörmət, sürət limiti, timeout, düzgün User-Agent.

- robots.txt 200: qaydalara əməl et. 4xx (yoxdur): məhdudiyyət yoxdur. 5xx və ya əlçatmazdır: ehtiyatla BLOKLA.
- Hər host üçün sorğular arasında minimum fasilə (default 1 san, robots.txt-də Crawl-delay varsa o).
- User-Agent özünü təqdim edir (gizlənmir). Qadağan olunmuş səhifələrə girilmir.
"""

import time
from urllib import robotparser
from urllib.parse import urlparse

import requests

USER_AGENT = "QiymetRadarBot/1.0 (ev layihesi; reqib qiymet izleme)"


class RobotsDisallowed(Exception):
    """robots.txt bu ünvanı scrape etməyi qadağan edir."""


class RobotsGuard:
    def __init__(self, user_agent: str = USER_AGENT, timeout: float = 5.0, http_get=None):
        self.ua = user_agent
        self.timeout = timeout
        self._get = http_get or (lambda url, **kw: requests.get(url, **kw))
        self._cache: dict = {}

    def _parser(self, url: str):
        p = urlparse(url)
        origin = f"{p.scheme}://{p.netloc}"
        if origin in self._cache:
            return self._cache[origin]
        try:
            r = self._get(origin + "/robots.txt", timeout=self.timeout, headers={"User-Agent": self.ua})
            if r.status_code == 200:
                rp = robotparser.RobotFileParser()
                rp.parse(r.text.splitlines())
            elif 400 <= r.status_code < 500:
                rp = None                                    # robots.txt yoxdur: qadağa qoyulmayıb
            else:
                rp = False                                   # 5xx: ehtiyatla hamısını blokla
        except requests.RequestException:
            rp = False                                       # əlçatmaz: ehtiyatla blokla
        self._cache[origin] = rp
        return rp

    def allowed(self, url: str) -> bool:
        rp = self._parser(url)
        if rp is None:
            return True
        if rp is False:
            return False
        return rp.can_fetch(self.ua, url)

    def crawl_delay(self, url: str):
        rp = self._parser(url)
        if rp is None or rp is False:
            return None
        d = rp.crawl_delay(self.ua)
        return float(d) if d is not None else None


class PoliteSession:
    """requests üzərində: robots yoxlaması + sürət limiti + timeout + kiçik retry. Testdə sleep/clock əvəz olunur."""

    def __init__(self, user_agent: str = USER_AGENT, min_interval: float = 1.0, timeout: float = 10.0,
                 check_robots: bool = True, retries: int = 2, session=None, sleep=time.sleep, clock=time.monotonic,
                 guard=None):
        self.ua, self.min_interval, self.timeout = user_agent, min_interval, timeout
        self.check_robots, self.retries = check_robots, retries
        self.session = session or requests.Session()
        self.sleep, self.clock = sleep, clock
        self.guard = guard or RobotsGuard(user_agent)
        self._last: dict = {}
        self.requests_made = 0

    def _wait(self, url: str) -> None:
        host = urlparse(url).netloc
        gap = self.min_interval
        if self.check_robots:
            gap = max(gap, self.guard.crawl_delay(url) or 0)
        if host in self._last:
            remaining = gap - (self.clock() - self._last[host])
            if remaining > 0:
                self.sleep(remaining)
        self._last[host] = self.clock()

    def get(self, url: str, **kw) -> requests.Response:
        if self.check_robots and not self.guard.allowed(url):
            raise RobotsDisallowed(f"robots.txt qadağan edir: {url}")
        headers = {"User-Agent": self.ua, **kw.pop("headers", {})}
        timeout = kw.pop("timeout", self.timeout)
        last_exc = None
        for attempt in range(self.retries + 1):
            self._wait(url)
            self.requests_made += 1
            try:
                r = self.session.get(url, headers=headers, timeout=timeout, **kw)
                if r.status_code >= 500 and attempt < self.retries:
                    last_exc = requests.HTTPError(f"{r.status_code} {url}")
                    self.sleep(0.5 * (attempt + 1))
                    continue
                ctype = r.headers.get("content-type", "").lower()
                if "charset" not in ctype and ("text" in ctype or "html" in ctype):
                    r.encoding = "utf-8"                     # requests ISO-8859-1 təxmin edir: '£' -> 'Â£'
                return r
            except requests.RequestException as e:
                last_exc = e
                if attempt < self.retries:
                    self.sleep(0.5 * (attempt + 1))
        raise last_exc or RuntimeError("naməlum şəbəkə xətası")
