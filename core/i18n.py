"""Interface text lookup: t("tabs.summary", "id") -> "Ringkasan". Falls back to English, then the key."""
from __future__ import annotations

import functools

import yaml

from config.settings import CONFIG_DIR


@functools.lru_cache(maxsize=4)
def _load(lang: str) -> dict:
    path = CONFIG_DIR / f"ui_{lang}.yaml"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _get(d: dict, key: str):
    for part in key.split("."):
        if not isinstance(d, dict) or part not in d:
            return None
        d = d[part]
    return d


def t(key: str, lang: str = "en", **kwargs) -> str:
    text = _get(_load(lang), key) or _get(_load("en"), key) or key
    return text.format(**kwargs) if kwargs else text
