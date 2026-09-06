"""
=============================================================================
DDM CONFIG - PUSAT ASUMSI DAN THRESHOLD MODEL DIVIDEN
=============================================================================
TUJUAN  : Menyimpan seluruh asumsi dan batas screening khusus DDM/GGM.
          Asumsi cost of capital (risk-free, ERP, beta) TIDAK diduplikasi
          di sini, melainkan diambil dari config.py milik tool DCF supaya
          kedua tool memakai satu sumber kebenaran yang sama.

RUMUS   : Tidak ada. File konstanta.

OUTPUT  : DDM_ASSUMPTIONS dan DDM_SCREENING.
=============================================================================
"""

from config import ASSUMPTIONS as BASE_ASSUMPTIONS

# -----------------------------------------------------------------------
# A. ASUMSI YANG DIWARISI DARI TOOL DCF (jangan diduplikasi)
# -----------------------------------------------------------------------
# risk_free_rate, equity_risk_premium, size_premium, beta_*, tax_*
# semuanya dibaca langsung dari config.py lewat s06_wacc.cost_of_equity().

DDM_ASSUMPTIONS = {
    # -------------------------------------------------------------------
    # B. PROYEKSI DIVIDEN
    # -------------------------------------------------------------------
    "forecast_years":        5,       # slider 5 - 10
    "terminal_growth":       0.040,   # 4.00%  slider 0.000 - 0.060

    # Diskonto akhir tahun, BUKAN mid-year seperti tool DCF.
    # Alasan: dividen adalah pembayaran diskret pada tanggal tertentu,
    # bukan arus kas yang mengalir merata sepanjang tahun. Konvensi
    # akhir tahun juga sedikit lebih konservatif.
    "mid_year_convention":   False,

    # Batas wajar hasil hitung historis
    "dps_growth_floor":     -0.150,   # -15%
    "dps_growth_cap":        0.250,   # +25%
    "roe_floor":             0.010,   # 1%, di bawah ini SGR tidak bermakna
    "roe_cap":               0.400,   # 40%, di atas ini kemungkinan distorsi
    "payout_floor":          0.050,   # 5%
    "payout_cap":            1.100,   # 110%

    # -------------------------------------------------------------------
    # C. SPREAD MINIMUM Ke DIKURANGI g
    # -------------------------------------------------------------------
    # Lebih longgar dari tool DCF (400bps) karena Ke secara struktural
    # lebih tinggi dari WACC, sehingga spread yang sama lebih mudah
    # tercapai. 300bps tetap cukup untuk menjaga Gordon Growth stabil.
    "min_ke_g_spread":       0.030,   # 300bps

    # Terminal growth tidak boleh melampaui growth tahun pertama, supaya
    # fade tidak justru mengakselerasi pertumbuhan menuju perpetuitas.
    "cap_terminal_at_g1":    True,

    # -------------------------------------------------------------------
    # D. KONSISTENSI TERMINAL
    # -------------------------------------------------------------------
    # Pada fase stabil berlaku g = b x ROE, sehingga payout terminal yang
    # konsisten adalah 1 - g/ROE. Kalau payout proyeksi menyimpang lebih
    # dari toleransi ini, model tidak konsisten secara internal.
    "terminal_payout_tolerance": 0.15,   # 15 poin persentase

    # -------------------------------------------------------------------
    # E. SKENARIO DAN SENSITIVITY
    # -------------------------------------------------------------------
    "scenario_sd_multiple":  1.0,
    "scenario_g_shift":      0.005,
    "min_growth_sd":         0.030,   # lantai SD, cegah skenario degenerate
    "min_payout_sd":         0.050,
    "sens_ke_step":          0.005,   # grid Ke +/- 50bps
    "sens_g_step":           0.0025,  # grid g +/- 25bps
    "sens_steps":            2,       # grid 5x5

    # -------------------------------------------------------------------
    # F. AMBANG REKOMENDASI (disamakan dengan tool DCF)
    # -------------------------------------------------------------------
    "buy_threshold":         0.10,
    "sell_threshold":       -0.10,
    "review_upside_threshold":    1.00,   # upside > 100% -> Review Required
    "review_downside_threshold": -0.50,   # downside > 50% -> Review Required
}


# -----------------------------------------------------------------------
# G. GATE SCREENING DDM
# -----------------------------------------------------------------------
DDM_SCREENING = {
    # Gate 1 - Rekam jejak dividen
    "min_dividend_years":      3,     # minimal 3 tahun lengkap membayar
    "dividend_lookback_years": 5,     # dari 5 tahun lengkap terakhir
    "require_latest_year_paid": True, # tahun lengkap terakhir WAJIB bayar

    # Gate 2 - Kecukupan laporan keuangan
    "min_annual_years":        4,

    # Gate 3 - Kualitas laba
    "min_ni_positive_years":   2,     # laba bersih positif >= 2 dari 3 tahun
    "ni_lookback_years":       3,
    "require_latest_ni_positive": True,

    # Gate 4 - Ekuitas
    "require_positive_equity": True,

    # Gate 5 - Ukuran
    "min_market_cap_idr":      1_000_000_000_000,   # IDR 1 triliun

    # Gate 6 - Payout ratio
    # Di bawah floor: dividen hanya token, nilai perusahaan sebagian besar
    # ada di laba ditahan, DDM akan understate parah.
    # Di atas cap: dividen dibayar melebihi laba, tidak berkelanjutan.
    "payout_min":              0.050,
    "payout_max":              1.100,

    # Gate 7 - Volatilitas dividen
    # Coefficient of variation = stdev / mean dari DPS tahunan.
    # Di atas batas ini aliran dividen terlalu tidak beraturan untuk
    # dimodelkan sebagai deret yang tumbuh stabil.
    "max_dps_cv":              1.200,
    "warn_dps_cv":             0.600,

    # Gate 8 - Deteksi dividen spesial
    # Kalau satu tahun DPS-nya lebih dari sekian kali median tahun lain,
    # kemungkinan ada dividen spesial yang mendistorsi tren.
    "special_div_multiple":    2.000,
}


# -----------------------------------------------------------------------
# H. DISCLAIMER
# -----------------------------------------------------------------------
DDM_DISCLAIMER = (
    "Disclaimer On. This output is generated by an automated model based on "
    "dividend history and public financial statements from yfinance, plus "
    "user-entered assumptions. The figures have not been verified against "
    "official financial statements or AGM resolutions, do not account for "
    "corporate actions, and do not constitute investment advice. For internal "
    "analysis purposes only."
)
