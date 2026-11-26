"""Calls Claude for one tab summary (SPEC 15.3).

- Official Anthropic SDK, structured outputs: `client.beta.messages.parse(output_format=TabSummary)`.
- The system prompt is the same on every call, so it is marked for prompt caching.
- Refusals: the server-side fallback is on (beta server-side-fallback-2026-07-01, fallbacks="default"); if the final
  answer is still a refusal, AIRefused is raised and the caller shows the rule-based fallback.
- Model and effort come from settings (AI_MODEL, AI_EFFORT), so cheaper or faster options can be tested later.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Optional

import anthropic
import yaml

from config.settings import Settings, settings as default_settings
from core.ai_summary.input_builder import display_format
from core.ai_summary.schema import TabSummary

PROMPTS = Path(__file__).parent / "prompts"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models that accept the server-side `fallbacks` parameter (others are called without it).
FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-sonnet-5-5", "claude-fable-5-2", "claude-fable-5-1"}

# US$ per million tokens: (input, output, cache write 5 min, cache read). Check the pricing page before relying on it.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 0.20),
    "claude-opus-5": (5.00, 25.00, 6.25, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 0.20),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.01),
    "claude-fable-5-2": (8.00, 40.00, 10.00, 0.20),
    "claude-opus-4-8": (5.00, 25.00, 6.25, 0.50),
}


class AIError(Exception):
    """The call failed (network, API error, or no usable answer)."""


class AIRefused(AIError):
    """The model (and its fallback) declined."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0

    @property
    def total(self) -> int:
        return self.input_tokens + self.output_tokens + self.cache_write_tokens + self.cache_read_tokens

    def add(self, o: "Usage") -> "Usage":
        return Usage(self.input_tokens + o.input_tokens, self.output_tokens + o.output_tokens,
                     self.cache_write_tokens + o.cache_write_tokens, self.cache_read_tokens + o.cache_read_tokens)

    def to_dict(self) -> dict:
        return {"input": self.input_tokens, "output": self.output_tokens, "cache_write": self.cache_write_tokens,
                "cache_read": self.cache_read_tokens, "total": self.total}


def cost_usd(u: Usage, model: str) -> Optional[float]:
    p = PRICES.get(model)
    if not p:
        return None
    return round((u.input_tokens * p[0] + u.output_tokens * p[1] + u.cache_write_tokens * p[2]
                  + u.cache_read_tokens * p[3]) / 1e6, 6)


@dataclass
class CallResult:
    summary: TabSummary
    usage: Usage
    model: str                # the model that actually answered (may be a fallback model)
    fell_back: bool
    request_id: Optional[str]


# =========================================================================== prompts
@lru_cache(maxsize=1)
def system_prompt() -> str:
    return (PROMPTS / "system.md").read_text(encoding="utf-8")


@lru_cache(maxsize=1)
def tab_focus() -> dict:
    with open(PROMPTS / "tab_focus.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def without_license_tags(x):
    """License tags stay in our code (cards, coverage report, safe mode) but are not sent to the model: it was
    skipping demo-tagged facts and listing "demo data" in data_gaps, which means nothing to app users."""
    if isinstance(x, dict):
        return {k: without_license_tags(v) for k, v in x.items() if k not in ("license_tag", "license")}
    if isinstance(x, list):
        return [without_license_tags(v) for v in x]
    return x


def user_message(tab: str, lang: str, currency: str, payload: dict,
                 today: Optional[date] = None, retry_note: Optional[str] = None) -> str:
    """The user message template from SPEC 15.6.2, without the rule_based_signal line (SPEC 16.4)."""
    tf = tab_focus()[tab]
    fmt = display_format(lang, currency)
    data = json.dumps(without_license_tags(payload), ensure_ascii=False, separators=(",", ":"))
    msg = (
        "<request>\n"
        f"tab: {tf['name']}\n"
        f"tab_focus: {tf['focus']}\n"
        f"language: {lang}\n"
        f'display_format: {{currency: "{fmt["currency"]}", example: "{fmt["example"]}", '
        f'percent example: "{fmt["percent example"]}"}}\n'
        f"today: {(today or date.today()).isoformat()}\n"
        "</request>\n\n"
        f"<stock_data>\n{data}\n</stock_data>\n\n"
        "Write the summary for this tab."
    )
    if retry_note:
        msg += f"\n\nYour previous answer failed these checks. Fix them and keep everything else accurate:\n{retry_note}"
    return msg


# =========================================================================== API call
class AIClient:
    def __init__(self, cfg: Optional[Settings] = None, sdk: Optional[anthropic.Anthropic] = None):
        self.cfg = cfg or default_settings
        # the key comes from settings (.env or Streamlit secrets); never hardcoded
        self.sdk = sdk or anthropic.Anthropic(api_key=self.cfg.anthropic_api_key or None, timeout=90.0, max_retries=2)

    def summarize(self, user: str) -> CallResult:
        model = self.cfg.ai_model
        kwargs: dict = dict(
            model=model,
            max_tokens=16000,
            system=[{"type": "text", "text": system_prompt(), "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": user}],
            output_format=TabSummary,
            output_config={"effort": self.cfg.ai_effort},
        )
        if model in FALLBACK_MODELS:
            kwargs.update(betas=[FALLBACK_BETA], fallbacks="default")
        try:
            resp = self.sdk.beta.messages.parse(**kwargs)
        except anthropic.APIConnectionError as e:
            raise AIError(f"network error: {e}") from e
        except anthropic.APIStatusError as e:
            raise AIError(f"API error {e.status_code}: {e.message}") from e

        u = resp.usage
        usage = Usage(u.input_tokens or 0, u.output_tokens or 0,
                      getattr(u, "cache_creation_input_tokens", 0) or 0, getattr(u, "cache_read_input_tokens", 0) or 0)
        fell_back = any(getattr(it, "type", "") == "fallback_message" for it in (getattr(u, "iterations", None) or []))
        if resp.stop_reason == "refusal":
            cat = getattr(getattr(resp, "stop_details", None), "category", None)
            raise AIRefused(f"refused (category: {cat})")
        if resp.stop_reason == "max_tokens":
            raise AIError("answer was cut off (max_tokens)")
        parsed = resp.parsed_output
        if parsed is None:
            raise AIError(f"no structured answer (stop_reason={resp.stop_reason})")
        return CallResult(parsed, usage, resp.model, fell_back, getattr(resp, "_request_id", None))
