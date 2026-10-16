"""Dataset-family and label registry (backed by families.yaml / labels.yaml)."""
from __future__ import annotations

import fnmatch
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
STATS_RE = re.compile(r"^(?P<base>.+)_(?P<stat>mean|std|median|p25|p75)$")


@dataclass
class Family:
    key: str
    title: str
    priority: int = 0
    detect: dict = field(default_factory=dict)
    unit_name: str = "rows"
    factors: list = field(default_factory=list)
    replicates: list = field(default_factory=list)
    ids: list = field(default_factory=list)
    ignore: list = field(default_factory=list)
    metrics_pinned: list = field(default_factory=list)
    defaults: dict = field(default_factory=dict)
    time_column: str | None = None
    series_unit: str | None = None
    rank_item: str | None = None
    n_column: str | None = None
    n_column_unit: str | None = None
    stats_suffixes: dict | None = None
    composites: list = field(default_factory=list)   # factors that are combinations of others
    baseline: dict | None = None    # {column, value}: reference rows (e.g. no filters applied)
    derived: dict | None = None     # new columns computed at load time (see families.yaml)

    def matches(self, columns: list[str]) -> bool:
        cols = set(columns)
        d = self.detect or {}
        if not set(d.get("all", [])) <= cols:
            return False
        if d.get("any") and not cols & set(d["any"]):
            return False
        if cols & set(d.get("none", [])):
            return False
        if d.get("suffix_stats"):
            bases = {}
            for c in columns:
                m = STATS_RE.match(c)
                if m:
                    bases.setdefault(m["base"], set()).add(m["stat"])
            if sum(1 for s in bases.values() if {"mean", "std"} <= s) < 3:
                return False
        return True

    def is_ignored(self, column: str) -> bool:
        return any(fnmatch.fnmatchcase(column, p) for p in self.ignore)


@lru_cache(maxsize=1)
def _families_yaml() -> dict:
    return yaml.safe_load((HERE / "families.yaml").read_text())["families"]


@lru_cache(maxsize=1)
def labels_yaml() -> dict:
    return yaml.safe_load((HERE / "labels.yaml").read_text())


def families() -> dict[str, Family]:
    return {k: Family(key=k, **v) for k, v in _families_yaml().items()}


def family(key: str) -> Family:
    fams = families()
    return fams.get(key, fams["generic"])


def detect_family(columns: list[str]) -> Family:
    """Best-matching family for a column list (column names only, never filenames)."""
    cands = [f for f in families().values() if f.matches(columns)]
    cands.sort(key=lambda f: (f.priority, len(f.detect.get("all", []))), reverse=True)
    return cands[0] if cands else family("generic")


# ----------------------------------------------------------------- labels --
_UNIT_SUFFIXES = [
    ("_mm", "mm"), ("_deg", "°"), ("_pct", "%"), ("_px", "px"), ("_s", "s"),
    ("_ms", "ms"), ("_m", "m"), ("_cm2", "cm²"), ("_mb", "MB"),
]


def column_info(col: str) -> dict:
    """{label, unit, better, fraction} for a column (registry, pattern or automatic)."""
    reg = labels_yaml()
    if col in reg.get("columns", {}):
        return dict(reg["columns"][col])
    for p in reg.get("patterns", []):
        m = re.match(p["match"], col)
        if m:
            info = {k: v for k, v in p.items() if k != "match"}
            label = info["label"]
            for i, g in enumerate(m.groups(), 1):
                label = label.replace("{%d}" % i, g)
            info["label"] = label
            return info
    # Wide-summary column such as fill_pct_mean -> base label + statistic
    m = STATS_RE.match(col)
    if m and m["base"] in reg.get("columns", {}):
        info = dict(reg["columns"][m["base"]])
        info["label"] = f'{info["label"]} ({m["stat"]})'
        return info
    name, unit = col, None
    for suf, u in _UNIT_SUFFIXES:
        if name.endswith(suf) and len(name) > len(suf):
            name, unit = name[: -len(suf)], u
            break
    text = name.replace("_", " ").strip()
    text = text[:1].upper() + text[1:]
    return {"label": text, "unit": unit} if unit else {"label": text}


def axis_label(col: str | None, overrides: dict | None = None, percent: bool = False) -> str:
    """'Label (unit)', honouring per-figure overrides keyed by column name."""
    if col is None:
        return ""
    if overrides and overrides.get(col):
        return overrides[col]
    info = column_info(col)
    unit = info.get("unit")
    if percent and info.get("fraction"):
        unit = "%"
    return f'{info["label"]} ({unit})' if unit else info["label"]


def value_label(value, overrides: dict | None = None, prettify: bool = True) -> str:
    """Display text for a category value."""
    key = _value_key(value)
    if overrides and key in overrides:
        return overrides[key]
    vals = labels_yaml().get("values", {})
    if key in vals:
        return vals[key]
    if isinstance(value, bool):
        return "On" if value else "Off"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    if prettify and re.fullmatch(r"\d+x\d+(@\d+)?", key):
        return key.replace("x", " × ", 1).replace("@", " @ ")
    return key.replace("_", " ") if prettify else key


def _value_key(value) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def better_direction(col: str) -> str:
    return column_info(col).get("better", "lower")


def is_fraction(col: str) -> bool:
    return bool(column_info(col).get("fraction"))


def pinned_order(metrics: list[str], fam: Family) -> list[str]:
    """Global pins first (in registry order), then family pins, then the rest (A-Z)."""
    pins = labels_yaml().get("pinned_metrics", []) + list(fam.metrics_pinned)
    out: list[str] = []
    for pat in pins:
        for m in metrics:
            if m not in out and fnmatch.fnmatchcase(m, pat):
                out.append(m)
    return out + sorted((m for m in metrics if m not in out), key=str.lower)


def n_pinned(metrics: list[str], fam: Family) -> int:
    pins = labels_yaml().get("pinned_metrics", []) + list(fam.metrics_pinned)
    return sum(1 for m in metrics if any(fnmatch.fnmatchcase(m, p) for p in pins))


def variant_groups(columns: list[str]) -> dict[str, dict]:
    """Variant groups (e.g. RMSE untrimmed/trim1/trim5) available in these columns."""
    out = {}
    for key, g in labels_yaml().get("variant_groups", {}).items():
        members = {k: v for k, v in g["members"].items() if v in columns}
        if len(members) >= 2:
            out[key] = {"title": g["title"], "members": members}
    return out
