"""
=============================================================================
SECTION D4 - PROYEKSI DIVIDEN PER SAHAM
=============================================================================
TUJUAN  : Memproyeksikan DPS selama periode eksplisit sebelum masuk fase
          pertumbuhan stabil.

RUMUS   :
  D4.1 FADE PERTUMBUHAN LINEAR
       g_t = g_1 - (g_1 - g_terminal) x (t - 1) / (N - 1)

       Sama seperti tool DCF. Pertumbuhan meluruh bertahap dari tingkat
       tahun pertama menuju tingkat perpetuitas, bukan konstan lalu
       terjun bebas di tahun terakhir.

       Terminal growth dibatasi tidak boleh melampaui g_1. Tanpa batas ini
       fade justru MENGAKSELERASI pertumbuhan menuju perpetuitas, yang
       kebalikan dari maksudnya.

  D4.2 DIVIDEN
       DPS_t = DPS_(t-1) x (1 + g_t)

  D4.3 JEJAK EPS DAN PAYOUT IMPLISIT
       EPS_t    = EPS_(t-1) x (1 + g_earnings)
       Payout_t = DPS_t / EPS_t

       Laba diproyeksikan tumbuh pada tingkat yang sama dengan dividen
       dalam kondisi payout stabil. Kalau payout implisit merangkak naik
       melewati 100 persen di dalam periode proyeksi, itu tanda asumsi
       pertumbuhan dividen tidak didukung pertumbuhan laba, dan model
       akan menandainya.

OUTPUT  : DataFrame proyeksi per tahun dan dict ringkasan.
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A


def project_dividends(drv, years=None, g1=None, terminal_g=None,
                      payout=None, flags=None):
    """
    Bangun proyeksi DPS. Parameter opsional dipakai Section D9 (skenario)
    untuk menimpa nilai base tanpa mengubah driver aslinya.
    """
    N = int(years or A["forecast_years"])
    g1 = drv["g_used"] if g1 is None else g1
    g_term = A["terminal_growth"] if terminal_g is None else terminal_g
    payout0 = drv["payout"] if payout is None else payout

    # Terminal growth tidak boleh melampaui pertumbuhan tahun pertama
    if A["cap_terminal_at_g1"] and g_term > g1:
        g_term = max(g1, 0.0)

    dps0 = drv["dps_base"]
    if not np.isfinite(dps0) or dps0 <= 0:
        return None, {"error": "Base DPS is not valid"}

    # Initial EPS is derived from DPS and payout to stay internally consistent
    eps0 = dps0 / payout0 if payout0 > 0 else np.nan

    rows = []
    prev_dps, prev_eps = dps0, eps0
    for t in range(1, N + 1):
        g_t = g1 - (g1 - g_term) * (t - 1) / (N - 1) if N > 1 else g1
        dps = prev_dps * (1 + g_t)
        eps = prev_eps * (1 + g_t) if np.isfinite(prev_eps) else np.nan
        po = (dps / eps) if (np.isfinite(eps) and eps > 0) else np.nan

        rows.append({
            "Year": t,
            "Growth": g_t,
            "DPS": dps,
            "EPS": eps,
            "Payout": po,
        })
        prev_dps, prev_eps = dps, eps

    proj = pd.DataFrame(rows).set_index("Year")

    # Warn if implied payout crosses 100%
    if flags is not None and proj["Payout"].notna().any():
        over = proj[proj["Payout"] > 1.0]
        if len(over):
            flags.warn("Implied payout",
                       f"Payout ratio crosses 100% in projection year(s) "
                       f"{over.index.tolist()}. Dividends grow faster than the "
                       f"earnings that support them.")

    summary = {
        "years": N,
        "g1": g1,
        "g_terminal": g_term,
        "payout_base": payout0,
        "dps_base": dps0,
        "dps_final": float(proj["DPS"].iloc[-1]),
        "eps_final": float(proj["EPS"].iloc[-1]) if np.isfinite(proj["EPS"].iloc[-1]) else np.nan,
        "payout_final": float(proj["Payout"].iloc[-1]) if np.isfinite(proj["Payout"].iloc[-1]) else np.nan,
    }
    return proj, summary


def projection_table(proj):
    """Format proyeksi untuk ditampilkan."""
    out = pd.DataFrame(index=proj.index)
    out["Growth %"] = (proj["Growth"] * 100).round(2)
    out["DPS (IDR)"] = proj["DPS"].round(2)
    out["EPS (IDR)"] = proj["EPS"].round(2)
    out["Payout %"] = (proj["Payout"] * 100).round(1)
    return out
