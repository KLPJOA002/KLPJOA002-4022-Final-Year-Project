"""Distribution plots: box / violin (+ strip overlay) and histogram / CDF."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import registry as reg
from .. import style as st
from ..pipeline import METRIC, _py
from . import VALUE, Option, register_plot

RASTER_ABOVE = 2000
WHISKERS = {"1.5 × IQR": 1.5, "min–max": (0, 100), "5–95 %": (5, 95)}


def _group_n(pre, keys) -> str:
    keys = [k for k in keys if k and k in pre.raw]
    n = pre.raw.groupby(keys, dropna=False).size() if keys else pd.Series([len(pre.raw)])
    if not len(n):
        return "0"
    lo, hi = int(n.min()), int(n.max())
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


def _box_keys(pre):
    r = pre.roles
    return [r["x"] if not pre.x_is_metric else None, r["hue"], r["style"], r["facet_col"],
            r["facet_row"], *r["by"]]


def _describe_box(pre, o) -> str:
    n = _group_n(pre, _box_keys(pre))
    kind = o.get("kind", "box")
    whisk = o.get("whiskers", "1.5 × IQR")
    if kind == "violin":
        shape = "Violins show the distribution (kernel density) with median and IQR"
    else:
        shape = f"Boxes show median and IQR, whiskers {whisk}"
    strip = "; dots are individual " + pre.unit_name if o.get("strip") else ""
    return f"{shape}{strip}; n = {n} {pre.unit_name} per {'violin' if kind == 'violin' else 'box'}."


@register_plot(
    "box", "Box / violin (+ points)", x="discrete", needs_raw=True, default_agg="none",
    default_spread="none", describe=_describe_box,
    options=[Option("kind", "choice", "box", "Shape", ["box", "violin", "both"]),
             Option("strip", "bool", False, "Overlay individual points"),
             Option("strip_alpha", "float", 0.45, "Point opacity", min=0.05, max=1),
             Option("whiskers", "choice", "1.5 × IQR", "Whiskers", list(WHISKERS)),
             Option("show_outliers", "bool", True, "Show outliers (when no points)"),
             Option("show_mean", "bool", False, "Mark the mean"),
             Option("group_width", "float", 0.8, "Group width", min=0.2, max=1.0),
             Option("fill_alpha", "float", 0.35, "Fill opacity", min=0, max=1)])
def box(ctx):
    ax, o = ctx.ax, ctx.opts
    ctx.opts["x_as_category"] = True
    raw = ctx.raw
    hue_col = ctx.roles["hue"]
    hues = ctx.levels.get("hue_present", ctx.levels.get("hue", [])) if hue_col else [None]
    hue_index = {reg._value_key(_py(h)): i for i, h in enumerate(hues)}
    nh = max(len(hues), 1)
    width = o["group_width"] / nh
    cats = ctx.x_categories() if ctx.roles["x"] else [None]
    rng = np.random.default_rng(0)
    lw = ctx.line_width * 0.8
    for s in ctx.series(raw):
        df = s.df
        pos_all = ctx.xpos(df) if ctx.roles["x"] else np.zeros(len(df))
        hi_ = hue_index.get(reg._value_key(_py(s.hue)), 0) if hue_col else 0
        off = (hi_ - (nh - 1) / 2) * width
        values = df[VALUE].to_numpy(dtype=float)
        groups, positions = [], []
        for p in np.unique(pos_all[np.isfinite(pos_all)]):
            v = values[(pos_all == p) & np.isfinite(values)]
            if len(v):
                groups.append(v)
                positions.append(p + off)
        if not groups:
            continue
        if o["kind"] in ("violin", "both"):
            parts = ax.violinplot(groups, positions=positions, widths=width * 0.9,
                                  showextrema=False)
            for b in parts["bodies"]:
                b.set_facecolor(s.colour)
                b.set_edgecolor(s.colour)
                b.set_alpha(o["fill_alpha"] if o["kind"] == "violin" else o["fill_alpha"] * 0.6)
                b.set_linewidth(lw * 0.6)
            if o["kind"] == "violin":
                for g, p in zip(groups, positions):
                    q1, med, q3 = np.percentile(g, [25, 50, 75])
                    ax.vlines(p, q1, q3, color=s.colour, linewidth=lw * 2.5, zorder=3)
                    ax.scatter([p], [med], s=ctx.marker_size ** 2, color="white",
                               edgecolors=s.colour, linewidths=lw, zorder=4)
        if o["kind"] in ("box", "both"):
            whis = WHISKERS[o["whiskers"]]
            bp = ax.boxplot(groups, positions=positions, widths=width * (0.45 if o["kind"] ==
                                                                         "both" else 0.75),
                            whis=whis, patch_artist=True, manage_ticks=False,
                            showfliers=o["show_outliers"] and not o["strip"],
                            showmeans=o["show_mean"],
                            medianprops=dict(color=st.ink(), linewidth=lw * 1.4),
                            boxprops=dict(edgecolor=s.colour, linewidth=lw),
                            whiskerprops=dict(color=s.colour, linewidth=lw),
                            capprops=dict(color=s.colour, linewidth=lw),
                            meanprops=dict(marker="D", markerfacecolor="white",
                                           markeredgecolor=st.ink(),
                                           markersize=ctx.marker_size * 0.9),
                            flierprops=dict(marker=".", markersize=ctx.marker_size * 0.8,
                                            markerfacecolor=s.colour, markeredgecolor="none",
                                            alpha=0.6))
            for patch in bp["boxes"]:
                r, g, b, _ = __import__("matplotlib").colors.to_rgba(s.colour)
                patch.set_facecolor((r, g, b, o["fill_alpha"]))
        if o["strip"]:
            jit = width * 0.18
            for g, p in zip(groups, positions):
                xs = p + rng.uniform(-jit, jit, len(g))
                ax.scatter(xs, g, s=(ctx.marker_size * 0.8) ** 2, color=s.colour,
                           alpha=o["strip_alpha"], edgecolors="none", zorder=5,
                           rasterized=len(g) > RASTER_ABOVE)
        ctx.add_handle(s, kind="patch")
    if ctx.roles["x"]:
        ctx.set_categorical_xticks()
    else:
        ax.set_xticks([])
        ax.set_xlim(-0.5, 0.5)


def _describe_hist(pre, o) -> str:
    r = pre.roles
    n = _group_n(pre, [r["hue"], r["style"], r["facet_col"], r["facet_row"], *r["by"]])
    what = "Empirical cumulative distribution" if o.get("kind") == "cdf" else "Histogram"
    return f"{what}; n = {n} {pre.unit_name} per curve."


@register_plot(
    "hist", "Histogram / CDF", x="none", needs_raw=True, default_agg="none",
    default_spread="none", roles=("hue", "facet"), describe=_describe_hist,
    options=[Option("kind", "choice", "hist", "Kind", ["hist", "cdf"]),
             Option("bins", "int", 30, "Bins", min=2, max=500),
             Option("density", "bool", False, "Normalise (density / fraction)"),
             Option("histtype", "choice", "step", "Bar style", ["step", "filled", "bars"]),
             Option("common_bins", "bool", True, "Same bins for every series"),
             Option("fill_alpha", "float", 0.3, "Fill opacity", min=0, max=1)])
def hist(ctx):
    ax, o = ctx.ax, ctx.opts
    series = list(ctx.series(ctx.raw))
    allv = ctx.pre.raw[VALUE].to_numpy(dtype=float)
    allv = allv[np.isfinite(allv)]
    if not len(allv):
        return
    if ctx.style.xlog and (allv > 0).all():
        edges = np.geomspace(allv.min(), allv.max(), o["bins"] + 1)
    else:
        edges = np.histogram_bin_edges(allv, bins=o["bins"])
    if o["kind"] == "cdf":
        ctx.opts["_ylabel"] = "Cumulative fraction"
    else:
        ctx.opts["_ylabel"] = "Fraction" if o["density"] else "Count"
    for s in series:
        v = s.df[VALUE].to_numpy(dtype=float)
        v = v[np.isfinite(v)]
        if not len(v):
            continue
        if o["kind"] == "cdf":
            xs = np.sort(v)
            ys = np.arange(1, len(xs) + 1) / len(xs)
            ax.step(np.r_[xs[0], xs], np.r_[0, ys], where="post", color=s.colour,
                    linestyle=s.linestyle, linewidth=ctx.line_width)
            ctx.add_handle(s, marker=False)
            continue
        bins = edges if o["common_bins"] else o["bins"]
        weights = np.full(len(v), 1 / len(v)) if o["density"] else None
        if o["histtype"] == "step":
            ax.hist(v, bins=bins, weights=weights, histtype="step", color=s.colour,
                    linewidth=ctx.line_width, linestyle=s.linestyle)
            ctx.add_handle(s, marker=False)
        else:
            ax.hist(v, bins=bins, weights=weights,
                    histtype="stepfilled" if o["histtype"] == "filled" else "bar",
                    color=s.colour, alpha=o["fill_alpha"] if len(series) > 1 else 0.85,
                    edgecolor="white" if o["histtype"] == "bars" else s.colour,
                    linewidth=0.5)
            ctx.add_handle(s, kind="patch")
    if o["kind"] == "cdf":
        ax.set_ylim(0, 1.02)
    else:
        ax.set_ylim(bottom=0)
