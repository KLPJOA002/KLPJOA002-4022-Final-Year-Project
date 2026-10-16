"""Per-frame time series (one line per trial / series unit)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import VALUE, Option, register_plot


def _describe(pre, o) -> str:
    unit = pre.roles["by"][-1] if pre.roles["by"] else None
    n_lines = pre.raw.groupby([c for c in [pre.roles["hue"], *pre.roles["by"]] if c],
                              dropna=False).ngroups if (pre.roles["hue"] or pre.roles["by"]) \
        else 1
    smooth = f"; rolling median over {o['window']} frames" if o.get("window", 0) > 1 else ""
    per = f" (one per {unit.replace('_', ' ')})" if unit else ""
    return f"{n_lines} series{per}{smooth}."


@register_plot(
    "timeseries", "Per-frame time series", x="numeric", default_agg="none",
    default_spread="none", auto_by="series_unit", describe=_describe,
    options=[Option("window", "int", 1, "Rolling median window (frames, 1 = off)", min=1,
                    max=500),
             Option("show_raw", "bool", True, "Show raw values behind smoothed line"),
             Option("raw_alpha", "float", 0.25, "Raw line opacity", min=0.02, max=1),
             Option("line_alpha", "float", 0.9, "Line opacity", min=0.05, max=1),
             Option("show_markers", "bool", False, "Markers")])
def timeseries(ctx):
    ax, o = ctx.ax, ctx.opts
    w = int(o["window"] or 1)
    for s in ctx.series():
        df = s.df
        x = ctx.xpos(df)
        order = np.argsort(x, kind="stable")
        x = x[order]
        y = df[VALUE].to_numpy(dtype=float)[order]
        lw = ctx.line_width * 0.8
        if w > 1:
            ys = pd.Series(y).rolling(w, center=True, min_periods=1).median().to_numpy()
            if o["show_raw"]:
                ax.plot(x, y, color=s.colour, linewidth=lw * 0.6, alpha=o["raw_alpha"],
                        zorder=1, rasterized=len(x) > 5000)
        else:
            ys = y
        ax.plot(x, ys, color=s.colour, linestyle=s.linestyle, linewidth=lw,
                alpha=o["line_alpha"], marker=s.marker if o["show_markers"] else None,
                markersize=ctx.marker_size * 0.7, zorder=2)
        ctx.add_handle(s, marker=o["show_markers"])
