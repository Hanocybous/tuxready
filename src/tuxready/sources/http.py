"""Tiny JSON-over-HTTP client with an on-disk cache, so repeat runs are fast and work offline."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from tuxready import __version__

USER_AGENT = f"tuxready/{__version__} (+https://github.com/Hanocybous/tuxready)"
DAY = 24 * 60 * 60
_MISSING = object()


def default_cache_dir() -> Path:
    if sys.platform == "win32" and os.environ.get("LOCALAPPDATA"):
        return Path(os.environ["LOCALAPPDATA"]) / "tuxready" / "cache"
    base = os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "tuxready"


class Http:
    def __init__(
        self,
        cache_dir: Path | None = None,
        offline: bool = False,
        refresh: bool = False,
        timeout: float = 15.0,
    ):
        self.cache_dir = cache_dir or default_cache_dir()
        self.offline = offline
        self.refresh = refresh
        self.timeout = timeout
        self.failures = 0
        self._lock = threading.Lock()

    def get_json(self, url: str, ttl: float = DAY):
        return self._fetch("GET", url, None, ttl)

    def post_json(self, url: str, body: dict, ttl: float = DAY):
        return self._fetch("POST", url, body, ttl)

    def _fetch(self, method: str, url: str, body: dict | None, ttl: float):
        """Return parsed JSON, or None if the resource is missing or unreachable."""
        payload = json.dumps(body, sort_keys=True).encode() if body is not None else None
        path = self._cache_path(method, url, payload)
        cached, age = self._read_cache(path)
        if cached is not _MISSING and (self.offline or (not self.refresh and age < ttl)):
            return cached
        if self.offline:
            return None

        request = urllib.request.Request(url, data=payload, method=method)
        request.add_header("User-Agent", USER_AGENT)
        request.add_header("Accept", "application/json")
        if payload is not None:
            request.add_header("Content-Type", "application/json")
        for attempt in range(2):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                self._write_cache(path, data)
                return data
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    self._write_cache(path, None)  # remember "not found"
                    return None
                if error.code < 500 and error.code != 429:
                    break
            except (urllib.error.URLError, TimeoutError, OSError, ValueError):
                pass
            if attempt == 0:
                time.sleep(1.0)
        with self._lock:
            self.failures += 1
        # Network trouble: a stale answer beats no answer.
        return None if cached is _MISSING else cached

    def _cache_path(self, method: str, url: str, payload: bytes | None) -> Path:
        digest = hashlib.sha256(method.encode() + url.encode() + (payload or b"")).hexdigest()
        return self.cache_dir / digest[:2] / f"{digest}.json"

    def _read_cache(self, path: Path):
        try:
            age = time.time() - path.stat().st_mtime
            return json.loads(path.read_text(encoding="utf-8"))["data"], age
        except (OSError, ValueError, KeyError):
            return _MISSING, float("inf")

    def _write_cache(self, path: Path, data) -> None:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(f".{threading.get_ident()}.tmp")
            tmp.write_text(json.dumps({"data": data}), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass  # caching is best-effort
