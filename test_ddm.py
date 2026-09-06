"""
=============================================================================
TEST DDM - VALIDASI MATEMATIKA DENGAN DATA SINTETIS
=============================================================================
TUJUAN  : Menguji Section D1 sampai D9 tanpa memanggil yfinance. Data
          laporan keuangan dan dividen dibuat manual dengan angka yang
          hasilnya bisa dihitung tangan, lalu dibandingkan dengan keluaran
          model.

          Jalankan dengan: python test_ddm.py
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A
from config import ASSUMPTIONS as BASE
from s01_fetch import CompanyData
from s02_lineitems import build_history, latest_snapshot
from s06_wacc import cost_of_equity
from d02_screening import run_ddm_screening
from d03_drivers import compute_payout, compute_roe, build_ddm_drivers
from d04_forecast import project_dividends
from d05_terminal import terminal_value
from d06_valuation import discount_dividends, make_ddm_recommendation
from d07_crosscheck import fair_pbv, residual_income, compare_methods
from d08_sensitivity import sensitivity_grid
from d09_scenario import run_scenarios

CUR_YEAR = 2026
SHARES = 10_000_000_000.0        # 10 miliar lembar


# -----------------------------------------------------------------------
# EMITEN SINTETIS
# Laba bersih tumbuh 8% per tahun, ekuitas tumbuh sejalan laba ditahan,
# payout 40% konsisten, DPS tumbuh 8% per tahun.
# -----------------------------------------------------------------------
def make_fake_dividend_company(payout=0.40, ni_growth=0.08):
    years = pd.to_datetime([f"{y}-12-31" for y in range(2021, 2026)])
    ni0 = 1_000e9
    ni = np.array([ni0 * (1 + ni_growth) ** i for i in range(5)])

    # Ekuitas: awal 8000bn, tumbuh sebesar laba ditahan tiap tahun
    eq = [8_000e9]
    for i in range(1, 5):
        eq.append(eq[-1] + ni[i - 1] * (1 - payout))
    eq = np.array(eq)

    income = pd.DataFrame(index=[
        "Total Revenue", "Cost Of Revenue", "Operating Income",
        "Pretax Income", "Tax Provision", "Net Income", "Interest Expense",
    ], columns=years, dtype=float)
    rev = ni / 0.15
    income.loc["Total Revenue"] = rev
    income.loc["Cost Of Revenue"] = rev * 0.55
    income.loc["Operating Income"] = ni / 0.78
    income.loc["Pretax Income"] = ni / 0.78
    income.loc["Tax Provision"] = ni / 0.78 * 0.22
    income.loc["Net Income"] = ni
    income.loc["Interest Expense"] = 200e9

    balance = pd.DataFrame(index=[
        "Cash And Cash Equivalents", "Total Debt", "Stockholders Equity",
        "Minority Interest", "Accounts Receivable", "Inventory",
        "Accounts Payable", "Net PPE", "Total Assets",
    ], columns=years, dtype=float)
    balance.loc["Cash And Cash Equivalents"] = rev * 0.10
    balance.loc["Total Debt"] = 3_000e9
    balance.loc["Stockholders Equity"] = eq
    balance.loc["Minority Interest"] = 0.0
    balance.loc["Accounts Receivable"] = rev * 0.08
    balance.loc["Inventory"] = rev * 0.05
    balance.loc["Accounts Payable"] = rev * 0.06
    balance.loc["Net PPE"] = rev * 0.30
    balance.loc["Total Assets"] = eq * 1.6

    cashflow = pd.DataFrame(index=[
        "Operating Cash Flow", "Capital Expenditure",
        "Depreciation And Amortization",
    ], columns=years, dtype=float)
    cashflow.loc["Depreciation And Amortization"] = rev * 0.04
    cashflow.loc["Capital Expenditure"] = -rev * 0.05
    cashflow.loc["Operating Cash Flow"] = ni * 1.2

    d = CompanyData("TESTDIV.JK")
    d.name = "PT Uji Dividen Tbk"
    d.sector = "Financial Services"
    d.industry = "Banks - Regional"
    d.income = income
    d.balance = balance
    d.cashflow = cashflow
    d.shares_outstanding = SHARES
    d.price = 1_000.0
    d.market_cap = d.price * SHARES
    d.trailing_pe = d.market_cap / float(ni[-1])
    d.fetch_ok = True
    return d, ni, eq


def make_dividend_profile(ni, payout, shares, ni_growth):
    """
    Dividen dibayar tahun T dari laba tahun buku T-1 (konvensi lagged).
    Tahun bayar 2022..2026, dengan 2026 sebagai tahun berjalan.
    """
    from utils import FlagLog
    # DPS_T = payout x EPS_(T-1)
    dps = {}
    for i, year_pay in enumerate(range(2022, 2027)):
        eps_prev = ni[i] / shares          # ni[0] = FY2021 -> dibayar 2022
        dps[year_pay] = payout * eps_prev

    annual_all = pd.Series(dps).sort_index()
    annual = annual_all[annual_all.index < CUR_YEAR]
    series = annual[annual.index >= CUR_YEAR - 5]
    yoy = series.pct_change().dropna()

    return {
        "annual_all": annual_all,
        "annual": annual,
        "series": series,
        "current_year": CUR_YEAR,
        "ytd_dps": float(annual_all.get(CUR_YEAR, 0.0)),
        "ytd_payments": 1,
        "latest_year": int(series.index[-1]),
        "latest_dps": float(series.iloc[-1]),
        "years_paid": int((series > 0).sum()),
        "years_in_window": 5,
        "latest_paid": True,
        "skipped_years": [],
        "g_median": float(np.median(yoy)),
        "g_mean": float(np.mean(yoy)),
        "g_sd": float(np.std(yoy, ddof=1)),
        "cagr": float((series.iloc[-1] / series.iloc[0]) ** (1 / (len(series) - 1)) - 1),
        "cv": float(series.std(ddof=1) / series.mean()),
        "special_years": [],
        "n_payments_total": len(annual_all),
        "payments_per_year": 1.0,
    }


def main():
    print("=" * 74)
    print("VALIDASI MATEMATIKA DDM - DATA SINTETIS")
    print("=" * 74)

    PAYOUT, NIG = 0.40, 0.08
    d, ni, eq = make_fake_dividend_company(PAYOUT, NIG)
    hist, ok = build_history(d)
    assert ok, "build_history gagal"
    snap = latest_snapshot(hist)
    dp = make_dividend_profile(ni, PAYOUT, SHARES, NIG)

    # ---- D1 ----
    print("\n[D1] Riwayat dividen")
    print(f"  DPS per tahun bayar : "
          f"{ {int(k): round(v,2) for k,v in dp['annual'].items()} }")
    print(f"  Median YoY growth   : {dp['g_median']*100:>7.2f}%  (harap 8.00)")
    print(f"  Tahun berjalan {CUR_YEAR}  : dibuang dari analisis, DPS "
          f"{dp['ytd_dps']:.2f}")
    assert abs(dp["g_median"] - NIG) < 1e-9, "growth DPS harus sama dengan growth laba"

    # ---- D3a payout dan ROE ----
    po = compute_payout(hist, dp, SHARES, d.flags)
    assert po is not None
    print("\n[D3a] Payout dan ROE")
    print(f"  Payout lagged       : {po['payout_lagged']*100:>7.2f}%  (harap 40.00)")
    print(f"  Payout kontemporer  : {po['payout_contemporaneous']*100:>7.2f}%  "
          f"(harap {40/1.08:.2f}, lebih rendah karena EPS sudah tumbuh)")
    print(f"  Basis dipakai       : {po['payout_basis']}")
    assert abs(po["payout_lagged"] - PAYOUT) < 1e-9, "payout lagged harus tepat 40%"
    assert po["payout_lagged"] > po["payout_contemporaneous"], \
        "lagged harus lebih tinggi dari kontemporer saat laba tumbuh"

    roe = compute_roe(hist, d.flags)
    print(f"  ROE median          : {roe['roe']*100:>7.2f}%  ({roe['n_obs']} observasi)")
    # cek manual ROE tahun terakhir
    roe_manual = ni[-1] / ((eq[-2] + eq[-1]) / 2)
    print(f"  Cek manual ROE FY25 : {roe_manual*100:>7.2f}%")
    assert roe["n_obs"] == 4

    # ---- D2 screening ----
    scr = run_ddm_screening(d, hist, dp, po)
    print("\n[D2] Screening")
    print(scr["detail"].to_string(index=False))
    print(f"  STATUS: {scr['status']}")
    assert scr["passed"], "emiten sintetis seharusnya lolos"

    # ---- D3b driver ----
    drv = build_ddm_drivers(hist, dp, po, roe, d.flags)
    print("\n[D3b] Driver")
    print(f"  Payout              : {drv['payout']*100:>7.2f}%")
    print(f"  Retention (b)       : {drv['retention']*100:>7.2f}%  (harap 60.00)")
    print(f"  ROE                 : {drv['roe']*100:>7.2f}%")
    print(f"  SGR = b x ROE       : {drv['sgr']*100:>7.2f}%")
    print(f"  Growth historis     : {drv['g_hist']*100:>7.2f}%")
    print(f"  Growth DIPAKAI      : {drv['g_used']*100:>7.2f}%  = min(historis, SGR)")
    assert abs(drv["retention"] - 0.60) < 1e-9
    assert abs(drv["sgr"] - drv["retention"] * drv["roe"]) < 1e-12, "SGR harus b x ROE"
    assert abs(drv["g_used"] - min(drv["g_hist"], drv["sgr"])) < 1e-12, \
        "growth harus min(historis, SGR)"

    # ---- S6 Cost of Equity ----
    beta = {"beta_raw": 1.05, "beta_adj": 1.2, "r_squared": 0.35,
            "n_obs": 248, "source": "dipaksa untuk pengujian"}
    kep = cost_of_equity(beta["beta_adj"])
    ke = kep["ke"]
    ke_manual = BASE["risk_free_rate"] + 1.2 * BASE["equity_risk_premium"] + BASE["size_premium"]
    print("\n[S6] Cost of Equity (dipakai ulang dari s06_wacc)")
    print(f"  Ke = {BASE['risk_free_rate']*100:.2f}% + 1.20 x "
          f"{BASE['equity_risk_premium']*100:.2f}% = {ke*100:.2f}%")
    print(f"  Cek manual          : {ke_manual*100:.2f}%")
    assert abs(ke - ke_manual) < 1e-12

    # ---- D4 proyeksi ----
    G_TERM = 0.04
    proj, fsum = project_dividends(drv, years=5, terminal_g=G_TERM, flags=d.flags)
    print("\n[D4] Proyeksi DPS")
    print(proj.round(4).to_string())
    g1 = drv["g_used"]
    dps1_manual = drv["dps_base"] * (1 + g1)
    print(f"\n  Cek manual DPS th-1 : {dps1_manual:.4f}")
    print(f"  Model DPS th-1      : {proj.loc[1,'DPS']:.4f}")
    assert abs(proj.loc[1, "DPS"] - dps1_manual) < 1e-9
    # fade harus monoton menurun kalau g1 > g_term
    if g1 > fsum["g_terminal"]:
        assert all(np.diff(proj["Growth"].values) < 1e-12), "fade harus menurun"
    assert abs(proj.loc[5, "Growth"] - fsum["g_terminal"]) < 1e-12, \
        "growth tahun terakhir harus sama dengan terminal"

    # ---- D5 terminal value ----
    payout_final = float(proj["Payout"].iloc[-1])
    tv = terminal_value(fsum["dps_final"], ke, terminal_g=fsum["g_terminal"],
                        roe_terminal=drv["roe"], payout_final=payout_final,
                        flags=d.flags)
    tv_manual = fsum["dps_final"] * (1 + fsum["g_terminal"]) / (ke - fsum["g_terminal"])
    payout_star_manual = 1 - fsum["g_terminal"] / drv["roe"]
    print("\n[D5] Terminal Value")
    print(f"  TV model            : {tv['tv_nominal']:.4f}")
    print(f"  TV manual           : {tv_manual:.4f}")
    print(f"  Payout konsisten    : {tv['payout_consistent']*100:.2f}%  "
          f"(manual {payout_star_manual*100:.2f}%)")
    print(f"  Payout proyeksi     : {payout_final*100:.2f}%")
    assert tv["valid"]
    assert abs(tv["tv_nominal"] - tv_manual) < 1e-9
    assert abs(tv["payout_consistent"] - payout_star_manual) < 1e-12

    # ---- D6 valuasi ----
    val = discount_dividends(proj, tv, ke, d, d.flags)
    pv_manual = sum(float(proj.loc[t, "DPS"]) / (1 + ke) ** t for t in range(1, 6))
    pv_tv_manual = tv_manual / (1 + ke) ** 5
    print("\n[D6] Valuasi")
    print(f"  PV dividen eksplisit: {val['pv_explicit']:.4f}  (manual {pv_manual:.4f})")
    print(f"  PV terminal value   : {val['pv_terminal']:.4f}  (manual {pv_tv_manual:.4f})")
    print(f"  Nilai wajar/saham   : IDR {val['fair_value_per_share']:,.2f}")
    print(f"  Kontribusi TV       : {val['tv_share_of_value']*100:.1f}%")
    print(f"  Div yield saat ini  : {val['dividend_yield_current']*100:.2f}%")
    assert abs(val["pv_explicit"] - pv_manual) < 1e-9, "diskonto akhir tahun"
    assert abs(val["pv_terminal"] - pv_tv_manual) < 1e-9
    assert abs(val["fair_value_per_share"] - (pv_manual + pv_tv_manual)) < 1e-9

    rec = make_ddm_recommendation(val, d.flags)
    print(f"  Harga IDR {val['market_price']:,.0f} vs fair value "
          f"IDR {val['fair_value_per_share']:,.0f}")
    print(f"  Upside {rec['upside']*100:+.1f}% -> {rec['rating']}")

    # ---- D7 cross-check ----
    bvps = snap["equity"] / SHARES
    pbv = fair_pbv(drv["roe"], ke, fsum["g_terminal"], bvps, d.flags)
    ri = residual_income(bvps, drv["roe"], ke, fsum["g_terminal"],
                         drv["retention"], years=5, flags=d.flags)
    pbv_manual = (drv["roe"] - fsum["g_terminal"]) / (ke - fsum["g_terminal"])
    print("\n[D7] Cross-check")
    print(f"  BVPS                : IDR {bvps:,.2f}")
    print(f"  Fair P/BV model     : {pbv['fair_pbv']:.4f}x  (manual {pbv_manual:.4f}x)")
    print(f"  Fair value P/BV     : IDR {pbv['fair_value']:,.2f}")
    print(f"  Residual income FV  : IDR {ri['fair_value']:,.2f}")
    assert abs(pbv["fair_pbv"] - pbv_manual) < 1e-12
    cc = compare_methods(val["fair_value_per_share"], pbv, ri, drv, d.price, d.flags)
    print()
    print(cc["table"].to_string(index=False))

    # ---- D8 sensitivity ----
    sens = sensitivity_grid(proj, ke, fsum["g_terminal"], drv, d)
    print("\n[D8] Sensitivity nilai wajar per saham (IDR)")
    print(sens["fair_value"].to_string())
    fv = sens["fair_value"].astype(float)
    assert fv.iloc[0, 0] > fv.iloc[-1, 0], "nilai harus turun saat Ke naik"
    assert fv.iloc[0, -1] > fv.iloc[0, 0], "nilai harus naik saat g naik"
    print(f"  Sel valid {sens['stats']['n_valid']}/{sens['stats']['n_cells']}")

    # ---- D9 skenario ----
    sc, _ = run_scenarios(drv, d, ke, years=5, g_base=fsum["g_terminal"])
    print("\n[D9] Skenario")
    print(sc.to_string())
    bull = sc.loc["BULL", "Fair value"]
    bear = sc.loc["BEAR", "Fair value"]
    if np.isfinite(bull) and np.isfinite(bear):
        assert bull > bear, "BULL harus di atas BEAR"

    # ---- flag ----
    print("\n[Flag data]")
    print(d.flags.render())

    print("\n" + "=" * 74)
    print("SELURUH ASSERTION DDM LULUS")
    print("=" * 74)


if __name__ == "__main__":
    main()
