"""
=============================================================================
DDM REPORT - PERAKITAN LAPORAN
=============================================================================
TUJUAN  : Menyusun seluruh keluaran section menjadi satu laporan berurutan,
          dengan flag data ditempatkan di posisi yang tidak bisa dilewati
          pembaca.

RUMUS   : Tidak ada. Ini lapisan penyajian.
OUTPUT  : String laporan lengkap, diakhiri disclaimer.
=============================================================================
"""

import numpy as np

from ddm_config import DDM_ASSUMPTIONS as A, DDM_DISCLAIMER
from d01_dividends import dividend_table, dividend_summary
from d03_drivers import ddm_drivers_table
from d04_forecast import projection_table
from d06_valuation import value_bridge_table
from d09_scenario import scenario_table

LINE = "=" * 78
THIN = "-" * 78


def _h(title):
    return f"\n{LINE}\n{title}\n{LINE}"


def _pct(v, dp=2, sign=False):
    if v is None or not np.isfinite(v):
        return "n/a"
    return f"{v*100:+.{dp}f}%" if sign else f"{v*100:.{dp}f}%"


def render_ddm_report(result):
    p = []
    d = result["data"]

    # ---------------- header ----------------
    p.append(_h(f"DIVIDEND DISCOUNT MODEL - {d.ticker} - {d.name}"))
    p.append(f"Sektor          : {d.sector or 'n/a'} / {d.industry or 'n/a'}")
    p.append(f"Harga pasar     : IDR {d.price:,.0f}" if np.isfinite(d.price)
             else "Harga pasar     : n/a")
    p.append(f"Market cap      : IDR {d.market_cap/1e12:,.2f} tn"
             if np.isfinite(d.market_cap) else "Market cap      : n/a")
    p.append(f"Mata uang lapkeu: {d.original_currency}"
             + (f" (dikonversi ke IDR @ {d.fx_rate:,.0f})" if d.fx_rate != 1.0 else ""))
    p.append("Metode          : Dividend Discount Model, Gordon Growth")
    p.append("Diskonto        : Cost of Equity (CAPM), BUKAN WACC")

    # ---------------- D1 riwayat dividen ----------------
    dp = result.get("div_profile")
    if dp is not None:
        p.append(_h("SECTION D1 - RIWAYAT DIVIDEN"))
        p.append(dividend_table(dp).to_string(index=False))
        p.append(THIN)
        p.append(dividend_summary(dp).to_string(index=False))

    # ---------------- D2 screening ----------------
    scr = result["screening"]
    p.append(_h("SECTION D2 - SCREENING KELAYAKAN MODEL DDM"))
    if hasattr(scr.get("detail"), "empty") and not scr["detail"].empty:
        p.append(scr["detail"].to_string(index=False))
        p.append("")
    p.append(f"STATUS: {scr['status']}")

    if not scr["passed"]:
        p.append(_h("FLAG DATA"))
        p.append(d.flags.render())
        p.append(_h("DISCLAIMER"))
        p.append(DDM_DISCLAIMER)
        return "\n".join(p)

    drv = result["drivers"]
    ke_parts = result["ke_parts"]
    proj = result["projection"]
    fsum = result["forecast_summary"]
    tv = result["terminal"]
    val = result["valuation"]
    rec = result["recommendation"]

    # ---------------- flag ----------------
    p.append(_h("PERINGATAN KUALITAS DATA - BACA SEBELUM MEMAKAI ANGKA DI BAWAH"))
    p.append(d.flags.render())

    # ---------------- D3 driver ----------------
    p.append(_h("SECTION D3 - DRIVER DIVIDEN"))
    p.append(ddm_drivers_table(drv).to_string(index=False))
    po = result.get("payout_info")
    if po is not None and po.get("table") is not None:
        p.append(THIN)
        p.append("Rincian payout per tahun bayar:")
        t = po["table"].copy()
        for c in ["DPS", "EPS (t-1)", "EPS (t)"]:
            t[c] = t[c].round(2)
        for c in ["Payout lagged", "Payout kontemporer"]:
            t[c] = t[c].apply(lambda v: f"{v*100:.1f}%" if np.isfinite(v) else "n/a")
        p.append(t.to_string(index=False))

    # ---------------- S5, S6 cost of equity ----------------
    b = result["beta"]
    p.append(_h("SECTION S5-S6 - BETA DAN COST OF EQUITY"))
    p.append(f"Metode beta                : {b['source']}, {b['n_obs']} observasi")
    p.append(f"Beta raw                   : {b['beta_raw']:.3f}"
             if np.isfinite(b["beta_raw"]) else "Beta raw                   : n/a")
    p.append(f"R-squared regresi          : {b['r_squared']:.3f}"
             if np.isfinite(b["r_squared"]) else "R-squared regresi          : n/a")
    p.append(f"Beta dipakai               : {ke_parts['beta']:.3f}")
    p.append(THIN)
    p.append(f"Risk-free rate             : {_pct(ke_parts['rf'])}")
    p.append(f"Equity Risk Premium        : {_pct(ke_parts['erp'])}")
    p.append(f"Size premium               : {_pct(ke_parts['size_premium'])}")
    p.append(f"COST OF EQUITY (CAPM)      : {_pct(ke_parts['ke'])}")

    # ---------------- D4 proyeksi ----------------
    p.append(_h("SECTION D4 - PROYEKSI DIVIDEN PER SAHAM"))
    p.append(projection_table(proj).to_string())
    p.append(THIN)
    p.append(f"Pertumbuhan tahun 1        : {_pct(fsum['g1'])}")
    p.append(f"Terminal growth            : {_pct(fsum['g_terminal'])}")
    p.append(f"Payout basis               : {_pct(fsum['payout_base'], 1)}")

    # ---------------- D5 terminal ----------------
    p.append(_h("SECTION D5 - TERMINAL VALUE"))
    p.append(f"Cost of Equity             : {_pct(tv['ke'])}")
    p.append(f"Terminal growth            : {_pct(tv['terminal_growth'])}")
    p.append(f"Spread (Ke - g)            : {_pct(tv['ke'] - tv['terminal_growth'])}")
    p.append(f"DPS tahun terakhir         : IDR {tv['dps_final']:,.2f}")
    p.append(f"Terminal Value nominal     : IDR {tv['tv_nominal']:,.2f} per saham")
    p.append(f"Payout konsisten (1 - g/ROE): {_pct(tv['payout_consistent'], 1)}")
    p.append(f"Payout proyeksi akhir       : {_pct(tv['payout_projected'], 1)}")
    if np.isfinite(tv.get("implied_terminal_pe", np.nan)):
        p.append(f"Implied terminal P/E        : {tv['implied_terminal_pe']:.2f}x")

    # ---------------- D6 valuasi ----------------
    p.append(_h("SECTION D6 - NILAI WAJAR PER SAHAM"))
    p.append(value_bridge_table(val).to_string(index=False))
    p.append(THIN)
    p.append(f"Kontribusi Terminal Value  : {_pct(val['tv_share_of_value'], 1)}")
    p.append(f"Dividend yield saat ini    : {_pct(val['dividend_yield_current'])}")
    p.append(f"Dividend yield di fair value: {_pct(val['dividend_yield_at_fv'])}")

    p.append(_h("KEPUTUSAN"))
    p.append(f"Harga pasar                : IDR {val['market_price']:,.0f}")
    p.append(f"Nilai wajar (base)         : IDR {val['fair_value_per_share']:,.0f}")
    p.append(f"Upside / downside          : {_pct(rec['upside'], 1, sign=True)}")
    p.append(f"REKOMENDASI                : {rec['rating']}")
    if rec.get("review_required"):
        p.append("")
        p.append(rec["reason_override"])
    else:
        p.append(f"Ambang: BUY jika upside > {A['buy_threshold']*100:.0f}%, "
                 f"SELL jika < {A['sell_threshold']*100:.0f}%, di antaranya HOLD.")

    # ---------------- D7 cross-check ----------------
    cc = result.get("crosscheck")
    if cc is not None:
        p.append(_h("SECTION D7 - CROSS-CHECK METODE BERBASIS EKUITAS"))
        p.append(f"BVPS                       : IDR {result['bvps']:,.2f}"
                 if np.isfinite(result.get("bvps", np.nan)) else "BVPS : n/a")
        p.append(f"P/BV saat ini              : {result['current_pbv']:.2f}x"
                 if np.isfinite(result.get("current_pbv", np.nan)) else "P/BV saat ini : n/a")
        p.append(THIN)
        p.append(cc["table"].to_string(index=False))
        if cc["diagnosis"]:
            p.append(THIN)
            p.append("DIAGNOSIS SELISIH:")
            p.append(cc["diagnosis"])

    # ---------------- D8 sensitivity ----------------
    sens = result["sensitivity"]
    p.append(_h("SECTION D8 - SENSITIVITY: NILAI WAJAR PER SAHAM (IDR)"))
    p.append("Baris = Cost of Equity, Kolom = Terminal growth")
    p.append(sens["fair_value"].to_string())
    p.append("")
    p.append("Upside terhadap harga pasar (%)")
    p.append(sens["upside"].to_string())
    st = sens["stats"]
    p.append(THIN)
    p.append(f"Rentang nilai wajar: IDR {st['min']:,.0f} sampai IDR {st['max']:,.0f}, "
             f"median IDR {st['median']:,.0f} ({st['n_valid']}/{st['n_cells']} sel valid)")

    # ---------------- D9 skenario ----------------
    p.append(_h("SECTION D9 - SKENARIO"))
    p.append(scenario_table(result["scenarios"]).to_string())

    # ---------------- keterbatasan ----------------
    p.append(_h("KETERBATASAN MODEL"))
    p.append("- DDM hanya menangkap nilai yang benar-benar dibagikan sebagai kas.")
    p.append("  Laba ditahan yang tidak pernah dibagikan tidak muncul sebagai nilai,")
    p.append("  sehingga emiten berpayout rendah akan cenderung understate.")
    p.append("- Riwayat dividen diagregasi per tahun kalender berdasarkan tanggal")
    p.append("  ex-dividend, bukan per tahun buku yang disetujui RUPS.")
    p.append("- Payout ratio memakai konvensi lagged, dividen tahun T dipasangkan")
    p.append("  dengan laba tahun buku T-1. Emiten dengan kebijakan berbeda akan meleset.")
    p.append("- Dividen spesial dan pembagian satu kali tidak dipisahkan otomatis,")
    p.append("  hanya ditandai. Perlu pemeriksaan manual.")
    p.append("- Corporate action dan peristiwa setelah tanggal neraca tidak diperhitungkan.")
    p.append("- Shares outstanding memakai basis dasar, bukan fully diluted.")
    p.append("- Tidak memakai consensus estimate. Seluruh proyeksi dari data historis.")

    p.append(_h("DISCLAIMER"))
    p.append(DDM_DISCLAIMER)
    return "\n".join(p)
