"""Heatmap of an aggregated metric over two factors (x = columns, row = rows)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from matplotlib import colormaps
from matplotlib.colors import Normalize, to_rgb

from .. import registry as reg
from .. import style as st
from ..pipeline import METRIC, _py, apply_filters, lower_first
from . import N, VALUE, Option, register_plot

CMAPS = ["auto", "rs_sequential", "rs_diverging", "viridis", "cividis", "magma", "RdBu_r",
         "coolwarm", "Greys"]
MAX_ANNOTATED = (30, 40)      # columns, rows: beyond this cells are too small for text
MAX_LABELLED = 60             # beyond this many columns/rows tick labels are dropped


# ---------------------------------------------------------------- baseline --
def _reference_rows(ctx, facet_levels):
    """Rows of the baseline configuration, in the same panel, honouring user filters
    unless a filter would remove every reference row."""
    col = ctx.opts.get("baseline_column")
    val = ctx.opts.get("baseline_value")
    fam = ctx.ds.family.baseline or {}
    if col is None and val is None:
        col, val = fam.get("column"), fam.get("value")
    if not col or val is None or col not in ctx.ds.profile:
        return None
    df = ctx.ds.frame()
    key = reg._value_key(_py(val))
    ref = df[df[col].map(lambda v: reg._value_key(_py(v)) == key)]
    for f in ctx.spec.filters:
        if not f.enabled or f.column == col:
            continue
        kept = apply_filters(ref, type(ctx.spec)(filters=[f]))
        if len(kept):
            ref = kept
    for role, lev in zip(("facet_row", "facet_col"), facet_levels):
        c = ctx.roles[role]
        if c and c != METRIC and c in ref and lev is not None:
            ref = ref[ref[c].map(lambda v: reg._value_key(_py(v)) == reg._value_key(_py(lev)))]
    return ref


def _agg_ref(ctx, ref, metric):
    vals = pd.to_numeric(ref[ctx.ds.value_column(metric, ctx.spec.aggregation.stored_stat)],
                         errors="coerce").dropna()
    if vals.empty:
        return np.nan
    func = ctx.spec.aggregation.func
    return float(vals.agg(func if func in ("mean", "median", "min", "max") else "mean"))


def matched_dims(ctx, ref) -> list[str]:
    """Heatmap axes the baseline is matched on: those whose levels vary in the reference
    rows (e.g. height), not the treatment axis (e.g. decimation, fixed in the baseline)."""
    out = []
    for role in ("row", "x"):
        c = ctx.roles[role]
        if c and c in ref and ref[c].nunique(dropna=True) > 1:
            out.append(c)
    return out


def baseline_matrix(ctx, metric, facet_levels, xs, rs):
    """Baseline per cell: matched on row/column levels present in the reference rows."""
    ref = _reference_rows(ctx, facet_levels)
    B = np.full((len(rs), len(xs)), np.nan)
    if ref is None or ref.empty:
        return B, []
    dims = matched_dims(ctx, ref)
    xc, rc = ctx.roles["x"], ctx.roles["row"]
    cache = {}
    for i, rv in enumerate(rs):
        for j, xv in enumerate(xs):
            sub = ref
            k = []
            for c, v in ((rc, rv), (xc, xv)):
                if c in dims:
                    sub = sub[sub[c].map(lambda u: reg._value_key(_py(u)) == reg._value_key(_py(v)))]
                    k.append(reg._value_key(_py(v)))
            k = tuple(k)
            if k not in cache:
                cache[k] = _agg_ref(ctx, sub, metric) if len(sub) else np.nan
            B[i, j] = cache[k]
    return B, dims


def baseline_value(ctx, metric: str, facet_levels=(None, None)) -> float | None:
    """Single baseline for the whole panel (used for ranking-style references)."""
    ref = _reference_rows(ctx, facet_levels)
    if ref is None or ref.empty:
        return None
    v = _agg_ref(ctx, ref, metric)
    return None if np.isnan(v) else v


def _centre(ctx, metric, facet_levels, all_values, xs=None, rs=None):
    """Scalar centre, or a per-cell matrix for baseline mode (when xs/rs given)."""
    mode = ctx.opts["centre"]
    if mode == "value":
        return ctx.opts.get("centre_value") or 0.0
    if mode == "median":
        return float(np.nanmedian(all_values)) if np.isfinite(all_values).any() else None
    if mode == "baseline":
        if xs is None:
            return baseline_value(ctx, metric, facet_levels)
        B, _ = baseline_matrix(ctx, metric, facet_levels, xs, rs)
        return B if np.isfinite(B).any() else None
    return None


def _transform(values, c0, show_as):
    if c0 is None:
        return values
    if show_as == "% change":
        with np.errstate(divide="ignore", invalid="ignore"):
            return 100 * (values - c0) / c0
    return values - c0


# ------------------------------------------------------------------ tables --
def _metric_of(ctx):
    for role, lev in zip(("facet_row", "facet_col"), ctx.facet_levels):
        if ctx.roles[role] == METRIC:
            return lev
    return ctx.pre.metrics[0]


def _table(ctx, df):
    xc, rc = ctx.roles["x"], ctx.roles["row"]
    xs = ctx.levels.get("x_present", ctx.levels.get("x", [None])) if xc else [None]
    rs = ctx.levels.get("row_present", ctx.levels.get("row", [None])) if rc else [None]
    xi = {reg._value_key(_py(v)): i for i, v in enumerate(xs)}
    ri = {reg._value_key(_py(v)): i for i, v in enumerate(rs)}
    M = np.full((len(rs), len(xs)), np.nan)
    Nm = np.zeros((len(rs), len(xs)), dtype=int)
    for _, r in df.iterrows():
        i = ri.get(reg._value_key(_py(r[rc]))) if rc else 0
        j = xi.get(reg._value_key(_py(r[xc]))) if xc else 0
        if i is not None and j is not None:
            M[i, j] = r[VALUE]
            Nm[i, j] = r[N] if N in r and pd.notna(r[N]) else 0
    return xs, rs, M, Nm


def _global_range(ctx, metric, show_as, centred):
    """Colour range over every facet so the shared colour bar is truthful."""
    cache = ctx.pre.__dict__.setdefault("_heat_cache", {})
    key = (metric, show_as, ctx.opts["centre"], centred)
    if key in cache:
        return cache[key]
    data = ctx.pre.data
    if METRIC in data:
        data = data[data[METRIC] == metric]
    fr, fc = ctx.roles["facet_row"], ctx.roles["facet_col"]
    groups = [c for c in (fr, fc) if c and c != METRIC]
    allv = data[VALUE].to_numpy(dtype=float)
    qs = []
    parts = data.groupby(groups, dropna=False) if groups else [((), data)]
    for lev, sub in parts:
        lev = lev if isinstance(lev, tuple) else (lev,)
        d = dict(zip(groups, lev))
        levels = (d.get(fr), d.get(fc))
        xs, rs, M, _ = _table(ctx, sub)
        c0 = _centre(ctx, metric, levels, allv, xs, rs) if centred else None
        qs.append(np.ravel(_transform(M, c0, show_as)))
    q = np.concatenate(qs) if qs else np.array([])
    q = q[np.isfinite(q)]
    cache[key] = (float(q.min()), float(q.max())) if len(q) else (0.0, 1.0)
    return cache[key]


def _fmt(v, decimals, show_as, centred):
    if not np.isfinite(v):
        return ""
    if decimals is None:
        a = abs(v)
        decimals = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 0.1 else 3
        if show_as == "% change":
            decimals = 0 if a >= 10 else 1
    s = f"{v:+.{decimals}f}" if centred and show_as != "value" else f"{v:.{decimals}f}"
    s = s.replace("-", "−")
    return s + (" %" if show_as == "% change" and centred else "")


# ------------------------------------------------------------------- plot --
def _describe(pre, o) -> str:
    parts = []
    r = pre.roles
    combos = 1
    for role in ("x", "row", "facet_col", "facet_row"):
        if r.get(role) and r[role] != METRIC:
            combos *= max(len(pre.levels.get(role + "_present", pre.levels.get(role, [1]))), 1)
    n_metrics = len(pre.metrics) if METRIC in (r["facet_col"], r["facet_row"]) else 1
    if len(pre.data) < combos * n_metrics:
        parts.append("Grey cells: no data for that combination.")
    centre = o.get("centre", "none")
    if centre == "baseline":
        col, val = o.get("baseline_column"), o.get("baseline_value")
        what = f"{lower_first(reg.axis_label(col).split(' (')[0])} “{reg.value_label(val)}”" \
            if col else "the baseline rows"
        kind = "percentage change" if o.get("show_as") == "% change" else "difference"
        matched = []
        if o.get("_ds") is not None:
            from types import SimpleNamespace
            shim = SimpleNamespace(opts=o, ds=o["_ds"], spec=o["_spec"], roles=pre.roles)
            ref = _reference_rows(shim, (None, None))
            matched = matched_dims(shim, ref) if ref is not None and len(ref) else []
        on = (" at the same " + " and ".join(lower_first(reg.axis_label(c).split(" (")[0])
                                            for c in matched)) if matched else ""
        parts.append(f"Colours show the {kind} from the baseline, {what}{on}.")
    elif centre == "value":
        parts.append(f"Colours centred on {o.get('centre_value') or 0:g}.")
    elif centre == "median":
        parts.append("Colours centred on the median cell.")
    return " ".join(parts)


@register_plot(
    "heatmap", "Heatmap", x="discrete", roles=("row", "facet"), default_agg="mean",
    default_spread="none", shared_colorbar=True, describe=_describe, point_word="cell",
    options=[Option("annotate", "bool", True, "Value in each cell"),
             Option("show_n", "bool", False, "n in each cell"),
             Option("decimals", "int", None, "Decimals (empty = automatic)", min=0, max=6),
             Option("centre", "choice", "none", "Colour centre",
                    ["none", "value", "baseline", "median"],
                    help="Diverging colours around a reference; the colour then shows "
                         "the difference from it"),
             Option("centre_value", "float", 0.0, "Centre value", show_if={"centre": ["value"]}),
             Option("baseline_column", "column", None, "Baseline column (empty = family default)",
                    show_if={"centre": ["baseline"]}),
             Option("baseline_value", "value", None, "Baseline value", of="baseline_column",
                    show_if={"centre": ["baseline"]}),
             Option("show_as", "choice", "value", "Cell text",
                    ["value", "difference", "% change"],
                    show_if={"centre": ["value", "baseline", "median"]}),
             Option("cmap", "choice", "auto", "Colour map", CMAPS),
             Option("reverse", "bool", False, "Reverse colour map"),
             Option("vmin", "float", None, "Colour scale min (empty = data)"),
             Option("vmax", "float", None, "Colour scale max (empty = data)"),
             Option("cell_gap", "bool", True, "White gaps between cells")])
def heatmap(ctx):
    ax, o = ctx.ax, ctx.opts
    metric = _metric_of(ctx)
    df = ctx.data
    if METRIC in df:
        df = df[df[METRIC] == metric]
    xs, rs, M, Nm = _table(ctx, df)
    allv = ctx.pre.data[VALUE].to_numpy(dtype=float)
    c0 = _centre(ctx, metric, ctx.facet_levels, allv, xs, rs)
    centred = o["centre"] != "none" and c0 is not None
    if o["centre"] != "none" and c0 is None:
        ctx.pre.warnings.append("No baseline rows found for the colour centre; "
                                "showing plain values.")
    colour_as = "% change" if (centred and o["show_as"] == "% change") else "difference"
    Q = _transform(M, c0, colour_as) if centred else M
    lo, hi = _global_range(ctx, metric, colour_as, centred)
    if centred:
        a = max(abs(lo), abs(hi)) or 1.0
        lo, hi = -a, a
    lo = o["vmin"] if o["vmin"] is not None else lo
    hi = o["vmax"] if o["vmax"] is not None else hi
    name = o["cmap"]
    if name == "auto":
        name = "rs_diverging" if centred else "rs_sequential"
    cmap = colormaps[name + ("_r" if o["reverse"] else "")]
    norm = Normalize(lo, hi if hi > lo else lo + 1e-9)
    ax.set_facecolor("#f1f1f1")
    mesh = ax.pcolormesh(np.arange(len(xs) + 1) - 0.5, np.arange(len(rs) + 1) - 0.5,
                         np.ma.masked_invalid(Q), cmap=cmap, norm=norm,
                         edgecolors="white" if o["cell_gap"] else "face",
                         linewidth=1.2 if o["cell_gap"] else 0, rasterized=False)
    ax.set_xlim(-0.5, len(xs) - 0.5)
    ax.set_ylim(len(rs) - 0.5, -0.5)
    for axis, cats, role, setter in (("x", xs, "x", ax.set_xticks), ("row", rs, "row",
                                                                       ax.set_yticks)):
        if len(cats) > MAX_LABELLED:
            setter([])
            if ctx.facet_index == 0:
                ctx.pre.warnings.append(
                    f"{reg.axis_label(ctx.roles[role]).split(' (')[0]} has {len(cats)} values — "
                    "too many for a heatmap axis. Choose a column with fewer values or filter.")
        else:
            setter(range(len(cats)), [ctx.value_label(ctx.roles[role], v) if v is not None
                                      else "" for v in cats])
    ax.tick_params(length=0)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.grid(False)
    show_text = o["annotate"] and len(xs) <= MAX_ANNOTATED[0] and len(rs) <= MAX_ANNOTATED[1]
    if o["annotate"] and not show_text and ctx.facet_index == 0:
        ctx.pre.warnings.append("Too many cells to print values; turn off “Value in each cell” "
                                "or filter to fewer rows/columns.")
    if show_text:
        text_vals = M if not centred or o["show_as"] == "value" else Q
        for i in range(len(rs)):
            for j in range(len(xs)):
                if not np.isfinite(M[i, j]):
                    continue
                r, g, b = to_rgb(cmap(norm(Q[i, j])))
                dark = 0.2126 * r + 0.7152 * g + 0.0722 * b < 0.5
                txt = _fmt(text_vals[i, j], o["decimals"], o["show_as"], centred)
                if o["show_n"]:
                    txt += f"\nn = {Nm[i, j]}"
                ax.text(j, i, txt, ha="center", va="center", fontsize=ctx.sizes["annotation"],
                        color="white" if dark else st.ink(), linespacing=1.1)
    unit = reg.column_info(metric).get("unit")
    label = reg.axis_label(metric, ctx.style.labels)
    if centred:
        base = label.split(" (")[0]
        label = (f"{base}: change from centre (%)" if colour_as == "% change" else
                 f"{base}: difference from centre" + (f" ({unit})" if unit else ""))
        if o["centre"] == "baseline":
            label = label.replace("centre", "baseline")
    ctx.colorbar_mappable = mesh
    ctx.colorbar_label = label
    ctx.colorbar_shared = METRIC not in (ctx.roles["facet_col"], ctx.roles["facet_row"])
    ctx.colorbar_key = metric        # one colour bar per metric, shared by its panels
