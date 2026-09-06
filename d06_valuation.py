"""
=============================================================================
SECTION D6 - DISKONTO, NILAI PER SAHAM, DAN REKOMENDASI
=============================================================================
TUJUAN  : Mendiskontokan seluruh aliran dividen ke nilai sekarang dan
          menerjemahkan selisihnya terhadap harga pasar menjadi keputusan.

CATATAN METODOLOGIS PENTING:
          Tingkat diskonto DDM adalah COST OF EQUITY, bukan WACC.

          Dividen adalah arus kas kepada pemegang saham biasa saja, bukan
          kepada seluruh penyedia modal. Mendiskontokannya dengan WACC
          (yang selalu lebih rendah dari Ke ketika ada utang) akan
          menghasilkan nilai yang terlalu tinggi secara sistematis. Untuk
          bank kesalahannya lebih besar lagi karena bobot utangnya besar.

          Fungsi cost_of_equity() dari s06_wacc.py dipakai ulang apa adanya,
          jadi tidak ada rumus CAPM yang ditulis dua kali. Yang tidak
          dipakai hanyalah tahap akhir penggabungan menjadi WACC.

RUMUS   :
  D6.1 DISKONTO DIVIDEN EKSPLISIT
       PV(DPS_t) = DPS_t / (1 + Ke)^t

       Konvensi akhir tahun, BUKAN tengah tahun seperti tool DCF. Dividen
       adalah pembayaran diskret pada tanggal tertentu, bukan arus kas
       yang mengalir merata sepanjang tahun.

  D6.2 DISKONTO TERMINAL VALUE
       PV(TV) = TV_N / (1 + Ke)^N

  D6.3 NILAI WAJAR PER SAHAM
       Nilai per saham = Sigma PV(DPS_t) + PV(TV)

       Berbeda dari DCF, tidak ada jembatan dari Enterprise Value ke Equity
       Value di sini. Model dividen langsung menghasilkan nilai ekuitas per
       lembar, karena yang didiskontokan memang sudah arus kas per lembar
       kepada pemegang saham. Kas dan utang tidak dikurangkan lagi.

  D6.4 UPSIDE DAN REKOMENDASI
       Upside = Nilai wajar / Harga pasar - 1

       Upside > +10%          -> BUY
       -10% <= Upside <= +10% -> HOLD
       Upside < -10%          -> SELL

       Upside > +100% atau < -50% -> Review Required, arahkan ke metode lain

  D6.5 METRIK IMPLISIT
       Dividend yield saat ini = DPS terakhir / Harga pasar
       Implied yield fair value = DPS_1 / Nilai wajar

OUTPUT  : dict lengkap berisi komponen valuasi dan rekomendasi.
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A
from d05_terminal import check_tv_dependency


# -----------------------------------------------------------------------
# D6.1 - D6.3 VALUASI
# -----------------------------------------------------------------------
def discount_dividends(proj, tv_info, ke, data, flags, mid_year=None):
    """Diskontokan proyeksi dividen dan terminal value."""
    mid = A["mid_year_convention"] if mid_year is None else mid_year
    N = len(proj)

    if not tv_info["valid"]:
        return {"valid": False, "reason": tv_info["reason"]}

    rows = []
    pv_explicit = 0.0
    for t in range(1, N + 1):
        dps = float(proj.loc[t, "DPS"])
        exponent = (t - 0.5) if mid else t
        df = 1.0 / ((1 + ke) ** exponent)
        pv = dps * df
        pv_explicit += pv
        rows.append({
            "Year": t, "DPS": dps, "Exponent": exponent,
            "Discount factor": df, "PV DPS": pv,
        })
    disc = pd.DataFrame(rows).set_index("Year")

    df_tv = 1.0 / ((1 + ke) ** N)
    pv_tv = tv_info["tv_nominal"] * df_tv

    fair_value = pv_explicit + pv_tv
    tv_share = check_tv_dependency(pv_tv, fair_value, flags)

    price = data.price
    upside = (fair_value / price - 1) if (np.isfinite(price) and price > 0) else np.nan

    # ---- metrik implisit ----
    dps_now = float(proj.loc[1, "DPS"])
    cur_yield = (dps_now / price) if (np.isfinite(price) and price > 0) else np.nan
    fv_yield = (dps_now / fair_value) if fair_value > 0 else np.nan

    return {
        "valid": True,
        "discount_table": disc,
        "pv_explicit": pv_explicit,
        "pv_terminal": pv_tv,
        "tv_nominal": tv_info["tv_nominal"],
        "tv_discount_factor": df_tv,
        "tv_share_of_value": tv_share,
        "fair_value_per_share": fair_value,
        "market_price": price,
        "upside": upside,
        "dividend_yield_current": cur_yield,
        "dividend_yield_at_fv": fv_yield,
        "ke": ke,
        "mid_year": mid,
    }


def value_bridge_table(v):
    """Per-share value composition table."""
    rows = [
        ("PV of explicit dividends", v["pv_explicit"]),
        ("PV of terminal value", v["pv_terminal"]),
        ("Fair value per share", v["fair_value_per_share"]),
    ]
    df = pd.DataFrame(rows, columns=["Component", "IDR per share"])
    df["IDR per share"] = df["IDR per share"].round(2)
    return df


# -----------------------------------------------------------------------
# D6.4 REKOMENDASI
# -----------------------------------------------------------------------
def make_ddm_recommendation(valuation, flags=None):
    upside = valuation.get("upside", np.nan)
    fv = valuation.get("fair_value_per_share", np.nan)
    px = valuation.get("market_price", np.nan)

    if not np.isfinite(upside):
        return {
            "rating": "N/A", "upside": np.nan, "label": "Cannot be rated",
            "note": "Fair value or market price is unavailable.",
            "review_required": False, "reason_override": "",
        }

    # ---- Review Required gate ----
    if upside > A["review_upside_threshold"] or upside < A["review_downside_threshold"]:
        reason = (
            "This result falls outside a defensible range for a dividend discount "
            "model. The gap between fair value and market price is wide enough that "
            "it more often signals a modelling or data issue than genuine "
            "mispricing. Consider cross-checking with SOTP, Net Asset Value, or "
            "relative valuation (P/BV, P/E against peers) before drawing a "
            "conclusion."
        )
        if flags:
            flags.warn("Recommendation",
                       f"Upside of {upside*100:+.0f}% is outside a defensible "
                       f"range. Rating changed to Review Required.")
        return {
            "rating": "Review Required",
            "upside": float(upside),
            "label": "Outside a reasonable range",
            "note": reason,
            "review_required": True,
            "reason_override": reason,
        }

    if upside > A["buy_threshold"]:
        rating, label = "BUY", "Undervalued"
    elif upside < A["sell_threshold"]:
        rating, label = "SELL", "Overvalued"
    else:
        rating, label = "HOLD", "Fairly valued"

    return {
        "rating": rating,
        "upside": float(upside),
        "label": label,
        "note": (f"Model fair value IDR {fv:,.0f} versus market price "
                 f"IDR {px:,.0f}, upside {upside*100:+.1f}%."),
        "review_required": False,
        "reason_override": "",
        "threshold_buy": A["buy_threshold"],
        "threshold_sell": A["sell_threshold"],
    }
