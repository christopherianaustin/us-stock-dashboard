"""Ownership, insider activity, Wall Street analysts' ratings and news helpers (pure functions).

Analyst ratings ("Buy", "Hold"...) are THIRD-PARTY opinions and must always be labeled
"Wall Street analysts' ratings" in the UI. They are never our own verdict.
"""
from __future__ import annotations

import re
from typing import Optional

import pandas as pd

RATING_COLS = ["strongBuy", "buy", "hold", "sell", "strongSell"]
RATING_LABELS = {"strongBuy": "Strong buy", "buy": "Buy", "hold": "Hold", "sell": "Sell", "strongSell": "Strong sell"}


# ---------------------------------------------------------------- holders
def holder_breakdown(major: Optional[pd.DataFrame]) -> Optional[dict[str, float]]:
    """{'Insiders': x, 'Institutions': y, 'Other / public': rest} as fractions."""
    if major is None or major.empty:
        return None
    vals = major.iloc[:, 0] if major.shape[1] else pd.Series(dtype=float)
    ins = float(vals.get("insidersPercentHeld", float("nan")))
    inst = float(vals.get("institutionsPercentHeld", float("nan")))
    if pd.isna(ins) and pd.isna(inst):
        return None
    ins, inst = (0.0 if pd.isna(ins) else ins), (0.0 if pd.isna(inst) else inst)
    other = max(0.0, 1 - ins - inst)
    return {"Insiders": ins, "Institutions": inst, "Other / public": other}


# ---------------------------------------------------------------- insiders
def classify_insider(text: Optional[str]) -> str:
    """'buy' (open-market purchase), 'sell' (sale) or 'other' (awards, gifts, option exercises...)."""
    t = (text or "").lower()
    if t.startswith("purchase") or "purchase at price" in t:
        return "buy"
    if t.startswith("sale") or "sale at price" in t:
        return "sell"
    return "other"


def insider_table(tx: Optional[pd.DataFrame]) -> pd.DataFrame:
    cols = ["date", "insider", "position", "type", "description", "shares", "value"]
    if tx is None or tx.empty:
        return pd.DataFrame(columns=cols)
    out = pd.DataFrame({
        "date": pd.to_datetime(tx.get("Start Date"), errors="coerce"),
        "insider": tx.get("Insider"),
        "position": tx.get("Position"),
        "description": tx.get("Text").fillna("") if "Text" in tx else "",
        "shares": pd.to_numeric(tx.get("Shares"), errors="coerce"),
        "value": pd.to_numeric(tx.get("Value"), errors="coerce"),
    })
    out["type"] = out["description"].map(classify_insider)
    return out[cols].sort_values("date", ascending=False).reset_index(drop=True)


def insider_monthly_net(table: pd.DataFrame, months: int = 24) -> pd.DataFrame:
    """Per month: value bought, value sold (negative) and net. Awards/gifts/exercises are excluded."""
    t = table[table["type"].isin(["buy", "sell"]) & table["date"].notna()].copy()
    if t.empty:
        return pd.DataFrame(columns=["bought", "sold", "net"])
    t["month"] = t["date"].dt.to_period("M").dt.to_timestamp()
    t["signed"] = t["value"].fillna(0) * t["type"].map({"buy": 1, "sell": -1})
    g = t.groupby(["month", "type"])["signed"].sum().unstack(fill_value=0)
    out = pd.DataFrame({"bought": g.get("buy", 0.0), "sold": g.get("sell", 0.0)})
    out["net"] = out["bought"] + out["sold"]
    start = pd.Timestamp.today().to_period("M").to_timestamp() - pd.DateOffset(months=months - 1)
    return out[out.index >= start].sort_index()


# ---------------------------------------------------------------- analysts
def recommendations_from_finnhub(rows: Optional[list[dict]]) -> pd.DataFrame:
    if not rows:
        return pd.DataFrame(columns=["month", *RATING_COLS])
    df = pd.DataFrame(rows)
    df["month"] = pd.to_datetime(df["period"])
    return df[["month", *RATING_COLS]].sort_values("month").drop_duplicates("month", keep="last").reset_index(drop=True)


def recommendations_from_yfinance(df: Optional[pd.DataFrame], today: Optional[pd.Timestamp] = None) -> pd.DataFrame:
    """yfinance periods '0m', '-1m', ... -> month start dates."""
    if df is None or df.empty:
        return pd.DataFrame(columns=["month", *RATING_COLS])
    today = (today or pd.Timestamp.today()).to_period("M").to_timestamp()
    months = []
    for p in df["period"]:
        m = re.match(r"^(-?\d+)m$", str(p))
        months.append(today + pd.DateOffset(months=int(m.group(1))) if m else pd.NaT)
    out = df.assign(month=months)[["month", *RATING_COLS]].dropna(subset=["month"])
    return out.sort_values("month").reset_index(drop=True)


def consensus_summary(rec: pd.DataFrame) -> Optional[dict]:
    """Latest month's counts and the average score (1 = strong buy ... 5 = strong sell), third-party view."""
    if rec.empty:
        return None
    last = rec.iloc[-1]
    counts = {c: int(last[c]) for c in RATING_COLS}
    total = sum(counts.values())
    if total == 0:
        return None
    score = sum(counts[c] * w for c, w in zip(RATING_COLS, (1, 2, 3, 4, 5))) / total
    return {"month": last["month"], "counts": counts, "total": total, "mean_score": score}


def upgrades_table(df: Optional[pd.DataFrame], limit: int = 15) -> pd.DataFrame:
    cols = ["date", "firm", "action", "from", "to", "price target"]
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    d = df.reset_index()
    date_col = "GradeDate" if "GradeDate" in d else d.columns[0]
    action_names = {"up": "Upgrade", "down": "Downgrade", "init": "Initiated", "main": "Maintained",
                    "reit": "Reiterated"}

    def target(r):
        cur, prior = r.get("currentPriceTarget"), r.get("priorPriceTarget")
        if not cur or pd.isna(cur) or cur == 0:
            return "—"
        if prior and not pd.isna(prior) and prior != 0 and prior != cur:
            return f"${prior:,.0f} → ${cur:,.0f}"
        return f"${cur:,.0f}"

    out = pd.DataFrame({
        "date": pd.to_datetime(d[date_col]).dt.date,
        "firm": d.get("Firm"),
        "action": d.get("Action").map(lambda a: action_names.get(str(a), str(a))),
        "from": d.get("FromGrade").replace("", "—"),
        "to": d.get("ToGrade"),
        "price target": d.apply(target, axis=1),
    })
    return out.sort_values("date", ascending=False).head(limit).reset_index(drop=True)


# ---------------------------------------------------------------- news
def news_from_finnhub(rows: Optional[list[dict]]) -> list[dict]:
    out = []
    for r in rows or []:
        if not r.get("headline") or not r.get("url"):
            continue
        out.append({"datetime": pd.Timestamp(r["datetime"], unit="s", tz="UTC"), "headline": r["headline"],
                    "source": r.get("source") or "", "url": r["url"], "image": r.get("image") or None,
                    "summary": r.get("summary") or ""})
    return out


def news_from_yfinance(rows: Optional[list[dict]]) -> list[dict]:
    out = []
    for r in rows or []:
        c = r.get("content", r)
        title = c.get("title")
        url = ((c.get("clickThroughUrl") or {}).get("url") or (c.get("canonicalUrl") or {}).get("url"))
        if not title or not url:
            continue
        thumbs = ((c.get("thumbnail") or {}).get("resolutions") or [])
        small = next((t["url"] for t in thumbs if t.get("tag") == "170x128"), thumbs[0]["url"] if thumbs else None)
        out.append({"datetime": pd.Timestamp(c.get("pubDate")), "headline": title,
                    "source": (c.get("provider") or {}).get("displayName", ""), "url": url, "image": small,
                    "summary": c.get("summary") or ""})
    return out


def _norm(h: str) -> str:
    return re.sub(r"[^a-z0-9]", "", h.lower())[:80]


def clean_news(items: list[dict], days: int, limit: int = 40) -> list[dict]:
    """Newest first, within `days`, duplicate headlines removed."""
    cutoff = pd.Timestamp.now(tz="UTC") - pd.Timedelta(days=days)
    seen, out = set(), []
    for it in sorted(items, key=lambda x: x["datetime"], reverse=True):
        ts = it["datetime"] if it["datetime"].tzinfo else it["datetime"].tz_localize("UTC")
        if ts < cutoff:
            continue
        key = _norm(it["headline"])
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
        if len(out) >= limit:
            break
    return out
