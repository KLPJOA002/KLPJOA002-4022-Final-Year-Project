"""Plot-type plugin registry.

A plot type is one function decorated with @register_plot. It receives a
DrawContext for one facet (axes + that facet's data) and draws on ctx.ax. It
must not reference dataset column names; it reads roles from the context.

    @register_plot("dots", label="Dot plot", options=[Option("size", "float", 4)])
    def dots(ctx):
        for s in ctx.series():
            ctx.ax.plot(ctx.xpos(s.df), s.df[VALUE], "o", color=s.colour)
            ctx.add_handle(s)

Drop a new module into this package and it is picked up automatically.
"""
from __future__ import annotations

import importlib
import pkgutil
from dataclasses import dataclass, field
from typing import Any, Callable

import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

from .. import registry as reg
from .. import style as st
from ..pipeline import HI, LO, METRIC, N, VALUE, Prepared, _py

PLOT_TYPES: dict[str, "PlotType"] = {}


@dataclass
class Option:
    name: str
    type: str                  # bool | int | float | choice | str | column | value
    default: Any
    label: str = ""
    choices: list | None = None
    min: float | None = None
    max: float | None = None
    help: str = ""
    show_if: dict | None = None     # {other_option: [values]} -> only shown when matched
    of: str | None = None           # type "value": option name holding the column, or "@x"


@dataclass
class PlotType:
    name: str
    label: str
    func: Callable
    x: str = "any"             # any | discrete | numeric | none | metric
    needs_raw: bool = False    # works on un-aggregated rows (box, hist)
    roles: tuple = ("hue", "style", "facet")
    default_agg: str = "mean"
    default_spread: str = "std"
    options: list[Option] = field(default_factory=list)
    multi_metric: bool = True
    shared_colorbar: bool = False
    secondary: bool = False          # supports the stacked secondary-indicator panel
    auto_by: str | None = None       # family attribute added to grouping (e.g. series_unit)
    describe: Callable | None = None # (pre, opts) -> sentence prepended to the auto footnote
    point_word: str = "point"        # what one aggregated value is drawn as (cell, bar, ...)
    min_height_cm: Callable | None = None  # (pre, opts, tick_pt) -> cm needed to avoid overlap

    def option_defaults(self) -> dict:
        return {o.name: o.default for o in self.options}


def register_plot(name: str, label: str, **meta):
    def deco(func):
        PLOT_TYPES[name] = PlotType(name=name, label=label, func=func, **meta)
        return func
    return deco


def load_plugins() -> dict[str, PlotType]:
    for mod in pkgutil.iter_modules(__path__):
        importlib.import_module(f"{__name__}.{mod.name}")
    return PLOT_TYPES


# ------------------------------------------------------------- drawing ctx --
@dataclass
class Series:
    hue: Any
    style: Any
    by: tuple
    df: pd.DataFrame
    colour: str
    marker: str
    linestyle: Any
    key: tuple


class DrawContext:
    """Everything a plot function needs for one facet."""

    def __init__(self, ax, fig, data, raw, pre: Prepared, spec, ds, ptype: PlotType,
                 legend: dict, facet_index: int = 0):
        self.ax, self.fig = ax, fig
        self.data, self.raw = data, raw
        self.pre, self.spec, self.ds, self.ptype = pre, spec, ds, ptype
        self.style = spec.style
        self.roles = pre.roles
        self.levels = pre.levels
        self.opts = {**ptype.option_defaults(), **(spec.options or {})}
        self.legend = legend                 # shared across facets: key -> (label, handle)
        self.facet_index = facet_index
        self.colorbar_mappable = None
        self.extra_artists: list = []
        sp = st.style_preset(spec.style.preset)
        self.sizes = {k: max(v * spec.style.font_scale, sp["sizes"]["min"])
                      for k, v in sp["sizes"].items()}
        self.line_width = spec.style.line_width or sp["line_width"]
        self.marker_size = spec.style.marker_size or sp["marker_size"]
        self.capsize = sp["capsize"]
        self._build_encodings()

    # ---- encodings (stable: based on full level lists) ----
    def _build_encodings(self):
        hue_levels = self.levels.get("hue", [None]) if self.roles["hue"] else [None]
        cols = st.palette(self.style, max(len(hue_levels), 1))
        self._colour = {reg._value_key(_py(v)): c for v, c in zip(hue_levels, cols)}
        for k, c in (self.style.colors or {}).items():
            self._colour[str(k)] = c
        markers, styles = st.markers(), st.linestyles()
        style_levels = self.levels.get("style", []) if self.roles["style"] else []
        self._marker = {reg._value_key(_py(v)): markers[i % len(markers)]
                        for i, v in enumerate(style_levels)}
        self._ls = {reg._value_key(_py(v)): styles[i % len(styles)]
                    for i, v in enumerate(style_levels)}
        n_hue = len(self.levels.get("hue_present", hue_levels)) if self.roles["hue"] else 1
        # Redundant encoding: >3 colours or greyscale -> markers (and dashes) follow hue too.
        self.redundant = (not self.roles["style"]) and self.roles["hue"] and (
            self.style.greyscale or n_hue > 3)
        if self.redundant:
            self._marker = {reg._value_key(_py(v)): markers[i % len(markers)]
                            for i, v in enumerate(hue_levels)}
            if self.style.greyscale:
                self._ls = {reg._value_key(_py(v)): styles[i % len(styles)]
                            for i, v in enumerate(hue_levels)}

    def colour(self, hue_value=None) -> str:
        if not self.roles["hue"]:
            return (self.style.colors or {}).get("__single__") or st.palette(self.style, 1)[0]
        return self._colour.get(reg._value_key(_py(hue_value)), st.ink_secondary())

    def marker(self, hue_value=None, style_value=None) -> str:
        if self.roles["style"]:
            return self._marker.get(reg._value_key(_py(style_value)), self.style.marker)
        if self.redundant:
            return self._marker.get(reg._value_key(_py(hue_value)), self.style.marker)
        return self.style.marker

    def linestyle(self, hue_value=None, style_value=None):
        if self.roles["style"]:
            return self._ls.get(reg._value_key(_py(style_value)), self.style.linestyle)
        if self.redundant and self.style.greyscale:
            return self._ls.get(reg._value_key(_py(hue_value)), self.style.linestyle)
        return self.style.linestyle

    # ---- labels ----
    def value_label(self, col, v) -> str:
        if col == METRIC:
            return reg.axis_label(v, self.style.labels)
        if v is None or (isinstance(v, float) and np.isnan(v)) or v is pd.NA:
            vl = self.style.value_labels or {}
            custom = vl.get(f"{col}=nan") or vl.get("nan")
            derived = (self.ds.family.derived or {}).get(col) or {}
            return custom or derived.get("missing_label") or "no value"
        return reg.value_label(_py(v), self.style.value_labels, self.style.prettify_values,
                               col=col)

    # ---- series iteration ----
    def series(self, df: pd.DataFrame | None = None):
        df = self.data if df is None else df
        h, s = self.roles["hue"], self.roles["style"]
        by = list(self.roles["by"])
        cols = [c for c in (h, s) if c] + [b for b in by if b not in (h, s)]
        if not cols:
            yield Series(None, None, (), df, self.colour(), self.marker(), self.linestyle(), ())
            return
        order_h = {reg._value_key(_py(v)): i for i, v in enumerate(self.levels.get("hue", []))}
        order_s = {reg._value_key(_py(v)): i for i, v in enumerate(self.levels.get("style", []))}
        groups = []
        for key, sub in df.groupby(cols, dropna=False, sort=False):
            key = key if isinstance(key, tuple) else (key,)
            d = dict(zip(cols, key))
            hv, sv = d.get(h) if h else None, d.get(s) if s else None
            bv = tuple(d[b] for b in by if b not in (h, s))
            rank = (order_h.get(reg._value_key(_py(hv)), 1e9) if h else 0,
                    order_s.get(reg._value_key(_py(sv)), 1e9) if s else 0,
                    tuple(str(x) for x in bv))
            groups.append((rank, Series(hv, sv, bv, sub, self.colour(hv), self.marker(hv, sv),
                                        self.linestyle(hv, sv), key)))
        for _, ser in sorted(groups, key=lambda t: t[0]):
            yield ser

    def n_series(self) -> int:
        return sum(1 for _ in self.series())

    # ---- x positions ----
    @property
    def x_categorical(self) -> bool:
        x = self.roles["x"]
        if not x:
            return True
        if self.pre.x_is_metric:
            return False
        if self.opts.get("x_as_category"):
            return True
        p = self.ds.profile.get(x)
        return p is None or p.kind != "numeric"

    def x_categories(self) -> list:
        return self.levels.get("x_present", self.levels.get("x", []))

    def xpos(self, df: pd.DataFrame) -> np.ndarray:
        if "__x__" not in df:
            return np.zeros(len(df))
        if not self.x_categorical:
            return pd.to_numeric(df["__x__"], errors="coerce").to_numpy(dtype=float)
        idx = {reg._value_key(_py(v)): i for i, v in enumerate(self.x_categories())}
        return np.array([idx.get(reg._value_key(_py(v)), np.nan) for v in df["__x__"]],
                        dtype=float)

    def set_categorical_xticks(self):
        cats = self.x_categories()
        self.ax.set_xticks(range(len(cats)))
        self.ax.set_xticklabels([self.value_label(self.roles["x"], v) for v in cats])
        self.ax.set_xlim(-0.5, len(cats) - 0.5)

    def dodge_offsets(self, n: int, width: float) -> np.ndarray:
        if n <= 1 or width <= 0:
            return np.zeros(max(n, 1))
        return (np.arange(n) - (n - 1) / 2) * width

    def min_x_step(self) -> float:
        if self.x_categorical:
            return 1.0
        xs = np.unique(self.xpos(self.data)[np.isfinite(self.xpos(self.data))])
        return float(np.min(np.diff(xs))) if len(xs) > 1 else 1.0

    # ---- legend ----
    def add_handle(self, s: Series, kind: str = "line", marker: bool = True, **kw):
        """Register legend entries for a series (deduplicated across facets).

        `marker=False` for marks drawn without markers (CDF steps, time series),
        so the legend shows exactly what is on the plot.
        """
        h, sty = self.roles["hue"], self.roles["style"]
        lw = kw.get("lw", self.line_width)
        if h and ("hue", reg._value_key(_py(s.hue))) not in self.legend:
            mk = s.marker if marker and (self.redundant or not sty) else None
            self.legend[("hue", reg._value_key(_py(s.hue)))] = (
                s.hue, _handle(kind, s.colour, mk,
                               s.linestyle if (self.redundant or not marker) else "-", lw,
                               self.marker_size))
        if sty and ("style", reg._value_key(_py(s.style))) not in self.legend:
            self.legend[("style", reg._value_key(_py(s.style)))] = (
                s.style, _handle(kind, st.ink_secondary(), s.marker if marker else None,
                                 s.linestyle, lw, self.marker_size))

    def spread_available(self, df: pd.DataFrame) -> bool:
        return LO in df and HI in df and np.isfinite(df[LO].to_numpy(dtype=float)).any()


def _handle(kind, colour, marker, linestyle, lw, ms):
    if kind == "patch":
        from matplotlib.patches import Patch
        return Patch(facecolor=colour, edgecolor="none")
    if kind == "marker":
        return Line2D([], [], color=colour, marker=marker or "o", linestyle="none",
                      markersize=ms + 1)
    return Line2D([], [], color=colour, marker=marker, linestyle=linestyle, linewidth=lw,
                  markersize=ms)


__all__ = ["register_plot", "Option", "PlotType", "PLOT_TYPES", "DrawContext", "load_plugins",
           "VALUE", "LO", "HI", "N", "METRIC"]
