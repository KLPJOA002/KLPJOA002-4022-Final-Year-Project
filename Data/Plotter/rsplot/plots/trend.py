"""Trend lines shared by the scatter and line plots (numpy-only fits)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd
from matplotlib import patheffects
from matplotlib.lines import Line2D

from .. import style as st
from . import VALUE, Option

KINDS = ["none", "linear", "quadratic", "cubic", "exponential", "logarithmic", "power",
         "smooth (LOWESS)", "moving median"]
LEAST_SQUARES = {"linear": 1, "quadratic": 2, "cubic": 3}
# distinct x values needed; polynomials need one more than their parameters, so a fit
# never just interpolates the points (a cubic through 4 x values is not a trend)
MIN_POINTS = {"linear": 2, "quadratic": 4, "cubic": 5, "exponential": 2, "logarithmic": 2,
              "power": 2, "smooth (LOWESS)": 5, "moving median": 3}
DESCRIPTION = {"linear": "linear least-squares fit", "quadratic": "quadratic least-squares fit",
               "cubic": "cubic least-squares fit",
               "exponential": "exponential fit (least squares on ln y)",
               "logarithmic": "logarithmic fit", "power": "power-law fit (least squares on ln–ln)",
               "smooth (LOWESS)": "LOWESS smooth", "moving median": "moving median"}
SHOW_TREND = {"trend": [k for k in KINDS if k != "none"]}

OPTIONS = [
    Option("trend", "choice", "none", "Trend line", KINDS),
    Option("trend_scope", "choice", "per series", "Fit", ["per series", "all data"],
           show_if=SHOW_TREND),
    Option("trend_data", "choice", "shown points", "Fit to", ["shown points", "all rows"],
           show_if=SHOW_TREND,
           help="all rows: fit the individual rows behind aggregated points"),
    Option("trend_label", "choice", "none", "Trend label", ["none", "R²", "equation + R²"],
           show_if=SHOW_TREND),
    Option("trend_band", "bool", False, "95 % confidence band (linear / quadratic / cubic)",
           show_if={"trend": list(LEAST_SQUARES)}),
    Option("trend_span", "float", 0.6, "LOWESS span (fraction of points)", min=0.1, max=1.0,
           show_if={"trend": ["smooth (LOWESS)"]}),
    Option("trend_window", "int", 5, "Moving-median window (points)", min=2, max=200,
           show_if={"trend": ["moving median"]}),
    Option("trend_extend", "bool", False, "Extend over the whole x axis",
           show_if={"trend": ["linear", "quadratic", "cubic", "exponential", "logarithmic",
                              "power"]}),
]


@dataclass
class TrendFit:
    kind: str
    predict: Callable[[np.ndarray], np.ndarray]
    r2: float | None
    equation: str
    xmin: float
    xmax: float
    coef: tuple = ()


# ------------------------------------------------------------------- fits --
def _r2(y, yhat) -> float | None:
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - np.mean(y)) ** 2))
    return 1 - ss_res / ss_tot if ss_tot > 0 else None


def _num(v: float) -> str:
    a = abs(v)
    s = f"{v:.3g}" if a >= 1e-3 or a == 0 else f"{v:.2e}"
    return s.replace("-", "−")


def _poly_eq(c) -> str:
    deg = len(c) - 1
    terms = []
    for i, a in enumerate(c):
        p = deg - i
        t = _num(a) + ("" if p == 0 else "x" if p == 1 else f"x^{p}".replace("^2", "²")
                       .replace("^3", "³"))
        terms.append(t)
    return "y = " + " + ".join(terms).replace("+ −", "− ")


def lowess(x, y, span=0.6, xs=None):
    """Locally weighted linear regression with tricube weights (no robustness steps)."""
    xs = x if xs is None else xs
    n = len(x)
    k = max(3, int(np.ceil(span * n)))
    out = np.empty(len(xs))
    for i, x0 in enumerate(xs):
        d = np.abs(x - x0)
        h = np.partition(d, k - 1)[k - 1] or 1e-12
        w = np.clip(1 - (d / h) ** 3, 0, None) ** 3
        sw = w.sum()
        if sw <= 0:
            out[i] = np.nan
            continue
        xm, ym = (w * x).sum() / sw, (w * y).sum() / sw
        var = (w * (x - xm) ** 2).sum()
        b = (w * (x - xm) * (y - ym)).sum() / var if var > 0 else 0.0
        out[i] = ym + b * (x0 - xm)
    return out


def fit_trend(x, y, kind: str, span: float = 0.6, window: int = 5) -> TrendFit | str:
    """Fit a trend; returns a TrendFit or a short reason why it cannot be fitted."""
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    need = MIN_POINTS.get(kind, 2)
    if len(np.unique(x)) < need:
        return f"needs at least {need} different x values"
    lo, hi = float(x.min()), float(x.max())
    if kind in LEAST_SQUARES:
        c = np.polyfit(x, y, LEAST_SQUARES[kind])
        f = lambda t, c=c: np.polyval(c, t)
        return TrendFit(kind, f, _r2(y, f(x)), _poly_eq(c), lo, hi, tuple(c))
    if kind == "exponential":
        if (y <= 0).any():
            return "needs y > 0"
        b, ln_a = np.polyfit(x, np.log(y), 1)
        a = float(np.exp(ln_a))
        f = lambda t, a=a, b=b: a * np.exp(b * t)
        return TrendFit(kind, f, _r2(y, f(x)), f"y = {_num(a)}·e^({_num(b)}x)", lo, hi, (a, b))
    if kind == "logarithmic":
        if (x <= 0).any():
            return "needs x > 0"
        b, a = np.polyfit(np.log(x), y, 1)
        f = lambda t, a=a, b=b: a + b * np.log(t)
        return TrendFit(kind, f, _r2(y, f(x)),
                        f"y = {_num(a)} + {_num(b)}·ln x".replace("+ −", "− "), lo, hi, (a, b))
    if kind == "power":
        if (x <= 0).any() or (y <= 0).any():
            return "needs x > 0 and y > 0"
        b, ln_a = np.polyfit(np.log(x), np.log(y), 1)
        a = float(np.exp(ln_a))
        f = lambda t, a=a, b=b: a * np.power(t, b)
        return TrendFit(kind, f, _r2(y, f(x)), f"y = {_num(a)}·x^{_num(b)}", lo, hi, (a, b))
    if kind == "smooth (LOWESS)":
        f = lambda t, x=x, y=y: lowess(x, y, span, np.asarray(t, float))
        return TrendFit(kind, f, _r2(y, f(x)), f"LOWESS, span {span:g}", lo, hi)
    if kind == "moving median":
        order = np.argsort(x, kind="stable")
        xs_, ys_ = x[order], y[order]
        med = pd.Series(ys_).rolling(int(window), center=True, min_periods=1).median().to_numpy()
        f = lambda t, xs_=xs_, med=med: np.interp(t, xs_, med)
        return TrendFit(kind, f, _r2(ys_, med), f"moving median, {int(window)} points", lo, hi)
    return f"unknown trend type '{kind}'"


def confidence_band(x, y, deg: int, xs):
    """95 % confidence band of a least-squares polynomial at xs (mean response)."""
    from scipy import stats
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n, p = len(x), deg + 1
    if n <= p:
        return None
    X = np.vander(x, p)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    s2 = resid @ resid / (n - p)
    cov = s2 * np.linalg.pinv(X.T @ X)
    Xs = np.vander(np.asarray(xs, float), p)
    se = np.sqrt(np.einsum("ij,jk,ik->i", Xs, cov, Xs))
    t = stats.t.ppf(0.975, n - p)
    yhat = Xs @ beta
    return yhat - t * se, yhat + t * se


# ---------------------------------------------------------------- drawing --
def _points(ctx, s, use_rows: bool):
    """(x, y) the trend is fitted to for series `s`."""
    if use_rows and ctx.pre.aggregated and len(ctx.raw):
        raw = ctx.raw
        for col, v in ((ctx.roles["hue"], s.hue), (ctx.roles["style"], s.style)):
            if col and col in raw:
                raw = raw[raw[col].map(lambda u: str(u) == str(v))]
        x = ctx.xpos(raw)
        return x, raw[VALUE].to_numpy(dtype=float)
    return ctx.xpos(s.df), s.df[VALUE].to_numpy(dtype=float)


def draw_trend(ctx, series) -> None:
    """Draw the configured trend line(s) on ctx.ax for the given series."""
    o = ctx.opts
    kind = o.get("trend") or "none"
    if kind == "none":
        return
    if ctx.x_categorical:
        if ctx.facet_index == 0:
            ctx.pre.warnings.append("Trend lines need a numeric x axis; none drawn.")
        return
    use_rows = o.get("trend_data") == "all rows"
    groups = []
    if o.get("trend_scope") == "all data":
        xs = [_points(ctx, s, use_rows) for s in series]
        x = np.concatenate([a for a, _ in xs]) if xs else np.array([])
        y = np.concatenate([b for _, b in xs]) if xs else np.array([])
        groups.append((None, st.ink(), x, y))
    else:
        for s in series:
            x, y = _points(ctx, s, use_rows)
            groups.append((s, s.colour, x, y))
    xlim = ctx.ax.get_xlim()
    for s, colour, x, y in groups:
        fit = fit_trend(x, y, kind, float(o.get("trend_span") or 0.6),
                        int(o.get("trend_window") or 5))
        name = ctx.value_label(ctx.roles["hue"], s.hue) if s is not None and ctx.roles["hue"] \
            else "all data"
        if isinstance(fit, str):
            ctx.pre.warnings.append(f"{kind.capitalize()} trend skipped for {name}: {fit}.")
            continue
        lo, hi = (min(xlim[0], fit.xmin), max(xlim[1], fit.xmax)) if o.get("trend_extend") \
            else (fit.xmin, fit.xmax)
        if kind in ("logarithmic", "power"):
            lo = max(lo, fit.xmin * 1e-3 if fit.xmin > 0 else 1e-9)
        xs = np.linspace(lo, hi, 200)
        ys = fit.predict(xs)
        if o.get("trend_band") and kind in LEAST_SQUARES:
            band = confidence_band(x, y, LEAST_SQUARES[kind], xs)
            if band is not None:
                ctx.ax.fill_between(xs, band[0], band[1], color=colour,
                                    alpha=ctx.style.band_alpha * 0.8, linewidth=0, zorder=1)
        ctx.ax.plot(xs, ys, color=colour, linewidth=ctx.line_width * 0.9,
                    linestyle=(0, (5, 2.5)), zorder=2.5)
        label = trend_text(fit, o.get("trend_label", "none"))
        # One legend entry per colour is only truthful when there is one panel; with
        # facets (or no colour groups) every fitted line is labelled where it ends.
        faceted = bool(ctx.roles["facet_col"] or ctx.roles["facet_row"])
        if label and (faceted or s is None or not ctx.roles["hue"]):
            fin = np.isfinite(ys)
            if fin.any():
                j = np.flatnonzero(fin)[-1]
                ctx.ax.annotate(label, (xs[j], ys[j]), xytext=(3, 3), textcoords="offset points",
                                ha="right", va="bottom", fontsize=ctx.sizes["annotation"],
                                color=st.ink_secondary(), annotation_clip=False, zorder=6,
                                path_effects=[patheffects.withStroke(linewidth=2.5,
                                                                     foreground="white")])
        elif label or (o.get("trend_scope") == "all data" and not faceted):
            key = ("trend", name)
            if key not in ctx.legend:
                text = f"{'Trend' if s is None else name + ' trend'}" + (f" ({label})" if label
                                                                       else "")
                ctx.legend[key] = (text, Line2D([], [], color=colour, linestyle=(0, (5, 2.5)),
                                                linewidth=ctx.line_width * 0.9))


def trend_text(fit: TrendFit, mode: str) -> str:
    r2 = (f"R² = {fit.r2:.2f}".replace("-0.00", "0.00").replace("-", "−")
          if fit.r2 is not None else "")
    if mode == "R²":
        return r2
    if mode == "equation + R²":
        return ", ".join(t for t in (fit.equation if fit.kind not in (
            "smooth (LOWESS)", "moving median") else "", r2) if t)
    return ""


def describe_trend(pre, o) -> str:
    kind = o.get("trend") or "none"
    if kind == "none":
        return ""
    what = DESCRIPTION.get(kind, kind)
    if kind == "smooth (LOWESS)":
        what += f" (span {float(o.get('trend_span') or 0.6):g})"
    elif kind == "moving median":
        what += f" over {int(o.get('trend_window') or 5)} points"
    faceted = bool(pre.roles["facet_col"] or pre.roles["facet_row"])
    hue = bool(pre.roles["hue"])
    if o.get("trend_scope") == "all data" or not hue:
        scope = "per panel" if faceted else "to all data"
    else:
        scope = "per series and panel" if faceted else "per series"
    rows = ", fitted to the individual rows" if o.get("trend_data") == "all rows" and \
        pre.aggregated else ""
    band = "; shaded: 95 % confidence interval of the fit" if o.get("trend_band") and \
        kind in LEAST_SQUARES else ""
    r2 = _r2_range(pre, o, kind)
    return f"Dashed lines: {what} {scope}{rows}{r2}{band}."


def _r2_range(pre, o, kind) -> str:
    """' (R² 0.71–0.93)' over the fitted series, refitted cheaply on the plotted data."""
    if kind in ("smooth (LOWESS)", "moving median") or pre.data.empty or "__x__" not in pre.data:
        return ""
    src = pre.raw if (o.get("trend_data") == "all rows" and pre.aggregated) else pre.data
    if "__x__" not in src:
        return ""
    panel = [c for c in (pre.roles["facet_col"], pre.roles["facet_row"]) if c and c in src]
    keys = panel if o.get("trend_scope") == "all data" else \
        [c for c in (pre.roles["hue"], pre.roles["style"]) if c and c in src] + panel
    groups = src.groupby(keys, dropna=False) if keys else [((), src)]
    vals = []
    for _, g in groups:
        x = pd.to_numeric(g["__x__"], errors="coerce").to_numpy(dtype=float)
        f = fit_trend(x, g[VALUE].to_numpy(dtype=float), kind)
        if not isinstance(f, str) and f.r2 is not None:
            vals.append(f.r2)
    if not vals:
        return ""
    fmt = lambda v: f"{v:.2f}".replace("-0.00", "0.00").replace("-", "−")
    lo, hi = min(vals), max(vals)
    return f" (R² = {fmt(lo)})" if abs(hi - lo) < 0.005 else f" (R² {fmt(lo)} to {fmt(hi)})"
