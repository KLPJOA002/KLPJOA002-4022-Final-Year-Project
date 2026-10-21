"""TableSpec: the complete, JSON-serialisable description of one table.

The plotted data come from an rsplot PlotSpec (embedded, so a saved table is
reproducible even if the figure's sidecar changes later); everything else is
layout and formatting.
"""
from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from typing import Any

TABLE_SPEC_VERSION = 1

# How a cell shows its spread. "auto": ± for SD / SEM, brackets for intervals.
SPREAD_FORMATS = {
    "auto": "Automatic (± for SD/SEM, [lo, hi] for intervals)",
    "pm": "± (SD/SEM; half-width for intervals)",
    "brackets": "1.22 [1.10, 1.31]",
    "parens": "1.22 (1.10–1.31)",
    "width": "1.22 (0.21)  — interval width",
    "column": "Separate column",
    "none": "Centre only",
}
STAT_PLACES = {
    "header": "Under each column heading",
    "caption": "In the caption only",
    "both": "Heading and caption",
    "none": "Nowhere",
}
N_MODES = {"caption": "Range in the caption", "column": "Column in the table", "none": "Not shown"}
BEST_MODES = ["auto", "lower", "higher", "zero", "none"]
FONT_SIZES = ["normalsize", "small", "footnotesize", "scriptsize"]
GROUP_SEPARATORS = {"space": "Small gap (\\addlinespace)", "midrule": "Rule (\\midrule)",
                    "none": "None"}


@dataclass
class Source:
    sidecar: str = ""              # .rsplot.json the plot came from ("" = rsplot's last figure)
    sidecar_saved_at: str = ""
    plot: dict = field(default_factory=dict)   # the rsplot PlotSpec, as saved


@dataclass
class Stats:
    """Statistic used. inherit = exactly what the figure used."""
    inherit: bool = True
    func: str = "median"           # mean | median | min | max  (when not inherited)
    spread: str = "iqr"            # none | std | sem | iqr | minmax | ci95
    stored_stat: str = "median"    # per-trial summary files
    stored_spread: str = "iqr"


@dataclass
class Layout:
    row_keys: list[str] = field(default_factory=list)   # grouping columns down the rows, in order
    col_keys: list[str] = field(default_factory=list)   # up to two across the columns (outer first)
    metrics: list[str] = field(default_factory=list)    # shown metrics, in order ([] = all)
    hidden: dict = field(default_factory=dict)          # column -> [value keys not shown]
    repeat_labels: bool = False    # repeat the outer row label on every row
    group_sep: str = "space"       # between groups of the first row key


@dataclass
class Format:
    spread_format: str = "auto"
    decimals: dict = field(default_factory=dict)        # metric -> int (missing = automatic)
    sig_figs: int = 3              # automatic decimals: significant figures of a typical value
    max_decimals: int = 4
    percent: bool | None = None    # fractions as % (None = as in the figure)
    spread_small: bool = False     # spread in \footnotesize
    stat_place: str = "header"
    n_mode: str = "caption"
    best: dict = field(default_factory=dict)            # metric -> auto|lower|higher|zero|none
    bold_best: bool = False
    best_scope: str = "column"     # column | group (within the first row key's groups)
    header_labels: dict = field(default_factory=dict)   # column/metric -> text ("|" = line break)
    value_labels: dict = field(default_factory=dict)    # "column=value" -> text (adds to figure's)
    wrap: int = 14                 # automatic header line length (0 = no wrapping)
    math_minus: bool = True        # −0.12 as $-$0.12


@dataclass
class Output:
    caption: str = ""
    caption_auto: bool = True      # append the statistic / fixed-factor sentence
    caption_detail: bool = True    # include the "Fixed: ...; averaged over ..." text
    label: str = ""
    placement: str = "ht"
    font_size: str = "small"
    tabcolsep: float | None = 8.0  # pt; None = LaTeX default
    makecell: bool = True
    resize: bool = False           # \resizebox{\textwidth}{!}{...}
    folder: str = ""
    filename: str = ""
    write_csv: bool = True


@dataclass
class TableSpec:
    source: Source = field(default_factory=Source)
    stats: Stats = field(default_factory=Stats)
    layout: Layout = field(default_factory=Layout)
    format: Format = field(default_factory=Format)
    output: Output = field(default_factory=Output)
    version: int = TABLE_SPEC_VERSION

    def to_dict(self) -> dict:
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "TableSpec":
        d = copy.deepcopy(d or {})
        return cls(source=_build(Source, d.get("source")), stats=_build(Stats, d.get("stats")),
                   layout=_build(Layout, d.get("layout")), format=_build(Format, d.get("format")),
                   output=_build(Output, d.get("output")),
                   version=d.get("version", TABLE_SPEC_VERSION))

    def copy(self) -> "TableSpec":
        return TableSpec.from_dict(self.to_dict())


def _build(cls, d: Any):
    if d is None:
        return cls()
    names = {f.name for f in dataclasses.fields(cls)}
    return cls(**{k: v for k, v in d.items() if k in names})
