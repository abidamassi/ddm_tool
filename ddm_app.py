"""
=============================================================================
DDM STREAMLIT APPLICATION
=============================================================================
PURPOSE : Web front end for the dividend discount model. The report follows
          the same order as the command line output, and reuses the theme
          from the DCF tool so both look like one desk.

CACHING : Network work (statements, dividend history, beta regression) is
          cached per ticker. Moving a slider only re-runs the arithmetic.

RUN     : streamlit run ddm_app.py
=============================================================================
"""

import copy
import warnings

import numpy as np
import pandas as pd
import streamlit as st

warnings.filterwarnings("ignore")

from config import ASSUMPTIONS as BASE
from ddm_config import DDM_ASSUMPTIONS as A, DDM_DISCLAIMER
from theme import (COLORS, RATING_COLOR, FLAG_COLOR,
                   inject_css, pill, metric_strip, callout, render_table)
from ddm_charts import (chart_dividend_history, chart_projection,
                        chart_sensitivity, chart_methods, chart_scenarios)
from ddm_main import fetch_ddm_bundle, analyze_ddm
from d01_dividends import dividend_table, dividend_summary
from d03_drivers import ddm_drivers_table
from d04_forecast import projection_table
from d06_valuation import value_bridge_table
from d09_scenario import scenario_table

AUTHOR = "Abida Massi Armand"

st.set_page_config(page_title="Dividend Discount Model",
                   page_icon="bank",
                   layout="wide",
                   initial_sidebar_state="expanded")
inject_css()


# =====================================================================
# RENDER HELPERS
# =====================================================================
def show_df(df, hide_index=False, status_col=None, center=False, equal_width=False):
    """Themed HTML table: rounded container, navy header. See theme.render_table."""
    render_table(df, hide_index=hide_index, status_col=status_col,
                 center=center, equal_width=equal_width)


def show_chart(fig):
    if fig is None:
        return None
    cfg = {"displayModeBar": False}
    try:
        return st.plotly_chart(fig, width="stretch", config=cfg)
    except TypeError:
        return st.plotly_chart(fig, use_container_width=True, config=cfg)


# =====================================================================
# CACHED DATA LAYER
# =====================================================================
@st.cache_data(show_spinner=False, ttl=3600)
def load_bundle(ticker):
    return fetch_ddm_bundle(ticker)


def run_analysis(ticker, rf, erp, years, g_term):
    bundle = copy.deepcopy(load_bundle(ticker))
    return analyze_ddm(ticker, rf=rf, erp=erp, years=years,
                       terminal_g=g_term, bundle=bundle)


# =====================================================================
# FORMATTERS
# =====================================================================
def f_idr(v, dp=0):
    return f"IDR {v:,.{dp}f}" if v is not None and np.isfinite(v) else "n/a"


def f_tn(v):
    return f"IDR {v/1e12:,.2f} tn" if v is not None and np.isfinite(v) else "n/a"


def f_pct(v, dp=2, sign=False):
    if v is None or not np.isfinite(v):
        return "n/a"
    return f"{v*100:+.{dp}f}%" if sign else f"{v*100:.{dp}f}%"


def f_x(v, dp=2):
    return f"{v:.{dp}f}x" if v is not None and np.isfinite(v) else "n/a"


# =====================================================================
# SIDEBAR
# =====================================================================
with st.sidebar:
    st.markdown(
        f'<div style="padding:.2rem 0 1rem 0;">'
        f'<div style="font-size:1.05rem;font-weight:600;color:#fff;letter-spacing:-.01em;">'
        f'Dividend Discount Model</div>'
        f'<div style="font-size:.7rem;color:{COLORS["ice"]};letter-spacing:.1em;'
        f'text-transform:uppercase;margin-top:.15rem;">Gordon growth, IDX equities</div>'
        f'</div>', unsafe_allow_html=True)

    st.markdown("---")

    ticker_in = st.text_input("Ticker", value="BBRI", max_chars=4,
                              help="Enter the 4-letter IDX code only. The .JK "
                                   "suffix is added automatically.").upper()

    st.markdown("---")
    st.markdown(
        f'<div style="font-size:.68rem;font-weight:600;letter-spacing:.14em;'
        f'text-transform:uppercase;color:{COLORS["ice"]};margin-bottom:.5rem;">'
        f'Assumptions</div>', unsafe_allow_html=True)

    rf_in = st.slider("Risk-free rate", 5.0, 9.0,
                      float(BASE["risk_free_rate"] * 100), 0.05,
                      format="%.2f%%",
                      help="Proxy for the 10-year INDOGB yield. Entered manually.") / 100

    erp_in = st.slider("Equity risk premium", 3.0, 10.0,
                       float(BASE["equity_risk_premium"] * 100), 0.10,
                       format="%.2f%%",
                       help="Feeds the CAPM cost of equity, which is the discount "
                            "rate for dividends.") / 100

    g_in = st.slider("Terminal growth", 0.0, 6.0,
                     float(A["terminal_growth"] * 100), 0.10,
                     format="%.2f%%",
                     help="Capped at the year-one growth rate. Cost of equity must "
                          "exceed this by at least 300bps.") / 100

    yrs_in = st.slider("Forecast horizon", 5, 10,
                       int(A["forecast_years"]), 1, format="%d years")

    st.markdown("---")
    run = st.button("Run analysis", use_container_width=True)


# =====================================================================
# STATE
# =====================================================================
if "ddm_result" not in st.session_state:
    st.session_state.ddm_result = None
    st.session_state.ddm_ticker = None

if run and ticker_in.strip():
    with st.spinner("Downloading filings and dividend history"):
        st.session_state.ddm_result = run_analysis(
            ticker_in.strip(), rf_in, erp_in, yrs_in, g_in)
        st.session_state.ddm_ticker = ticker_in.strip().upper()
elif (st.session_state.ddm_result is not None
      and ticker_in.strip().upper() == st.session_state.ddm_ticker):
    st.session_state.ddm_result = run_analysis(
        ticker_in.strip(), rf_in, erp_in, yrs_in, g_in)

r = st.session_state.ddm_result


def render_disclaimer():
    st.markdown(
        f'<div class="disclaimer">'
        f'<div class="sig">Disclaimer On &nbsp;|&nbsp; {AUTHOR}</div>'
        f'{DDM_DISCLAIMER}</div>', unsafe_allow_html=True)


def render_flags(flags):
    if flags.has_issue:
        rows = "".join(
            f'<div class="flagrow">'
            f'<div class="flagtag" style="background:{FLAG_COLOR.get(lv, COLORS["miss"])}">{lv}</div>'
            f'<div class="flagfield">{fd}</div><div class="flagnote">{nt}</div></div>'
            for lv, fd, nt in flags.items)
        st.markdown(f'<div class="flagbox">{rows}</div>', unsafe_allow_html=True)
    else:
        callout("No data quality issues detected.")


# =====================================================================
# EMPTY STATE
# =====================================================================
if r is None:
    st.markdown('<div class="masthead"><p class="eyebrow">Equity research tooling</p>'
                '<h1>Dividend Discount Model</h1>'
                '<div class="sub">Gordon growth on dividends, discounted at the '
                'cost of equity. Indonesian listed equities, including banks and '
                'other financials.</div></div>', unsafe_allow_html=True)
    st.markdown('<div class="empty"><h3>No company loaded</h3>'
                '<p>Enter an IDX ticker in the sidebar and select Run analysis.</p>'
                '</div>', unsafe_allow_html=True)
    render_disclaimer()
    st.stop()


d = r["data"]
scr = r["screening"]

# =====================================================================
# MASTHEAD
# =====================================================================
st.markdown(
    f'<div class="masthead"><p class="eyebrow">Dividend discount model report</p>'
    f'<h1>{d.ticker} &nbsp;&middot;&nbsp; {d.name or "Unnamed"}</h1>'
    f'<div class="sub">{d.sector or "Sector n/a"} &nbsp;|&nbsp; '
    f'{d.industry or "Industry n/a"}</div></div>',
    unsafe_allow_html=True)

metric_strip([
    ("Market price", f_idr(d.price)),
    ("Market cap", f_tn(d.market_cap)),
    ("Reporting currency", d.original_currency),
    ("FX applied", f"{d.fx_rate:,.0f}" if d.fx_rate != 1.0 else "None"),
])

if d.fx_rate != 1.0:
    callout(f"<b>Currency note.</b> Filings are reported in {d.original_currency} "
            f"and have been converted to IDR at {d.fx_rate:,.0f}. Dividends are "
            f"quoted in IDR already, matching the share price, so no conversion "
            f"is applied to them.")


# =====================================================================
# VERDICT (rendered first; only available once screening passes)
# =====================================================================
if scr["passed"]:
    val = r["valuation"]
    rec = r["recommendation"]
    drv = r["drivers"]
    kep = r["ke_parts"]
    proj = r["projection"]
    fsum = r["forecast_summary"]
    tv = r["terminal"]
    sens = r["sensitivity"]
    sc_df = r["scenarios"]
    cc = r["crosscheck"]

    pill("01", "Valuation verdict")

    fv = val["fair_value_per_share"]
    px = val["market_price"]
    rating = rec["rating"]
    rcolor = COLORS["ink_muted"] if rec.get("review_required") else \
        RATING_COLOR.get(rating, COLORS["ink_muted"])

    sc_vals = [float(sc_df.loc[s, "Fair value"]) for s in ["BEAR", "BULL"]
               if s in sc_df.index and pd.notna(sc_df.loc[s, "Fair value"])]
    lo = min(sc_vals) if sc_vals else fv
    hi = max(sc_vals) if sc_vals else fv
    span = max(hi - lo, 1e-9)
    pos = float(np.clip((px - lo) / span, 0, 1)) * 100
    fv_pos = float(np.clip((fv - lo) / span, 0, 1)) * 100

    rating_font = "1.5rem" if rec.get("review_required") else "2.5rem"
    up = rec["upside"]
    updown_label = "Downside" if (up is not None and np.isfinite(up) and up < 0) \
        else "Upside"

    st.markdown(f"""
<div class="verdict">
  <div class="row">
    <div>
      <div class="lab">Recommendation</div>
      <div class="rating" style="color:{rcolor};font-size:{rating_font}">{rating}</div>
    </div>
    <div>
      <div class="lab">Fair value per share</div>
      <div class="big">{f_idr(fv)}</div>
      <div class="small">Base case</div>
    </div>
    <div>
      <div class="lab">Market price</div>
      <div class="big">{f_idr(px)}</div>
      <div class="small">{rec['label']}</div>
    </div>
    <div>
      <div class="lab">{updown_label}</div>
      <div class="big" style="color:{rcolor}">{f_pct(up, 1, sign=True)}</div>
      <div class="small">Dividend yield {f_pct(val['dividend_yield_current'])}</div>
    </div>
  </div>
  <div class="scale">
    <div class="lab">Where the market price sits inside the bear to bull range</div>
    <div class="track">
      <div class="fill" style="left:0%;width:{fv_pos:.1f}%"></div>
      <div class="mark" style="left:{pos:.1f}%"></div>
    </div>
    <div class="ends"><span>Bear {f_idr(lo)}</span><span>Bull {f_idr(hi)}</span></div>
  </div>
</div>
""", unsafe_allow_html=True)

    if rec.get("review_required"):
        callout(f"<b>Review required.</b> {rec['reason_override']}")


# =====================================================================
# D1 - DIVIDEND HISTORY
# =====================================================================
dp = r.get("div_profile")
if dp is not None:
    pill("02", "Dividend history",
         "Payments are aggregated by calendar year from ex-dividend dates. The "
         "current year is excluded from growth and consistency analysis.")
    c1, c2 = st.columns([1.3, 1])
    with c1:
        show_chart(chart_dividend_history(dp, r.get("payout_info")))
    with c2:
        show_df(dividend_summary(dp), hide_index=True)
    dtab = dividend_table(dp).drop(columns=["Note"])
    show_df(dtab, hide_index=True, center=True, equal_width=True)


# =====================================================================
# D2 - SCREENING
# =====================================================================
pill("03", "Model eligibility screening",
     "These gates test whether a dividend discount model can be applied at all. "
     "Unlike the DCF tool, financials are accepted here, that is the main use case.")

if isinstance(scr.get("detail"), pd.DataFrame) and not scr["detail"].empty:
    show_df(scr["detail"], hide_index=True, status_col="Status")

if scr["passed"]:
    st.markdown('<div class="callout"><b class="gate-ok">ELIGIBLE.</b> '
                'All gates passed. The valuation above is calculated.</div>',
                unsafe_allow_html=True)
else:
    st.markdown(f'<div class="callout"><b class="gate-no">CANNOT PROCEED.</b> '
                f'{scr["status"]}</div>', unsafe_allow_html=True)
    pill("04", "Data quality warnings")
    render_flags(d.flags)
    render_disclaimer()
    st.stop()


# =====================================================================
# DATA QUALITY
# =====================================================================
pill("04", "Data quality warnings",
     "Read these before relying on any figure below. They record where a value "
     "was missing, proxied, clipped, or where an assumption was constrained.")
render_flags(d.flags)


# =====================================================================
# D3 - DRIVERS
# =====================================================================
pill("05", "Dividend drivers and model decisions",
     "Every driver is the median of the company's own reported history.")

c1, c2 = st.columns([1.05, 1])
with c1:
    show_df(ddm_drivers_table(drv), hide_index=True)
with c2:
    if np.isfinite(drv["sgr"]) and drv["g_used"] < drv["g_hist"] - 1e-9:
        callout(f"<b>Growth constrained by retained earnings.</b> Historical DPS "
                f"growth of {f_pct(drv['g_hist'])} exceeds the sustainable growth "
                f"rate. Retention of {f_pct(drv['retention'], 1)} multiplied by ROE "
                f"of {f_pct(drv['roe'], 1)} gives {f_pct(drv['sgr'])}, which is the "
                f"rate applied. The excess came from a rising payout ratio, which "
                f"cannot continue indefinitely because payout is capped at 100%.")
    else:
        callout(f"<b>Growth not constrained.</b> Historical DPS growth of "
                f"{f_pct(drv['g_hist'])} is within the sustainable growth rate of "
                f"{f_pct(drv['sgr'])}.")

    callout(f"<b>Payout basis.</b> {drv['payout_basis']}. Dividends paid in year T "
            f"are matched against earnings for fiscal year T-1, reflecting the "
            f"Indonesian practice of approving the prior year's distribution at the "
            f"AGM.")

po = r.get("payout_info")
if po is not None and po.get("table") is not None:
    st.markdown('<p class="pill-note">Payout ratio, year by year '
               '(last 4 years)</p>', unsafe_allow_html=True)
    t = po["table"].tail(4).copy()
    for c in ["DPS", "EPS (t-1)", "EPS (t)"]:
        t[c] = t[c].round(2)
    for c in ["Payout (lagged)", "Payout (contemporaneous)"]:
        t[c] = t[c].apply(lambda v: f"{v*100:.1f}%" if pd.notna(v) else "n/a")
    show_df(t, hide_index=True)


# =====================================================================
# S5 / S6 - COST OF EQUITY
# =====================================================================
pill("06", "Beta and cost of equity",
     "Reused from the DCF tool's CAPM module. Only the equity leg is used, "
     "the WACC combination step is deliberately skipped.")

b = r["beta"]
c1, c2 = st.columns([1, 1])
with c1:
    rows = [
        ("Risk-free rate", f_pct(kep["rf"])),
        ("Equity risk premium", f_pct(kep["erp"])),
        ("Beta raw (regression)", f"{b['beta_raw']:.3f}"
         if np.isfinite(b["beta_raw"]) else "n/a"),
        ("R-squared", f"{b['r_squared']:.3f}"
         if np.isfinite(b["r_squared"]) else "n/a"),
        ("Beta applied", f"{kep['beta']:.3f}"),
        ("Size premium", f_pct(kep["size_premium"])),
        ("Cost of equity (CAPM)", f_pct(kep["ke"])),
    ]
    show_df(pd.DataFrame(rows, columns=["Component", "Value"]), hide_index=True)
with c2:
    metric_strip([("Cost of equity", f_pct(kep["ke"])),
                  ("Terminal growth", f_pct(fsum["g_terminal"]))])
    st.write("")
    metric_strip([("Spread Ke minus g", f_pct(kep["ke"] - fsum["g_terminal"])),
                  ("Minimum required", f_pct(A["min_ke_g_spread"]))])
    st.write("")
    callout(f"<b>Beta method.</b> {b['source']}, {b['n_obs']} observations.")
    callout("<b>Why cost of equity, not WACC.</b> Dividends accrue to ordinary "
            "shareholders alone, not to all capital providers. Discounting them at "
            "WACC, which is lower whenever debt is present, would overstate value "
            "systematically. The error is largest for banks.")


# =====================================================================
# D4 - PROJECTION
# =====================================================================
pill("07", "Dividend projection",
     f"{fsum['years']} year explicit forecast. Growth fades linearly from the "
     f"year-one rate toward the terminal rate.")

show_chart(chart_projection(proj))
show_df(projection_table(proj))


# =====================================================================
# D5 - TERMINAL VALUE
# =====================================================================
pill("08", "Terminal value",
     "Gordon growth on the final projected dividend, with a consistency test on "
     "the terminal payout ratio.")

metric_strip([
    ("Cost of equity", f_pct(tv["ke"])),
    ("Terminal growth", f_pct(tv["terminal_growth"])),
    ("Spread", f_pct(tv["ke"] - tv["terminal_growth"])),
    ("Final year DPS", f_idr(tv["dps_final"], 2)),
    ("Terminal value", f_idr(tv["tv_nominal"], 2)),
])
st.write("")
metric_strip([
    ("Payout implied by projection", f_pct(tv["payout_projected"], 1)),
    ("Payout consistent with growth", f_pct(tv["payout_consistent"], 1)),
    ("Implied terminal P/E", f_x(tv.get("implied_terminal_pe", np.nan))),
])

gap = tv.get("payout_gap", np.nan)
if np.isfinite(gap) and abs(gap) > A["terminal_payout_tolerance"]:
    direction = "above" if gap > 0 else "below"
    effect = ("value is overstated, the company is distributing more than the "
              "assumed growth allows for"
              if gap > 0 else
              "value is understated, retained earnings beyond what growth requires "
              "never reach shareholders in this model")
    callout(f"<b>Terminal payout inconsistency.</b> The projected payout sits "
            f"{abs(gap)*100:.1f} percentage points {direction} the level consistent "
            f"with stable growth, which is 1 minus g divided by ROE. The effect is "
            f"that {effect}.")


# =====================================================================
# D6 - VALUE COMPOSITION
# =====================================================================
pill("09", "Value composition",
     "No enterprise-to-equity bridge is needed. Dividends are already cash flows "
     "per share to shareholders, so cash and debt are not deducted again.")

c1, c2 = st.columns([1, 1])
with c1:
    show_df(value_bridge_table(val), hide_index=True)
with c2:
    metric_strip([("Terminal value share", f_pct(val["tv_share_of_value"], 1)),
                  ("Dividend yield now", f_pct(val["dividend_yield_current"]))])
    st.write("")
    metric_strip([("Yield at fair value", f_pct(val["dividend_yield_at_fv"])),
                  ("Book value per share", f_idr(r.get("bvps", np.nan), 2))])

if np.isfinite(val["tv_share_of_value"]) and val["tv_share_of_value"] > 0.80:
    callout(f"<b>Terminal value dependency.</b> "
            f"{f_pct(val['tv_share_of_value'], 1)} of value comes from the terminal "
            f"period. The valuation rests largely on a perpetuity assumption rather "
            f"than on dividends that can be verified.")


# =====================================================================
# D7 - CROSS-CHECK
# =====================================================================
pill("10", "Cross-check against equity-based methods",
     "Fair P/BV and residual income use the same inputs. Where they diverge, the "
     "cause is almost always the payout ratio, not a disagreement between methods.")

c1, c2 = st.columns([1.15, 1])
with c1:
    show_chart(chart_methods(cc["table"], px, r.get("bvps")))
with c2:
    show_df(cc["table"], hide_index=True)
    metric_strip([("Current P/BV", f_x(r.get("current_pbv", np.nan))),
                  ("Fair P/BV", f_x(r["fair_pbv"].get("fair_pbv", np.nan)))])

if cc["diagnosis"]:
    callout(f"<b>Why the methods differ.</b> {cc['diagnosis']}")


# =====================================================================
# D8 - SENSITIVITY
# =====================================================================
pill("11", "Sensitivity",
     "Dividends are held constant. Only the discount rate and terminal growth "
     "move, which isolates the effect of the cost of capital.")

show_chart(chart_sensitivity(sens, px))
stt = sens["stats"]
metric_strip([
    ("Lowest fair value", f_idr(stt["min"])),
    ("Median", f_idr(stt["median"])),
    ("Highest fair value", f_idr(stt["max"])),
    ("Valid cells", f"{stt['n_valid']} of {stt['n_cells']}"),
])


# =====================================================================
# D9 - SCENARIOS
# =====================================================================
pill("12", "Scenarios",
     "Bull and bear shift dividend growth and the payout ratio by one standard "
     "deviation of the company's own history, with terminal growth moved 50bps "
     "either way. Cost of equity is held constant.")

c1, c2 = st.columns([1.15, 1])
with c1:
    show_chart(chart_scenarios(sc_df, px))
with c2:
    show_df(scenario_table(sc_df), status_col="Rating")


# =====================================================================
# LIMITATIONS
# =====================================================================
pill("13", "Model limitations")
st.markdown("""
<div class="limits"><ul>
<li>A dividend discount model only captures value that is actually distributed as
cash. Retained earnings that are never paid out do not appear as value, so
companies with a low payout ratio are systematically understated.</li>
<li>Dividends are aggregated by calendar year from ex-dividend dates, not by the
fiscal year approved at the AGM.</li>
<li>The payout ratio uses a lagged convention, matching dividends paid in year T
against earnings for fiscal year T-1. Companies with a different distribution
policy will be mismeasured.</li>
<li>Special or one-off dividends are flagged but not separated automatically.
They need manual review.</li>
<li>Corporate actions and post balance sheet events are not reflected.</li>
<li>Share count is the basic figure, not fully diluted.</li>
<li>No consensus estimates are used. Every forecast is derived from reported
history and the assumptions set in the sidebar.</li>
<li>Data comes from yfinance and has not been reconciled against audited financial
statements, IDX filings, or AGM resolutions.</li>
</ul></div>
""", unsafe_allow_html=True)

render_disclaimer()
