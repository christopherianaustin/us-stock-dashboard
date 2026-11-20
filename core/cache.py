"""Disk cache shared by all providers (survives app restarts).

Each cached value is tagged with the ticker it belongs to, so the
"Refresh data" button can clear only that ticker.
"""
from __future__ import annotations

import functools
import hashlib
import pickle
from typing import Any, Callable

import diskcache

from config.settings import CACHE_DIR, settings
from core.logging_setup import get_logger

log = get_logger("cache")
_cache = diskcache.Cache(str(CACHE_DIR), tag_index=True)

_MISSING = object()


def _make_key(namespace: str, args: tuple, kwargs: dict) -> str:
    raw = pickle.dumps((args, sorted(kwargs.items())))
    return f"{namespace}:{hashlib.sha1(raw).hexdigest()}"


def cached(namespace: str, ttl_key: str, tag_arg: int | None = 0, method: bool = False):
    """Decorator: cache a function's result on disk.

    namespace: unique name for the function.
    ttl_key:   key in settings.cache_ttl (e.g. "quote").
    tag_arg:   index of the positional argument holding the ticker (used for
               per-ticker refresh). None = not ticker specific.
    method:    True when decorating a class method; `self` is then ignored
               (not part of the key, not counted in tag_arg).

    `None` results are NOT cached, so a temporary failure is retried next time.
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            key_args = args[1:] if method else args
            key = _make_key(namespace, key_args, kwargs)
            value = _cache.get(key, default=_MISSING)
            if value is not _MISSING:
                return value
            value = func(*args, **kwargs)
            if value is not None:
                tag = None
                if tag_arg is not None and len(key_args) > tag_arg:
                    tag = str(key_args[tag_arg]).upper()
                _cache.set(key, value, expire=settings.cache_ttl[ttl_key], tag=tag)
            return value

        return wrapper

    return decorator


def clear_ticker(symbol: str, extra_tags: tuple[str, ...] = ()) -> int:
    """Remove every cached item tagged with this ticker (all spellings, e.g.
    BRK.B and BRK-B) plus any extra tags (e.g. the SEC CIK). Returns count removed."""
    removed = 0
    s = symbol.upper()
    for tag in {s, s.replace(".", "-"), s.replace("-", "."), *[str(t).upper() for t in extra_tags]}:
        removed += _cache.evict(tag)
    log.info("Cleared %s cached items for %s", removed, symbol)
    return removed


def clear_all() -> None:
    _cache.clear()


def get_raw(key: str, default: Any = None) -> Any:
    return _cache.get(key, default=default)


def set_raw(key: str, value: Any, ttl_key: str, tag: str | None = None) -> None:
    _cache.set(key, value, expire=settings.cache_ttl[ttl_key], tag=tag)
