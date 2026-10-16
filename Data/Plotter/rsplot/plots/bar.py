"""Grouped bar chart with error bars."""
from __future__ import annotations

import numpy as np

from .. import registry as reg
from .. import style as st
from ..pipeline import _py
from . import HI, LO, VALUE, Option, register_plot

HATCHES = ["", "///", "\\\\\\", "xxx", "...", "+++", "ooo", "---"]


def _fmt(v: float) -> str:
    a = abs(v)
    return f"{v:.0f}" if a >= 100 else f"{v:.1f}" if a >= 10 else f"{v:.2f}" if a >= 0.1 \
        else f"{v:.3f}"


@register_plot(
    "bar", "Grouped bar with error bars", x="discrete", default_agg="mean",
    default_spread="std", secondary=True, point_word="bar",
    options=[Option("orientation", "choice", "vertical", "Orientation",
                    ["vertical", "horizontal"]),
             Option("group_width", "float", 0.8, "Group width", min=0.2, max=1.0),
             Option("capsize", "float", None, "Error-bar cap width (pt, 0 = none)", min=0, max=10),
             Option("show_errorbars", "bool", True, "Error bars"),
             Option("value_labels", "bool", False, "Value on each bar"),
             Option("baseline", "float", None, "Bar baseline (empty = 0)")])
def bar(ctx):
    ax, o = ctx.ax, ctx.opts
    ctx.opts["x_as_category"] = True
    horizontal = o["orientation"] == "horizontal"
    cats = ctx.x_categories() if ctx.roles["x"] else [None]
    hue_col = ctx.roles["hue"]
    hues = ctx.levels.get("hue_present", ctx.levels.get("hue", [])) if hue_col else [None]
    hue_index = {reg._value_key(_py(h)): i for i, h in enumerate(hues)}
    nh = max(len(hues), 1)
    width = o["group_width"] / nh
    base = o["baseline"] or 0.0
    cap = ctx.capsize if o["capsize"] is None else float(o["capsize"])
    for s in ctx.series():
        df = s.df
        pos = ctx.xpos(df) if ctx.roles["x"] else np.zeros(len(df))
        hi_ = hue_index.get(reg._value_key(_py(s.hue)), 0) if hue_col else 0
        pos = pos + (hi_ - (nh - 1) / 2) * width
        y = df[VALUE].to_numpy(dtype=float)
        hatch = HATCHES[hi_ % len(HATCHES)] if ctx.style.greyscale else None
        kw = dict(color=s.colour, edgecolor="white", linewidth=0.6, hatch=hatch, zorder=2)
        if horizontal:
            bars = ax.barh(pos, y - base, height=width * 0.94, left=base, **kw)
        else:
            bars = ax.bar(pos, y - base, width=width * 0.94, bottom=base, **kw)
        if o["show_errorbars"] and ctx.spread_available(df):
            err = np.vstack([np.clip(y - df[LO], 0, None), np.clip(df[HI] - y, 0, None)])
            ekw = dict(fmt="none", ecolor=st.ink_secondary(), elinewidth=ctx.line_width * 0.7,
                       capsize=cap, capthick=ctx.line_width * 0.7, zorder=3)
            if horizontal:
                ax.errorbar(y, pos, xerr=err, **ekw)
            else:
                ax.errorbar(pos, y, yerr=err, **ekw)
        if o["value_labels"] or ctx.style.annotate:
            top = df[HI].to_numpy(dtype=float) if (o["show_errorbars"] and
                                                   ctx.spread_available(df)) else y
            for p, v, t in zip(pos, y, np.where(np.isfinite(top), top, y)):
                if not np.isfinite(v):
                    continue
                xy, off, ha, va = ((t, p), (3, 0), "left", "center") if horizontal else \
                    ((p, t), (0, 2), "center", "bottom")
                ax.annotate(_fmt(v), xy, xytext=off, textcoords="offset points", ha=ha, va=va,
                            fontsize=ctx.sizes["annotation"], color=st.ink_secondary(),
                            annotation_clip=False)
        ctx.add_handle(s, kind="patch")
        del bars
    labels = [ctx.value_label(ctx.roles["x"], c) if c is not None else "" for c in cats]
    if horizontal:
        ax.set_yticks(range(len(cats)), labels)
        ax.set_ylim(len(cats) - 0.5, -0.5)          # first category at the top
        ax.tick_params(axis="y", length=0)
    else:
        ax.set_xticks(range(len(cats)), labels)
        ax.set_xlim(-0.5, len(cats) - 0.5)
        ax.tick_params(axis="x", length=0)
    (ax.axvline if horizontal else ax.axhline)(base, color=st.ink_secondary(),
                                               linewidth=0.6, zorder=1)
