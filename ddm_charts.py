"""
=============================================================================
DDM CHARTS - PLOTLY VISUALS
=============================================================================
PURPOSE : Build every chart in the DDM app. Colours and fonts are taken from
          theme.py, the same tokens the DCF tool uses, so both tools look
          like they belong to the same desk.

CHARTS  : 1. History     annual DPS bars with the payout ratio line
          2. Projection  projected DPS and EPS with the payout path
          3. Sensitivity cost of equity by terminal growth heatmap
          4. Methods     DDM against fair P/BV and residual income
          5. Scenario    bull, base, and bear against market price

OUTPUT  : Plotly Figure objects.
=============================================================================
"""

import copy

import numpy as np
import pandas as pd
import plotly.graph_objects as go

from theme import COLORS, PLOTLY_LAYOUT


def _base(title=None, height=340):
    layout = copy.deepcopy(PLOTLY_LAYOUT)
    if title:
        layout["title"]["text"] = title
    layout["height"] = height
    return layout


# ---------------------------------------------------------------------
# 1. DIVIDEND HISTORY
# ---------------------------------------------------------------------
def chart_dividend_history(div_profile, payout_info=None):
    """Annual dividend per share, with the payout ratio on the right axis.
    Last 10 years only."""
    s = div_profile["annual"].tail(10)
    years = [str(int(y)) for y in s.index]
    vals = [float(v) for v in s.values]
    specials = set(div_profile.get("special_years", []))

    colors = [COLORS["hold"] if int(y) in specials else COLORS["navy"]
              for y in s.index]

    fig = go.Figure()
    fig.add_bar(x=years, y=vals, name="DPS",
                marker_color=colors,
                hovertemplate="%{x}: IDR %{y:,.2f}<extra></extra>")

    if payout_info is not None and payout_info.get("table") is not None:
        t = payout_info["table"]
        po_x, po_y = [], []
        for _, row in t.iterrows():
            if str(int(row["Year paid"])) not in years:
                continue
            v = row.get("Payout (lagged)")
            if pd.notna(v) and 0 < v < 3:
                po_x.append(str(int(row["Year paid"])))
                po_y.append(float(v) * 100)
        if po_x:
            fig.add_scatter(x=po_x, y=po_y, name="Payout ratio", yaxis="y2",
                            mode="lines+markers",
                            line=dict(color=COLORS["ice"], width=2.5),
                            marker=dict(size=7, color=COLORS["ice"]),
                            hovertemplate="Payout: %{y:.1f}%<extra></extra>")

    layout = _base("Dividend per share and payout ratio", 340)
    layout["yaxis"]["title"] = dict(text="DPS (IDR)", font=dict(size=11))
    layout["yaxis2"] = dict(title=dict(text="Payout %", font=dict(size=11)),
                            overlaying="y", side="right", showgrid=False,
                            tickfont=dict(size=11), linecolor=COLORS["rule"])
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------
# 2. PROJECTION
# ---------------------------------------------------------------------
def chart_projection(proj):
    """Projected DPS and EPS, with the implied payout path."""
    yrs = [f"Y{int(t)}" for t in proj.index]

    fig = go.Figure()
    fig.add_bar(x=yrs, y=proj["EPS"].round(2), name="EPS",
                marker_color=COLORS["ice_pale"],
                marker_line=dict(color=COLORS["ice"], width=1),
                hovertemplate="EPS: IDR %{y:,.2f}<extra></extra>")
    fig.add_bar(x=yrs, y=proj["DPS"].round(2), name="DPS",
                marker_color=COLORS["navy"],
                hovertemplate="DPS: IDR %{y:,.2f}<extra></extra>")
    fig.add_scatter(x=yrs, y=(proj["Payout"] * 100).round(1), name="Payout",
                    yaxis="y2", mode="lines+markers",
                    line=dict(color=COLORS["hold"], width=2.5),
                    marker=dict(size=7, color=COLORS["hold"]),
                    hovertemplate="Payout: %{y:.1f}%<extra></extra>")

    layout = _base("Projected dividend, earnings, and payout", 350)
    layout["barmode"] = "overlay"
    layout["yaxis"]["title"] = dict(text="IDR per share", font=dict(size=11))
    layout["yaxis2"] = dict(title=dict(text="Payout %", font=dict(size=11)),
                            overlaying="y", side="right", showgrid=False,
                            tickfont=dict(size=11), linecolor=COLORS["rule"],
                            range=[0, 110])
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------
# 3. SENSITIVITY
# ---------------------------------------------------------------------
def chart_sensitivity(sens, price):
    """Cost of equity by terminal growth. Colour encodes upside."""
    fv = sens["fair_value"].astype(float)
    z = fv.values
    up = (z / price - 1) * 100 if (price and np.isfinite(price) and price > 0) else z

    fig = go.Figure(go.Heatmap(
        z=up, x=list(fv.columns), y=list(fv.index),
        text=[[f"{v:,.0f}" if np.isfinite(v) else "n/a" for v in row] for row in z],
        texttemplate="%{text}", textfont=dict(size=11, family="Poppins"),
        colorscale=[[0.0, COLORS["sell"]], [0.45, "#F2E9DC"],
                    [0.55, COLORS["ice_pale"]], [1.0, COLORS["navy"]]],
        zmid=0,
        colorbar=dict(title=dict(text="Upside %", font=dict(size=10)),
                      thickness=12, tickfont=dict(size=10), outlinewidth=0),
        hovertemplate="Ke %{y} | g %{x}<br>Fair value IDR %{text}<extra></extra>",
    ))
    layout = _base("Fair value per share by cost of equity and terminal growth (IDR)", 360)
    layout["xaxis"]["title"] = dict(text="Terminal growth", font=dict(size=11))
    layout["yaxis"]["title"] = dict(text="Cost of equity", font=dict(size=11))
    layout["xaxis"]["gridcolor"] = "rgba(0,0,0,0)"
    layout["yaxis"]["gridcolor"] = "rgba(0,0,0,0)"
    layout["yaxis"]["autorange"] = "reversed"
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------
# 4. METHOD COMPARISON
# ---------------------------------------------------------------------
def chart_methods(cc_table, price, bvps=None):
    """DDM against the two equity-based cross-checks."""
    t = cc_table.dropna(subset=["Fair value (IDR)"])
    if t.empty:
        return None

    names = [n.replace(" (ROE-g)/(Ke-g)", "") for n in t["Method"]]
    vals = t["Fair value (IDR)"].astype(float).tolist()
    bar_colors = [COLORS["navy"], COLORS["ice"], COLORS["ice_pale"]][:len(vals)]

    fig = go.Figure()
    fig.add_bar(x=names, y=vals, marker_color=bar_colors,
                marker_line=dict(color=COLORS["navy_soft"], width=1),
                text=[f"IDR {v:,.0f}" for v in vals],
                textposition="outside", textfont=dict(size=11),
                hovertemplate="%{x}: IDR %{y:,.0f}<extra></extra>")

    if price and np.isfinite(price) and price > 0:
        fig.add_hline(y=price, line=dict(color=COLORS["sell"], width=2, dash="dash"),
                      annotation_text=f"Market price IDR {price:,.0f}",
                      annotation_position="top left",
                      annotation_font=dict(size=11, color=COLORS["sell"]))
    if bvps and np.isfinite(bvps) and bvps > 0:
        fig.add_hline(y=bvps, line=dict(color=COLORS["ink_muted"], width=1.5, dash="dot"),
                      annotation_text=f"Book value IDR {bvps:,.0f}",
                      annotation_position="bottom left",
                      annotation_font=dict(size=10, color=COLORS["ink_muted"]))

    top = max(vals + [price or 0, bvps or 0])
    layout = _base("Fair value by method (IDR per share)", 360)
    layout["yaxis"]["range"] = [0, top * 1.25]
    layout["yaxis"]["title"] = dict(text="IDR per share", font=dict(size=11))
    layout["showlegend"] = False
    layout["xaxis"]["tickfont"] = dict(size=10)
    fig.update_layout(**layout)
    return fig


# ---------------------------------------------------------------------
# 5. SCENARIOS
# ---------------------------------------------------------------------
def chart_scenarios(sc_df, price):
    """Bull, base, and bear fair value with the market price as reference."""
    order = [s for s in ["BEAR", "BASE", "BULL"] if s in sc_df.index]
    vals = [float(sc_df.loc[s, "Fair value"]) for s in order]
    ratings = [str(sc_df.loc[s, "Rating"]) for s in order]

    bar_colors = {"BEAR": COLORS["ice_pale"], "BASE": COLORS["navy"],
                  "BULL": COLORS["ice"]}
    fig = go.Figure()
    fig.add_bar(x=order, y=vals,
                marker_color=[bar_colors[s] for s in order],
                marker_line=dict(color=COLORS["navy_soft"], width=1),
                text=[f"IDR {v:,.0f}<br>{r}" if np.isfinite(v) else "n/a"
                      for v, r in zip(vals, ratings)],
                textposition="outside", textfont=dict(size=11),
                hovertemplate="%{x}: IDR %{y:,.0f}<extra></extra>")

    if price and np.isfinite(price) and price > 0:
        fig.add_hline(y=price, line=dict(color=COLORS["sell"], width=2, dash="dash"),
                      annotation_text=f"Market price IDR {price:,.0f}",
                      annotation_position="top left",
                      annotation_font=dict(size=11, color=COLORS["sell"]))

    finite = [v for v in vals if np.isfinite(v)]
    top = max(finite + ([price] if price and np.isfinite(price) else [0]))
    layout = _base("Scenario fair value against market price (IDR per share)", 350)
    layout["yaxis"]["range"] = [0, top * 1.28]
    layout["yaxis"]["title"] = dict(text="IDR per share", font=dict(size=11))
    layout["showlegend"] = False
    fig.update_layout(**layout)
    return fig

