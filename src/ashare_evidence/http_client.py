from __future__ import annotations

import ssl
from functools import lru_cache
from typing import Any
from urllib import request


@lru_cache(maxsize=1)
def _ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def urlopen(target: Any, *, timeout: int, disable_proxies: bool = False):
    handlers: list[Any] = [request.HTTPSHandler(context=_ssl_context())]
    if disable_proxies:
        handlers.insert(0, request.ProxyHandler({}))
    opener = request.build_opener(*handlers)
    return opener.open(target, timeout=timeout)
