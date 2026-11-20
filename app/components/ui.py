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
.pill {display:inline-flex;align-items:center;gap:6px;padding:4px 12px;margin:0 8px 8px 0;border-radius:999px;
       font-size:0.875rem;line-height:1.25rem;font-weight:500;background:#F5F5F7;color:#6E6E73;cursor:help}
.pill .pill-score {font-variant-numeric:tabular-nums;opacity:.75}
.pill.strong  {background:#E6F4EA;color:#0A6B12}
.pill.neutral {background:#FFF3DC;color:#8A5300}
.pill.weak    {background:#FCE8E6;color:#A8261E}
.rangebar {position:relative;height:6px;border-radius:3px;margin:12px 0 8px;background:#E5E5EA}
.rangebar .mark {position:absolute;top:-5px;width:16px;height:16px;border-radius:50%;background:#1D1D1F;
                 border:3px solid #FFFFFF;box-shadow:0 0 0 1px #D2D2D7;transform:translateX(-8px)}
.rangelabels {display:flex;justify-content:space-between;font-size:0.75rem;line-height:1rem;color:#6E6E73;
              font-variant-numeric:tabular-nums}
.subtle {font-size:0.875rem;line-height:1.25rem;color:#6E6E73}
.ptable {width:100%;border-collapse:collapse;font-size:0.9375rem}
.ptable td {padding:12px 8px;border-bottom:1px solid #E5E5EA;vertical-align:top}
.ptable td.k {width:32%;color:#6E6E73}
.ptable td.s {width:1%;white-space:nowrap;text-align:right}
.na {color:#86868B}

/* ---------- layout & type ---------- */
[data-testid="stMainBlockContainer"] {max-width:1200px;padding-top:2rem}
h1, h2, h3 {letter-spacing:-0.02em; text-wrap:balance}
p, li {text-wrap:pretty}
[data-testid="stMetricValue"] {font-variant-numeric:tabular-nums;letter-spacing:-0.01em}

/* ---------- tabs: quiet text tabs with a blue underline ---------- */
[data-baseweb="tab-list"] {gap:4px;border-bottom:1px solid #E5E5EA}
[data-baseweb="tab"] {font-size:0.9375rem;font-weight:500;color:#6E6E73;padding:12px 12px}
[data-baseweb="tab"][aria-selected="true"] {color:#1D1D1F}

/* ---------- buttons: instant, physical feedback (Apple: respond on press) ---------- */
button, [data-baseweb="tab"] {transition:transform 150ms cubic-bezier(0.32,0.72,0,1), background-color 150ms ease,
                                     color 150ms ease}
button:active {transform:scale(0.97)}
button:focus-visible, a:focus-visible {outline:3px solid rgba(0,113,227,.45);outline-offset:2px}

/* ---------- hero (price header) ---------- */
.nv-hero {display:grid;grid-template-columns:minmax(0,1fr) auto;gap:24px 48px;align-items:end;margin:8px 0 24px}
.nv-id {display:flex;gap:16px;align-items:center}
.nv-logo {width:48px;height:48px;border-radius:12px;object-fit:contain;background:#FFFFFF;box-shadow:0 0 0 1px #E5E5EA}
.nv-logo.nv-initials {display:flex;align-items:center;justify-content:center;background:#F5F5F7;color:#6E6E73;
                      font-weight:600;font-size:1.125rem;box-shadow:none}
.nv-name {font-size:1.875rem;line-height:2.25rem;font-weight:600;letter-spacing:-0.02em;color:#1D1D1F;margin:0}
.nv-ticker {display:inline-block;margin-left:8px;padding:2px 8px;border-radius:8px;background:#F5F5F7;
            font-size:0.875rem;font-weight:500;color:#6E6E73;letter-spacing:0;vertical-align:middle}
.nv-meta {font-size:0.875rem;line-height:1.25rem;color:#6E6E73;margin-top:4px}
.nv-about {font-size:1rem;line-height:1.5rem;color:#424245;max-width:680px;margin-top:16px;text-wrap:pretty}
.nv-pricebox {text-align:right}
.nv-price {font-size:3rem;line-height:1;font-weight:600;letter-spacing:-0.03em;font-variant-numeric:tabular-nums;
           color:#1D1D1F}
.nv-change {display:inline-flex;gap:6px;align-items:center;margin-top:8px;padding:4px 12px;border-radius:999px;
            font-size:0.875rem;line-height:1.25rem;font-weight:600;font-variant-numeric:tabular-nums}
.nv-change.up {background:#E6F4EA;color:#0A6B12}
.nv-change.down {background:#FCE8E6;color:#A8261E}
.nv-change.flat {background:#F5F5F7;color:#6E6E73}
.nv-asof {font-size:0.75rem;line-height:1rem;color:#86868B;margin-top:8px}

.nv-stats {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 16px}
.nv-stat {background:#F5F5F7;border-radius:16px;padding:16px 20px}
.nv-stat-label {font-size:0.8125rem;line-height:1.25rem;color:#6E6E73;cursor:help}
.nv-stat-value {font-size:1.25rem;line-height:1.75rem;font-weight:600;color:#1D1D1F;font-variant-numeric:tabular-nums;
                margin-top:4px}
.nv-stat-sub {font-size:0.8125rem;line-height:1.25rem;color:#6E6E73;margin-top:2px}
.nv-pills {margin:8px 0 4px}
.nv-pills-label {font-size:0.8125rem;color:#6E6E73;margin:0 8px 8px 0;display:inline-block}
.nv-fresh {font-size:0.8125rem;line-height:1.25rem;color:#86868B;margin:4px 0 8px}
.nv-fresh a {color:#0066CC;text-decoration:none}

/* ---------- overview: short version + explained numbers ---------- */
.nv-section-title {font-size:1.5rem;line-height:2rem;font-weight:600;letter-spacing:-0.02em;color:#1D1D1F;margin:8px 0 4px}
.nv-section-sub {font-size:1rem;line-height:1.5rem;color:#6E6E73;margin:0 0 16px;max-width:680px}
.nv-two {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:32px}
.nv-card {background:#F5F5F7;border-radius:16px;padding:20px 24px}
.nv-card h4 {font-size:1rem;line-height:1.5rem;font-weight:600;margin:0 0 12px;color:#1D1D1F;letter-spacing:0}
.nv-list {list-style:none;margin:0;padding:0}
.nv-list li {position:relative;padding:0 0 12px 32px;font-size:0.9375rem;line-height:1.5rem;color:#1D1D1F}
.nv-list li:last-child {padding-bottom:0}
.nv-list li::before {position:absolute;left:0;top:2px;width:20px;height:20px;border-radius:50%;
                     display:flex;align-items:center;justify-content:center;font-size:0.75rem;font-weight:700}
.nv-list.good li::before {content:"\\2713";background:#E6F4EA;color:#0A6B12}
.nv-list.watch li::before {content:"!";background:#FFF3DC;color:#8A5300}
.nv-empty {font-size:0.9375rem;color:#6E6E73}

.nv-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;margin-bottom:8px}
.nv-num {background:#F5F5F7;border-radius:16px;padding:20px 24px;display:flex;flex-direction:column;gap:8px}
.nv-num-label {font-size:0.875rem;line-height:1.25rem;color:#6E6E73;cursor:help}
.nv-num-value {font-size:1.875rem;line-height:2.25rem;font-weight:600;letter-spacing:-0.02em;color:#1D1D1F;
               font-variant-numeric:tabular-nums}
.nv-num-text {font-size:0.875rem;line-height:1.25rem;color:#424245;text-wrap:pretty}
.nv-tone {align-self:flex-start;padding:2px 10px;border-radius:999px;font-size:0.8125rem;line-height:1.25rem;font-weight:600}
.nv-tone.good {background:#E6F4EA;color:#0A6B12}
.nv-tone.neutral {background:#E8E8ED;color:#424245}
.nv-tone.watch {background:#FFF3DC;color:#8A5300}
.nv-tone.na {background:transparent;color:#86868B;padding-left:0}
.nv-note {font-size:0.8125rem;line-height:1.25rem;color:#86868B;margin:8px 0 32px}

/* ---------- mobile ---------- */
@media (max-width: 640px) {
  [data-testid="stMainBlockContainer"] {padding-top:1rem}
  .nv-hero {grid-template-columns:1fr;gap:16px}
  .nv-pricebox {text-align:left}
  .nv-price {font-size:2.25rem}
  .nv-stats, .nv-two {grid-template-columns:1fr}
  .nv-name {font-size:1.5rem;line-height:2rem}
}
@media (prefers-reduced-motion: reduce) {
  * {transition:none !important}
  button:active {transform:none}
}
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


def attr(text: str) -> str:
    """Make text safe inside an HTML attribute (e.g. a hover tooltip) that goes through st.markdown.
    Line breaks become '&#10;': the tooltip still shows them, but Markdown never sees a blank line
    (a blank line would end the HTML block and print the rest of the HTML as text)."""
    return html.escape(str(text), quote=True).replace("\r", "").replace("\n", "&#10;")


def show_sources() -> bool:
    """Investors first: source/license badges are hidden unless 'Show data sources' is on.
    Safe mode always shows them, since its purpose is reviewing licenses."""
    return bool(st.session_state.get("show_sources", False)) or safe_mode()


def badge_html(dp: DataPoint, show_source: bool = True) -> str:
    """Small colored license badge with the source; hover shows details."""
    if not dp.available or dp.license_tag is None or not show_sources():
        return ""
    label, _, css = BADGES[dp.license_tag]
    text = f"{label} · {dp.source.value}" if (show_source and dp.source) else label
    return f'<span class="lb {css}" title="{html.escape(source_text(dp))}">{html.escape(text)}</span>'


def dot_html(dp: DataPoint) -> str:
    if not show_sources():
        return ""
    if hidden_by_safe_mode(dp):
        return f'<span class="dot na" title="{SAFE_MODE_TEXT}"></span>'
    css = BADGES[dp.license_tag][2] if dp.available and dp.license_tag else "na"
    return f'<span class="dot {css}" title="{html.escape(source_text(dp))}"></span>'


def badge(dp: DataPoint) -> None:
    """Native Streamlit badge under a metric (only when 'Show data sources' is on)."""
    if dp.available and dp.license_tag and not hidden_by_safe_mode(dp) and show_sources():
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
