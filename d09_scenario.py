"""
=============================================================================
SECTION D9 - SKENARIO BULL, BASE, BEAR
=============================================================================
TUJUAN  : Membentuk tiga skenario kebijakan dividen yang koheren, bukan
          sekadar menggeser satu variabel. Berbeda dari Section D8 yang
          menguji cost of capital, section ini menguji asumsi dividen itu
          sendiri.

RUMUS   : Deviasi diambil dari volatilitas historis emiten, bukan dari
          angka yang ditentukan sembarangan.

          SD_growth = standar deviasi pertumbuhan DPS historis
          SD_payout = standar deviasi payout ratio historis

          BULL   growth     = base + 1 x SD_growth
                 payout     = base + 1 x SD_payout, dibatasi maksimum 100%
                 terminal g = base + 50bps

          BASE   seluruhnya pada nilai median historis

          BEAR   growth     = base - 1 x SD_growth
                 payout     = base - 1 x SD_payout, dibatasi minimum 5%
                 terminal g = base - 50bps

          Cost of Equity DITAHAN KONSTAN di ketiga skenario. Pergerakannya
          sudah diuji terpisah di Section D8, dan mencampurnya di sini akan
          membuat sumber perubahan nilai tidak bisa diurai.

          Payout ikut digeser karena pada model dividen, kebijakan payout
          adalah keputusan manajemen yang secara langsung menentukan arus
          kas kepada pemegang saham. Payout lebih tinggi menaikkan dividen
          jangka pendek tetapi menurunkan pertumbuhan jangka panjang, dan
          ketegangan itu justru inti dari skenario yang bermakna.

OUTPUT  : DataFrame ringkasan tiga skenario beserta nilai wajar dan rating.
=============================================================================
"""

import numpy as np
import pandas as pd

from ddm_config import DDM_ASSUMPTIONS as A
from d04_forecast import project_dividends
from d05_terminal import terminal_value
from d06_valuation import discount_dividends, make_ddm_recommendation
from d08_sensitivity import _NullFlags


def run_scenarios(drv, data, ke, years=None, g_base=None):
    N = int(years or A["forecast_years"])
    g_term_base = A["terminal_growth"] if g_base is None else g_base
    k = A["scenario_sd_multiple"]
    shift = A["scenario_g_shift"]

    g0, sd_g = drv["g_used"], drv["g_sd"]
    p0, sd_p = drv["payout"], drv["payout_sd"]
    roe = drv.get("roe", np.nan)

    specs = {
        "BULL": {"g1": g0 + k * sd_g,
                 "payout": min(p0 + k * sd_p, 1.00),
                 "g_term": g_term_base + shift},
        "BASE": {"g1": g0,
                 "payout": p0,
                 "g_term": g_term_base},
        "BEAR": {"g1": g0 - k * sd_g,
                 "payout": max(p0 - k * sd_p, 0.05),
                 "g_term": max(g_term_base - shift, 0.0)},
    }

    rows, detail = [], {}
    null = _NullFlags()

    for name, s in specs.items():
        proj, summ = project_dividends(drv, years=N, g1=s["g1"],
                                       terminal_g=s["g_term"],
                                       payout=s["payout"], flags=None)
        if proj is None:
            rows.append({"Scenario": name, "Growth Y1": s["g1"],
                         "Payout": s["payout"], "Terminal g": s["g_term"],
                         "Fair value": np.nan, "Upside": np.nan,
                         "Rating": "N/A", "Note": "projection failed"})
            continue

        payout_final = (float(proj["Payout"].iloc[-1])
                        if np.isfinite(proj["Payout"].iloc[-1]) else np.nan)
        tv = terminal_value(summ["dps_final"], ke, terminal_g=s["g_term"],
                            roe_terminal=roe, payout_final=payout_final, flags=None)
        if not tv["valid"]:
            rows.append({"Scenario": name, "Growth Y1": s["g1"],
                         "Payout": s["payout"], "Terminal g": s["g_term"],
                         "Fair value": np.nan, "Upside": np.nan,
                         "Rating": "N/A", "Note": tv["reason"][:60]})
            continue

        v = discount_dividends(proj, tv, ke, data, flags=null)
        rec = make_ddm_recommendation(v)
        detail[name] = {"proj": proj, "val": v, "tv": tv}

        rows.append({
            "Scenario": name,
            "Growth Y1": s["g1"],
            "Payout": s["payout"],
            "Terminal g": s["g_term"],
            "Fair value": v["fair_value_per_share"],
            "Upside": v["upside"],
            "Rating": rec["rating"],
            "Note": "",
        })

    df = pd.DataFrame(rows).set_index("Scenario").reindex(["BULL", "BASE", "BEAR"])
    return df, detail


def scenario_table(df):
    """Format the scenario table for display."""
    out = pd.DataFrame(index=df.index)
    out["Growth Y1"] = (df["Growth Y1"] * 100).round(2).astype(str) + "%"
    out["Payout"] = (df["Payout"] * 100).round(1).astype(str) + "%"
    out["Terminal g"] = (df["Terminal g"] * 100).round(2).astype(str) + "%"
    out["Fair value (IDR)"] = df["Fair value"].round(0)
    out["Upside"] = df["Upside"].apply(
        lambda v: f"{v*100:+.1f}%" if pd.notna(v) else "n/a")
    out["Rating"] = df["Rating"]
    return out
