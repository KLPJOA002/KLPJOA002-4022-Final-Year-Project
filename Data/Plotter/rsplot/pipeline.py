"""Spec + Dataset -> tidy, aggregated data ready for a plot function.

Long format: every metric in spec.mapping.y becomes rows tagged with METRIC, so
"overlay" (metric as hue) and "side by side" (metric as facet) need no special
cases in the plot functions.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import registry as reg
from .data import Dataset, sort_values
from .spec import PlotSpec

METRIC = "__metric__"   # pseudo-column holding the metric name
VALUE = "__value__"
X_VALUE = "__xvalue__"  # aggregated x when x is itself a metric
LO, HI, N = "__lo__", "__hi__", "__n__"

SPREAD_PHRASES = {"std": " ± SD", "sem": " ± SEM", "iqr": " with IQR", "minmax": " with range",
                  "ci95": " with 95 % CI of the mean"}
AGG_WORDS = {"mean": "averaged over", "median": "median taken over", "min": "minimum over",
             "max": "maximum over", "count": "counted over", "none": "points pooled across"}


@dataclass
class FactorNote:
    column: str
    n_values: int
    values: list
    status: str            # fixed | filtered | constant | unfixed
    action: str = ""       # for unfixed: averaged over / pooled across ...


@dataclass
class Prepared:
    data: pd.DataFrame                  # one row per plotted point (aggregated or raw)
    raw: pd.DataFrame                   # filtered long rows (box / hist / strip)
    roles: dict                         # x, hue, style, facet_col, facet_row, row, by -> column
    metrics: list[str]
    levels: dict                        # role -> ordered level list (stable, from full data)
    x_is_metric: bool
    aggregated: bool
    n_total: int
    n_filtered: int
    n_nan: int
    notes: list[FactorNote]
    footnote: str
    warnings: list[str] = field(default_factory=list)
    unit_name: str = "rows"
    secondary: pd.DataFrame | None = None
    n_nan_x: int = 0                    # rows dropped because the x factor has no value


# ------------------------------------------------------------------ filters --
def apply_filters(df: pd.DataFrame, spec: PlotSpec) -> pd.DataFrame:
    mask = pd.Series(True, index=df.index)
    for f in spec.filters:
        if not f.enabled or f.column not in df.columns:
            continue
        s = df[f.column]
        if f.kind == "range":
            m = pd.Series(True, index=df.index)
            num = pd.to_numeric(s, errors="coerce")
            if f.lo is not None:
                m &= num >= f.lo
            if f.hi is not None:
                m &= num <= f.hi
            m = m.fillna(False)
        else:
            if f.values is None:
                continue
            wanted = {reg._value_key(v) for v in f.values}
            m = s.map(lambda v: pd.notna(v) and reg._value_key(_py(v)) in wanted).astype(bool)
        if f.keep_nan:
            m |= s.isna()
        mask &= m
    return df[mask]


def _py(v):
    """numpy scalar -> python scalar (so float keys match JSON values)."""
    return v.item() if hasattr(v, "item") else v


# ----------------------------------------------------------------- prepare --
def prepare(ds: Dataset, spec: PlotSpec, needs_raw: bool = False,
            point_word: str = "point") -> Prepared:
    m = spec.mapping
    df = ds.frame()
    metrics = [y for y in m.y if y in ds.stats or y in df.columns]
    if not metrics:
        raise ValueError("Choose at least one metric (y).")
    for col in (m.x, m.hue, m.style, m.facet, m.row, *(m.by or [])):
        if col and col not in df.columns and col != METRIC:
            raise ValueError(f"Column '{col}' is not in this dataset.")

    n_total = len(df)
    dff = apply_filters(df, spec)
    n_filtered = len(dff)

    # ---- roles (multi-metric placement) ----
    roles = {"x": m.x, "hue": m.hue, "style": m.style, "facet_col": m.facet,
             "facet_row": None, "row": m.row, "by": [b for b in (m.by or []) if b]}
    if len(metrics) > 1:
        if m.y_mode == "side_by_side":
            if roles["facet_col"] is None:
                roles["facet_col"] = METRIC
            else:
                roles["facet_row"] = METRIC
        elif roles["hue"] is None:
            roles["hue"] = METRIC
        elif roles["style"] is None:
            roles["style"] = METRIC
        else:
            roles["facet_row"] = METRIC

    x_is_metric = bool(m.x and m.x in ds.profile and ds.profile[m.x].role == "metric"
                       and m.x not in ds.family.factors)
    keys = [c for c in (roles["facet_row"], roles["facet_col"], roles["row"], roles["hue"],
                        roles["style"], *roles["by"]) if c]
    if m.x and not x_is_metric:
        keys = [m.x] + keys
    keys = list(dict.fromkeys(keys))
    keep = [c for c in keys if c != METRIC] + ([m.x] if x_is_metric else [])

    # Rows with no value on a factor x axis (e.g. tilt of a fused tilt set) cannot be
    # placed; drop them up front so they are not counted in n or in the factor notes.
    n_nan_x = 0
    if m.x and not x_is_metric and m.x in dff:
        no_x = dff[m.x].isna()
        n_nan_x = int(no_x.sum())
        dff = dff[~no_x]

    # ---- long format ----
    stat = spec.aggregation.stored_stat
    parts, n_nan = [], 0
    for y in metrics:
        vcol = ds.value_column(y, stat)
        part = dff[list(dict.fromkeys(keep))].copy()
        part[METRIC] = y
        part[VALUE] = pd.to_numeric(dff[vcol], errors="coerce")
        if ds.is_summary() and y in ds.stats:
            lo, hi = _stored_spread(dff, ds.stats[y], part[VALUE], spec.aggregation.stored_spread)
            part[LO], part[HI] = lo, hi
            ncol = ds.family.n_column
            part[N] = dff[ncol].to_numpy() if ncol and ncol in dff else 1
        if x_is_metric:
            part[X_VALUE] = pd.to_numeric(dff[ds.value_column(m.x, stat)], errors="coerce")
        bad = part[VALUE].isna() | (part[X_VALUE].isna() if x_is_metric else False)
        n_nan += int(bad.sum())
        parts.append(part[~bad])
    long = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if m.x and len(long):
        long["__x__"] = long[X_VALUE] if x_is_metric else long[m.x]

    # ---- aggregate ----
    # Distribution plots (box, histogram, ...) always draw the individual rows.
    func = "none" if needs_raw else spec.aggregation.func
    aggregated = func != "none"
    warnings: list[str] = []
    if aggregated and len(long):
        data = aggregate(long, keys, func, spec.aggregation.spread, x_is_metric)
        if spec.aggregation.spread != "none" and (data[N] < 2).all():
            warnings.append("Every group has a single value, so no spread can be shown "
                            "(n = 1 per point).")
    else:
        data = long.copy()
        if LO not in data:
            data[LO] = np.nan
            data[HI] = np.nan
        if N not in data:
            data[N] = 1
    if x_is_metric and len(data) and X_VALUE in data:
        data["__x__"] = data[X_VALUE]
    elif m.x and len(data) and m.x in data:
        data["__x__"] = data[m.x]

    levels = _levels(ds, roles, metrics, long)
    if m.x and not x_is_metric and len(data):
        order = {v: i for i, v in enumerate(levels.get("x", []))}
        data = data.assign(__order__=data[m.x].map(lambda v: order.get(v, 1e9)))
        data = data.sort_values("__order__", kind="stable").drop(columns="__order__")
    elif x_is_metric and len(data):
        data = data.sort_values("__x__", kind="stable")

    pooled = needs_raw or func == "none"
    notes = factor_notes(ds, spec, dff, keys, func, pooled)
    if func == "none" and not needs_raw and spec.plot_type in ("line", "bar", "heatmap"):
        dup = long.duplicated(subset=[k for k in keys] or None, keep=False).any() if keys else len(long) > 1
        if dup:
            warnings.append("Several rows share the same x / colour / facet values and no "
                            "aggregation is selected; they are drawn on top of each other.")
    pre = Prepared(data=data.reset_index(drop=True), raw=long, roles=roles, metrics=metrics,
                   levels=levels, x_is_metric=x_is_metric, aggregated=aggregated,
                   n_total=n_total, n_filtered=n_filtered, n_nan=n_nan, notes=notes,
                   footnote="", warnings=warnings, unit_name=ds.family.unit_name,
                   n_nan_x=n_nan_x)
    pre.footnote = build_footnote(ds, spec, pre, point_word)
    return pre


def _stored_spread(dff, stats: dict, centre: pd.Series, mode: str):
    if mode == "std" and "std" in stats:
        sd = pd.to_numeric(dff[stats["std"]], errors="coerce").to_numpy()
        return centre.to_numpy() - sd, centre.to_numpy() + sd
    if mode == "iqr" and "p25" in stats and "p75" in stats:
        return (pd.to_numeric(dff[stats["p25"]], errors="coerce").to_numpy(),
                pd.to_numeric(dff[stats["p75"]], errors="coerce").to_numpy())
    return np.full(len(dff), np.nan), np.full(len(dff), np.nan)


def aggregate(long: pd.DataFrame, keys: list[str], func: str, spread: str,
              x_is_metric: bool = False) -> pd.DataFrame:
    keys = keys or [METRIC]
    if METRIC not in keys:
        keys = keys + [METRIC]
    g = long.groupby(keys, dropna=False, sort=False, observed=True)
    v = g[VALUE]
    n = v.count()
    centre = n.astype(float) if func == "count" else v.agg(func)
    out = pd.DataFrame({VALUE: centre, N: n})
    if func != "count":
        lo, hi = spread_bounds(v, centre, n, spread)
        out[LO], out[HI] = lo, hi
    else:
        out[LO] = out[HI] = np.nan
    if x_is_metric:
        out[X_VALUE] = g[X_VALUE].agg("mean" if func == "count" else func)
        xlo, xhi = spread_bounds(g[X_VALUE], out[X_VALUE], n, spread)
        out["__xlo__"], out["__xhi__"] = xlo, xhi
    return out.reset_index()


def spread_bounds(v, centre, n, spread: str):
    if spread == "std":
        sd = v.std(ddof=1)
        return centre - sd, centre + sd
    if spread == "sem":
        se = v.sem(ddof=1)
        return centre - se, centre + se
    if spread == "iqr":
        return v.quantile(0.25), v.quantile(0.75)
    if spread == "minmax":
        return v.min(), v.max()
    if spread == "ci95":
        from scipy import stats
        mean, se = v.mean(), v.sem(ddof=1)
        t = pd.Series(stats.t.ppf(0.975, np.maximum(n - 1, 1)), index=n.index)
        t[n < 2] = np.nan
        # CI is about the mean; centred on the chosen statistic only if it is the mean
        return mean - t * se, mean + t * se
    nan = pd.Series(np.nan, index=centre.index)
    return nan, nan


def _levels(ds: Dataset, roles: dict, metrics: list[str], long: pd.DataFrame) -> dict:
    """Ordered levels per role, taken from the *unfiltered* data so colours stay put."""
    out = {}
    for role, col in roles.items():
        if role == "by" or not col:
            continue
        if col == METRIC:
            out[role] = list(metrics)
        elif col in ds.profile and ds.profile[col].values is not None:
            present = set(long[col].dropna().map(_py).tolist()) if col in long else set()
            full = [_py(v) for v in ds.profile[col].values]
            out[role] = full
            out[role + "_present"] = [v for v in full if v in present]
            if long[col].isna().any() if col in long else False:
                out[role].append(np.nan)
                out[role + "_present"].append(np.nan)
        elif col in long:
            out[role] = sort_values(long[col].dropna().unique().tolist())
    return out


# ------------------------------------------------------------ factor notes --
def factor_notes(ds: Dataset, spec: PlotSpec, dff: pd.DataFrame, keys: list[str],
                 func: str, pooled_plot: bool) -> list[FactorNote]:
    """Classify every experimental factor that is not part of the plotted grouping.

    A factor is "unfixed" only if it takes more than one value *within* some
    plotted group (point / box / cell); a factor that is fully determined by the
    grouping (e.g. decimation_on given decimation_magnitude) is not flagged.
    """
    keys = [k for k in dict.fromkeys(keys) if k and k != METRIC and k in dff]
    filtered = {f.column for f in spec.filters if f.enabled}
    composites = set(ds.family.composites)
    notes = []
    for c in ds.experimental_factors():
        if c in keys or c not in dff:
            continue
        vals = dff[c].map(_py).unique().tolist()
        vals = sort_values([v for v in vals if not _isnan(v) and v is not pd.NA]) + (
            ["n/a"] if dff[c].isna().any() else [])
        if len(vals) <= 1:
            status = "filtered" if c in filtered else (
                "constant" if ds.profile[c].constant else "fixed")
            notes.append(FactorNote(c, len(vals), vals, status))
            continue
        within = (dff.groupby(keys, dropna=False, observed=True, sort=False)[c]
                  .nunique(dropna=False).max() if keys else len(vals))
        if within > 1:
            notes.append(FactorNote(c, len(vals), vals, "unfixed",
                                    AGG_WORDS["none" if pooled_plot else func]))
        else:
            notes.append(FactorNote(c, len(vals), vals, "determined"))
    # A composite (e.g. config_label) is only worth flagging if nothing it is made of is.
    if any(n.status == "unfixed" and n.column not in composites for n in notes):
        for n in notes:
            if n.column in composites and n.status == "unfixed":
                n.status = "composite"
    return notes


def _isnan(v) -> bool:
    return isinstance(v, float) and np.isnan(v)


def unfixed(pre: Prepared) -> list[FactorNote]:
    return [n for n in pre.notes if n.status == "unfixed"]


# ---------------------------------------------------------------- footnote --
def _fmt_value(v) -> str:
    return reg.value_label(v)


def _n_range(series: pd.Series) -> str:
    s = series.dropna()
    if s.empty:
        return "0"
    lo, hi = int(s.min()), int(s.max())
    return f"{lo}" if lo == hi else f"{lo}–{hi}"


def lower_first(s: str) -> str:
    """'Mean accuracy RMSE' -> 'mean accuracy RMSE' (acronyms such as 'RMSE' kept)."""
    return s if len(s) > 1 and s[1].isupper() else s[:1].lower() + s[1:]


def build_footnote(ds: Dataset, spec: PlotSpec, pre: Prepared, point_word: str = "point") -> str:
    labels = spec.style.labels
    lab = lambda c: reg.axis_label(c, labels).split(" (")[0]
    parts = []
    agg = spec.aggregation
    unit = ds.family.unit_name
    if pre.aggregated and len(pre.data) and agg.func != "none":
        word = {"mean": "Mean", "median": "Median", "min": "Minimum", "max": "Maximum",
                "count": "Count"}[agg.func]
        spread = "" if agg.spread == "none" or agg.func == "count" else \
            SPREAD_PHRASES[agg.spread]
        parts.append(f"{word}{spread} of n = {_n_range(pre.data[N])} {unit} per {point_word}.")
    elif ds.is_summary() and len(pre.data):
        stat = agg.stored_stat
        sp = {"std": " ± SD", "iqr": " with IQR", "none": ""}.get(agg.stored_spread, "")
        n_unit = ds.family.n_column_unit or "frames"
        parts.append(f"Per-trial {stat}{sp} over n = {_n_range(pre.data[N])} {n_unit}.")
    fixed = [n for n in pre.notes if n.status in ("filtered", "constant", "fixed")
             and n.values and n.values[0] != "n/a"]
    if fixed:
        parts.append("Fixed: " + "; ".join(f"{lab(n.column)} = {_fmt_value(n.values[0])}"
                                          for n in fixed) + ".")
    unf, seen = [], set()
    for n in unfixed(pre):           # e.g. object / object_label: same label, same split
        key = (lab(n.column), n.n_values)
        if key not in seen:
            seen.add(key)
            unf.append(n)
    if unf:
        action = unf[0].action
        shown = ", ".join(f"{lab(n.column)} ({n.n_values})" for n in unf[:6])
        more = f" and {len(unf) - 6} more" if len(unf) > 6 else ""
        parts.append(f"{action[:1].upper() + action[1:]}: {shown}{more}.")
    comp = [n for n in pre.notes if n.status == "composite"]
    if comp:
        parts.append("Spanning " + ", ".join(f"{n.n_values} {lab(n.column).lower()}s"
                                            for n in comp) + ".")
    other = [f for f in spec.filters if f.enabled and not filter_is_noop(ds, f)
             and f.column not in {n.column for n in pre.notes}]
    if other:
        parts.append("Filters: " + "; ".join(filter_text(f, labels) for f in other) + ".")
    if pre.n_nan_x:
        xl = lower_first(reg.axis_label(spec.mapping.x, labels).split(" (")[0])
        parts.append(f"{pre.n_nan_x:,} rows without a {xl} value excluded.")
    if pre.n_nan:
        parts.append(f"{pre.n_nan:,} rows without a value excluded.")
    return " ".join(parts)


def filter_is_noop(ds: Dataset, f) -> bool:
    """True if the filter keeps every row (e.g. just added, or all values ticked)."""
    p = ds.profile.get(f.column)
    if p is None or not f.enabled:
        return True
    if p.non_null < 1 and not f.keep_nan:
        return False
    if f.kind == "range":
        return ((f.lo is None or p.vmin is None or f.lo <= p.vmin) and
                (f.hi is None or p.vmax is None or f.hi >= p.vmax))
    if p.values is None or f.values is None:
        return f.values is None
    return {reg._value_key(v) for v in p.values} <= {reg._value_key(v) for v in f.values}


def filter_text(f, labels=None) -> str:
    """Readable filter description: 'Height = 641 mm', 'Preset: Default, High density',
    'Accuracy RMSE ≤ 10 mm'."""
    info = reg.column_info(f.column)
    name = (labels or {}).get(f.column) or info["label"]
    unit = info.get("unit")
    u = f" {unit}" if unit and unit not in ("%", "°") else (unit or "")
    if f.kind == "range":
        if f.lo is not None and f.hi is not None:
            return f"{name} {f.lo:.4g}–{f.hi:.4g}{u}"
        if f.lo is not None:
            return f"{name} ≥ {f.lo:.4g}{u}"
        return f"{name} ≤ {f.hi:.4g}{u}"
    vals = [_fmt_value(v) for v in (f.values or [])]
    if len(vals) == 1:
        return f"{name} = {vals[0]}{u}"
    if not vals:
        return f"{name}: none"
    shown = ", ".join(vals[:4]) + (f" + {len(vals) - 4} more" if len(vals) > 4 else "")
    return f"{name}: {shown}"
