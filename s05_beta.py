"""
=============================================================================
SECTION 5 - BETA
=============================================================================
TUJUAN  : Mengukur sensitivitas return saham terhadap return pasar. Beta ini
          menjadi input Cost of Equity di Section 6.

          Kami TIDAK memakai info["beta"] dari yfinance. Untuk ticker .JK
          angka itu sering kosong, atau dihitung terhadap indeks yang salah.
          Beta dihitung sendiri terhadap IHSG (^JKSE).

RUMUS   : Return mingguan  R_t = ln(P_t / P_t-1)
          Raw beta         beta_raw = Cov(R_saham, R_IHSG) / Var(R_IHSG)
          Blume adjustment beta_adj = 0.67 x beta_raw + 0.33 x 1.00

          Blume adjustment menarik beta ke arah 1.0 karena beta historis
          secara empiris cenderung mean-reverting. Ini konvensi standar
          (dipakai Bloomberg pada Adjusted Beta).

          Periode : 3 tahun, frekuensi mingguan (sekitar 156 observasi).
                    Mingguan dipilih untuk mengurangi noise dari
                    non-synchronous trading pada saham berlikuiditas tipis.

OUTPUT  : dict {beta_raw, beta_adj, r_squared, n_obs, source}
=============================================================================
"""

import numpy as np
import pandas as pd
import yfinance as yf

from config import ASSUMPTIONS
from utils import clip_flag

MARKET_INDEX = "^JKSE"
_MKT_CACHE = {}


def _market_returns(period=None, interval=None):
    """Ambil return mingguan IHSG. Di-cache supaya batch tidak fetch berulang."""
    period = period or ASSUMPTIONS["beta_period"]
    interval = interval or ASSUMPTIONS["beta_interval"]
    key = f"mkt_{period}_{interval}"
    if key in _MKT_CACHE:
        return _MKT_CACHE[key]
    try:
        h = yf.Ticker(MARKET_INDEX).history(period=period, interval=interval)
        if h is None or h.empty:
            return None
        px = h["Close"].dropna()
        ret = np.log(px / px.shift(1)).dropna()
        _MKT_CACHE[key] = ret
        return ret
    except Exception:
        return None


def compute_beta(ticker, flags, period=None, interval=None):
    """
    Compute the stock's beta against the IHSG. If it cannot be computed at
    all (no market or price data), fall back to a market beta of 1.0 with
    an explicit flag rather than silently. Whenever a regression result
    exists, the real regression beta is used, not a fixed substitute.
    """
    A = ASSUMPTIONS
    period = period or A["beta_period"]
    interval = interval or A["beta_interval"]
    fb = 1.0
    out = {"beta_raw": np.nan, "beta_adj": fb, "r_squared": np.nan,
           "n_obs": 0, "source": f"fallback beta {fb:.2f} (no data)"}

    mkt = _market_returns(period, interval)
    if mkt is None:
        flags.warn("Beta", f"Failed to fetch IHSG data. Beta of {fb:.2f} used.")
        return out

    try:
        h = yf.Ticker(ticker).history(period=period, interval=interval)
        if h is None or h.empty:
            flags.warn("Beta", f"Failed to fetch price history. Beta of {fb:.2f} used.")
            return out
        px = h["Close"].dropna()
        stk = np.log(px / px.shift(1)).dropna()
    except Exception as exc:
        flags.warn("Beta", f"Error fetching prices ({type(exc).__name__}). Beta of {fb:.2f} used.")
        return out

    # Samakan tanggal. Timezone dinormalisasi supaya join tidak gagal.
    df = pd.DataFrame({"stk": stk, "mkt": mkt})
    df.index = pd.to_datetime(df.index).tz_localize(None) if df.index.tz is not None else df.index
    try:
        s = stk.copy(); m = mkt.copy()
        s.index = pd.to_datetime(s.index).tz_localize(None) if getattr(s.index, "tz", None) else s.index
        m.index = pd.to_datetime(m.index).tz_localize(None) if getattr(m.index, "tz", None) else m.index
        df = pd.concat([s.rename("stk"), m.rename("mkt")], axis=1).dropna()
    except Exception:
        df = df.dropna()

    n = len(df)
    min_obs = 120 if interval == "1d" else 52
    if n < min_obs:
        flags.warn("Beta", f"Only {n} observations (minimum {min_obs} for "
                           f"the {interval} interval). Beta of {fb:.2f} used.")
        return out

    x = df["mkt"].values
    y = df["stk"].values
    var_m = np.var(x, ddof=1)
    if var_m == 0 or not np.isfinite(var_m):
        flags.warn("Beta", f"Market variance is zero. Beta of {fb:.2f} used.")
        return out

    cov = np.cov(y, x, ddof=1)[0, 1]
    beta_raw = cov / var_m

    corr = np.corrcoef(y, x)[0, 1]
    r2 = corr ** 2 if np.isfinite(corr) else np.nan

    beta_adj = 0.67 * beta_raw + 0.33 * 1.0

    # The real, Blume-adjusted regression beta is used as-is, only clipped
    # to a sanity range (beta_floor/beta_cap) in case of a data artefact.
    # No structural floor or fallback substitution is applied here: the
    # regression result is the beta, not a value overridden by assumption.
    beta_adj = clip_flag(beta_adj, A["beta_floor"], A["beta_cap"], "Beta", flags)

    # Low explanatory power is flagged, not silently substituted. A low
    # R-squared means market movements explain little of the stock's own
    # movements, so the beta should be read with that caveat rather than
    # discarded for a fixed number.
    if not np.isfinite(r2) or r2 < A["beta_min_r2"]:
        flags.warn("Beta",
                   f"Regression R-squared is only {r2:.3f}, below the "
                   f"{A['beta_min_r2']:.2f} threshold. The regression beta "
                   f"({beta_adj:.3f}) is still used, but market movements "
                   f"explain little of this stock's own movements, so it "
                   f"should be read with that caveat.")
        return {
            "beta_raw": float(beta_raw),
            "beta_adj": float(beta_adj),
            "r_squared": float(r2) if np.isfinite(r2) else np.nan,
            "n_obs": int(n),
            "source": (f"regression {interval} over {period} vs {MARKET_INDEX}, "
                       f"Blume adjusted (low R-squared)"),
        }

    return {
        "beta_raw": float(beta_raw),
        "beta_adj": float(beta_adj),
        "r_squared": float(r2) if np.isfinite(r2) else np.nan,
        "n_obs": int(n),
        "source": f"regression {interval} over {period} vs {MARKET_INDEX}, Blume adjusted",
    }
