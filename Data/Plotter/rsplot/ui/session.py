"""UI-independent logic behind the app (testable headless)."""
from __future__ import annotations

import base64
import fnmatch
import os
from dataclasses import dataclass, field
from pathlib import Path

from .. import registry as reg
from .. import state
from .. import style as st
from ..data import Dataset, load_dataset, read_header
from ..pipeline import METRIC
from ..plots import PLOT_TYPES, load_plugins
from ..render import render
from ..spec import Aggregation, DatasetRef, Filter, Mapping, PlotSpec

PROJECT = state.ROOT.parent                # .../Data
EXTRA_ROOTS = [PROJECT.parent / "Code/Processing/Parameter_Sweep/results/Parameter_Results"]
SKIP_DIRS = ["*_Old", ".venv", ".git", "__pycache__", ".state", "Plotter", "cache", "cropped",
             "eval_runs"]


# ------------------------------------------------------------- discovery --
def _skip_dir(path: Path) -> bool:
    if any(fnmatch.fnmatch(path.name, p) for p in SKIP_DIRS):
        return True
    # per-trial raw folders: <X>_Analysis/Data/... (aggregated CSVs live in Plots/)
    return path.name == "Data" and path.parent.name.endswith("_Analysis")


def find_candidates(roots: list[Path] | None = None, limit: int = 300) -> list[dict]:
    """CSV files under the project (skipping *_Old and raw trial folders) with their family."""
    roots = roots or [PROJECT, *[r for r in EXTRA_ROOTS if r.exists()]]
    out, seen = [], set()
    for root in roots:
        for dirpath, dirnames, filenames in os.walk(root):
            d = Path(dirpath)
            dirnames[:] = sorted(n for n in dirnames if not _skip_dir(d / n))
            for f in sorted(filenames):
                if not f.lower().endswith(".csv"):
                    continue
                p = (d / f).resolve()
                if p in seen:
                    continue
                seen.add(p)
                try:
                    fam = reg.detect_family(read_header(p))
                except Exception:   # unreadable / empty CSV
                    continue
                newer = superseded_by(p)
                out.append({"path": str(p), "family": fam.key, "title": fam.title,
                            "rel": _rel(p),
                            "note": f"older: newer copy in {newer}" if newer else "",
                            "suggest": fam.key != "generic" and not newer})
                if len(out) >= limit:
                    return out
    return out


def superseded_by(p: Path) -> str | None:
    """Name of a sibling version folder (V2, V3, ...) holding the same file, if any.

    e.g. Filter_Results/results.csv is superseded by Filter_Results/V3/results.csv,
    and Filter_Results/plots/ranking_1.csv by Filter_Results/V3/plots/ranking_1.csv.
    """
    for up in range(0, 3):
        base = p.parents[up]
        rel = p.relative_to(base)
        versions = sorted((d for d in base.glob("V[0-9]*") if d.is_dir() and d not in p.parents),
                          key=lambda d: d.name)
        for d in reversed(versions):
            if (d / rel).exists():
                return d.name
    return None


def _rel(p: Path) -> str:
    for base in (PROJECT.parent,):
        try:
            return str(p.relative_to(base))
        except ValueError:
            pass
    return str(p)


def dataset_name(path: str) -> str:
    p = Path(path)
    return f"{p.parent.parent.name}/{p.parent.name}/{p.name}"


# --------------------------------------------------------------- defaults --
def default_spec(ds: Dataset, family_key: str | None = None, keep: PlotSpec | None = None
                 ) -> PlotSpec:
    """Starting spec for a dataset: family defaults, validated against its columns.

    Style and export settings of `keep` (the previous figure) are carried over so
    switching dataset does not lose the look of the figure.
    """
    load_plugins()
    d = dict(ds.family.defaults or {})
    cols = set(ds.profile) | set(ds.stats)
    metrics = ds.metrics()
    factors = ds.factors()
    ok = lambda c: c if c and c in cols else None
    y = [m for m in d.get("y", []) if m in cols] or metrics[:1]
    ptype = d.get("plot_type", "line")
    x = ok(d.get("x")) or next((f for f in factors if ds.profile[f].kind == "numeric"),
                               factors[0] if factors else None)
    if PLOT_TYPES[ptype].x == "none":
        x = None
    spec = PlotSpec(
        plot_type=ptype,
        dataset=DatasetRef(path=str(ds.path), family=family_key or ds.family.key),
        mapping=Mapping(x=x, y=y, hue=ok(d.get("hue")), facet=ok(d.get("facet")),
                        row=ok(d.get("row"))),
        aggregation=Aggregation(func=d.get("aggregation", PLOT_TYPES[ptype].default_agg),
                                spread=d.get("spread", PLOT_TYPES[ptype].default_spread)))
    if keep is not None:
        spec.style = keep.copy().style
        spec.style.labels, spec.style.value_labels, spec.style.colors = {}, {}, {}
        spec.style.xlim = spec.style.ylim = None
        spec.style.xlabel = spec.style.ylabel = None
        spec.export = keep.copy().export
    return spec


def column_label(ds: Dataset, col: str) -> str:
    """'Accuracy RMSE (mm) · acc_rmse_mm' for dropdowns."""
    if col == METRIC:
        return "Metric"
    lab = reg.axis_label(col)
    p = ds.profile.get(col)
    extra = f" · {p.n_unique} values" if p is not None and p.discrete and p.kind != "numeric" \
        else ""
    return f"{lab} · {col}{extra}" if lab.lower().replace(" ", "_") != col else f"{lab}{extra}"


def options(ds: Dataset, cols: list[str], none: bool = True) -> dict:
    out = {None: "(none)"} if none else {}
    out.update({c: column_label(ds, c) for c in cols})
    return out


def metric_options(ds: Dataset, include_sparse: bool = False) -> dict:
    ms = ds.metrics(include_sparse)
    npin = reg.n_pinned(ms, ds.family)
    return {m: ("★ " if i < npin else "") + column_label(ds, m) for i, m in enumerate(ms)}


def filter_columns(ds: Dataset) -> dict:
    cols = [c for c, p in ds.profile.items() if p.kind != "empty" and
            (p.values is not None or p.kind == "numeric")]
    order = ds.factors() + [c for c in cols if c not in ds.factors()]
    return {c: column_label(ds, c) for c in order if c in cols}


def new_filter(ds: Dataset, col: str) -> Filter:
    """A filter that initially keeps everything (so adding it changes nothing)."""
    p = ds.profile[col]
    keep_nan = p.non_null < 1     # rows without a value stay until you untick it
    if p.kind == "numeric" and (p.values is None or p.n_unique > 30):
        return Filter(col, kind="range", lo=p.vmin, hi=p.vmax, keep_nan=keep_nan)
    return Filter(col, kind="in", values=list(p.values or []), keep_nan=keep_nan)


def fix_to_one(ds: Dataset, spec: PlotSpec, col: str) -> None:
    """Quick fix for an unfixed factor: filter it to its first value."""
    vals = ds.profile[col].values or []
    spec.filters = [f for f in spec.filters if f.column != col]
    if vals:
        spec.filters.append(Filter(col, kind="in", values=[vals[0]]))


# --------------------------------------------------------------- variants --
VARIANT_SHORT = {"untrimmed": "Untrimmed", "trim1": "Trim 1 %", "trim5": "Trim 5 %"}
VARIANT_LABELS = {"untrimmed": "Untrimmed", "trim1": "Worst 1 % trimmed",
                  "trim5": "Worst 5 % trimmed"}


def variants(ds: Dataset) -> dict:
    cols = list(ds.profile) + list(ds.stats)
    return reg.variant_groups(cols)


def set_variants(spec: PlotSpec, members: dict, chosen: list[str]) -> None:
    """Replace the group's metrics in spec.mapping.y by the chosen variants, keeping
    their position (first group member's slot) and any other metrics."""
    group_cols = set(members.values())
    y = spec.mapping.y
    pos = next((i for i, m in enumerate(y) if m in group_cols), len(y))
    rest = [m for m in y if m not in group_cols]
    new = [members[k] for k in members if k in chosen]
    spec.mapping.y = rest[:pos] + new + rest[pos:]


# ---------------------------------------------------------------- preview --
@dataclass
class Preview:
    png_b64: str = ""
    width_cm: float = 0
    height_cm: float = 0
    warnings: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    footnote: str = ""
    n_total: int = 0
    n_filtered: int = 0
    n_nan: int = 0
    n_nan_x: int = 0
    x_label: str = ""
    error: str = ""
    latex_width: str = ""


def preview(spec: PlotSpec, ds: Dataset, dpi: float) -> Preview:
    """Render to PNG (runs in a worker thread)."""
    try:
        res = render(spec, ds=ds)
        png = res.png_bytes(dpi=dpi)
        pre = res.pre
        return Preview(base64.b64encode(png).decode(), res.width_cm, res.height_cm,
                       res.warnings, pre.notes if pre else [], res.footnote,
                       pre.n_total if pre else 0, pre.n_filtered if pre else 0,
                       pre.n_nan if pre else 0, n_nan_x=pre.n_nan_x if pre else 0,
                       x_label=reg.axis_label(spec.mapping.x).split(" (")[0]
                       if spec.mapping.x else "", latex_width=res.latex_width)
    except Exception as e:   # shown in the preview pane instead of crashing the UI
        import traceback
        traceback.print_exc()
        return Preview(error=f"{type(e).__name__}: {e}")


def load_registered(entry: dict) -> Dataset:
    return load_dataset(entry["path"], entry.get("family"))


def tex_available() -> tuple[bool, str]:
    return st.tex_status()
