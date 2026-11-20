"""Shared UI helpers: formatting, license badges, metric cards, disclaimer."""
from __future__ import annotations

import html
import math
from typing import Any, Callable, Optional

import streamlit as st

from core.glossary import label as g_label
from core.glossary import tooltip, ui
from core.models import DataPoint, LicenseTag

SAFE_MODE_TEXT = "Requires a licensed data provider"

BADGES = {
    LicenseTag.COMMERCIAL_OK: ("Licensed-safe", "green", "lic"),
    LicenseTag.CALCULATED_SAFE: ("Calculated", "blue", "calc"),
    LicenseTag.DEMO_ONLY: ("Demo data", "orange", "demo"),
}

CSS = """
<style>
.lb {display:inline-block;padding:1px 7px;border-radius:9px;font-size:0.72rem;font-weight:600;
     line-height:1.5;vertical-align:middle;white-space:nowrap;cursor:help}
.lb.lic  {background:rgba(33,150,83,.15); color:#1e8e4e}
.lb.calc {background:rgba(41,121,255,.15); color:#2f6fd6}
.lb.demo {background:rgba(245,124,0,.17); color:#c96500}
.dot {display:inline-block;width:7px;height:7px;border-radius:50%;margin-left:4px;vertical-align:middle;cursor:help}
.dot.lic{background:#21a35b}.dot.calc{background:#2f6fd6}.dot.demo{background:#f08a00}.dot.na{background:#999}
.pill {display:inline-block;padding:3px 11px;margin:2px 4px 2px 0;border-radius:14px;font-size:0.8rem;
       border:1px dashed rgba(128,128,128,.6);color:rgba(128,128,128,1);cursor:help}
.pill.strong  {border:1px solid #0ca30c;background:rgba(12,163,12,.14);color:#0a7d0a}
.pill.neutral {border:1px solid #d89a00;background:rgba(250,178,25,.18);color:#8a6200}
.pill.weak    {border:1px solid #d03b3b;background:rgba(208,59,59,.13);color:#b02f2f}
.rangebar {position:relative;height:8px;border-radius:4px;margin:10px 2px 4px;
           background:linear-gradient(90deg, rgba(214,69,65,.55), rgba(128,128,128,.35), rgba(33,150,83,.55))}
.rangebar .mark {position:absolute;top:-5px;width:4px;height:18px;border-radius:2px;background:currentColor;transform:translateX(-2px)}
.rangelabels {display:flex;justify-content:space-between;font-size:0.78rem;opacity:.8}
.subtle {font-size:0.85rem;opacity:.85}
.ptable {width:100%;border-collapse:collapse;font-size:0.92rem}
.ptable td {padding:7px 6px;border-bottom:1px solid rgba(128,128,128,.2);vertical-align:top}
.ptable td.k {width:32%;opacity:.8}
.ptable td.s {width:1%;white-space:nowrap;text-align:right}
.na {opacity:.7;font-style:italic}
</style>
"""


def inject_css() -> None:
    st.html(CSS)


# ---------- formatting ----------
def _num(v: Any) -> Optional[float]:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def fmt_money(v: Any, decimals: int = 2) -> str:
    f = _num(v)
    return "N/A" if f is None else f"${f:,.{decimals}f}"


def fmt_big_money(v: Any) -> str:
    f = _num(v)
    if f is None:
        return "N/A"
    for div, suf in ((1e12, "T"), (1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(f) >= div:
            return f"${f / div:,.2f}{suf}"
    return f"${f:,.0f}"


def fmt_int(v: Any) -> str:
    f = _num(v)
    return "N/A" if f is None else f"{f:,.0f}"


def fmt_pct(v: Any, decimals: int = 2, signed: bool = True) -> str:
    f = _num(v)
    if f is None:
        return "N/A"
    return f"{f * 100:+.{decimals}f}%" if signed else f"{f * 100:.{decimals}f}%"


# ---------- license / source ----------
def safe_mode() -> bool:
    return bool(st.session_state.get("safe_mode", False))


def lang() -> str:
    return st.session_state.get("lang", "en")


def hidden_by_safe_mode(dp: DataPoint) -> bool:
    return safe_mode() and dp.license_tag == LicenseTag.DEMO_ONLY


def source_text(dp: DataPoint) -> str:
    if not dp.available:
        return f"Not available: {dp.na_reason or 'no data'}"
    label = BADGES.get(dp.license_tag, ("", "", ""))[0]
    parts = [f"Source: {dp.source.value if dp.source else '?'}", f"License: {label} ({dp.license_tag.value})"]
    if dp.derived:
        parts.append("Derived (calculated by us)")
    if dp.as_of:
        parts.append(f"As of {str(dp.as_of)[:10]}")
    if dp.note:
        parts.append(dp.note)
    return " · ".join(parts)


def badge_html(dp: DataPoint, show_source: bool = True) -> str:
    """Small colored license badge with the source; hover shows details."""
    if not dp.available or dp.license_tag is None:
        return ""
    label, _, css = BADGES[dp.license_tag]
    text = f"{label} · {dp.source.value}" if (show_source and dp.source) else label
    return f'<span class="lb {css}" title="{html.escape(source_text(dp))}">{html.escape(text)}</span>'


def dot_html(dp: DataPoint) -> str:
    if hidden_by_safe_mode(dp):
        return f'<span class="dot na" title="{SAFE_MODE_TEXT}"></span>'
    css = BADGES[dp.license_tag][2] if dp.available and dp.license_tag else "na"
    return f'<span class="dot {css}" title="{html.escape(source_text(dp))}"></span>'


def badge(dp: DataPoint) -> None:
    """Native Streamlit badge under a metric."""
    if dp.available and dp.license_tag and not hidden_by_safe_mode(dp):
        label, color, _ = BADGES[dp.license_tag]
        src = dp.source.value if dp.source else ""
        st.badge(f"{label} · {src}", color=color, help=source_text(dp))


def text_value(dp: DataPoint, fmt: Callable[[Any], str] = str) -> str:
    """Escaped HTML for an inline value, handling N/A and safe mode."""
    if hidden_by_safe_mode(dp):
        return f'<span class="na">{SAFE_MODE_TEXT}</span>'
    if not dp.available:
        return f'<span class="na">N/A ({html.escape(dp.na_reason or "no data")})</span>'
    return html.escape(fmt(dp.value))


def metric(key: str, dp: DataPoint, fmt: Callable[[Any], str] = str,
           delta: Optional[str] = None, delta_color: str = "normal") -> None:
    """Metric card: label with tooltip, value (or N/A + reason), license badge."""
    label = g_label(key, lang())
    help_text = tooltip(key, lang()) or None
    if hidden_by_safe_mode(dp):
        st.metric(label, "—", help=help_text)
        st.caption(SAFE_MODE_TEXT)
        return
    if not dp.available:
        st.metric(label, "N/A", help=help_text)
        st.caption(dp.na_reason or "Data source unavailable")
        return
    st.metric(label, fmt(dp.value), delta=delta, delta_color=delta_color, help=help_text)
    badge(dp)


def fmt_unit(v: Any, unit: str) -> str:
    """Format by unit: x (multiple), ratio (%), USD (big money), USD/shares ($x.xx)."""
    f = _num(v)
    if f is None:
        return "N/A"
    if unit == "x":
        return f"{f:,.2f}x" if abs(f) < 100 else f"{f:,.0f}x"
    if unit == "ratio":
        return f"{f * 100:,.1f}%"
    if unit == "USD":
        return ("-" if f < 0 else "") + fmt_big_money(abs(f))
    if unit == "USD/shares":
        return fmt_money(f)
    return f"{f:,.2f}"


def metric_dp(label: str, dp: DataPoint, unit: str, help_key: Optional[str] = None,
              sub: Optional[str] = None) -> None:
    """Metric card for a calculated DataPoint: value or N/A + reason, comparison line, badge."""
    help_text = tooltip(help_key, lang()) if help_key else None
    if dp.note and help_text:
        help_text += f"\n\n**This value:** {dp.note}"
    if hidden_by_safe_mode(dp):
        st.metric(label, "—", help=help_text)
        st.caption(SAFE_MODE_TEXT)
        return
    if not dp.available:
        st.metric(label, "N/A", help=help_text)
        st.caption(dp.na_reason or "Not available")
        return
    st.metric(label, fmt_unit(dp.value, unit), help=help_text)
    if sub:
        st.caption(sub)
    badge(dp)


def disclaimer() -> None:
    st.divider()
    st.caption("⚠️ " + ui("disclaimer", lang()))
