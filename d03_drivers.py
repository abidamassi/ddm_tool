"""
=============================================================================
SECTION D3 - DRIVER DIVIDEN (PAYOUT, ROE, SUSTAINABLE GROWTH)
=============================================================================
TUJUAN  : Menurunkan asumsi proyeksi dividen dari data emiten itu sendiri,
          dan memaksa pertumbuhan yang dipakai konsisten dengan kemampuan
          perusahaan menahan laba.

          Ini padanan langsung dari pembatas RR x ROIC di tool DCF. Kalau
          di sana growth dibatasi kemampuan reinvestasi, di sini growth
          dibatasi kemampuan menahan laba.

RUMUS   :
  D3.1 EARNINGS PER SHARE
       EPS_t = Laba Bersih_t / Jumlah Saham Beredar

       Laba bersih sudah dalam IDR (dikonversi Section 1 tool DCF bila
       laporan aslinya USD). DPS juga sudah IDR. Keduanya sebanding.

  D3.2 PAYOUT RATIO, DUA KONVENSI
       Lagged        : Payout_t = DPS_t / EPS_(t-1)
       Kontemporer   : Payout_t = DPS_t / EPS_t

       Versi LAGGED dipakai sebagai angka utama. Alasannya, dividen yang
       dibayarkan pada tahun T di Indonesia umumnya adalah pembagian laba
       tahun buku T-1 yang disetujui RUPS pada tahun T. Memasangkan DPS
       tahun T dengan EPS tahun T adalah pemasangan yang salah periode.

       Versi kontemporer tetap dihitung dan ditampilkan sebagai pembanding.

  D3.3 RETURN ON EQUITY
       ROE_t = Laba Bersih_t / Rata-rata Ekuitas
       Rata-rata Ekuitas = (Ekuitas_t + Ekuitas_(t-1)) / 2

       Memakai rata-rata, bukan ekuitas akhir tahun, karena laba dihasilkan
       sepanjang tahun oleh basis modal yang berubah.

  D3.4 SUSTAINABLE GROWTH RATE
       b   = retention ratio = 1 - payout ratio
       SGR = b x ROE

       Ini persamaan pertumbuhan fundamental untuk model dividen. Sebuah
       perusahaan hanya bisa menumbuhkan dividennya secara berkelanjutan
       sebesar laba yang ditahan dikali tingkat pengembalian atas modal.

  D3.5 PEMBATAS PERTUMBUHAN
       g_dipakai = min(g historis median, SGR)

       Kalau pertumbuhan DPS historis melebihi SGR, itu berarti emiten
       menaikkan payout ratio dari tahun ke tahun, bukan menumbuhkan
       kapasitas laba. Cara itu punya batas mutlak karena payout tidak
       bisa melewati 100 persen, jadi tidak boleh diekstrapolasi
       selamanya.

OUTPUT  : dict driver dan standar deviasinya.
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A
from utils import clip_flag, nanstd


# -----------------------------------------------------------------------
# D3.1 - D3.2 PAYOUT RATIO
# -----------------------------------------------------------------------
def compute_payout(hist, div_profile, shares_outstanding, flags):
    """
    Hitung EPS, DPS berpasangan, dan payout ratio dalam dua konvensi.
    """
    if not np.isfinite(shares_outstanding) or shares_outstanding <= 0:
        flags.missing("Shares outstanding",
                      "Payout ratio and EPS cannot be computed.")
        return None

    ni = pd.to_numeric(hist.loc["net_income"], errors="coerce")

    # Map financial statements to fiscal years
    eps_by_year = {}
    non_dec = []
    for col in hist.columns:
        try:
            ts = pd.Timestamp(col)
        except Exception:
            continue
        if ts.month != 12:
            non_dec.append(str(col)[:10])
        val = ni.get(col, np.nan)
        if pd.notna(val):
            eps_by_year[int(ts.year)] = float(val) / shares_outstanding

    if non_dec:
        flags.warn("Fiscal year",
                   f"Period(s) {non_dec} do not end in December. Mapping "
                   f"calendar-year dividends to fiscal years becomes less precise.")

    if not eps_by_year:
        flags.missing("EPS", "Net income could not be mapped to fiscal years.")
        return None

    dps_by_year = {int(y): float(v) for y, v in div_profile["annual"].items()}

    rows = []
    for y in sorted(dps_by_year):
        dps = dps_by_year[y]
        eps_lag = eps_by_year.get(y - 1, np.nan)     # prior fiscal year's earnings
        eps_now = eps_by_year.get(y, np.nan)
        rows.append({
            "Year paid": y,
            "DPS": dps,
            "EPS (t-1)": eps_lag,
            "EPS (t)": eps_now,
            "Payout (lagged)": (dps / eps_lag) if (np.isfinite(eps_lag) and eps_lag > 0) else np.nan,
            "Payout (contemporaneous)": (dps / eps_now) if (np.isfinite(eps_now) and eps_now > 0) else np.nan,
        })

    table = pd.DataFrame(rows)
    lagged = table["Payout (lagged)"].dropna()
    contemp = table["Payout (contemporaneous)"].dropna()

    # Drop implausible values before taking the median
    lagged_clean = lagged[(lagged > 0) & (lagged < 3.0)]
    contemp_clean = contemp[(contemp > 0) & (contemp < 3.0)]

    payout_lag = float(np.median(lagged_clean)) if len(lagged_clean) else np.nan
    payout_con = float(np.median(contemp_clean)) if len(contemp_clean) else np.nan

    if np.isfinite(payout_lag):
        payout, basis = payout_lag, "lagged (DPS_t / EPS_t-1)"
    elif np.isfinite(payout_con):
        payout, basis = payout_con, "contemporaneous (DPS_t / EPS_t)"
        flags.warn("Payout ratio",
                   "The lagged version could not be computed, the "
                   "contemporaneous version is used instead. This pairs a "
                   "dividend with the same year's earnings, which is less "
                   "accurate for Indonesian practice.")
    else:
        flags.missing("Payout ratio", "Cannot be computed from available data.")
        return None

    payout_sd = float(nanstd(lagged_clean.tolist())) if len(lagged_clean) > 1 else np.nan

    if payout > 1.0:
        flags.warn("Payout ratio",
                   f"Median payout of {payout*100:.1f}% exceeds 100%. Dividends "
                   f"are paid beyond earnings, funded by prior cash or debt. Not "
                   f"sustainable at this level.")

    return {
        "table": table,
        "payout": payout,
        "payout_basis": basis,
        "payout_lagged": payout_lag,
        "payout_contemporaneous": payout_con,
        "payout_sd": payout_sd,
        "eps_by_year": eps_by_year,
        "latest_eps": eps_by_year.get(max(eps_by_year), np.nan),
    }


# -----------------------------------------------------------------------
# D3.3 ROE
# -----------------------------------------------------------------------
def compute_roe(hist, flags):
    """ROE per periode memakai rata-rata ekuitas."""
    ni = pd.to_numeric(hist.loc["net_income"], errors="coerce")
    eq = pd.to_numeric(hist.loc["equity"], errors="coerce")

    vals, by_year = [], {}
    for i in range(1, len(hist.columns)):
        n, e0, e1 = ni.iloc[i], eq.iloc[i - 1], eq.iloc[i]
        if pd.isna(n) or pd.isna(e0) or pd.isna(e1):
            continue
        avg_eq = (e0 + e1) / 2.0
        if avg_eq <= 0:
            continue
        r = float(n / avg_eq)
        vals.append(r)
        try:
            by_year[int(pd.Timestamp(hist.columns[i]).year)] = r
        except Exception:
            pass

    if not vals:
        flags.missing("ROE", "Cannot be computed from net income and equity.")
        return {"roe": np.nan, "roe_sd": np.nan, "by_year": {}, "n_obs": 0}

    roe_raw = float(np.median(vals))
    roe = clip_flag(roe_raw, A["roe_floor"], A["roe_cap"], "ROE", flags)
    return {
        "roe": roe,
        "roe_raw": roe_raw,
        "roe_sd": float(nanstd(vals)) if len(vals) > 1 else np.nan,
        "by_year": by_year,
        "n_obs": len(vals),
    }


# -----------------------------------------------------------------------
# D3.4 - D3.5 DRIVER GABUNGAN
# -----------------------------------------------------------------------
def build_ddm_drivers(hist, div_profile, payout_info, roe_info, flags):
    """
    Gabungkan payout, ROE, dan pertumbuhan historis menjadi satu set driver,
    dengan pertumbuhan dibatasi Sustainable Growth Rate.
    """
    payout = payout_info["payout"]
    payout = clip_flag(payout, A["payout_floor"], A["payout_cap"],
                       "Payout ratio", flags)
    retention = max(1.0 - payout, 0.0)
    roe = roe_info["roe"]

    # ---- Sustainable Growth Rate ----
    if np.isfinite(roe) and np.isfinite(retention):
        sgr = retention * roe
    else:
        sgr = np.nan
        flags.warn("Sustainable Growth Rate",
                   "Cannot be computed, ROE or payout is unavailable.")

    # ---- historical growth ----
    g_hist_raw = div_profile["g_median"]
    if not np.isfinite(g_hist_raw):
        g_hist_raw = 0.0
        flags.warn("DPS growth",
                   "Median historical growth could not be computed, 0% used.")
    g_hist = clip_flag(g_hist_raw, A["dps_growth_floor"], A["dps_growth_cap"],
                       "Historical DPS growth", flags)

    # ---- constraint ----
    if np.isfinite(sgr):
        g_sust = max(sgr, 0.0)
        if g_sust < g_hist:
            flags.warn(
                "Growth constrained by retained earnings",
                f"Historical DPS growth of {g_hist*100:.2f}% exceeds the "
                f"Sustainable Growth Rate. Retention of {retention*100:.1f}% "
                f"times ROE of {roe*100:.1f}% yields only {g_sust*100:.2f}%. The "
                f"gap comes from a rising payout ratio, not growing earnings "
                f"capacity, and cannot continue indefinitely because payout is "
                f"capped at 100%. Growth is lowered to {g_sust*100:.2f}%."
            )
            g_used = g_sust
        else:
            g_used = g_hist
    else:
        g_used = g_hist
        flags.warn("Growth constraint",
                   "SGR is unavailable, growth uses the historical median "
                   "with no fundamental constraint.")

    # ---- standard deviation for scenarios ----
    g_sd = div_profile["g_sd"]
    if not np.isfinite(g_sd) or g_sd < A["min_growth_sd"]:
        if np.isfinite(g_sd):
            flags.warn("DPS growth SD",
                       f"Historical volatility is only {g_sd*100:.2f}%, too low "
                       f"for meaningful scenarios. A floor of "
                       f"{A['min_growth_sd']*100:.1f}% is used instead.")
        g_sd = A["min_growth_sd"]

    p_sd = payout_info.get("payout_sd", np.nan)
    if not np.isfinite(p_sd) or p_sd < A["min_payout_sd"]:
        p_sd = A["min_payout_sd"]

    return {
        "dps_base":      div_profile["latest_dps"],
        "base_year":     div_profile["latest_year"],
        "payout":        float(payout),
        "payout_sd":     float(p_sd),
        "payout_basis":  payout_info["payout_basis"],
        "retention":     float(retention),
        "roe":           float(roe) if np.isfinite(roe) else np.nan,
        "roe_sd":        roe_info.get("roe_sd", np.nan),
        "sgr":           float(sgr) if np.isfinite(sgr) else np.nan,
        "g_hist":        float(g_hist),
        "g_used":        float(g_used),
        "g_sd":          float(g_sd),
        "cv":            div_profile["cv"],
    }


def ddm_drivers_table(drv):
    """Driver table for display."""
    def pct(v, dp=2):
        return f"{v*100:.{dp}f}%" if v is not None and np.isfinite(v) else "n/a"

    rows = [
        ("DPS base (latest year)",
         f"IDR {drv['dps_base']:,.2f}" if np.isfinite(drv["dps_base"]) else "n/a",
         f"year {drv['base_year']}"),
        ("Payout ratio (median)", pct(drv["payout"], 1), drv["payout_basis"]),
        ("Retention ratio (b = 1 - payout)", pct(drv["retention"], 1), ""),
        ("ROE (median, average equity)", pct(drv["roe"], 1),
         f"SD {pct(drv['roe_sd'], 1)}"),
        ("Sustainable Growth Rate (b x ROE)", pct(drv["sgr"]), "fundamental upper bound"),
        ("Historical DPS growth (median)", pct(drv["g_hist"]),
         f"SD {pct(drv['g_sd'])}"),
        ("Growth used", pct(drv["g_used"]), "min(historical, SGR)"),
    ]
    return pd.DataFrame(rows, columns=["Driver", "Value", "Note"])
