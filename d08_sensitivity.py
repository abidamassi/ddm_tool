"""
=============================================================================
SECTION D8 - SENSITIVITY ANALYSIS
=============================================================================
TUJUAN  : Menunjukkan seberapa rapuh nilai wajar terhadap dua variabel yang
          paling menentukan, yaitu Cost of Equity dan terminal growth.

          Untuk DDM, kepekaan ini biasanya LEBIH TAJAM daripada DCF, karena
          Ke lebih tinggi dari WACC sehingga spread Ke dikurangi g menjadi
          penyebut yang lebih kecil secara relatif terhadap perubahan yang
          sama. Satu angka nilai wajar tunggal karena itu memberi kesan
          presisi yang menyesatkan.

RUMUS   : Untuk setiap kombinasi (Ke_i, g_j)
            1. Terminal Value = DPS_N x (1 + g_j) / (Ke_i - g_j)
            2. Diskontokan ulang seluruh dividen dengan Ke_i
            3. Jumlahkan menjadi nilai wajar per saham

          Proyeksi DPS TIDAK berubah antar sel. Yang berubah hanya tingkat
          diskonto dan terminal growth. Ini disengaja supaya pengaruh cost
          of capital terisolasi dari pengaruh asumsi dividen, yang ditangani
          Section D9 lewat skenario.

          Grid default 5x5
            Ke              : base -100bps sampai +100bps, langkah 50bps
            Terminal growth : base -50bps sampai +50bps, langkah 25bps

OUTPUT  : DataFrame nilai wajar, DataFrame upside, dan statistik rentang.
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A
from d05_terminal import terminal_value
from d06_valuation import discount_dividends


class _NullFlags:
    """Penampung flag kosong agar grid tidak mencatat peringatan berulang."""
    def warn(self, *a, **k): pass
    def missing(self, *a, **k): pass
    def zero(self, *a, **k): pass
    def check_series(self, *a, **k): return True


def sensitivity_grid(proj, ke_base, g_base, drv, data):
    """Bangun grid sensitivity Ke x terminal growth."""
    steps = A["sens_steps"]
    ke_axis = [ke_base + i * A["sens_ke_step"] for i in range(-steps, steps + 1)]
    g_axis = [g_base + j * A["sens_g_step"] for j in range(-steps, steps + 1)]

    fv_grid = pd.DataFrame(index=[f"{k*100:.2f}%" for k in ke_axis],
                           columns=[f"{g*100:.2f}%" for g in g_axis],
                           dtype=float)
    up_grid = fv_grid.copy()

    dps_final = float(proj["DPS"].iloc[-1])
    payout_final = (float(proj["Payout"].iloc[-1])
                    if np.isfinite(proj["Payout"].iloc[-1]) else np.nan)
    roe = drv.get("roe", np.nan)
    null = _NullFlags()

    for k in ke_axis:
        for g in g_axis:
            tv = terminal_value(dps_final, k, terminal_g=g,
                                roe_terminal=roe, payout_final=payout_final,
                                flags=None)
            if not tv["valid"]:
                continue
            v = discount_dividends(proj, tv, k, data, flags=null)
            if not v["valid"]:
                continue
            fv_grid.loc[f"{k*100:.2f}%", f"{g*100:.2f}%"] = v["fair_value_per_share"]
            up_grid.loc[f"{k*100:.2f}%", f"{g*100:.2f}%"] = v["upside"]

    fv_grid.index.name = "Ke \\ Terminal g"
    up_grid.index.name = "Ke \\ Terminal g"

    flat = fv_grid.values.astype(float).ravel()
    flat = flat[np.isfinite(flat)]
    stats = {
        "min": float(flat.min()) if flat.size else np.nan,
        "max": float(flat.max()) if flat.size else np.nan,
        "median": float(np.median(flat)) if flat.size else np.nan,
        "n_valid": int(flat.size),
        "n_cells": int(fv_grid.size),
    }

    return {
        "fair_value": fv_grid.round(0),
        "upside": (up_grid.astype(float) * 100).round(1),
        "stats": stats,
        "ke_axis": ke_axis,
        "g_axis": g_axis,
    }
