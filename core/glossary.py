"""Loads tooltip text from config/glossary_<lang>.yaml."""
from __future__ import annotations

import functools

import yaml

from config.settings import CONFIG_DIR


@functools.lru_cache(maxsize=4)
def load_glossary(lang: str = "en") -> dict:
    path = CONFIG_DIR / f"glossary_{lang}.yaml"
    if not path.exists():
        path = CONFIG_DIR / "glossary_en.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def term(key: str, lang: str = "en") -> dict:
    """Entry for one metric, falling back to English if missing in the chosen language."""
    return load_glossary(lang).get(key) or load_glossary("en").get(key) or {}


def ui(key: str, lang: str = "en") -> str:
    return (load_glossary(lang).get("_ui") or {}).get(key) or load_glossary("en")["_ui"].get(key, key)


def tooltip(key: str, lang: str = "en") -> str:
    """Markdown tooltip: what / how / good-or-bad."""
    t = term(key, lang)
    if not t:
        return ""
    return (f"**{ui('what', lang)}:** {t.get('what', '')}\n\n"
            f"**{ui('how', lang)}:** {t.get('how', '')}\n\n"
            f"**{ui('good_bad', lang)}:** {t.get('good_bad', '')}")


def label(key: str, lang: str = "en") -> str:
    return term(key, lang).get("label", key)
