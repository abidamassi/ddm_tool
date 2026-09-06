"""
=============================================================================
SECTION D7 - CROSS-CHECK: FAIR P/BV DAN RESIDUAL INCOME
=============================================================================
TUJUAN  : Menyandingkan hasil DDM dengan dua metode berbasis ekuitas yang
          menggunakan input sama persis. Kalau ketiganya jauh berbeda, itu
          sinyal ada asumsi yang tidak konsisten, bukan tiga pendapat yang
          bisa dirata-rata.

  D7.1 FAIR P/BV GORDON GROWTH
       Fair P/BV  = (ROE - g) / (Ke - g)
       Fair Value = Fair P/BV x Book Value per Share

       Ini konvensi yang lazim dipakai untuk bank di Indonesia. Secara
       matematis ini adalah bentuk lain dari Gordon Growth DDM, dengan
       asumsi payout berada tepat pada tingkat yang konsisten dengan
       pertumbuhan, yaitu payout = 1 - g/ROE.

       Karena itu perbandingannya informatif. Kalau hasil DDM dan Fair P/BV
       berbeda jauh, penyebabnya hampir selalu payout ratio aktual yang
       menyimpang dari tingkat konsistennya. DDM memakai payout aktual,
       sedangkan Fair P/BV memaksakan payout konsisten.

  D7.2 RESIDUAL INCOME (EXCESS RETURN)
       Nilai = BVPS_0 + Sigma [ (ROE - Ke) x BVPS_(t-1) / (1 + Ke)^t ]
                      + PV(terminal residual income)

       BVPS bertumbuh sebesar laba ditahan:
       BVPS_t = BVPS_(t-1) x (1 + ROE x b)

       Terminal:
       RI_(N+1) = (ROE - Ke) x BVPS_N
       TV       = RI_(N+1) / (Ke - g)

       Metode ini memisahkan nilai buku yang sudah ada dari nilai tambah
       yang diciptakan di atas biaya modal. Kalau ROE sama dengan Ke,
       perusahaan tidak menciptakan nilai apa pun di atas nilai bukunya,
       dan hasilnya akan mendekati BVPS.

  D7.3 UJI KESELARASAN
       Ketiga metode dibandingkan. Selisih besar diberi penjelasan
       penyebabnya, bukan sekadar ditampilkan berdampingan.

OUTPUT  : dict berisi hasil kedua metode dan diagnosis selisihnya.
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A


# -----------------------------------------------------------------------
# D7.1 FAIR P/BV
# -----------------------------------------------------------------------
def fair_pbv(roe, ke, g, bvps, flags=None):
    """Gordon Growth dalam bentuk P/BV."""
    out = {"roe": roe, "ke": ke, "g": g, "bvps": bvps,
           "fair_pbv": np.nan, "fair_value": np.nan,
           "current_pbv": np.nan, "valid": False, "reason": ""}

    if not all(np.isfinite(x) for x in [roe, ke, g, bvps]):
        out["reason"] = "One of the inputs is unavailable."
        return out
    if bvps <= 0:
        out["reason"] = "Book value per share is not positive."
        return out

    spread = ke - g
    if spread < A["min_ke_g_spread"]:
        out["reason"] = (f"The Ke minus g spread is only {spread*100:.2f}%, "
                         f"below the minimum {A['min_ke_g_spread']*10000:.0f}bps.")
        return out

    pbv = (roe - g) / spread
    out["fair_pbv"] = pbv
    out["fair_value"] = pbv * bvps
    out["valid"] = True

    if pbv <= 0 and flags:
        flags.warn("Fair P/BV",
                   f"Fair P/BV is negative ({pbv:.2f}x) because ROE of "
                   f"{roe*100:.1f}% is below terminal growth of {g*100:.2f}%. "
                   f"The company cannot grow faster than its own return on "
                   f"capital.")
    return out


# -----------------------------------------------------------------------
# D7.2 RESIDUAL INCOME
# -----------------------------------------------------------------------
def residual_income(bvps, roe, ke, g, retention, years=None, flags=None):
    """Excess return model berbasis nilai buku."""
    N = int(years or A["forecast_years"])
    out = {"valid": False, "reason": "", "bvps_0": bvps,
           "pv_ri": np.nan, "pv_terminal": np.nan, "fair_value": np.nan,
           "table": None}

    if not all(np.isfinite(x) for x in [bvps, roe, ke, g, retention]):
        out["reason"] = "One of the inputs is unavailable."
        return out
    if bvps <= 0:
        out["reason"] = "Book value per share is not positive."
        return out

    spread_ke_g = ke - g
    if spread_ke_g < A["min_ke_g_spread"]:
        out["reason"] = (f"The Ke minus g spread is only {spread_ke_g*100:.2f}%, "
                         f"below the minimum.")
        return out

    g_bv = roe * retention          # book value growth from retained earnings
    rows = []
    pv_ri = 0.0
    bv_prev = bvps

    for t in range(1, N + 1):
        ri = (roe - ke) * bv_prev
        df = 1.0 / ((1 + ke) ** t)
        pv = ri * df
        pv_ri += pv
        rows.append({
            "Year": t, "Opening BVPS": bv_prev, "Residual income": ri,
            "Discount factor": df, "PV RI": pv,
        })
        bv_prev = bv_prev * (1 + g_bv)

    bv_final = bv_prev
    ri_next = (roe - ke) * bv_final
    tv = ri_next / spread_ke_g
    pv_tv = tv / ((1 + ke) ** N)

    out.update({
        "valid": True,
        "table": pd.DataFrame(rows).set_index("Year"),
        "pv_ri": pv_ri,
        "pv_terminal": pv_tv,
        "bvps_final": bv_final,
        "bv_growth": g_bv,
        "fair_value": bvps + pv_ri + pv_tv,
        "excess_return": roe - ke,
    })

    if flags and (roe - ke) < 0:
        flags.warn("Residual income",
                   f"ROE of {roe*100:.1f}% is below the Cost of Equity of "
                   f"{ke*100:.1f}%. The company destroys value relative to its "
                   f"cost of capital, so fair value sits below book value.")
    return out


# -----------------------------------------------------------------------
# D7.3 PERBANDINGAN
# -----------------------------------------------------------------------
def compare_methods(ddm_value, pbv_result, ri_result, drv, price, flags=None):
    """
    Sandingkan ketiga metode dan jelaskan penyebab selisihnya.
    """
    rows = []

    def add(name, val, note=""):
        up = (val / price - 1) if (np.isfinite(val) and np.isfinite(price) and price > 0) else np.nan
        rows.append({
            "Method": name,
            "Fair value (IDR)": round(val, 0) if np.isfinite(val) else np.nan,
            "Upside": f"{up*100:+.1f}%" if np.isfinite(up) else "n/a",
            "Note": note,
        })

    add("DDM Gordon Growth", ddm_value, "uses the actual payout ratio")
    if pbv_result["valid"]:
        add("Fair P/BV (ROE-g)/(Ke-g)", pbv_result["fair_value"],
            f"fair P/BV {pbv_result['fair_pbv']:.2f}x, forces a consistent payout")
    else:
        rows.append({"Method": "Fair P/BV (ROE-g)/(Ke-g)", "Fair value (IDR)": np.nan,
                     "Upside": "n/a", "Note": pbv_result["reason"][:60]})
    if ri_result["valid"]:
        add("Residual Income", ri_result["fair_value"],
            f"excess return {ri_result['excess_return']*100:+.1f}% above Ke")
    else:
        rows.append({"Method": "Residual Income", "Fair value (IDR)": np.nan,
                     "Upside": "n/a", "Note": ri_result["reason"][:60]})

    table = pd.DataFrame(rows)

    # ---- diagnose the gap ----
    diagnosis = ""
    if pbv_result["valid"] and np.isfinite(ddm_value) and pbv_result["fair_value"] > 0:
        ratio = ddm_value / pbv_result["fair_value"]
        payout_actual = drv["payout"]
        roe = drv["roe"]
        g = A["terminal_growth"]
        payout_star = 1.0 - (g / roe) if (np.isfinite(roe) and roe > 0) else np.nan

        if abs(ratio - 1.0) > 0.20 and np.isfinite(payout_star):
            direction = "lower" if ratio < 1 else "higher"
            diagnosis = (
                f"DDM produces a value {abs(ratio-1)*100:.0f}% {direction} than "
                f"Fair P/BV. The cause is that the actual payout ratio of "
                f"{payout_actual*100:.1f}% deviates from the payout consistent "
                f"with stable growth ({payout_star*100:.1f}% = 1 - g/ROE). DDM "
                f"uses the actual payout, Fair P/BV forces a consistent one. "
                f"This gap is not a disagreement between methods, but an "
                f"arithmetic consequence of a dividend policy that differs from "
                f"its sustainable level."
            )
            if flags:
                flags.warn("Method alignment", diagnosis)

    return {"table": table, "diagnosis": diagnosis}
