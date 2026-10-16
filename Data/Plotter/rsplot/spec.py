"""PlotSpec: the complete, JSON-serialisable description of one figure.

UI -> PlotSpec -> pipeline.prepare -> render. Nothing else carries state, so a
saved sidecar fully reproduces a figure.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Any

SPEC_VERSION = 1

AGG_FUNCS = ["none", "mean", "median", "min", "max", "count"]
SPREADS = ["none", "std", "sem", "iqr", "minmax", "ci95"]
SPREAD_LABELS = {"none": "None", "std": "± SD", "sem": "± SEM", "iqr": "IQR (25–75 %)",
                 "minmax": "Min–max", "ci95": "95 % CI"}
LEGEND_LOCS = ["outside right", "outside top", "outside bottom", "best", "upper left",
               "upper right", "lower left", "lower right", "off"]
MARGINS = {"tight": 0.02, "normal": 0.05, "loose": 0.10}


@dataclass
class DatasetRef:
    path: str = ""
    family: str | None = None
    include_ignored: bool = False


@dataclass
class Mapping:
    x: str | None = None
    y: list[str] = field(default_factory=list)   # one or more metrics
    y_mode: str = "overlay"                      # overlay | side_by_side (when len(y) > 1)
    hue: str | None = None
    facet: str | None = None
    facet_cols: int = 0                          # 0 = automatic
    style: str | None = None                     # marker / line-style column
    row: str | None = None                       # heatmap rows
    secondary: str | None = None                 # e.g. outlier_fraction, drawn in a panel below
    by: list[str] = field(default_factory=list)  # extra grouping without colour (e.g. one line per trial)


@dataclass
class Filter:
    column: str
    kind: str = "in"               # in | range
    values: list | None = None     # for kind == in
    lo: float | None = None        # for kind == range
    hi: float | None = None
    keep_nan: bool = False
    enabled: bool = True


@dataclass
class Aggregation:
    func: str = "none"             # see AGG_FUNCS
    spread: str = "none"           # see SPREADS
    stored_stat: str = "median"    # summary files: centre statistic (mean | median)
    stored_spread: str = "iqr"     # summary files: std | iqr | none


@dataclass
class Style:
    preset: str = "thesis"         # style preset name (typography, line weights)
    show_title: bool = False
    title: str = ""
    subtitle: str = ""
    footnote_mode: str = "auto"    # auto | custom | off
    footnote: str = ""
    xlabel: str | None = None      # None = automatic
    ylabel: str | None = None
    labels: dict = field(default_factory=dict)        # column -> display label
    value_labels: dict = field(default_factory=dict)  # category value -> display label
    prettify_values: bool = True
    xlim: list | None = None       # [lo, hi]; either may be None
    ylim: list | None = None
    xlog: bool = False
    ylog: bool = False
    x_ticks: int = 0               # 0 = automatic
    y_ticks: int = 0
    x_tick_format: str = ""        # e.g. "{x:.1f}" ; "" = automatic
    y_tick_format: str = ""
    fraction_as_percent: bool = True
    grid: bool = True
    legend: str = "outside right"
    legend_cols: int = 0
    legend_title: bool = True
    show_n: bool = True
    palette: str = "default"       # default | greyscale | <matplotlib cmap name>
    greyscale: bool = False
    colors: dict = field(default_factory=dict)        # series value -> hex
    cmap: str = "rs_sequential"
    marker: str = "o"
    marker_size: float | None = None   # None = preset default
    line_width: float | None = None
    linestyle: str = "-"
    band_alpha: float = 0.18
    annotate: bool = False
    margin: str = "normal"         # tight | normal | loose
    pad_pct: float | None = None   # overrides margin when set
    font_scale: float = 1.0
    sharex: bool = True
    sharey: bool = True


@dataclass
class Export:
    size_preset: str = "thesis_caption"
    width_cm: float | None = None   # None = from preset
    height_cm: float | None = None  # None = width * preset aspect
    formats: list[str] = field(default_factory=lambda: ["pdf"])
    dpi: int = 300
    transparent: bool = False
    folder: str = ""
    filename: str = ""
    usetex: bool = False
    mathtext: str = "stix"          # stix (Times-style, matches mathptmx) | cm | custom (text font)


@dataclass
class PlotSpec:
    plot_type: str = "line"
    dataset: DatasetRef = field(default_factory=DatasetRef)
    mapping: Mapping = field(default_factory=Mapping)
    filters: list[Filter] = field(default_factory=list)
    aggregation: Aggregation = field(default_factory=Aggregation)
    style: Style = field(default_factory=Style)
    export: Export = field(default_factory=Export)
    options: dict = field(default_factory=dict)       # plot-type specific options
    version: int = SPEC_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PlotSpec":
        """Tolerant loader: unknown keys are dropped, missing keys take defaults."""
        d = copy.deepcopy(d or {})
        return cls(
            plot_type=d.get("plot_type", "line"),
            dataset=_build(DatasetRef, d.get("dataset")),
            mapping=_build(Mapping, d.get("mapping")),
            filters=[_build(Filter, f) for f in d.get("filters", []) if f.get("column")],
            aggregation=_build(Aggregation, d.get("aggregation")),
            style=_build(Style, d.get("style")),
            export=_build(Export, d.get("export")),
            options=_migrate_options(dict(d.get("options") or {})),
            version=d.get("version", SPEC_VERSION),
        )

    def copy(self) -> "PlotSpec":
        return PlotSpec.from_dict(self.to_dict())


def _migrate_options(o: dict) -> dict:
    """Older saved figures: scatter option `fit` became `trend`."""
    if "fit" in o:
        o.setdefault("trend", o.pop("fit"))
    return o


def _build(cls, d: Any):
    if d is None:
        return cls() if cls is not Filter else None
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})
