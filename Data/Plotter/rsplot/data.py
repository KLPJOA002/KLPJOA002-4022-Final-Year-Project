"""Dataset loading, type normalisation and column profiling."""
from __future__ import annotations

import threading
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from . import registry as reg

MAX_CATEGORIES = 60        # string columns with more unique values are treated as text/ids
SPARSE_FRACTION = 0.05     # columns with < 5 % non-null values are "mostly empty"
_BOOL_STRINGS = {"true": True, "false": False}


@dataclass
class ColumnProfile:
    name: str
    kind: str                  # numeric | boolean | categorical | text | empty
    role: str                  # metric | factor | replicate | id | text
    n_unique: int
    non_null: float            # fraction 0..1
    values: list | None = None # sorted unique values when n_unique is small
    vmin: float | None = None
    vmax: float | None = None

    @property
    def constant(self) -> bool:
        return self.n_unique <= 1

    @property
    def sparse(self) -> bool:
        return self.non_null < SPARSE_FRACTION

    @property
    def discrete(self) -> bool:
        """Usable as a grouping column (hue / facet / filter multiselect)."""
        return self.kind in ("boolean", "categorical") or (
            self.kind == "numeric" and self.n_unique <= MAX_CATEGORIES)


@dataclass
class Dataset:
    path: Path
    family: reg.Family
    columns: list[str]                       # every column in the file header
    loaded: list[str]                        # columns actually loaded (ignored ones pruned)
    profile: dict[str, ColumnProfile]
    n_rows: int
    stats: dict[str, dict[str, str]] = field(default_factory=dict)  # wide summary: base -> {stat: col}
    df: pd.DataFrame | None = field(default=None, repr=False)

    # ------------------------------------------------------------ columns --
    def metrics(self, include_sparse: bool = False) -> list[str]:
        """Numeric columns usable as y, pinned ones first. Summary files list base names."""
        stat_cols = {c for d in self.stats.values() for c in d.values()}
        out = list(self.stats)
        for c, p in self.profile.items():
            if c in stat_cols or p.kind != "numeric" or p.role in ("id", "replicate"):
                continue
            if p.sparse and not include_sparse:
                continue
            out.append(c)
        return reg.pinned_order(out, self.family)

    def factors(self) -> list[str]:
        """Discrete columns sensible for hue / facet / style, declared factors first."""
        declared = [c for c in self.family.factors if c in self.profile]
        auto = [c for c, p in self.profile.items()
                if c not in declared and p.role == "factor" and not p.constant]
        return declared + auto

    def x_candidates(self) -> list[str]:
        f = self.factors()
        rest = [c for c in self.metrics() if c not in f]
        extra = [c for c, p in self.profile.items()
                 if c not in f and c not in rest and p.role in ("replicate", "id")
                 and p.kind != "text"]
        return f + rest + extra

    def experimental_factors(self) -> list[str]:
        """Factors whose variation must be accounted for (not replicates).

        Families that declare factors are checked against those only; generic
        files fall back to every auto-detected discrete column.
        """
        cols = [c for c in self.family.factors if c in self.profile] or self.factors()
        return [c for c in cols
                if self.profile[c].role == "factor" and not self.profile[c].sparse]

    def replicate_columns(self) -> list[str]:
        return [c for c in self.family.replicates if c in self.profile]

    def is_summary(self) -> bool:
        return bool(self.stats)

    def value_column(self, metric: str, stat: str = "mean") -> str:
        """Actual column holding `metric` (for summaries: base_<stat>)."""
        if metric in self.stats:
            d = self.stats[metric]
            return d.get(stat) or d.get("mean") or next(iter(d.values()))
        return metric

    def frame(self) -> pd.DataFrame:
        assert self.df is not None
        return self.df


# ------------------------------------------------------------------ cache --
_CACHE: "OrderedDict[tuple, Dataset]" = OrderedDict()
_LOCK = threading.Lock()
_CACHE_SIZE = 6


def read_header(path: str | Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


def sniff(path: str | Path) -> reg.Family:
    """Detected family for a file, from its header only."""
    return reg.detect_family(read_header(path))


def load_dataset(path: str | Path, family_key: str | None = None,
                 include_ignored: bool = False) -> Dataset:
    """Load (cached on path + mtime + size + family) and profile a CSV file."""
    path = Path(path).expanduser().resolve()
    st = path.stat()
    key = (str(path), st.st_mtime_ns, st.st_size, family_key, include_ignored)
    with _LOCK:
        if key in _CACHE:
            _CACHE.move_to_end(key)
            return _CACHE[key]
    columns = read_header(path)
    fam = reg.family(family_key) if family_key else reg.detect_family(columns)
    usecols = columns if include_ignored else [c for c in columns if not fam.is_ignored(c)]
    df = pd.read_csv(path, usecols=usecols, low_memory=False)
    df = add_derived(normalise_types(df), fam)
    ds = Dataset(path=path, family=fam, columns=columns, loaded=list(df.columns),
                 profile=profile_columns(df, fam), n_rows=len(df),
                 stats=_stats_columns(list(df.columns)) if fam.stats_suffixes else {},
                 df=df)
    with _LOCK:
        _CACHE[key] = ds
        while len(_CACHE) > _CACHE_SIZE:
            _CACHE.popitem(last=False)
    return ds


def dataset_from_frame(df: pd.DataFrame, family_key: str | None = None,
                       name: str = "<memory>") -> Dataset:
    """Wrap an in-memory DataFrame (used by tests)."""
    fam = reg.family(family_key) if family_key else reg.detect_family(list(df.columns))
    df = add_derived(normalise_types(df.copy()), fam)
    return Dataset(path=Path(name), family=fam, columns=list(df.columns),
                   loaded=list(df.columns), profile=profile_columns(df, fam),
                   n_rows=len(df),
                   stats=_stats_columns(list(df.columns)) if fam.stats_suffixes else {},
                   df=df)


# ----------------------------------------------------------- normalising --
def normalise_types(df: pd.DataFrame) -> pd.DataFrame:
    """Turn 'True'/'False' text or object columns into nullable booleans."""
    for c in df.columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s) or pd.api.types.is_numeric_dtype(s):
            continue
        nonnull = s.dropna()
        if nonnull.empty:
            continue
        vals = set(nonnull.astype(str).str.strip().str.lower().unique())
        if vals <= set(_BOOL_STRINGS):
            df[c] = s.map(lambda v: _BOOL_STRINGS.get(str(v).strip().lower())
                          if pd.notna(v) else pd.NA).astype("boolean")
    return df


def add_derived(df: pd.DataFrame, fam: reg.Family) -> pd.DataFrame:
    """Add the family's derived columns, e.g. tilt_deg = number(tilts) where n_tilts == 1.

    Spec per column: {from: <source>, parse: number, when: {<column>: <value>, ...}}.
    Rows not matching `when` get no value. Missing source columns are skipped.
    """
    for name, d in (fam.derived or {}).items():
        src = d.get("from")
        if src not in df.columns or name in df.columns:
            continue
        values = df[src]
        if d.get("parse") == "number":
            values = pd.to_numeric(values, errors="coerce")
        keep = pd.Series(True, index=df.index)
        for col, want in (d.get("when") or {}).items():
            if col not in df.columns:
                keep &= False
                continue
            keep &= df[col].map(lambda v: pd.notna(v) and reg._value_key(
                v.item() if hasattr(v, "item") else v) == reg._value_key(want))
        df[name] = values.where(keep)
    return df


def _stats_columns(columns: list[str]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for c in columns:
        m = reg.STATS_RE.match(c)
        if m:
            out.setdefault(m["base"], {})[m["stat"]] = c
    return {b: d for b, d in out.items() if "mean" in d or "median" in d}


def profile_columns(df: pd.DataFrame, fam: reg.Family) -> dict[str, ColumnProfile]:
    out = {}
    declared_factors = set(fam.factors)
    for c in df.columns:
        s = df[c]
        nn = float(s.notna().mean()) if len(s) else 0.0
        nu = int(s.nunique(dropna=True))
        if nn == 0:
            kind = "empty"
        elif pd.api.types.is_bool_dtype(s):
            kind = "boolean"
        elif pd.api.types.is_numeric_dtype(s):
            kind = "numeric"
        elif nu <= MAX_CATEGORIES:
            kind = "categorical"
        else:
            kind = "text"

        if c in fam.ids:
            role = "id"
        elif c in fam.replicates:
            role = "replicate"
        elif c in declared_factors:
            role = "factor"
        elif kind in ("boolean", "categorical"):
            role = "factor"
        elif kind == "numeric":
            # Generic files: small integer-valued sets look like factors.
            ints = np.allclose(s.dropna() % 1, 0) if nu else False
            role = "factor" if (fam.key == "generic" and nu <= 12 and ints) else "metric"
        else:
            role = "text"

        values = None
        vmin = vmax = None
        if kind == "numeric" and nn > 0:
            vmin, vmax = float(np.nanmin(s)), float(np.nanmax(s))
        if (kind in ("boolean", "categorical")
                or (kind == "numeric" and nu <= MAX_CATEGORIES)
                or (kind == "text" and role == "factor" and nu <= 5000)):
            values = sort_values(s.dropna().unique().tolist())
        out[c] = ColumnProfile(c, kind, role, nu, nn, values, vmin, vmax)
    return out


def sort_values(values: list) -> list:
    """Natural sort: numbers numerically, strings with embedded numbers sensibly."""
    import re

    def key(v):
        if isinstance(v, (bool, np.bool_)):
            return (0, float(v), "")
        if isinstance(v, (int, float, np.number)):
            return (0, float(v), "")
        s = str(v)
        m = re.match(r"^\s*(-?\d+(?:\.\d+)?)", s)
        return (1, float(m.group(1)) if m else float("inf"), s.lower())

    try:
        return sorted(values, key=key)
    except TypeError:
        return sorted(values, key=str)
