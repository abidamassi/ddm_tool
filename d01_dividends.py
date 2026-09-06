"""
=============================================================================
SECTION D1 - RIWAYAT DIVIDEN
=============================================================================
TUJUAN  : Menarik riwayat pembayaran dividen dari yfinance dan mengubahnya
          menjadi deret Dividend Per Share (DPS) tahunan yang bisa dipakai
          untuk mengukur konsistensi, pertumbuhan, dan volatilitas.

SUMBER DATA:
          yfinance Ticker.dividends
            -> pandas Series
            -> index : tanggal ex-dividend (timezone aware)
            -> value : dividen per lembar dalam MATA UANG PERDAGANGAN

          Untuk ticker .JK nilainya sudah dalam IDR, sama dengan mata uang
          harga saham, jadi TIDAK perlu konversi kurs. Ini berbeda dari
          laporan keuangan yang bisa dilaporkan dalam USD dan harus
          dikonversi (ditangani Section 1 tool DCF).

RUMUS   :
  D1.1 AGREGASI TAHUNAN
       DPS_tahun = jumlah seluruh pembayaran dengan ex-date di tahun itu

       Emiten IDX umumnya membayar satu sampai dua kali setahun (interim
       dan final). Penjumlahan per tahun kalender menangani keduanya.

  D1.2 PEMBUANGAN TAHUN BERJALAN
       Tahun kalender yang sedang berjalan DIBUANG dari analisis
       pertumbuhan dan konsistensi. Alasannya: kalau emiten biasa membayar
       di bulan Desember dan sekarang baru bulan September, tahun berjalan
       akan tercatat nol dan terbaca sebagai penurunan drastis yang palsu.

  D1.3 PERTUMBUHAN
       YoY_t  = DPS_t / DPS_(t-1) - 1
       g_med  = median dari seluruh YoY
       CAGR   = (DPS_akhir / DPS_awal)^(1/n) - 1

       Median dipakai sebagai angka utama, konsisten dengan tool DCF,
       karena lebih tahan terhadap satu tahun ekstrem.

  D1.4 VOLATILITAS
       CV = standar deviasi DPS / rata-rata DPS

       Ini mengukur seberapa beraturan aliran dividennya. DDM
       mengasumsikan deret dividen yang tumbuh teratur, jadi CV tinggi
       berarti asumsi dasarnya tidak terpenuhi.

  D1.5 DETEKSI DIVIDEN SPESIAL
       Sebuah tahun ditandai kalau DPS-nya melebihi kelipatan tertentu
       dari median tahun-tahun lainnya.

OUTPUT  : dict berisi deret DPS tahunan, metrik pertumbuhan, volatilitas,
          rekam jejak pembayaran, dan flag.
=============================================================================
"""

from datetime import datetime

import numpy as np
import pandas as pd
import yfinance as yf

from ddm_config import DDM_SCREENING


# -----------------------------------------------------------------------
# D1.1 PENGAMBILAN
# -----------------------------------------------------------------------
def fetch_dividends(ticker, flags):
    """
    Ambil Series dividen mentah dari yfinance.
    Tidak pernah melempar exception ke pemanggil.
    """
    try:
        tk = yf.Ticker(ticker)
        div = tk.dividends
    except Exception as exc:
        flags.missing("Dividend history",
                      f"Failed to fetch data ({type(exc).__name__}).")
        return None

    if div is None or len(div) == 0:
        flags.missing("Dividend history",
                      "yfinance did not return a single dividend payment.")
        return None

    div = pd.to_numeric(div, errors="coerce").dropna()
    div = div[div > 0]
    if len(div) == 0:
        flags.missing("Dividend history", "Every dividend value is zero or invalid.")
        return None
    return div


# -----------------------------------------------------------------------
# D1.2 AGREGASI DAN METRIK
# -----------------------------------------------------------------------
def build_dividend_history(ticker, flags, current_year=None):
    """
    Bangun profil dividen tahunan lengkap dengan metrik turunannya.

    Mengembalikan (profil, ok). `ok` False kalau data tidak cukup untuk
    dianalisis sama sekali.
    """
    S = DDM_SCREENING
    cur_year = current_year or datetime.now().year

    div = fetch_dividends(ticker, flags)
    if div is None:
        return None, False

    # ---- agregasi ke tahun kalender ----
    try:
        years = div.index.year
    except AttributeError:
        flags.missing("Dividend history", "The date index could not be read.")
        return None, False

    annual_all = div.groupby(years).sum().sort_index()
    annual_all.index = annual_all.index.astype(int)

    # ---- pisahkan tahun berjalan ----
    ytd = float(annual_all.get(cur_year, 0.0))
    n_pay_ytd = int((div.index.year == cur_year).sum())
    annual = annual_all[annual_all.index < cur_year]

    if len(annual) == 0:
        flags.missing("Dividend history",
                      "No complete calendar year with a dividend payment.")
        return None, False

    # ---- rekam jejak dalam jendela lookback ----
    lookback = S["dividend_lookback_years"]
    window_years = list(range(cur_year - lookback, cur_year))   # tahun lengkap
    paid_flags = {y: float(annual.get(y, 0.0)) > 0 for y in window_years}
    years_paid = int(sum(paid_flags.values()))
    latest_complete_year = cur_year - 1
    latest_paid = bool(paid_flags.get(latest_complete_year, False))

    # Tahun yang terlewat di tengah rekam jejak
    skipped = [y for y, p in paid_flags.items() if not p]

    # ---- deret untuk analisis pertumbuhan ----
    # Hanya tahun yang benar-benar membayar, dan hanya dalam jendela
    # lookback, supaya sejarah lama yang sudah tidak relevan tidak ikut.
    series = annual[annual.index >= cur_year - lookback]
    series = series[series > 0]

    # ---- pertumbuhan ----
    yoy = series.pct_change().dropna()
    g_median = float(np.median(yoy)) if len(yoy) else np.nan
    g_mean = float(np.mean(yoy)) if len(yoy) else np.nan
    g_sd = float(np.std(yoy, ddof=1)) if len(yoy) > 1 else np.nan

    if len(series) >= 2 and series.iloc[0] > 0:
        n_periods = len(series) - 1
        cagr = float((series.iloc[-1] / series.iloc[0]) ** (1 / n_periods) - 1)
    else:
        cagr = np.nan

    # ---- volatilitas ----
    if len(series) > 1 and float(series.mean()) > 0:
        cv = float(series.std(ddof=1) / series.mean())
    else:
        cv = np.nan

    # ---- deteksi dividen spesial ----
    specials = []
    if len(series) >= 3:
        for y in series.index:
            others = series.drop(index=y)
            med_other = float(others.median())
            if med_other > 0 and float(series[y]) > med_other * S["special_div_multiple"]:
                specials.append(int(y))
    if specials:
        flags.warn("Special dividend",
                   f"Year(s) {specials} have DPS well above the median of other "
                   f"years, possibly a special or one-off distribution that "
                   f"distorts the trend. Growth uses the median to stay resilient "
                   f"to this, but the figure should be checked manually.")

    # ---- track record flag ----
    if skipped:
        flags.warn("Dividend consistency",
                   f"No payment in year(s) {sorted(skipped)} within the last "
                   f"{lookback}-year window.")
    if np.isfinite(cv) and cv > S["warn_dps_cv"]:
        flags.warn("Dividend volatility",
                   f"DPS coefficient of variation is {cv:.2f}. The dividend "
                   f"stream is fairly irregular, weakening the stable-growth "
                   f"assumption.")

    profile = {
        "annual_all":      annual_all,          # termasuk tahun berjalan
        "annual":          annual,              # hanya tahun lengkap
        "series":          series,              # jendela lookback, yang membayar
        "current_year":    cur_year,
        "ytd_dps":         ytd,
        "ytd_payments":    n_pay_ytd,
        "latest_year":     int(series.index[-1]) if len(series) else None,
        "latest_dps":      float(series.iloc[-1]) if len(series) else np.nan,
        "years_paid":      years_paid,
        "years_in_window": lookback,
        "latest_paid":     latest_paid,
        "skipped_years":   sorted(skipped),
        "g_median":        g_median,
        "g_mean":          g_mean,
        "g_sd":            g_sd,
        "cagr":            cagr,
        "cv":              cv,
        "special_years":   specials,
        "n_payments_total": int(len(div)),
        "payments_per_year": (float(len(div[div.index.year < cur_year]) / len(annual))
                              if len(annual) else np.nan),
    }
    return profile, True


# -----------------------------------------------------------------------
# D1.3 TABEL TAMPILAN
# -----------------------------------------------------------------------
def dividend_table(profile):
    """Annual DPS history with year-over-year growth, last 10 years only."""
    s = profile["annual"].tail(10)
    df = pd.DataFrame({"Year": s.index.astype(int), "DPS (IDR)": s.values})
    df["YoY"] = s.pct_change().values
    df["YoY"] = df["YoY"].apply(
        lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "n/a")
    df["DPS (IDR)"] = df["DPS (IDR)"].round(2)
    df["Note"] = [
        "special dividend?" if int(y) in profile["special_years"] else ""
        for y in s.index
    ]
    return df


def dividend_summary(profile):
    """Summary of dividend metrics."""
    rows = [
        ("Years paid within window",
         f"{profile['years_paid']} of {profile['years_in_window']} years"),
        ("Payment frequency",
         f"{profile['payments_per_year']:.1f} times per year"
         if np.isfinite(profile["payments_per_year"]) else "n/a"),
        ("DPS, latest complete year",
         f"IDR {profile['latest_dps']:,.2f} ({profile['latest_year']})"
         if np.isfinite(profile["latest_dps"]) else "n/a"),
        ("DPS, year to date",
         f"IDR {profile['ytd_dps']:,.2f} ({profile['ytd_payments']} payments)"
         if profile["ytd_dps"] > 0 else "no payment yet"),
        ("DPS growth (median YoY)",
         f"{profile['g_median']*100:.2f}%" if np.isfinite(profile["g_median"]) else "n/a"),
        ("DPS growth (CAGR)",
         f"{profile['cagr']*100:.2f}%" if np.isfinite(profile["cagr"]) else "n/a"),
        ("DPS volatility (CV)",
         f"{profile['cv']:.2f}" if np.isfinite(profile["cv"]) else "n/a"),
    ]
    return pd.DataFrame(rows, columns=["Metric", "Value"])
