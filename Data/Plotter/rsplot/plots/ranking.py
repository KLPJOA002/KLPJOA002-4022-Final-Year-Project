"""Top-N ranking (horizontal bars), from pre-ranked files or computed from a sweep."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .. import registry as reg
from .. import style as st
from ..pipeline import METRIC, _py, lower_first
from . import HI, LO, N, VALUE, Option, register_plot

MIN_N_FRACTION = 0.8     # default: items need >= 80 % of the largest n to be ranked


def _ascending(ctx, metric) -> bool:
    order = ctx.opts["order"]
    if order == "auto":
        return reg.better_direction(metric) != "higher"
    return order == "lowest first"


def _highlight(ctx):
    v = ctx.opts.get("highlight")
    if v is not None:
        return v
    b = ctx.ds.family.baseline or {}
    return b.get("value") if b.get("column") == ctx.roles["x"] else None


def _rank(ctx, df, metric):
    """(ranked rows, highlight row or None, n excluded, min_n)."""
    if METRIC in df:
        df = df[df[METRIC] == metric]
    df = df[np.isfinite(df[VALUE].to_numpy(dtype=float))]
    nmax = df[N].max() if len(df) else 0
    min_n = ctx.opts["min_n"]
    if min_n is None:
        min_n = int(np.ceil(MIN_N_FRACTION * nmax)) if nmax > 1 else 1
    ok = df[df[N] >= min_n]
    excluded = len(df) - len(ok)
    ok = ok.sort_values(VALUE, ascending=_ascending(ctx, metric), kind="stable")
    hl = _highlight(ctx)
    hl_row = None
    if hl is not None:
        key = reg._value_key(_py(hl))
        m = df["__x__"].map(lambda v: reg._value_key(_py(v)) == key)
        if m.any():
            hl_row = df[m].iloc[0]
    top = ok.head(int(ctx.opts["top_n"]))
    return top, hl_row, excluded, min_n


def _describe(pre, o) -> str:
    if pre.data.empty:
        return ""
    m = pre.metrics[0]
    item = reg.axis_label(pre.roles["x"]).split(" (")[0].lower()
    n_items = pre.data["__x__"].nunique()
    better = "lower is better" if reg.better_direction(m) != "higher" else "higher is better"
    if o.get("order") == "lowest first":
        better = "lowest first"
    elif o.get("order") == "highest first":
        better = "highest first"
    n = pre.data[N].dropna()
    s = (f"Top {min(int(o.get('top_n', 15)), n_items)} of {n_items} {item}s by "
         f"{lower_first(reg.axis_label(m).split(' (')[0])} ({better}).")
    if pre.aggregated and len(n) and n.max() > 1:
        nmax = int(n.max())
        min_n = o.get("min_n") or int(np.ceil(MIN_N_FRACTION * nmax))
        s += f" Items with fewer than {min_n} {pre.unit_name} are not ranked."
    return s


def _min_height(pre, o, tick_pt) -> float:
    """Height (cm) at which every item label has its own line."""
    if pre.data.empty:
        return 0.0
    r = pre.roles
    groups = [c for c in (r["facet_row"], r["facet_col"]) if c and c in pre.data]
    counts = pre.data.groupby(groups, dropna=False)["__x__"].nunique() if groups else \
        [pre.data["__x__"].nunique()]
    top = int(o.get("top_n", 15))
    rows = sum(min(top, int(c)) + 1.3 for c in counts)          # + reference row and gap
    line_cm = tick_pt * 1.6 / 72 * 2.54
    return rows * line_cm + len(counts) * 1.4 + 2.2              # panel titles, x axis, note


@register_plot(
    "ranking", "Top-N ranking", x="discrete", roles=("hue", "facet"), default_agg="mean",
    default_spread="std", describe=_describe, point_word="item", min_height_cm=_min_height,
    options=[Option("top_n", "int", 15, "Show top N", min=1, max=200),
             Option("mark", "choice", "auto", "Draw as", ["auto", "bars", "dots"],
                    help="auto: dots with a zoomed axis when the values differ by < 20 %, "
                         "otherwise bars from zero"),
             Option("order", "choice", "auto", "Order",
                    ["auto", "lowest first", "highest first"],
                    help="auto: best first, using the metric's 'better' direction"),
             Option("min_n", "int", None, "Minimum n per item (empty = 80 % of the largest)",
                    min=1),
             Option("show_values", "bool", True, "Values on bars"),
             Option("show_bar_n", "bool", False, "n on bars"),
             Option("highlight", "value", None, "Highlight item (e.g. baseline)", of="@x"),
             Option("reference_line", "bool", True, "Reference line at highlighted item"),
             Option("error_column", "column", None, "± error from column (pre-computed files)",
                    choices=["metrics"],
                    help="e.g. std_acc_rmse_mm in ranking_*.csv; used when not aggregating"),
             Option("capsize", "float", None, "Error-bar cap width (pt, 0 = none)", min=0,
                    max=10)])
def ranking(ctx):
    ax, o = ctx.ax, ctx.opts
    metric = ctx.pre.metrics[0]
    for role, lev in zip(("facet_row", "facet_col"), ctx.facet_levels):
        if ctx.roles[role] == METRIC:
            metric = lev
    data = ctx.data
    ecol = o.get("error_column")
    if ecol and ecol in ctx.ds.profile and not ctx.pre.aggregated:
        src = ctx.ds.frame().drop_duplicates(ctx.roles["x"]).set_index(ctx.roles["x"])[ecol]
        err = data["__x__"].map(src).astype(float).to_numpy()
        data = data.assign(**{LO: data[VALUE] - err, HI: data[VALUE] + err})
    if ctx.roles["hue"] and data["__x__"].duplicated().any() and ctx.facet_index == 0:
        ctx.pre.warnings.append("Colour splits items into several entries (each colour is "
                                "ranked separately). Use small multiples (facet) for one "
                                "ranking per group.")
    top, hl_row, excluded, min_n = _rank(ctx, data, metric)
    rows = list(top.iterrows())
    in_top = hl_row is not None and any(
        reg._value_key(_py(r["__x__"])) == reg._value_key(_py(hl_row["__x__"])) for _, r in rows)
    extra = [] if (hl_row is None or in_top) else [(None, hl_row)]
    allrows = rows + extra
    cap = ctx.capsize if o["capsize"] is None else float(o["capsize"])
    vals = np.array([float(r[VALUE]) for _, r in allrows]) if allrows else np.array([0.0])
    span = (vals.max() - vals.min()) / max(abs(vals).max(), 1e-12)
    dots = o["mark"] == "dots" or (o["mark"] == "auto" and span < 0.2)
    labels = []
    for pos, (_, r) in enumerate(allrows):
        is_hl = hl_row is not None and reg._value_key(_py(r["__x__"])) == \
            reg._value_key(_py(hl_row["__x__"]))
        colour = st.ink_secondary() if is_hl else ctx.colour(r[ctx.roles["hue"]]) \
            if ctx.roles["hue"] else ctx.colour()
        y = pos + (0.6 if extra and pos == len(allrows) - 1 else 0)
        v = float(r[VALUE])
        if dots:
            ax.hlines(y, 0, 1, transform=ax.get_yaxis_transform(), color="#ececec",
                      linewidth=0.6, zorder=0)
            ax.plot([v], [y], marker="D" if is_hl else "o", color=colour, linestyle="none",
                    markersize=ctx.marker_size * 1.4, markeredgecolor="white", zorder=4)
        else:
            ax.barh(y, v, height=0.72, color=colour, edgecolor="white", linewidth=0.5,
                    zorder=2, alpha=0.55 if is_hl else 1)
        end = v
        if np.isfinite(r.get(LO, np.nan)) and np.isfinite(r.get(HI, np.nan)):
            ax.errorbar(v, y, xerr=[[max(v - r[LO], 0)], [max(r[HI] - v, 0)]], fmt="none",
                        ecolor=st.ink_secondary(), elinewidth=ctx.line_width * 0.7,
                        capsize=cap, zorder=3)
            end = max(v, r[HI])
        txt = []
        if o["show_values"]:
            txt.append(_fmt(v))
        if o["show_bar_n"] and pd.notna(r.get(N)):
            txt.append(f"n = {int(r[N])}")
        if txt:
            ax.annotate("  ".join(txt), (end, y), xytext=(3, 0), textcoords="offset points",
                        va="center", ha="left", fontsize=ctx.sizes["annotation"],
                        color=st.ink_secondary(), annotation_clip=False)
        lab = ctx.value_label(ctx.roles["x"], r["__x__"])
        labels.append((y, lab + (" — reference" if is_hl and not in_top else "")))
        if is_hl and o["reference_line"]:
            ax.axvline(v, color=st.ink_secondary(), linewidth=0.7, linestyle=(0, (4, 3)),
                       zorder=1)
        if ctx.roles["hue"]:
            from . import Series
            hv = r[ctx.roles["hue"]]
            ctx.add_handle(Series(hv, None, (), top, ctx.colour(hv), "o", "-", ()),
                           kind="marker" if dots else "patch")
    ax.set_yticks([y for y, _ in labels], [t for _, t in labels])
    ax.set_ylim(max([y for y, _ in labels], default=0) + 0.6, -0.6)
    ax.tick_params(axis="y", length=0)
    if not dots:
        ax.axvline(0, color=st.ink_secondary(), linewidth=0.6, zorder=1)
    ctx.opts["_ranking_dots"] = dots
    if excluded and ctx.facet_index == 0:
        ctx.pre.warnings.append(f"{excluded} item(s) with n < {min_n} were not ranked "
                                "(change “Minimum n per item” to include them).")


def _fmt(v: float) -> str:
    a = abs(v)
    s = f"{v:.0f}" if a >= 100 else f"{v:.1f}" if a >= 10 else f"{v:.2f}" if a >= 0.1 \
        else f"{v:.3f}"
    return s.replace("-", "−")
