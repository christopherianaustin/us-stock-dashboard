"""Plain-language explanations for key numbers (Overview tab).

Each function returns an Explained value: a short label ("Low debt"), a tone and one everyday sentence.
Tones describe the data only:  "good" (generally favourable), "neutral", "watch" (worth a closer look).
They are never a buy / sell verdict. Texts exist in English ("en") and Bahasa Indonesia ("id").
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class Explained:
    label: str
    tone: str          # good / neutral / watch / na
    sentence: str


def _t(lang: str, en: str, id_: str) -> str:
    return id_ if lang == "id" else en


def _pct(v: float, decimals: int = 0) -> str:
    return f"{abs(v) * 100:.{decimals}f}%"


def pe_ratio(pe: Optional[float], percentile_5y: Optional[float], lang: str = "en",
             negative_earnings: bool = False) -> Explained:
    if pe is None:
        if negative_earnings:
            return Explained(_t(lang, "Not meaningful", "Tidak bermakna"), "na",
                             _t(lang, "The company lost money over the last year, so there is no P/E.",
                                "Perusahaan merugi dalam setahun terakhir, jadi P/E tidak ada."))
        return Explained(_t(lang, "Not available", "Tidak tersedia"), "na", "")
    sentence = _t(lang, f"Investors pay ${pe:,.2f} for every $1 of yearly profit.",
                  f"Investor membayar ${pe:,.2f} untuk setiap $1 laba tahunan.")
    if percentile_5y is None:
        return Explained(_t(lang, "No history to compare", "Belum ada riwayat"), "neutral", sentence)
    if percentile_5y >= 0.8:
        return Explained(_t(lang, "Pricier than usual", "Lebih mahal dari biasanya"), "watch",
                         sentence + _t(lang, f" That is higher than on {_pct(percentile_5y)} of days in the past 5 years.",
                                       f" Lebih tinggi dari {_pct(percentile_5y)} hari dalam 5 tahun terakhir."))
    if percentile_5y <= 0.2:
        return Explained(_t(lang, "Cheaper than usual", "Lebih murah dari biasanya"), "good",
                         sentence + _t(lang, f" That is lower than on {_pct(1 - percentile_5y)} of days in the past 5 years.",
                                       f" Lebih rendah dari {_pct(1 - percentile_5y)} hari dalam 5 tahun terakhir."))
    return Explained(_t(lang, "Around its usual level", "Sekitar level biasanya"), "neutral", sentence)


def revenue_growth(g: Optional[float], lang: str = "en") -> Explained:
    if g is None:
        return Explained(_t(lang, "Not available", "Tidak tersedia"), "na", "")
    more = g >= 0
    sentence = _t(lang, f"Sales were {_pct(g)} {'higher' if more else 'lower'} than the same quarter last year.",
                  f"Penjualan {_pct(g)} {'lebih tinggi' if more else 'lebih rendah'} dibanding kuartal yang sama tahun lalu.")
    if g >= 0.10:
        return Explained(_t(lang, "Growing fast", "Tumbuh cepat"), "good", sentence)
    if g >= 0.02:
        return Explained(_t(lang, "Growing", "Tumbuh"), "good", sentence)
    if g > -0.02:
        return Explained(_t(lang, "About flat", "Relatif datar"), "neutral", sentence)
    return Explained(_t(lang, "Shrinking", "Menyusut"), "watch", sentence)


def net_margin(m: Optional[float], lang: str = "en") -> Explained:
    if m is None:
        return Explained(_t(lang, "Not available", "Tidak tersedia"), "na", "")
    if m < 0:
        return Explained(_t(lang, "Losing money", "Merugi"), "watch",
                         _t(lang, f"Loses ${abs(m):.2f} on every $1 of sales.",
                            f"Rugi ${abs(m):.2f} dari setiap $1 penjualan."))
    sentence = _t(lang, f"Keeps ${m:.2f} as profit from every $1 of sales.",
                  f"Menyisakan ${m:.2f} laba dari setiap $1 penjualan.")
    if m >= 0.20:
        return Explained(_t(lang, "Very profitable", "Sangat menguntungkan"), "good", sentence)
    if m >= 0.05:
        return Explained(_t(lang, "Profitable", "Menguntungkan"), "neutral", sentence)
    return Explained(_t(lang, "Thin profit", "Laba tipis"), "watch", sentence)


def debt_to_equity(de: Optional[float], lang: str = "en", is_financial: bool = False) -> Explained:
    if is_financial:
        return Explained(_t(lang, "Not meaningful for banks", "Tidak bermakna untuk bank"), "na",
                         _t(lang, "Borrowing and lending is a bank's core business, so this ratio doesn't apply.",
                            "Meminjam dan meminjamkan adalah bisnis inti bank, jadi rasio ini tidak berlaku."))
    if de is None:
        return Explained(_t(lang, "Not available", "Tidak tersedia"), "na", "")
    sentence = _t(lang, f"Has ${de:.2f} of debt for every $1 the owners have in the company.",
                  f"Memiliki utang ${de:.2f} untuk setiap $1 modal pemilik.")
    if de <= 0.5:
        return Explained(_t(lang, "Low debt", "Utang rendah"), "good", sentence)
    if de <= 1.5:
        return Explained(_t(lang, "Moderate debt", "Utang sedang"), "neutral", sentence)
    return Explained(_t(lang, "High debt", "Utang tinggi"), "watch", sentence)


def dividend_yield(y: Optional[float], pays: bool, lang: str = "en") -> Explained:
    if not pays:
        return Explained(_t(lang, "No dividend", "Tanpa dividen"), "neutral",
                         _t(lang, "Doesn't pay a dividend. Profits are reinvested or used for buybacks.",
                            "Tidak membagi dividen. Laba diinvestasikan kembali atau dipakai untuk buyback."))
    if y is None:
        return Explained(_t(lang, "Not available", "Tidak tersedia"), "na", "")
    sentence = _t(lang, f"Pays about ${y * 100:.2f} a year for every $100 invested.",
                  f"Membayar sekitar ${y * 100:.2f} per tahun untuk setiap $100 yang diinvestasikan.")
    if y >= 0.04:
        return Explained(_t(lang, "High yield", "Imbal hasil tinggi"), "good", sentence)
    if y >= 0.015:
        return Explained(_t(lang, "Moderate yield", "Imbal hasil sedang"), "neutral", sentence)
    return Explained(_t(lang, "Small yield", "Imbal hasil kecil"), "neutral", sentence)


def beta(b: Optional[float], lang: str = "en") -> Explained:
    if b is None:
        return Explained(_t(lang, "Not available", "Tidak tersedia"), "na", "")
    sentence = _t(lang, f"When the market moved 1%, this stock tended to move about {b:.1f}%.",
                  f"Saat pasar bergerak 1%, saham ini cenderung bergerak sekitar {b:.1f}%.")
    if b <= 0.8:
        return Explained(_t(lang, "Calmer than the market", "Lebih tenang dari pasar"), "good", sentence)
    if b <= 1.2:
        return Explained(_t(lang, "Moves with the market", "Bergerak seperti pasar"), "neutral", sentence)
    return Explained(_t(lang, "Bigger swings than the market", "Ayunan lebih besar dari pasar"), "watch", sentence)
