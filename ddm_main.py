"""
=============================================================================
DDM MAIN - ORKESTRATOR
=============================================================================
TUJUAN  : Menjalankan seluruh section DDM secara berurutan. File ini tidak
          berisi rumus apa pun, hanya mengatur urutan pemanggilan.

MODUL YANG DIPAKAI ULANG DARI TOOL DCF (tidak ditulis dua kali):
    s01_fetch.fetch_company     pengambilan data dan konversi ke IDR
    s02_lineitems.build_history ekstraksi pos laporan keuangan
    s05_beta.compute_beta       regresi beta harian terhadap IHSG
    s06_wacc.cost_of_equity     CAPM, Ke = Rf + beta x ERP + size premium

    Yang TIDAK dipakai adalah tahap penggabungan WACC, karena DDM harus
    memakai Cost of Equity, bukan WACC.

URUTAN ALUR (tidak boleh dibalik):

    S1   Fetch data yfinance dan konversi ke IDR
    S2   Ekstraksi line item dan pemeriksaan kualitas data
    D1   Riwayat dividen dan agregasi tahunan
    D3a  Payout ratio dan ROE       (dibutuhkan gate payout di D2)
    D2   Screening kelayakan DDM    -> kalau gagal, BERHENTI
    D3b  Driver gabungan dengan pembatas Sustainable Growth Rate
    S5   Beta
    S6   Cost of Equity (CAPM)
    D4   Proyeksi DPS
    D5   Terminal value
    D6   Diskonto, nilai per saham, rekomendasi
    D7   Cross-check Fair P/BV dan Residual Income
    D8   Sensitivity Ke x terminal growth
    D9   Skenario Bull / Base / Bear

CARA PAKAI:
    from ddm_main import analyze_ddm, print_ddm_report
    r = analyze_ddm("BBCA")
    print_ddm_report(r)
=============================================================================
"""

import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

from ddm_config import DDM_ASSUMPTIONS, DDM_DISCLAIMER
from s01_fetch import fetch_company
from s02_lineitems import build_history, latest_snapshot
from s05_beta import compute_beta
from s06_wacc import cost_of_equity
from d01_dividends import build_dividend_history
from d02_screening import run_ddm_screening
from d03_drivers import compute_payout, compute_roe, build_ddm_drivers
from d04_forecast import project_dividends
from d05_terminal import terminal_value
from d06_valuation import discount_dividends, make_ddm_recommendation
from d07_crosscheck import fair_pbv, residual_income, compare_methods
from d08_sensitivity import sensitivity_grid
from d09_scenario import run_scenarios


# -----------------------------------------------------------------------
# LAYER FETCH (dipisah supaya bisa di-cache oleh UI)
# -----------------------------------------------------------------------
def fetch_ddm_bundle(raw_ticker):
    """
    Jalankan HANYA tahap yang butuh jaringan: S1, S2, D1, dan S5 (beta).
    Hasilnya bisa di-cache supaya menggeser slider tidak memicu fetch ulang.
    """
    data = fetch_company(raw_ticker)
    out = {"data": data, "hist": None, "snapshot": None,
           "div_profile": None, "beta": None, "stage": None, "ok": False}

    if not data.fetch_ok:
        out["stage"] = f"S1 - fetch failed: {data.fetch_error}"
        return out

    hist, li_ok = build_history(data)
    out["hist"] = hist
    if not li_ok:
        out["stage"] = "S2 - critical financial statement line items unavailable"
        return out
    out["snapshot"] = latest_snapshot(hist)

    div_profile, div_ok = build_dividend_history(data.ticker, data.flags)
    out["div_profile"] = div_profile
    if not div_ok:
        out["stage"] = "D1 - dividend history unavailable"
        # keep going so screening can still report the reason

    out["beta"] = compute_beta(data.ticker, data.flags)
    out["ok"] = True
    return out


# -----------------------------------------------------------------------
# PIPELINE UTAMA
# -----------------------------------------------------------------------
def analyze_ddm(raw_ticker, rf=None, erp=None, size_prem=None,
                years=None, terminal_g=None, bundle=None):
    """
    Jalankan seluruh pipeline DDM untuk satu emiten.
    Parameter rf, erp, size_prem, years, terminal_g adalah titik masuk slider.
    """
    A = DDM_ASSUMPTIONS
    N = int(years or A["forecast_years"])
    g_term = A["terminal_growth"] if terminal_g is None else terminal_g

    out = {"ticker": raw_ticker, "ok": False, "stage": None, "method": "DDM"}

    # ---------------- S1, S2, D1, S5 ----------------
    if bundle is None:
        bundle = fetch_ddm_bundle(raw_ticker)

    data = bundle["data"]
    out["data"] = data

    def _stop(stage, status):
        out["stage"] = stage
        out["screening"] = {
            "passed": False, "status": status, "detail": pd.DataFrame(),
            "failed_gates": [stage], "ticker": data.ticker, "name": data.name,
        }
        return out

    if not data.fetch_ok:
        return _stop("Fetch data", data.fetch_error or "Fetch failed.")

    hist = bundle["hist"]
    out["history"] = hist
    if hist is None or bundle["snapshot"] is None:
        return _stop("Line item completeness",
                     "Critical financial statement line items unavailable.")

    snapshot = bundle["snapshot"]
    out["snapshot"] = snapshot
    div_profile = bundle["div_profile"]
    out["div_profile"] = div_profile

    # ---------------- D3a: payout dan ROE ----------------
    payout_info, roe_info = None, None
    if div_profile is not None:
        payout_info = compute_payout(hist, div_profile,
                                     data.shares_outstanding, data.flags)
        roe_info = compute_roe(hist, data.flags)
    out["payout_info"] = payout_info
    out["roe_info"] = roe_info

    # ---------------- D2: screening ----------------
    scr = run_ddm_screening(data, hist, div_profile, payout_info)
    out["screening"] = scr
    if not scr["passed"]:
        out["stage"] = "D2 - failed screening"
        return out

    # ---------------- D3b: driver ----------------
    drv = build_ddm_drivers(hist, div_profile, payout_info, roe_info, data.flags)
    out["drivers"] = drv

    # ---------------- S5, S6: beta dan Cost of Equity ----------------
    beta = bundle["beta"]
    out["beta"] = beta
    ke_parts = cost_of_equity(beta["beta_adj"], rf=rf, erp=erp, size_prem=size_prem)
    ke = ke_parts["ke"]
    out["ke_parts"] = ke_parts
    out["ke"] = ke

    # ---------------- D4: proyeksi ----------------
    proj, fsum = project_dividends(drv, years=N, terminal_g=g_term,
                                   flags=data.flags)
    if proj is None:
        return _stop("Dividend projection",
                     "The base DPS is not valid to project forward.")
    out["projection"] = proj
    out["forecast_summary"] = fsum

    # ---------------- D5: terminal value ----------------
    payout_final = (float(proj["Payout"].iloc[-1])
                    if np.isfinite(proj["Payout"].iloc[-1]) else np.nan)
    tv = terminal_value(fsum["dps_final"], ke, terminal_g=fsum["g_terminal"],
                        roe_terminal=drv.get("roe"), payout_final=payout_final,
                        flags=data.flags)
    out["terminal"] = tv
    if not tv["valid"]:
        out["screening"]["passed"] = False
        out["screening"]["status"] = tv["reason"]
        out["stage"] = "D5 - terminal value invalid"
        return out

    # ---------------- D6: valuation and recommendation ----------------
    val = discount_dividends(proj, tv, ke, data, data.flags)
    out["valuation"] = val
    if not val["valid"]:
        out["screening"]["passed"] = False
        out["screening"]["status"] = val.get("reason", "")
        out["stage"] = "D6 - valuation failed"
        return out

    out["recommendation"] = make_ddm_recommendation(val, data.flags)

    # ---------------- D7: cross-check ----------------
    shares = data.shares_outstanding
    bvps = (snapshot["equity"] / shares
            if (np.isfinite(shares) and shares > 0 and np.isfinite(snapshot["equity"]))
            else np.nan)
    out["bvps"] = bvps
    out["current_pbv"] = (data.price / bvps
                          if (np.isfinite(bvps) and bvps > 0 and np.isfinite(data.price))
                          else np.nan)

    pbv_res = fair_pbv(drv.get("roe", np.nan), ke, fsum["g_terminal"], bvps, data.flags)
    ri_res = residual_income(bvps, drv.get("roe", np.nan), ke, fsum["g_terminal"],
                             drv["retention"], years=N, flags=data.flags)
    out["fair_pbv"] = pbv_res
    out["residual_income"] = ri_res
    out["crosscheck"] = compare_methods(val["fair_value_per_share"], pbv_res,
                                        ri_res, drv, data.price, data.flags)

    # ---------------- D8: sensitivity ----------------
    out["sensitivity"] = sensitivity_grid(proj, ke, fsum["g_terminal"], drv, data)

    # ---------------- D9: skenario ----------------
    sc_df, sc_detail = run_scenarios(drv, data, ke, years=N,
                                     g_base=fsum["g_terminal"])
    out["scenarios"] = sc_df
    out["scenario_detail"] = sc_detail

    out["ok"] = True
    out["stage"] = "Selesai"
    return out


def print_ddm_report(result):
    """Cetak laporan lengkap."""
    from ddm_report import render_ddm_report
    print(render_ddm_report(result))


# -----------------------------------------------------------------------
# BATCH
# -----------------------------------------------------------------------
def batch_ddm(tickers, rf=None, erp=None, terminal_g=None, years=None,
              show_progress=True):
    """Jalankan pipeline untuk sekumpulan ticker dan kembalikan tabel ringkas."""
    rows = []
    for i, t in enumerate(tickers, 1):
        if show_progress:
            print(f"  ({i}/{len(tickers)}) {t} ...", end=" ", flush=True)
        try:
            r = analyze_ddm(t, rf=rf, erp=erp, terminal_g=terminal_g, years=years)
        except Exception as exc:
            rows.append({"Ticker": t, "Nama": "", "Rating": "ERROR",
                         "Status": f"{type(exc).__name__}: {exc}"})
            if show_progress:
                print("ERROR")
            continue

        d = r["data"]
        if not r["ok"]:
            rows.append({
                "Ticker": d.ticker, "Nama": d.name or "", "Harga": d.price,
                "Fair Value": np.nan, "Upside %": np.nan,
                "Rating": "CANNOT PROCEED", "Div Yield %": np.nan,
                "Payout %": np.nan, "Ke %": np.nan, "Flag": len(d.flags.items),
                "Status": r["screening"]["status"],
            })
            if show_progress:
                print("ditolak")
            continue

        v, rec, drv = r["valuation"], r["recommendation"], r["drivers"]
        rows.append({
            "Ticker": d.ticker, "Nama": d.name or "",
            "Harga": round(v["market_price"], 0),
            "Fair Value": round(v["fair_value_per_share"], 0),
            "Upside %": round(rec["upside"] * 100, 1),
            "Rating": rec["rating"],
            "Div Yield %": round(v["dividend_yield_current"] * 100, 2)
            if np.isfinite(v["dividend_yield_current"]) else np.nan,
            "Payout %": round(drv["payout"] * 100, 1),
            "Ke %": round(r["ke"] * 100, 2),
            "Flag": len(d.flags.items),
            "Status": "OK",
        })
        if show_progress:
            print(f"{rec['rating']} ({rec['upside']*100:+.0f}%)")

    df = pd.DataFrame(rows)
    if "Upside %" in df.columns:
        df = df.sort_values("Upside %", ascending=False, na_position="last")
    print("\n" + "=" * 78)
    print(DDM_DISCLAIMER)
    return df.reset_index(drop=True)


if __name__ == "__main__":
    import sys
    tk = sys.argv[1] if len(sys.argv) > 1 else "BBCA"
    print_ddm_report(analyze_ddm(tk))
