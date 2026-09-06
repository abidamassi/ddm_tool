"""
=============================================================================
SECTION D5 - TERMINAL VALUE (GORDON GROWTH)
=============================================================================
TUJUAN  : Menilai aliran dividen setelah periode proyeksi eksplisit
          berakhir, dan menguji apakah asumsi fase stabilnya konsisten
          secara internal.

RUMUS   :
  D5.1 GORDON GROWTH
       DPS_(N+1) = DPS_N x (1 + g)
       TV_N      = DPS_(N+1) / (Ke - g)

       Syarat mutlak Ke lebih besar dari g. Kalau tidak, penyebutnya nol
       atau negatif dan nilai perusahaan menjadi tak hingga atau negatif.
       Model menolak melanjutkan bila spread minimum tidak terpenuhi.

  D5.2 UJI KONSISTENSI PAYOUT TERMINAL
       Pada fase stabil berlaku  g = b x ROE
       sehingga                  b = g / ROE
       dan payout konsisten      payout* = 1 - g / ROE

       Contoh, dengan g 4% dan ROE terminal 15%, payout yang konsisten
       adalah 1 - 4/15 = 73.3%. Kalau proyeksi memakai payout 40%,
       artinya perusahaan menahan jauh lebih banyak laba daripada yang
       dibutuhkan untuk tumbuh 4%, dan kelebihan laba ditahan itu tidak
       pernah sampai ke pemegang saham dalam model. Nilainya akan
       understate.

       Ini padanan langsung dari uji terminal reinvestment rate di tool
       DCF, dan memaksa kita mengakui bahwa pertumbuhan ada harganya.

  D5.3 UJI KEWAJARAN LAIN
       Implied terminal P/E = 1 / (Ke - g) x payout*
       Kontribusi TV        = PV(TV) / Nilai Total

OUTPUT  : dict {tv_nominal, valid, reason, payout konsisten, dan uji}
=============================================================================
"""

import numpy as np

from ddm_config import DDM_ASSUMPTIONS as A


def terminal_value(dps_final, ke, terminal_g=None, roe_terminal=None,
                   payout_final=None, flags=None):
    """
    Hitung terminal value dan uji konsistensi fase stabilnya.
    """
    g = A["terminal_growth"] if terminal_g is None else terminal_g

    result = {
        "terminal_growth": g,
        "ke": ke,
        "dps_final": dps_final,
        "dps_terminal": np.nan,
        "tv_nominal": np.nan,
        "payout_consistent": np.nan,
        "payout_projected": payout_final,
        "payout_gap": np.nan,
        "implied_terminal_pe": np.nan,
        "valid": False,
        "reason": "",
    }

    # ---- Ke must exceed g by a minimum spread ----
    spread = ke - g
    min_spread = A["min_ke_g_spread"]
    if spread < min_spread:
        result["reason"] = (
            f"Cost of Equity ({ke*100:.2f}%) is only {spread*100:.2f}% above "
            f"terminal growth ({g*100:.2f}%). A minimum spread of "
            f"{min_spread*10000:.0f}bps is needed for Gordon Growth to stay "
            f"stable. Below that, value becomes highly sensitive to small "
            f"assumption changes. Lower the terminal growth rate."
        )
        if flags:
            flags.warn("Terminal Value", result["reason"])
        return result

    if not np.isfinite(dps_final) or dps_final <= 0:
        result["reason"] = (
            f"The final projected year's DPS is not positive ({dps_final}). "
            f"The Gordon Growth terminal value is not meaningful."
        )
        if flags:
            flags.warn("Terminal Value", result["reason"])
        return result

    dps_next = dps_final * (1 + g)
    tv = dps_next / spread

    result["dps_terminal"] = dps_next
    result["tv_nominal"] = tv
    result["valid"] = True

    # ---- D5.2 konsistensi payout terminal ----
    if roe_terminal is not None and np.isfinite(roe_terminal) and roe_terminal > 0:
        payout_star = 1.0 - (g / roe_terminal)
        result["payout_consistent"] = payout_star

        if np.isfinite(payout_final):
            gap = payout_final - payout_star
            result["payout_gap"] = gap
            if flags and abs(gap) > A["terminal_payout_tolerance"]:
                direction = "higher" if gap > 0 else "lower"
                effect = ("value tends to be overstated because the company "
                          "distributes more than the growth rate allows for"
                          if gap > 0 else
                          "value tends to be understated because the excess "
                          "retained earnings never reach shareholders in this "
                          "model")
                flags.warn(
                    "Terminal payout consistency",
                    f"The final projected payout of {payout_final*100:.1f}% is "
                    f"{abs(gap)*100:.1f} percentage points {direction} than the "
                    f"payout consistent with the stable phase "
                    f"({payout_star*100:.1f}% = 1 - g/ROE). As a result, {effect}."
                )

        if payout_star <= 0 and flags:
            flags.warn("Terminal payout consistency",
                       f"Terminal growth of {g*100:.2f}% exceeds the terminal "
                       f"ROE of {roe_terminal*100:.1f}%. A company cannot grow "
                       f"sustainably faster than its own return on capital. "
                       f"Lower the terminal growth rate.")

        # ---- D5.3 implied terminal P/E ----
        if payout_star > 0:
            result["implied_terminal_pe"] = payout_star * (1 + g) / spread

    return result


def check_tv_dependency(pv_tv, total_value, flags=None):
    """Uji seberapa besar nilai bergantung pada terminal value."""
    if not np.isfinite(total_value) or total_value == 0:
        return np.nan
    share = pv_tv / total_value
    if flags and share > 0.80:
        flags.warn("Terminal value dependency",
                   f"{share*100:.1f}% of value comes from the terminal value. "
                   f"The valuation rests almost entirely on the perpetuity "
                   f"assumption, not on dividends that can be verified.")
    return share
