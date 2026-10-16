"""PlotSpec -> matplotlib Figure (headless, thread-safe: no pyplot)."""
from __future__ import annotations

import logging
import math
import textwrap
import threading
from dataclasses import dataclass, field

import matplotlib as mpl
import numpy as np
import pandas as pd
from matplotlib.backends.backend_agg import FigureCanvasAgg
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, MaxNLocator, PercentFormatter, StrMethodFormatter

from . import registry as reg
from . import state
from . import style as st
from .data import Dataset, load_dataset
from .pipeline import METRIC, N, Prepared, _py, prepare
from .plots import PLOT_TYPES, DrawContext, load_plugins
from .spec import MARGINS, PlotSpec

_RENDER_LOCK = threading.Lock()   # rc_context is process-global
logging.getLogger("matplotlib.font_manager").setLevel(logging.ERROR)  # fallback-weight noise


@dataclass
class RenderResult:
    fig: Figure
    pre: Prepared | None
    width_cm: float
    height_cm: float
    warnings: list[str] = field(default_factory=list)
    footnote: str = ""
    latex_width: str = ""
    rc: dict = field(default_factory=dict, repr=False)
    auto_footnote: str = ""     # what was fixed / averaged, even when not drawn (for captions)

    def savefig(self, path, **kw):
        """Save inside the same rc context the figure was built with (fonts, mathtext)."""
        with _RENDER_LOCK, mpl.rc_context(self.rc):
            self.fig.savefig(path, **kw)

    def png_bytes(self, dpi: float = 110) -> bytes:
        import io
        buf = io.BytesIO()
        self.savefig(buf, format="png", dpi=dpi)
        return buf.getvalue()


def _drop_unused_roles(spec: PlotSpec, ptype) -> PlotSpec:
    """Ignore mapping fields the plot type does not use (e.g. heatmap rows left over
    after switching to a ranking), so they never silently split the groups."""
    m = spec.mapping
    unused = {"hue": "hue", "style": "style", "facet": "facet", "row": "row"}
    drop = [f for f, role in unused.items() if getattr(m, f) and role not in ptype.roles]
    if ptype.x == "none" and m.x:
        drop.append("x")
    if not drop:
        return spec
    spec = spec.copy()
    for f in drop:
        setattr(spec.mapping, f, None)
    return spec


def get_dataset(spec: PlotSpec) -> Dataset:
    return load_dataset(spec.dataset.path, spec.dataset.family, spec.dataset.include_ignored)


def render(spec: PlotSpec, ds: Dataset | None = None, settings: dict | None = None,
           dpi: float | None = None) -> RenderResult:
    load_plugins()
    settings = settings or state.settings()
    ds = ds or get_dataset(spec)
    ptype = PLOT_TYPES.get(spec.plot_type)
    if ptype is None:
        raise ValueError(f"Unknown plot type '{spec.plot_type}'.")
    w_cm, h_cm = st.figure_size_cm(spec.export, settings["textwidth_cm"])
    warnings: list[str] = []
    if spec.style.preset == "thesis" and h_cm > settings["thesis_max_height_cm"]:
        warnings.append(f"Figure height {h_cm:g} cm exceeds the thesis maximum of "
                        f"{settings['thesis_max_height_cm']:g} cm.")
    if spec.style.preset == "thesis" and w_cm > settings["textwidth_cm"] + 1e-6:
        warnings.append(f"Figure width {w_cm:g} cm is wider than the text block "
                        f"({settings['textwidth_cm']:g} cm); it would be scaled down.")
    if spec.export.usetex and not st.tex_status()[0]:
        warnings.append("usetex requested but unavailable: " + st.tex_status()[1])
        spec = spec.copy()
        spec.export.usetex = False

    spec = _drop_unused_roles(spec, ptype)
    if ptype.auto_by:
        unit = getattr(ds.family, ptype.auto_by, None)
        m = spec.mapping
        if unit and unit in ds.profile and unit not in (m.x, m.hue, m.style, m.facet, *m.by):
            spec = spec.copy()
            spec.mapping.by = list(spec.mapping.by) + [unit]
    if ds.family.baseline and any(o.name == "baseline_column" for o in ptype.options) and \
            not (spec.options or {}).get("baseline_column"):
        spec = spec.copy()
        spec.options["baseline_column"] = ds.family.baseline["column"]
        spec.options["baseline_value"] = ds.family.baseline["value"]
    pre = prepare(ds, spec, needs_raw=ptype.needs_raw, point_word=ptype.point_word)
    warnings += pre.warnings
    sec = None
    if spec.mapping.secondary:
        if not ptype.secondary:
            warnings.append(f"The '{ptype.label}' plot has no secondary-indicator panel.")
        elif spec.mapping.secondary not in ds.metrics(include_sparse=True):
            warnings.append(f"Secondary indicator '{spec.mapping.secondary}' is not a metric "
                            "of this dataset.")
        else:
            sec = _secondary_spec(spec)
            sec_pre = prepare(ds, sec, needs_raw=ptype.needs_raw, point_word=ptype.point_word)
            sec = (sec, sec_pre)
    if ptype.min_height_cm is not None and len(pre.data):
        sp = st.style_preset(spec.style.preset)
        tick = max(sp["sizes"]["tick"] * spec.style.font_scale, sp["sizes"]["min"])
        opts = {**ptype.option_defaults(), **(spec.options or {})}
        need = ptype.min_height_cm(pre, opts, tick)
        foot_cm = 1.2 if spec.style.footnote_mode != "off" else 0
        need += foot_cm
        thesis = spec.style.preset.startswith("thesis")
        # thesis figures may grow up to the page limit; slides / posters keep their shape
        limit = settings["thesis_max_height_cm"] if thesis else h_cm
        if spec.export.height_cm is None and need > h_cm:
            h_cm = round(min(need, max(limit, h_cm)), 1)
            if need > limit + 0.05:
                where = f"the thesis maximum is {limit:g} cm" if thesis else \
                    f"this {spec.export.size_preset.replace('_', ' ')} size is {limit:g} cm tall"
                warnings.append(f"The labels need about {need:.0f} cm of height but {where}; "
                                "reduce “Show top N” or use fewer panels.")
        elif spec.export.height_cm is not None and need > spec.export.height_cm + 0.05:
            warnings.append(f"Labels will overlap at {h_cm:g} cm height; about {need:.1f} cm "
                            "is needed (clear the height to size it automatically, or reduce "
                            "“Show top N”).")
    rc = st.rc_params(spec.style, spec.export)
    with _RENDER_LOCK, mpl.rc_context(rc):
        fig = Figure(figsize=(w_cm / st.CM_PER_IN, h_cm / st.CM_PER_IN),
                     dpi=dpi or 100, layout="constrained")
        FigureCanvasAgg(fig)
        T = (lambda s: st.tex_escape(s)) if spec.export.usetex else st.mathtext_escape
        opts = {**ptype.option_defaults(), **(spec.options or {}), "_ds": ds, "_spec": spec}
        lead = ptype.describe(pre, opts) if ptype.describe and len(pre.raw) else ""
        if sec:
            lead += (" " if lead else "") + "Lower panel: " + reg.axis_label(
                spec.mapping.secondary, spec.style.labels).split(" (")[0].lower() + "."
        auto_foot = (lead + " " + pre.footnote).strip()
        foot = {"auto": auto_foot, "custom": spec.style.footnote}.get(spec.style.footnote_mode, "")
        main = _header_footer(fig, spec, T, foot)
        if pre.data.empty:
            ax = main.add_subplot()
            ax.set_axis_off()
            ax.text(0.5, 0.5, "No data after filtering", ha="center", va="center",
                    color=st.ink_secondary(), transform=ax.transAxes)
        else:
            _draw(main, ds, spec, pre, ptype, T, w_cm, warnings, sec)
        fig.canvas.draw()
        _fit_labels(fig)
        warnings += [w for w in dict.fromkeys(pre.warnings) if w not in warnings]
    res = RenderResult(fig, pre, w_cm, h_cm, warnings, foot,
                       st.latex_width(w_cm, settings["textwidth_cm"]), rc)
    res.auto_footnote = auto_foot
    return res


# --------------------------------------------------------------- drawing --
def _facet_grid(pre: Prepared, spec: PlotSpec, w_cm: float, ptype=None):
    fc, fr = pre.roles["facet_col"], pre.roles["facet_row"]
    cols = pre.levels.get("facet_col_present", pre.levels.get("facet_col")) if fc else [None]
    rows = pre.levels.get("facet_row_present", pre.levels.get("facet_row")) if fr else [None]
    if fc and not fr:
        n = len(cols)
        ncols = spec.mapping.facet_cols or (n if n <= 3 else min(math.ceil(math.sqrt(n)),
                                                                 4 if w_cm > 18 else 3))
        if ptype is not None and ptype.name == "ranking" and not spec.mapping.facet_cols:
            ncols = 1      # long item labels: stack rankings vertically
        ncols = max(1, min(ncols, n))
        nrows = math.ceil(n / ncols)
        cells = [((None, c), (i // ncols, i % ncols)) for i, c in enumerate(cols)]
        return nrows, ncols, cells
    cells = [((r, c), (i, j)) for i, r in enumerate(rows) for j, c in enumerate(cols)]
    return len(rows), len(cols), cells


def _subset(df: pd.DataFrame, col: str | None, level) -> pd.DataFrame:
    if col is None or col not in df:
        return df
    key = reg._value_key(_py(level))
    if isinstance(level, float) and np.isnan(level):
        return df[df[col].isna()]
    return df[df[col].map(lambda v: reg._value_key(_py(v)) == key)]


def _secondary_spec(spec: PlotSpec) -> PlotSpec:
    """Spec for the stacked indicator panel: same mapping/filters, one metric, own axis."""
    sec = spec.copy()
    sec.mapping.y = [spec.mapping.secondary]
    sec.mapping.secondary = None
    if sec.mapping.hue == METRIC or (len(spec.mapping.y) > 1 and spec.mapping.y_mode == "overlay"
                                     and not spec.mapping.hue):
        sec.mapping.hue = None
    sec.style.ylim = None
    sec.style.ylog = False
    sec.style.ylabel = None
    sec.style.y_ticks = sec.style.y_ticks or 3
    sec.style.annotate = False
    return sec


SECONDARY_RATIO = 0.32


def _make_axes(fig, nrows, ncols, sharex, sharey, with_secondary):
    if not with_secondary:
        axes = fig.subplots(nrows, ncols, sharex=sharex, sharey=sharey, squeeze=False)
        return axes, None
    allax = fig.subplots(nrows * 2, ncols, squeeze=False,
                         gridspec_kw={"height_ratios": [1, SECONDARY_RATIO] * nrows})
    main, low = allax[0::2], allax[1::2]
    for r in range(nrows):
        for c in range(ncols):
            low[r, c].sharex(main[r, c])
            if sharex and (r or c):
                main[r, c].sharex(main[0, 0])
            if sharey and (r or c):
                main[r, c].sharey(main[0, 0])
                low[r, c].sharey(low[0, 0])
    return main, low


def _draw(fig, ds, spec, pre, ptype, T, w_cm, warnings, sec=None):
    s = spec.style
    nrows, ncols, cells = _facet_grid(pre, spec, w_cm, ptype)
    percent_all = s.fraction_as_percent and all(reg.is_fraction(m) for m in pre.metrics)
    common, _ = metric_names(spec, pre.metrics, percent_all)
    metric_facet = METRIC in (pre.roles["facet_col"], pre.roles["facet_row"]) and not common
    sharey = s.sharey and not metric_facet and ptype.name not in ("heatmap", "ranking")
    sharex = s.sharex and ptype.name not in ("heatmap", "ranking")
    axes, low = _make_axes(fig, nrows, ncols, sharex, sharey, sec is not None)
    used = set()
    legend: dict = {}
    contexts, low_contexts = [], []
    for i, ((rlev, clev), (r, c)) in enumerate(cells):
        ax = axes[r, c]
        used.add((r, c))
        data = _subset(_subset(pre.data, pre.roles["facet_row"], rlev), pre.roles["facet_col"], clev)
        raw = _subset(_subset(pre.raw, pre.roles["facet_row"], rlev), pre.roles["facet_col"], clev)
        ctx = DrawContext(ax, fig, data, raw, pre, spec, ds, ptype, legend, i)
        ctx.facet_levels = (rlev, clev)
        contexts.append(ctx)
        if data.empty and raw.empty:
            ax.text(0.5, 0.5, "No data", ha="center", va="center", transform=ax.transAxes,
                    color=st.ink_secondary(), fontsize=ctx.sizes["annotation"])
        else:
            ptype.func(ctx)
        _facet_title(ctx, T, rlev, clev, nrows, ncols)
        if sec is not None:
            sspec, spre = sec
            sdata = _subset(_subset(spre.data, spre.roles["facet_row"], rlev),
                            spre.roles["facet_col"], clev)
            sraw = _subset(_subset(spre.raw, spre.roles["facet_row"], rlev),
                           spre.roles["facet_col"], clev)
            sctx = DrawContext(low[r, c], fig, sdata, sraw, spre, sspec, ds, ptype, {}, i)
            sctx.facet_levels = (rlev, clev)
            low_contexts.append(sctx)
            if not (sdata.empty and sraw.empty):
                ptype.func(sctx)
    for r in range(nrows):
        for c in range(ncols):
            if (r, c) not in used:
                axes[r, c].set_axis_off()
                if low is not None:
                    low[r, c].set_axis_off()
    for ctx in contexts:
        _style_axes(ctx, T, axes, cells)
    for ctx in low_contexts:
        _style_axes(ctx, T, axes, cells)
        main_ax = axes[[rc for _, rc in cells][ctx.facet_index]]
        main_ax.set_xlabel("")
        main_ax.tick_params(labelbottom=False)
        ctx.ax.yaxis.label.set_fontsize(ctx.sizes["tick"])
    _colorbar(fig, contexts, axes, T)
    _legend(fig, axes, contexts, spec, pre, T)


def _facet_title(ctx, T, rlev, clev, nrows, ncols):
    parts = []
    percent = ctx.style.fraction_as_percent and all(reg.is_fraction(m) for m in ctx.pre.metrics)
    common, short = metric_names(ctx.spec, ctx.pre.metrics, percent)
    for role, lev in (("facet_row", rlev), ("facet_col", clev)):
        col = ctx.roles[role]
        if col == METRIC:
            if common:
                parts.append(short[lev])
        elif col:
            parts.append(ctx.value_label(col, lev))
    if parts:
        ctx.ax.set_title(T(" · ".join(parts)), loc="left", fontsize=ctx.sizes["label"],
                         color=st.ink())


def metric_names(spec: PlotSpec, metrics: list[str], percent: bool = False):
    """(shared axis label or None, {metric: legend/facet label}).

    Variants of one quantity (e.g. RMSE untrimmed / trim1 / trim5) share a base
    label and unit: the axis carries "Accuracy RMSE (mm)" and entries read
    "Untrimmed", "Worst 1 % trimmed", ...
    """
    full = {m: reg.axis_label(m, spec.style.labels, percent) for m in metrics}
    if len(metrics) < 2 or any(m in spec.style.labels for m in metrics):
        return None, full
    infos = {m: reg.column_info(m) for m in metrics}
    bases = {i["label"].split(", ")[0] for i in infos.values()}
    units = {("%" if percent and i.get("fraction") else i.get("unit")) for i in infos.values()}
    if len(bases) != 1 or len(units) != 1:
        return None, full
    base, unit = bases.pop(), units.pop()
    short = {}
    for m, i in infos.items():
        if ", " in i["label"]:
            rest = i["label"].split(", ", 1)[1]
            short[m] = rest[:1].upper() + rest[1:]
        else:
            short[m] = "Untrimmed" if any(m in g["members"].values() and
                                          g["members"].get("untrimmed") == m
                                          for g in reg.variant_groups(metrics).values()) else base
    return (f"{base} ({unit})" if unit else base), short


def _metric_label(spec: PlotSpec, metrics: list[str], percent: bool) -> str:
    common, names = metric_names(spec, metrics, percent)
    if common:
        return common
    if len(metrics) == 1:
        return names[metrics[0]]
    units = {("%" if percent and reg.is_fraction(m) else reg.column_info(m).get("unit"))
             for m in metrics}
    unit = units.pop() if len(units) == 1 else None
    return f"Value ({unit})" if unit else "Value"


def _style_axes(ctx, T, axes, cells):
    ax, s, spec, pre = ctx.ax, ctx.style, ctx.spec, ctx.pre
    (r, c) = [rc for (lev, rc) in cells][ctx.facet_index]
    nrows, ncols = axes.shape
    metrics_here = pre.metrics
    percent_all = s.fraction_as_percent and all(reg.is_fraction(m) for m in pre.metrics)
    common, _ = metric_names(spec, pre.metrics, percent_all)
    for role in ("facet_row", "facet_col"):
        if ctx.roles[role] == METRIC and not common:
            lev = ctx.facet_levels[0 if role == "facet_row" else 1]
            metrics_here = [lev]
    percent = s.fraction_as_percent and all(reg.is_fraction(m) for m in metrics_here)
    horizontal = ctx.opts.get("orientation") == "horizontal" or ctx.ptype.name == "ranking"
    ylab = s.ylabel if s.ylabel is not None else _metric_label(spec, metrics_here, percent)
    xlab = s.xlabel if s.xlabel is not None else reg.axis_label(pre.roles["x"], s.labels,
                                                                  s.fraction_as_percent)
    if ctx.ptype.name in ("hist", "cdf"):
        xlab, ylab = (s.xlabel if s.xlabel is not None else ylab), (
            s.ylabel if s.ylabel is not None else ctx.opts.get("_ylabel", "Count"))
        percent_x, percent_y = percent, False
    elif ctx.ptype.name == "heatmap":
        ylab = s.ylabel if s.ylabel is not None else reg.axis_label(pre.roles["row"], s.labels)
        percent_x = percent_y = False
    elif horizontal:
        xlab, ylab = ylab, (s.xlabel if s.xlabel is not None else "")
        percent_x, percent_y = percent, False
    else:
        percent_x, percent_y = False, percent
    # outer labels only (unless axes differ per panel)
    metric_facet = METRIC in (ctx.roles["facet_col"], ctx.roles["facet_row"]) and not common
    last_row = r == nrows - 1 or not any((rr, c) in [rc for _, rc in cells]
                                         for rr in range(r + 1, nrows))
    if last_row or not s.sharex:
        ax.set_xlabel(T(xlab))
    if c == 0 or metric_facet or not s.sharey:
        ax.set_ylabel(T(ylab))
    if ctx.ptype.name == "heatmap":
        return
    if pre.x_is_metric and reg.is_fraction(pre.roles["x"]) and s.fraction_as_percent:
        percent_x = True
    if s.xlog:
        ax.set_xscale("log")
    if s.ylog:
        ax.set_yscale("log")
    for axis, pct, nt, fmt in ((ax.xaxis, percent_x, s.x_ticks, s.x_tick_format),
                               (ax.yaxis, percent_y, s.y_ticks, s.y_tick_format)):
        categorical = (axis is ax.xaxis and ctx.x_categorical and not horizontal
                       and ctx.ptype.name not in ("hist", "cdf")) or (
            axis is ax.yaxis and horizontal)
        if categorical:
            continue
        if pct:
            axis.set_major_formatter(FuncFormatter(_percent_tick(axis)))
        if nt:
            axis.set_major_locator(MaxNLocator(nt))
        if fmt:
            try:
                axis.set_major_formatter(StrMethodFormatter(fmt))
            except ValueError:
                pass
    ax.grid(s.grid, axis="x" if horizontal else "y")
    ax.grid(False, axis="y" if horizontal else "x")
    pad = (s.pad_pct / 100.0) if s.pad_pct is not None else MARGINS.get(s.margin, 0.05)
    if ctx.x_categorical and not horizontal and ctx.ptype.name not in ("hist", "cdf"):
        ax.margins(y=pad)
    elif horizontal:
        ax.margins(x=pad)
    else:
        ax.margins(x=pad, y=pad)
    ax.autoscale_view()
    for axis, log, fmt in ((ax.xaxis, s.xlog, s.x_tick_format), (ax.yaxis, s.ylog, s.y_tick_format)):
        if log and not fmt:
            _plain_log_ticks(axis)
    if s.xlim and any(v is not None for v in s.xlim):
        ax.set_xlim(*[v if v is not None else cur for v, cur in zip(s.xlim, ax.get_xlim())])
    if s.ylim and any(v is not None for v in s.ylim):
        ax.set_ylim(*[v if v is not None else cur for v, cur in zip(s.ylim, ax.get_ylim())])


def _percent_tick(axis):
    """Percent tick labels with as few decimals as the visible range needs."""
    def fmt(v, pos=None):
        lo, hi = axis.get_view_interval()
        rng = abs(hi - lo) * 100
        d = 0 if rng >= 4 else 1 if rng >= 0.4 else 2
        sign = r"\%" if mpl.rcParams["text.usetex"] else "%"
        return f"{v * 100:.{d}f}{sign}"
    return fmt


def _plain_log_ticks(axis):
    """Log axes labelled 2, 5, 10 ... instead of 2 x 10^0; minor labels on narrow ranges."""
    def major(v, pos=None):
        return f"{v:g}"

    def minor(v, pos=None):
        lo, hi = sorted(axis.get_view_interval())
        if lo <= 0 or np.log10(hi / lo) > 1.3:
            return ""
        mant = v / 10 ** np.floor(np.log10(v) + 1e-9)
        return f"{v:g}" if round(mant) in (2, 3, 5) else ""
    axis.set_major_formatter(FuncFormatter(major))
    axis.set_minor_formatter(FuncFormatter(minor))


def _colorbar(fig, contexts, axes, T):
    maps = [c for c in contexts if c.colorbar_mappable is not None]
    if not maps:
        return
    ctx = maps[0]
    shared = getattr(ctx, "colorbar_shared", ctx.ptype.shared_colorbar) or len(maps) == 1
    targets = [m for m in maps] if not shared else [maps[0]]
    for m in targets:
        ax_list = [c.ax for c in maps] if shared else [m.ax]
        cb = fig.colorbar(m.colorbar_mappable, ax=ax_list, pad=0.03, fraction=0.05,
                          aspect=25 if len(ax_list) > 1 else 18)
        cb.outline.set_visible(False)
        cb.ax.tick_params(labelsize=ctx.sizes["tick"], length=2)
        if getattr(m, "colorbar_label", ""):
            cb.set_label(T(m.colorbar_label), fontsize=ctx.sizes["label"])
        if getattr(m, "colorbar_percent", False):
            cb.ax.yaxis.set_major_formatter(PercentFormatter(1.0))


def _n_text(pre: Prepared, col: str, level, per_group: bool = False) -> str:
    """n for one legend entry: per point (aggregated), per box/curve (distribution
    plots, `per_group`), or the number of rows drawn."""
    if col is None or col not in pre.data:
        return ""
    if per_group:
        sub = _subset(pre.raw, col, level)
        r = pre.roles
        keys = [c for c in (None if pre.x_is_metric else r["x"], r["style"], r["facet_col"],
                            r["facet_row"], *r["by"]) if c and c in sub]
        sizes = sub.groupby(keys, dropna=False).size() if keys else pd.Series([len(sub)])
        if sizes.empty:
            return ""
        lo, hi = int(sizes.min()), int(sizes.max())
        return f"n = {lo}" if lo == hi else f"n = {lo}–{hi}"
    sub = _subset(pre.data if pre.aggregated or N in pre.data else pre.raw, col, level)
    if sub.empty:
        return ""
    if pre.aggregated or (pre.data[N] > 1).any():
        n = sub[N].dropna()
        lo, hi = int(n.min()), int(n.max())
    else:
        lo = hi = len(sub)
    return f"n = {lo}" if lo == hi else f"n = {lo}–{hi}"


def _legend(fig, axes, contexts, spec, pre, T):
    s = spec.style
    if not contexts:
        return
    ctx = contexts[0]
    legend = ctx.legend
    if s.legend == "off" or not legend:
        _single_n_annotation(contexts, spec, pre, T)
        return
    handles, labels = [], []
    sections = [("hue", pre.roles["hue"]), ("style", pre.roles["style"])]
    present = [(k, c) for k, c in sections if c and any(key[0] == k for key in legend)]
    multi_section = len(present) > 1
    percent = s.fraction_as_percent and all(reg.is_fraction(m) for m in pre.metrics)
    common, short = metric_names(spec, pre.metrics, percent)
    title = None
    for kind, col in present:
        entries = [(key, v) for key, v in legend.items() if key[0] == kind]
        heading = "Metric" if col == METRIC else reg.axis_label(col, s.labels)
        if s.legend_title and not (col == METRIC and common):
            if multi_section:
                handles.append(Line2D([], [], linestyle="none", marker=None))
                labels.append(T(heading))
            else:
                title = T(heading)
        order = {reg._value_key(_py(v)): i for i, v in enumerate(pre.levels.get(kind, []))}
        entries.sort(key=lambda kv: order.get(kv[0][1], 1e9))
        for key, (value, handle) in entries:
            text = short.get(value, ctx.value_label(col, value)) if col == METRIC \
                else ctx.value_label(col, value)
            if s.show_n and kind == "hue" and col != METRIC:
                nt = _n_text(pre, col, value, per_group=ctx.ptype.needs_raw)
                text = f"{text} ({nt})" if nt else text
            handles.append(handle)
            labels.append(T(text))
    for key, (text, handle) in legend.items():
        if key[0] == "trend":
            handles.append(handle)
            labels.append(T(text))
    if not pre.roles["hue"]:
        _single_n_annotation(contexts, spec, pre, T)
    if not handles:
        return
    loc = s.legend
    kw = dict(frameon=False, fontsize=ctx.sizes["legend"], handlelength=1.6, title=title,
              alignment="left")
    if loc.startswith("outside"):
        where = {"outside right": "outside right upper", "outside top": "outside upper left",
                 "outside bottom": "outside lower center"}[loc]
        ncol = s.legend_cols or (1 if loc == "outside right" else min(len(handles), 5))
        leg = fig.legend(handles, labels, loc=where, ncols=ncol, **kw)
    else:
        target = axes[0, -1] if axes[0, -1].has_data() else axes.flat[0]
        leg = target.legend(handles, labels, loc=loc, ncols=s.legend_cols or 1, **kw)
    _style_legend_headers(leg, labels, handles)
    if leg.get_title().get_text():
        leg.get_title().set_color(st.ink())
        leg.get_title().set_fontweight("semibold")


def _style_legend_headers(leg, labels, handles):
    for text, h in zip(leg.get_texts(), handles):
        if isinstance(h, Line2D) and h.get_marker() in (None, "None", "") and \
                h.get_linestyle() in ("None", "none", ""):
            text.set_color(st.ink())
            text.set_fontweight("semibold")
            text.set_x(-20)   # pull headers left over the (empty) handle slot


def _single_n_annotation(contexts, spec, pre, T):
    if not spec.style.show_n or spec.style.footnote_mode == "auto":
        return
    unit = pre.unit_name
    if pre.aggregated:
        n = pre.data[N].dropna()
        txt = f"n = {int(n.min())}" + (f"–{int(n.max())}" if n.max() != n.min() else "") + \
            f" {unit} per point"
    else:
        txt = f"n = {len(pre.raw)} {unit}"
    ax = contexts[0].ax
    ax.text(0.99, 0.98, T(txt), transform=ax.transAxes, ha="right", va="top",
            fontsize=contexts[0].sizes["annotation"], color=st.ink_secondary())


# --------------------------------------------------------- header/footer --
def _wrap_to_width(fig, text, size, weight="normal", width_frac=0.98):
    """Wrap `text` so it fits the figure width; returns (wrapped, height_in)."""
    r = fig.canvas.get_renderer()
    t = fig.text(0, 0, text, fontsize=size, fontweight=weight)
    limit = fig.bbox.width * width_frac
    chars = len(text)
    while chars > 15 and t.get_window_extent(r).width > limit:
        chars = int(chars * 0.93)
        t.set_text("\n".join(textwrap.wrap(text, chars, break_on_hyphens=False)))
    wrapped, h = t.get_text(), t.get_window_extent(r).height / fig.dpi
    t.remove()
    return wrapped, h


def _header_footer(fig, spec, T, foot: str):
    """Split the figure into header / main / footer subfigures; returns the main one.

    Text blocks get exactly the height they need, so legends placed "outside"
    in the main subfigure can never collide with the title or footnote.
    """
    s = spec.style
    sp = st.style_preset(s.preset)
    size = lambda k: max(sp["sizes"][k] * s.font_scale, sp["sizes"]["min"])
    blocks = []   # (kind, text, size, colour, weight, height_in)
    if s.show_title and s.title:
        blocks.append(("head", T(s.title), size("title"), st.ink(), "semibold"))
    if s.subtitle:
        blocks.append(("head", T(s.subtitle), size("label"), st.ink_secondary(), "normal"))
    if foot:
        blocks.append(("foot", T(foot), size("footnote"), st.ink_secondary(), "normal"))
    if not blocks:
        return fig
    H = fig.get_figheight()
    measured = []
    for kind, text, sz, col, wt in blocks:
        wrapped, h = _wrap_to_width(fig, text, sz, wt)
        measured.append((kind, wrapped, sz, col, wt, h + sz * 0.45 / 72))
    head = [m for m in measured if m[0] == "head"]
    footb = [m for m in measured if m[0] == "foot"]
    head_h = sum(m[5] for m in head)
    foot_h = sum(m[5] for m in footb)
    main_h = max(H - head_h - foot_h, H * 0.3)
    ratios = ([head_h] if head else []) + [main_h] + ([foot_h] if footb else [])
    subs = fig.subfigures(len(ratios), 1, height_ratios=ratios, hspace=0)
    subs = list(np.atleast_1d(subs))
    i = 0
    if head:
        y = 1.0
        for _, text, sz, col, wt, h in head:
            subs[0].text(0, y, text, ha="left", va="top", fontsize=sz, color=col,
                         fontweight=wt)
            y -= h / head_h
        i = 1
    main = subs[i]
    if footb:
        _, text, sz, col, wt, h = footb[0]
        subs[-1].text(0, 0.0, text, ha="left", va="bottom", fontsize=sz, color=col)
    return main


def _wrap_label(text: str) -> str:
    """Split a one-line label in two at the space nearest its middle."""
    if "\n" in text or " " not in text:
        return text
    mid = len(text) // 2
    spaces = [i for i, ch in enumerate(text) if ch == " "]
    cut = min(spaces, key=lambda i: abs(i - mid))
    return text[:cut] + "\n" + text[cut + 1:]


def _fit_labels(fig):
    """Wrap axis labels longer than their axis; rotate overlapping x tick labels."""
    r = fig.canvas.get_renderer()
    changed = False
    for ax in fig.axes:
        if not ax.axison:
            continue
        box = ax.get_window_extent(r)
        yl, xl = ax.yaxis.label, ax.xaxis.label
        if yl.get_text() and yl.get_window_extent(r).height > box.height * 1.02:
            yl.set_text(_wrap_label(yl.get_text()))
            changed = True
        if xl.get_text() and xl.get_window_extent(r).width > box.width * 1.02:
            xl.set_text(_wrap_label(xl.get_text()))
            changed = True
        labels = [t for t in ax.get_xticklabels() if t.get_text() and t.get_visible()]
        if len(labels) >= 2 and not labels[0].get_rotation():
            boxes = [t.get_window_extent(r) for t in labels]
            if any(a.x1 + 2 > b.x0 for a, b in zip(boxes, boxes[1:])):
                for t in labels:
                    t.set_rotation(30)
                    t.set_ha("right")
                    t.set_rotation_mode("anchor")
                changed = True
    if changed:
        fig.canvas.draw()
