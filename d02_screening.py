"""
=============================================================================
SECTION D2 - SCREENING KELAYAKAN MODEL DDM
=============================================================================
TUJUAN  : Menentukan apakah satu emiten LAYAK dinilai dengan Dividend
          Discount Model. Sama seperti tool DCF, ini bukan screening
          "sahamnya menarik atau tidak", melainkan "modelnya berlaku atau
          tidak".

PERBEDAAN MENDASAR DARI SCREENING DCF:
          Tool DCF MENOLAK emiten sektor keuangan. Tool DDM justru
          MENERIMA mereka, karena bank dan asuransi adalah kasus penggunaan
          utamanya. Yang menentukan kelayakan di sini bukan sektor,
          melainkan apakah emiten benar-benar membagikan dividen secara
          teratur dalam porsi yang bermakna terhadap labanya.

RUMUS   : Gate 1  Membayar dividen >= 3 dari 5 tahun lengkap terakhir
          Gate 2  Tahun lengkap terakhir WAJIB membayar
          Gate 3  Laporan tahunan >= 4 tahun
          Gate 4  Laba bersih positif >= 2 dari 3 tahun terakhir
          Gate 5  Laba bersih periode terakhir positif
          Gate 6  Total ekuitas positif
          Gate 7  Market cap >= IDR 1 triliun
          Gate 8  5% <= Payout ratio <= 110%
          Gate 9  Coefficient of variation DPS <= 1.20
          Gate 10 DPS tahun lengkap terakhir > 0

          Catatan Gate 8. Payout di bawah 5% berarti dividen hanya bersifat
          token, sebagian besar nilai perusahaan tertahan sebagai laba
          ditahan dan tidak pernah sampai ke pemegang saham sebagai kas.
          DDM akan meng-understate secara parah. Payout di atas 110%
          berarti dividen dibayar melebihi laba, dibiayai kas lama atau
          utang, dan tidak berkelanjutan.

OUTPUT  : dict {passed, status, failed_gates, detail}
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_SCREENING


def run_ddm_screening(data, hist, div_profile, payout_info):
    """
    Jalankan seluruh gate DDM.

    data         : CompanyData hasil Section 1 tool DCF
    hist         : DataFrame historis hasil Section 2 tool DCF
    div_profile  : hasil Section D1
    payout_info  : hasil Section D3 (payout ratio), boleh None kalau
                   belum dihitung, gate payout akan dilewati dengan flag
    """
    S = DDM_SCREENING
    results = []

    def add(no, name, actual, criteria, passed):
        results.append({
            "No": no, "Gate": name, "Value": actual,
            "Criteria": criteria, "Status": "PASS" if passed else "FAIL"
        })

    # ---------------- Gate 1: dividend track record ----------------
    if div_profile is None:
        add(1, "Dividend track record", "no data",
            f">= {S['min_dividend_years']} of {S['dividend_lookback_years']} years", False)
        return _compile(results, data)

    yp = div_profile["years_paid"]
    add(1, "Dividend track record",
        f"{yp} of {div_profile['years_in_window']} complete years",
        f">= {S['min_dividend_years']} years", yp >= S["min_dividend_years"])

    # ---------------- Gate 2: continuity ----------------
    if S["require_latest_year_paid"]:
        add(2, "Dividend, latest complete year",
            "paid" if div_profile["latest_paid"] else "not paid",
            "must be paid (uninterrupted stream)", div_profile["latest_paid"])

    # ---------------- Gate 3: reporting adequacy ----------------
    n_years = hist.shape[1] if hist is not None else 0
    add(3, "Annual reports available", f"{n_years} years",
        f">= {S['min_annual_years']} years", n_years >= S["min_annual_years"])

    if hist is None or n_years == 0:
        return _compile(results, data)

    ni = pd.to_numeric(hist.loc["net_income"], errors="coerce")
    eq = pd.to_numeric(hist.loc["equity"], errors="coerce")

    # ---------------- Gate 4: earnings quality ----------------
    lb = S["ni_lookback_years"]
    recent_ni = ni.iloc[-lb:]
    n_pos = int((recent_ni > 0).sum())
    add(4, "Positive net income",
        f"{n_pos} of the last {len(recent_ni)} years",
        f">= {S['min_ni_positive_years']} of {lb} years",
        n_pos >= S["min_ni_positive_years"])

    # ---------------- Gate 5: latest earnings ----------------
    ni_last = float(ni.iloc[-1]) if pd.notna(ni.iloc[-1]) else np.nan
    ni_ok = bool(np.isfinite(ni_last) and ni_last > 0)
    add(5, "Net income, latest period",
        f"IDR {ni_last/1e9:,.0f} bn" if np.isfinite(ni_last) else "n/a",
        "> 0 (dividends must come from earnings)", ni_ok)

    # ---------------- Gate 6: equity ----------------
    eq_last = float(eq.iloc[-1]) if pd.notna(eq.iloc[-1]) else np.nan
    eq_ok = bool(np.isfinite(eq_last) and eq_last > 0)
    add(6, "Positive total equity",
        f"IDR {eq_last/1e12:,.2f} tn" if np.isfinite(eq_last) else "n/a",
        "> 0 (needed for ROE and P/BV)", eq_ok)

    # ---------------- Gate 7: size ----------------
    mcap = data.market_cap
    add(7, "Market cap",
        f"IDR {mcap/1e12:,.2f} tn" if np.isfinite(mcap) else "n/a",
        f">= IDR {S['min_market_cap_idr']/1e12:,.0f} tn",
        bool(np.isfinite(mcap) and mcap >= S["min_market_cap_idr"]))

    # ---------------- Gate 8: payout ratio ----------------
    if payout_info is None or not np.isfinite(payout_info.get("payout", np.nan)):
        add(8, "Payout ratio", "cannot be computed",
            f"{S['payout_min']*100:.0f}% - {S['payout_max']*100:.0f}%", False)
    else:
        po = payout_info["payout"]
        po_ok = bool(S["payout_min"] <= po <= S["payout_max"])
        add(8, "Payout ratio", f"{po*100:.1f}%",
            f"{S['payout_min']*100:.0f}% - {S['payout_max']*100:.0f}% "
            f"(below = token dividend, above = unsustainable)", po_ok)

    # ---------------- Gate 9: volatility ----------------
    cv = div_profile["cv"]
    if not np.isfinite(cv):
        cv_ok, cv_txt = True, "cannot be computed (limited data)"
    else:
        cv_ok = bool(cv <= S["max_dps_cv"])
        cv_txt = f"{cv:.2f}"
    add(9, "DPS volatility (CV)", cv_txt,
        f"<= {S['max_dps_cv']:.2f}", cv_ok)

    # ---------------- Gate 10: latest DPS ----------------
    dps_last = div_profile["latest_dps"]
    dps_ok = bool(np.isfinite(dps_last) and dps_last > 0)
    add(10, "DPS, latest complete year",
        f"IDR {dps_last:,.2f}" if np.isfinite(dps_last) else "n/a",
        "> 0", dps_ok)

    return _compile(results, data)


def _compile(results, data):
    detail = pd.DataFrame(results)
    failed = detail.loc[detail["Status"] == "FAIL", "Gate"].tolist()
    passed = len(failed) == 0

    if passed:
        status = "Eligible, proceeding to the DDM calculation."
    elif "Dividend track record" in failed or "Dividend, latest complete year" in failed:
        status = ("The dividend track record is insufficient. DDM requires a "
                  "regular dividend stream. Use DCF for non-financial issuers, "
                  "or Relative Valuation instead.")
    elif "Payout ratio" in failed:
        status = ("The payout ratio is outside a reasonable range, either too "
                  "small relative to earnings (DDM would understate value) or "
                  "above earnings (unsustainable). Use Residual Income, P/BV, "
                  "or DCF instead.")
    else:
        status = "Failed: " + "; ".join(failed)

    return {
        "ticker": data.ticker,
        "name": data.name,
        "passed": passed,
        "status": status,
        "failed_gates": failed,
        "detail": detail,
    }
