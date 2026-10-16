"""Line (with spread band / error bars) and scatter plots."""
from __future__ import annotations

import numpy as np

from .. import style as st
from . import HI, LO, VALUE, Option, register_plot
from .trend import OPTIONS as TREND_OPTIONS
from .trend import describe_trend, draw_trend

SPREAD_DISPLAY = Option("spread_display", "choice", "errorbars", "Show spread as",
                        ["errorbars", "band", "both", "none"])
CAPSIZE = Option("capsize", "float", None, "Error-bar cap width (pt, 0 = none)", min=0, max=10,
                 help="Empty = style preset default")
AUTO_DODGE = 0.06   # fraction of the x step between series when error bars are shown
RASTER_ABOVE = 3000   # rasterise point clouds this large inside vector output


def _spread(ctx, x, df, colour, mode):
    if mode == "none" or not ctx.spread_available(df):
        return
    y = df[VALUE].to_numpy(dtype=float)
    lo, hi = df[LO].to_numpy(dtype=float), df[HI].to_numpy(dtype=float)
    if mode in ("band", "both") and len(x) > 1 and not ctx.x_categorical:
        ctx.ax.fill_between(x, lo, hi, color=colour, alpha=ctx.style.band_alpha,
                            linewidth=0, zorder=1)
    if mode in ("errorbars", "both") or (mode == "band" and (ctx.x_categorical or len(x) == 1)):
        err = np.vstack([np.clip(y - lo, 0, None), np.clip(hi - y, 0, None)])
        ctx.ax.errorbar(x, y, yerr=err, fmt="none", ecolor=colour,
                        elinewidth=ctx.line_width * 0.75, capthick=ctx.line_width * 0.75,
                        capsize=_capsize(ctx), zorder=2)


def _capsize(ctx):
    c = ctx.opts.get("capsize")
    return ctx.capsize if c is None else float(c)


def _direct_label(ctx, x, y, s):
    if not len(x) or s.hue is None:
        return
    i = int(np.nanargmax(x)) if np.isfinite(x).any() else len(x) - 1
    ctx.ax.annotate(ctx.value_label(ctx.roles["hue"], s.hue), (x[i], y[i]),
                    xytext=(4, 0), textcoords="offset points", va="center", ha="left",
                    fontsize=ctx.sizes["annotation"], color=st.ink_secondary(),
                    annotation_clip=False)


@register_plot(
    "line", "Line with spread", x="any", default_agg="mean", default_spread="std", secondary=True,
    describe=describe_trend,
    options=[SPREAD_DISPLAY, CAPSIZE,
             Option("show_markers", "bool", True, "Markers"),
             Option("dodge", "float", None, "Dodge series (fraction of x step)", min=0, max=0.5,
                    help="Empty = automatic (small offset when error bars overlap)"),
             Option("x_as_category", "bool", False, "Treat x as categories"),
             *TREND_OPTIONS])
def line(ctx):
    ax, o = ctx.ax, ctx.opts
    series = list(ctx.series())
    dodge = o["dodge"]
    if dodge is None:
        dodge = AUTO_DODGE if (o["spread_display"] in ("errorbars", "both") and len(series) > 1
                               and ctx.spread_available(ctx.data)) else 0.0
    offsets = ctx.dodge_offsets(len(series), dodge * ctx.min_x_step())
    for s, off in zip(series, offsets):
        df = s.df
        x = ctx.xpos(df) + off
        order = np.argsort(x, kind="stable")
        df, x = df.iloc[order], x[order]
        y = df[VALUE].to_numpy(dtype=float)
        _spread(ctx, x, df, s.colour, o["spread_display"])
        ax.plot(x, y, color=s.colour, linestyle=s.linestyle, linewidth=ctx.line_width,
                marker=s.marker if o["show_markers"] else None, markersize=ctx.marker_size,
                markeredgecolor="white", zorder=3)
        ctx.add_handle(s, marker=o["show_markers"])
        if ctx.style.annotate:
            _direct_label(ctx, x, y, s)
    draw_trend(ctx, series)
    if ctx.x_categorical:
        ctx.set_categorical_xticks()


@register_plot(
    "scatter", "Scatter / metric vs metric", x="any", default_agg="none", secondary=True,
    default_spread="none", describe=describe_trend,
    options=[Option("spread_display", "choice", "errorbars", "Show spread as",
                    ["errorbars", "none"]), CAPSIZE,
             Option("alpha", "float", 0.85, "Point opacity", min=0.05, max=1),
             Option("jitter", "float", 0.0, "Jitter (fraction of x step)", min=0, max=0.4),
             Option("x_as_category", "bool", False, "Treat x as categories"),
             *TREND_OPTIONS])
def scatter(ctx):
    ax, o = ctx.ax, ctx.opts
    rng = np.random.default_rng(0)
    series = list(ctx.series())
    for s in series:
        df = s.df
        x = ctx.xpos(df)
        if o["jitter"]:
            x = x + rng.uniform(-1, 1, len(x)) * o["jitter"] * ctx.min_x_step()
        y = df[VALUE].to_numpy(dtype=float)
        if o["spread_display"] == "errorbars":
            if ctx.spread_available(df):
                err = np.vstack([np.clip(y - df[LO], 0, None), np.clip(df[HI] - y, 0, None)])
                ax.errorbar(x, y, yerr=err, fmt="none", ecolor=s.colour, alpha=0.6,
                            elinewidth=ctx.line_width * 0.6, capsize=_capsize(ctx), zorder=2)
            if "__xlo__" in df and np.isfinite(df["__xlo__"].to_numpy(dtype=float)).any():
                xerr = np.vstack([np.clip(x - df["__xlo__"], 0, None),
                                  np.clip(df["__xhi__"] - x, 0, None)])
                ax.errorbar(x, y, xerr=xerr, fmt="none", ecolor=s.colour, alpha=0.6,
                            elinewidth=ctx.line_width * 0.6, capsize=_capsize(ctx), zorder=2)
        ax.scatter(x, y, s=ctx.marker_size ** 2 * 1.4, color=s.colour, marker=s.marker,
                   alpha=o["alpha"], edgecolors="white", linewidths=0.4, zorder=3,
                   rasterized=len(x) > RASTER_ABOVE)
        if ctx.style.annotate and ctx.roles["by"]:
            for xi, yi, (_, row) in list(zip(x, y, df.iterrows()))[:40]:
                txt = ", ".join(ctx.value_label(b, row[b]) for b in ctx.roles["by"] if b in row)
                ax.annotate(txt, (xi, yi), xytext=(3, 2), textcoords="offset points",
                            fontsize=ctx.sizes["annotation"], color=st.ink_secondary())
        ctx.add_handle(s, kind="marker")
    draw_trend(ctx, series)
    if ctx.x_categorical:
        ctx.set_categorical_xticks()
