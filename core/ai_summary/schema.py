"""Output schema of one AI summary (SPEC 16.3, replaces 15.5).

The card shows two lists only: bullish points (facts that support a positive view) and bearish points (facts that
support a negative view, or risks). The answer is forced into this shape with structured outputs; the word and item
limits are checked by validator.py (structured outputs guarantee the shape, not the lengths).
"""
from __future__ import annotations

from pydantic import BaseModel, Field

# Limits from SPEC 16.3 / 16.6, used by the validator
LIMITS = {
    "points": 4,            # per list
    "title_words_min": 2,
    "title_words_max": 6,
    "detail_words": 25,
    "data_gaps": 3,
}


class Point(BaseModel):
    title: str = Field(description='2 to 6 plain words that name the point, e.g. "Profit margins above peers".')
    detail: str = Field(description="One sentence, at most 25 words, with at least one number and its context.")
    metric_keys: list[str] = Field(description="Keys from the input data used in this point.")


class TabSummary(BaseModel):
    bullish: list[Point] = Field(description="0 to 4 facts that support a positive view, most important first.")
    bearish: list[Point] = Field(description="0 to 4 facts that support a negative view or are risks, most important first.")
    data_gaps: list[str] = Field(description="0 to 3 notes on missing or unreliable data that limits this summary.")
