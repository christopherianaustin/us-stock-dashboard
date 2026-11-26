"""Output schema of one AI summary (SPEC 15.5).

The model's answer is forced into this shape with structured outputs. The word and item limits are checked by
validator.py (structured outputs guarantee the shape, not the lengths).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Signal = Literal["Strong", "Neutral", "Weak", "Not enough data", "Not applicable"]
SIGNALS: tuple[str, ...] = ("Strong", "Neutral", "Weak", "Not enough data", "Not applicable")

# Limits from SPEC 15.5 / 15.6.1, used by the validator
LIMITS = {
    "headline_words": 12,
    "takeaway_words": 45,
    "takeaway_sentences": 2,
    "point_words": 25,
    "points": 3,
    "what_to_watch_next": 2,
}


class Point(BaseModel):
    text: str = Field(description="At most 25 words, with at least one number and its context.")
    metric_keys: list[str] = Field(description="Keys from the input data used in this point.")


class TabSummary(BaseModel):
    signal: Signal
    headline: str = Field(description="The key takeaway in at most 12 words.")
    takeaway: str = Field(description="1 to 2 sentences, at most 45 words.")
    positives: list[Point] = Field(description="0 to 3 points.")
    watch_outs: list[Point] = Field(description="0 to 3 points.")
    what_to_watch_next: list[str] = Field(description="0 to 2 upcoming events or trends, with dates or levels.")
    ask_yourself: str = Field(description="One short question.")
    data_gaps: list[str] = Field(description="Missing or unreliable data that limits this summary.")
