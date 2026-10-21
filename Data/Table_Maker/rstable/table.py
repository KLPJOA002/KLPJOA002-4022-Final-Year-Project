"""TableSpec -> rsplot pipeline -> Table (numbers, layout and statistic, no formatting).

The values are produced by rsplot's own `pipeline.prepare` on the figure's
PlotSpec, i.e. exactly the points (centre, spread bounds, n) the figure drew.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from rsplot import registry as reg
from rsplot.data import Dataset, sort_values
from rsplot.pipeline import HI, LO, METRIC, N, VALUE, X_VALUE, Prepared, _py, prepare
from rsplot.plots import PLOT_TYPES, load_plugins
from rsplot.render import _drop_unused_roles, get_dataset
from rsplot.spec import PlotSpec

from .spec import TableSpec

DUP = "__dup__"          # pseudo key numbering rows that share every grouping value
SYMMETRIC = {"std", "sem"}
INTERVAL = {"iqr", "minmax", "ci95"}

CENTRE_WORDS = {"mean": "mean", "median": "median", "min": "minimum", "max": "maximum",
                "count": "count", "none": "value"}
CENTRE_PLURAL = {"mean": "means", "median": "medians", "min": "minima", "max": "maxima",
                 "count": "counts", "none": "single values"}
SPREAD_LONG = {"std": "standard deviation (SD)", "sem": "standard error of the mean (SEM)",
               "iqr": "interquartile range (Q1–Q3)", "minmax": "range (minimum–maximum)",
               "ci95": "95 % confidence interval of the mean"}
SPREAD_SHORT = {"std": "SD", "sem": "SEM", "iqr": "IQR", "minmax": "range", "ci95": "95 % CI"}
# Header text of the spread for each cell format (intervals / symmetric)
SPREAD_HEAD = {
    "brackets": {"iqr": "[Q1, Q3]", "minmax": "[min, max]", "ci95": "[95 % CI]",
                 "std": "[−SD, +SD]", "sem": "[−SEM, +SEM]"},
    "parens": {"iqr": "(Q1–Q3)", "minmax": "(min–max)", "ci95": "(95 % CI)",
               "std": "(−SD–+SD)", "sem": "(−SEM–+SEM)"},
    "pm": {"iqr": "± ½IQR", "minmax": "± ½range", "ci95": "± 95 % CI", "std": "± SD",
           "sem": "± SEM"},
    "width": {"iqr": "(IQR)", "minmax": "(range)", "ci95": "(CI width)", "std": "(SD)",
              "sem": "(SEM)"},
    "column": {"iqr": "Q1–Q3", "minmax": "min–max", "ci95": "95 % CI", "std": "SD",
               "sem": "SEM"},
}


@dataclass
class StatInfo:
    func: str                 # centre statistic
    spread: str               # none | std | sem | iqr | minmax | ci95
    per_trial: bool           # values are stored per-trial statistics (summary file)
    unit_name: str            # what n counts (scans, frames, ...)
    fmt: str                  # resolved cell spread format
    source: str               # "figure" | "override"

    @property
    def has_spread(self) -> bool:
        return self.spread != "none" and self.fmt != "none" and self.func != "count"

    def short(self) -> str:
        """'median [Q1, Q3]' — the statistic, as written under a column heading."""
        c = CENTRE_WORDS.get(self.func, self.func)
        if self.per_trial:
            c = f"per-trial {c}"
        if not self.has_spread:
            return c
        if self.fmt == "column":
            return c
        return f"{c} {SPREAD_HEAD[self.fmt][self.spread]}"

    def spread_head(self) -> str:
        return SPREAD_HEAD["column"].get(self.spread, "")

    def sentence(self, n_text: str = "") -> str:
        """Caption sentence describing the statistic (LaTeX-ready plain text)."""
        what = CENTRE_PLURAL.get(self.func, self.func)
        if self.per_trial:
            what = f"per-trial {what}"
        s = f"Values are {what}"
        if self.has_spread:
            long = SPREAD_LONG[self.spread]
            if self.fmt == "pm":
                s += (f" ± the {long}" if self.spread in SYMMETRIC
                      else f" ± half the {long}")
            elif self.fmt == "brackets":
                s += f" with the {long} in brackets"
            elif self.fmt == "parens":
                s += f" with the {long} in parentheses"
            elif self.fmt == "width":
                s += (f" with the {long} in parentheses" if self.spread in SYMMETRIC
                      else f" with the width of the {long} in parentheses")
            elif self.fmt == "column":
                s += f", with the {long} in the adjacent column"
        if n_text:
            s += f", over {n_text}" if not self.per_trial else f" (over {n_text} per trial)"
        return s + "."


@dataclass
class Cell:
    value: float
    lo: float = np.nan
    hi: float = np.nan
    n: float = np.nan
    metric: str = ""
    best: bool = False


@dataclass
class Table:
    row_keys: list[str]
    col_keys: list[str]
    rows: list[tuple]                      # key values per row (in row_keys order)
    cols: list[tuple]                      # key values per data column (in col_keys order)
    cells: dict                            # (row index, col index) -> Cell
    metrics: list[str]                     # metrics shown, in order
    stat: StatInfo
    percent: dict                          # metric -> shown as % (value * 100)
    decimals: dict                         # metric -> decimals used
    n_text: str                            # "n = 4–5 scans"
    detail: str                            # rsplot's "Fixed: ...; averaged over ..." text
    warnings: list[str] = field(default_factory=list)
    plot: PlotSpec | None = None
    ds: Dataset | None = None
    x_metric: str | None = None            # x column when x was a metric (X_VALUE key)
    available: list[str] = field(default_factory=list)   # every grouping key (incl. METRIC)
    all_values: dict = field(default_factory=dict)       # key -> values present (before hiding)
    figure_stat: str = ""                  # the figure's own statistic, e.g. "median [Q1, Q3]"

    def metric_of(self, r: int, c: int) -> str:
        key = dict(zip(self.row_keys, self.rows[r])) | dict(zip(self.col_keys, self.cols[c]))
        return key.get(METRIC, self.metrics[0] if self.metrics else "")


# ------------------------------------------------------------- plot spec --
def plot_spec(ts: TableSpec) -> PlotSpec:
    """The figure's PlotSpec with any statistic override applied."""
    load_plugins()
    ps = PlotSpec.from_dict(ts.source.plot)
    if ps.plot_type not in PLOT_TYPES:
        raise ValueError(f"Unknown plot type '{ps.plot_type}' in the figure settings.")
    ps = _drop_unused_roles(ps, PLOT_TYPES[ps.plot_type])
    if not ts.stats.inherit:
        ps.aggregation.func = ts.stats.func
        ps.aggregation.spread = ts.stats.spread
        ps.aggregation.stored_stat = ts.stats.stored_stat
        ps.aggregation.stored_spread = ts.stats.stored_spread
    return ps


def prepared(ts: TableSpec, ds: Dataset | None = None) -> tuple[PlotSpec, Dataset, Prepared]:
    ps = plot_spec(ts)
    ds = ds or get_dataset(ps)
    # Tables always tabulate one value per group (never the raw rows of a box plot),
    # so the aggregation is applied whatever the figure's plot type drew.
    pre = prepare(ds, ps, needs_raw=False, point_word="cell")
    return ps, ds, pre


def available_keys(pre: Prepared) -> list[str]:
    """Grouping columns that identify one value: rows or columns of the table."""
    r = pre.roles
    keys = [r.get("facet_row"), r.get("facet_col"), r.get("row"),
            None if pre.x_is_metric else r.get("x"), r.get("hue"), r.get("style"),
            *(r.get("by") or [])]
    out = [k for k in dict.fromkeys(keys) if k and k != METRIC]
    if pre.x_is_metric and r.get("x"):
        out.insert(0, X_VALUE)
    return out + [METRIC]


def default_layout(ts: TableSpec, pre: Prepared) -> None:
    """Fill an empty layout: metrics across the columns, every factor down the rows."""
    lay = ts.layout
    keys = available_keys(pre)
    if not lay.row_keys and not lay.col_keys:
        lay.col_keys = [METRIC]
        lay.row_keys = [k for k in keys if k != METRIC]
    if not lay.metrics:
        lay.metrics = list(pre.metrics)


def normalise_layout(ts: TableSpec, pre: Prepared) -> list[str]:
    """Make the layout consistent with the data; returns notes about what changed."""
    lay, notes = ts.layout, []
    keys = available_keys(pre)
    lay.row_keys = [k for k in dict.fromkeys(lay.row_keys) if k in keys]
    lay.col_keys = [k for k in dict.fromkeys(lay.col_keys) if k in keys and k not in lay.row_keys
                    and k != X_VALUE][:2]
    for k in keys:                     # every grouping column must be placed somewhere
        if k not in lay.row_keys and k not in lay.col_keys:
            if k == METRIC and len(lay.col_keys) < 2:
                lay.col_keys.append(k)
            else:
                lay.row_keys.append(k)
                notes.append(f"{key_label(k, pre=pre)} added to the rows (it separates values).")
    lay.metrics = [m for m in dict.fromkeys(lay.metrics) if m in pre.metrics] or list(pre.metrics)
    return notes


# ------------------------------------------------------------------ build --
def build(ts: TableSpec, ds: Dataset | None = None) -> Table:
    ps, ds, pre = prepared(ts, ds)
    default_layout(ts, pre)
    warnings = normalise_layout(ts, pre) + list(pre.warnings)
    lay, fm = ts.layout, ts.format

    stat = stat_info(ts, ps, ds, pre)
    data = pre.data.copy()
    data = data[data[METRIC].isin(lay.metrics)]
    if pre.x_is_metric and X_VALUE in data:
        data[X_VALUE] = data[X_VALUE].astype(float)

    all_values = {}
    for k in lay.row_keys + lay.col_keys:
        if k not in (METRIC, X_VALUE) and k in data:
            all_values[k] = [v[0] for v in _combos(data, [k], {k: _order(k, ds, data, [])})]

    # hidden values
    for col, hidden in (lay.hidden or {}).items():
        if col in data and hidden and col != METRIC:
            keys = data[col].map(lambda v: _vkey(v))
            data = data[~keys.isin(set(hidden))]

    keys = lay.row_keys + lay.col_keys
    dup = data.duplicated(subset=keys, keep=False)
    if dup.any():
        data[DUP] = data.groupby(keys, dropna=False, sort=False).cumcount() + 1
        lay_rows = lay.row_keys + [DUP]
        warnings.append("Several values share the same row and column (the figure did not "
                        "aggregate them); they are numbered in a '#' column. Choose a "
                        "statistic under Data → Statistic to combine them.")
    else:
        lay_rows = list(lay.row_keys)

    orders = {k: _order(k, ds, data, lay.metrics) for k in lay_rows + lay.col_keys}
    rows = _combos(data, lay_rows, orders)
    cols = _combos(data, lay.col_keys, orders) if lay.col_keys else [()]

    percent = {m: _percent(ts, ps, m) for m in lay.metrics}
    rindex = {r: i for i, r in enumerate(rows)}
    cindex = {c: j for j, c in enumerate(cols)}
    cells = {}
    for rec in data.to_dict("records"):
        r = tuple(_py(rec[k]) for k in lay_rows)
        c = tuple(_py(rec[k]) for k in lay.col_keys)
        m = rec[METRIC]
        k = 100.0 if percent.get(m) else 1.0
        cells[(rindex[_norm(r)], cindex[_norm(c)])] = Cell(
            _f(rec[VALUE]) * k, _f(rec.get(LO)) * k, _f(rec.get(HI)) * k, _f(rec.get(N)), m)

    decimals = {}
    for m in lay.metrics:
        if m in fm.decimals and fm.decimals[m] is not None and fm.decimals[m] != "":
            decimals[m] = int(fm.decimals[m])
        else:
            vals = [c.value for c in cells.values() if c.metric == m]
            decimals[m] = auto_decimals(vals, fm.sig_figs, fm.max_decimals,
                                        integer=stat.func == "count")

    t = Table(row_keys=lay_rows, col_keys=list(lay.col_keys), rows=rows, cols=cols, cells=cells,
              metrics=list(lay.metrics), stat=stat, percent=percent, decimals=decimals,
              n_text=n_text(cells.values(), stat), detail=detail_text(pre, ds),
              warnings=warnings, plot=ps, ds=ds,
              x_metric=ps.mapping.x if pre.x_is_metric else None,
              available=available_keys(pre), all_values=all_values,
              figure_stat=figure_stat(ts, ds, pre))
    if fm.bold_best:
        mark_best(t, ts)
    if not cells:
        t.warnings.append("No values to show (everything is filtered or hidden).")
    return t


def stat_info(ts: TableSpec, ps: PlotSpec, ds: Dataset, pre: Prepared) -> StatInfo:
    agg = ps.aggregation
    if pre.aggregated:
        func, spread, per_trial = agg.func, agg.spread, False
        unit = ds.family.unit_name
    elif ds.is_summary():
        func, spread, per_trial = agg.stored_stat, agg.stored_spread, True
        unit = ds.family.n_column_unit or "frames"
    else:
        func, spread, per_trial = "none", "none", False
        unit = ds.family.unit_name
    if spread not in SYMMETRIC | INTERVAL:
        spread = "none"
    fmt = ts.format.spread_format
    if fmt == "auto":
        fmt = "pm" if spread in SYMMETRIC else "brackets"
    return StatInfo(func, spread, per_trial, unit, fmt,
                    "figure" if ts.stats.inherit else "override")


def figure_stat(ts: TableSpec, ds: Dataset, pre: Prepared) -> str:
    """The statistic the figure itself used (before any override in the table)."""
    base = TableSpec.from_dict(ts.to_dict())
    base.stats.inherit = True
    ps = plot_spec(base)
    agg = ps.aggregation
    if agg.func != "none":
        sp = SPREAD_SHORT.get(agg.spread)
        return CENTRE_WORDS.get(agg.func, agg.func) + (f" with {sp}" if sp else "")
    if ds.is_summary():
        sp = SPREAD_SHORT.get(agg.stored_spread)
        return f"per-trial {agg.stored_stat}" + (f" with {sp}" if sp else "")
    return "single values (not aggregated)"


def detail_text(pre: Prepared, ds: Dataset) -> str:
    """rsplot's footnote without its first (statistic) sentence."""
    text = pre.footnote or ""
    if (pre.aggregated or ds.is_summary()) and ". " in text:
        text = text.split(". ", 1)[1]
    elif (pre.aggregated or ds.is_summary()) and text.endswith("."):
        text = ""
    return text.replace(" per point", " per cell").strip()


def n_text(cells, stat: StatInfo) -> str:
    ns = [c.n for c in cells if not _isnan(c.n)]
    if not ns or stat.func == "none" and not stat.per_trial:
        return ""
    lo, hi = int(min(ns)), int(max(ns))
    rng = f"{lo}" if lo == hi else f"{lo}–{hi}"
    return f"n = {rng} {stat.unit_name}"


def mark_best(t: Table, ts: TableSpec) -> None:
    """Bold the best value of each comparable set (same metric; per column, or per row
    when the metrics run down the rows), optionally within groups of the first row key."""
    fm = ts.format
    by_row = METRIC in t.row_keys
    group_of = (lambda r: t.rows[r][0]) if (fm.best_scope == "group" and len(t.row_keys) > 1
                                            and t.row_keys[0] != METRIC) else (lambda r: None)
    sets: dict = {}
    for (r, c), cell in t.cells.items():
        key = (cell.metric, r if by_row else c, group_of(r))
        sets.setdefault(key, []).append(cell)
    for (m, _, _), cs in sets.items():
        mode = best_mode(m, fm.best.get(m, "auto"))
        if mode == "none" or len(cs) < 2:
            continue
        d = t.decimals.get(m, 2)
        score = {"lower": lambda v: v, "higher": lambda v: -v, "zero": abs}[mode]
        vals = [round(score(c.value), d) for c in cs if not _isnan(c.value)]
        if not vals:
            continue
        top = min(vals)
        for c in cs:
            if not _isnan(c.value) and round(score(c.value), d) == top:
                c.best = True


def best_mode(metric: str, choice: str = "auto") -> str:
    if choice and choice != "auto":
        return choice
    info = reg.column_info(metric)
    if "better" in info:
        return info["better"]
    return "zero" if "bias" in metric or "signed" in metric else "none"


# ---------------------------------------------------------------- helpers --
def auto_decimals(values, sig: int = 3, max_dec: int = 4, integer: bool = False) -> int:
    if integer:
        return 0
    v = [abs(x) for x in values if not _isnan(x) and x != 0]
    if not v:
        return 2
    # the largest value gets `sig` significant figures; the column shares its decimals
    typical = float(max(v))
    return int(min(max(sig - 1 - math.floor(math.log10(typical)), 0), max_dec))


def _percent(ts: TableSpec, ps: PlotSpec, metric: str) -> bool:
    on = ts.format.percent if ts.format.percent is not None else ps.style.fraction_as_percent
    return bool(on and reg.is_fraction(metric))


def _order(key: str, ds: Dataset, data: pd.DataFrame, metrics: list[str]) -> dict:
    if key == METRIC:
        vals = list(metrics)
    elif key == DUP:
        vals = sorted(data[DUP].unique().tolist())
    elif key == X_VALUE:
        vals = sorted(data[X_VALUE].dropna().unique().tolist())
    elif key in ds.profile and ds.profile[key].values is not None:
        vals = [_py(v) for v in ds.profile[key].values]
    else:
        vals = sort_values([_py(v) for v in data[key].dropna().unique().tolist()])
    return {_vkey(v): i for i, v in enumerate(vals)}


def _combos(data: pd.DataFrame, keys: list[str], orders: dict) -> list[tuple]:
    if not keys:
        return [()]
    seen = {}
    for rec in data[keys].itertuples(index=False, name=None):
        t = _norm(tuple(_py(v) for v in rec))
        seen.setdefault(t, None)

    def sk(t):
        return tuple(orders[k].get(_vkey(v), 1e9 if not _isnan(v) else 2e9)
                     for k, v in zip(keys, t))
    return sorted(seen, key=sk)


def _norm(t: tuple) -> tuple:
    """NaN != NaN; use one sentinel so missing values group together."""
    return tuple(None if _isnan(v) or v is pd.NA else v for v in t)


def _vkey(v) -> str:
    if v is None or _isnan(v) or v is pd.NA:
        return "n/a"
    return reg._value_key(_py(v))


def _isnan(v) -> bool:
    return isinstance(v, float) and math.isnan(v)


def _f(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return np.nan


def key_label(key: str, plot: PlotSpec | None = None, pre: Prepared | None = None,
              x_metric: str | None = None) -> str:
    """'Height (mm)' for a grouping column (figure renames honoured)."""
    labels = plot.style.labels if plot else {}
    if key == METRIC:
        return "Metric"
    if key == DUP:
        return "#"
    if key == X_VALUE:
        x = x_metric or (pre.roles.get("x") if pre else None)
        return reg.axis_label(x, labels) if x else "x"
    return reg.axis_label(key, labels)


def value_text(key: str, value, plot: PlotSpec | None, extra: dict | None = None,
               x_decimals: int = 2) -> str:
    """Display text of a grouping value (figure renames, then this table's renames)."""
    if key == METRIC:
        return reg.axis_label(value, plot.style.labels if plot else None).split(" (")[0]
    if value is None:
        k = f"{key}=n/a"
        return (extra or {}).get(k) or "n/a"
    if key == X_VALUE:
        return f"{value:.{x_decimals}f}"
    if key == DUP:
        return str(value)
    vk = reg.value_key(key, value)
    if extra and extra.get(vk):
        return extra[vk]
    overrides = plot.style.value_labels if plot else None
    prettify = plot.style.prettify_values if plot else True
    return reg.value_label(value, overrides, prettify, key)
