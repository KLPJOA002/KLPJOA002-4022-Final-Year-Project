"""Headless tests: numbers equal rsplot's pipeline, layouts, formats, saving, LaTeX."""
import glob
import itertools
import json
import os
import shutil
import tempfile

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("RSTABLE_STATE_DIR", tempfile.mkdtemp(prefix="rstable_state_"))
os.environ.setdefault("RSPLOT_STATE_DIR", tempfile.mkdtemp(prefix="rsplot_state_"))

from rsplot.data import dataset_from_frame  # noqa: E402
from rsplot.pipeline import METRIC  # noqa: E402
from rsplot.spec import Aggregation, Filter, Mapping, PlotSpec  # noqa: E402

from rstable import store  # noqa: E402
from rstable.render import cell_parts, colspec, to_frame, to_html, to_latex, wrap_label  # noqa: E402
from rstable.spec import TableSpec, Source  # noqa: E402
from rstable.table import build  # noqa: E402

RNG = np.random.default_rng(1)
FIGS = "/home/joab/Documents/4022/Report/uct-thesis-template/figs"


def _sweep():
    rows = []
    for dec, shape, h, rot in itertools.product([1, 2, 4], ["Big_Wave", "Small_Wave"],
                                                [641, 701], [0, 90, 180, 270]):
        rmse = 2 + 0.1 * dec + (0.4 if shape == "Small_Wave" else 0) + RNG.normal(0, 0.1)
        rows.append(dict(config_id=f"c{dec}", config_label=f"dec{dec}", scan_id=f"A{rot}",
                         scan_key=f"{shape}_{h}_{rot}", status="ok", shape=shape, height_mm=h,
                         rotation_label=rot, tilt_deg=0, decimation_on=dec > 1,
                         decimation_magnitude=dec, spatial_on=False, temporal_on=False,
                         hole_filling_on=False, hdr_merge_on=False, acc_rmse_mm=rmse,
                         acc_rmse_trim1_mm=rmse - .2, acc_rmse_trim5_mm=rmse - .4,
                         signed_bias_mm=RNG.normal(-0.05, 0.1), outlier_fraction=0.01,
                         **{"completeness@2mm": 0.6 + RNG.random() * 0.1,
                            "fscore@2mm": 0.7 + RNG.random() * 0.1}, covered_fraction=0.95))
    return pd.DataFrame(rows)


def _summary():
    rows = []
    for i, h in enumerate([604, 628, 667, 723]):
        r = dict(trial_name=f"T{i}", session=f"S{i}", trial=0, gt_axis_mm=h,
                 condition="lights", n_frames=500 + i)
        for m in ("z_err_median_mm", "plane_rms_mm", "fill_pct", "std_z_mm"):
            base = h / 500
            r.update({f"{m}_mean": base, f"{m}_std": 0.1, f"{m}_median": base,
                      f"{m}_p25": base - 0.1, f"{m}_p75": base + 0.15})
        rows.append(r)
    return pd.DataFrame(rows)


@pytest.fixture(scope="module")
def sweep():
    return dataset_from_frame(_sweep())


def _ts(spec: PlotSpec, **fmt) -> TableSpec:
    ts = TableSpec(source=Source(plot=spec.to_dict()))
    ts.output.filename = "t"
    for k, v in fmt.items():
        setattr(ts.format, k, v)
    return ts


def _spec(**agg):
    return PlotSpec(plot_type="line",
                    mapping=Mapping(x="height_mm", y=["acc_rmse_mm", "signed_bias_mm"],
                                    hue="decimation_magnitude", facet="shape"),
                    aggregation=Aggregation(func=agg.get("func", "median"),
                                            spread=agg.get("spread", "iqr")))


def test_values_are_the_plotted_ones(sweep):
    ts = _ts(_spec())
    t = build(ts, ds=sweep)
    df = sweep.frame()
    g = df[(df["shape"] == "Big_Wave") & (df.height_mm == 641) & (df.decimation_magnitude == 2)]
    r = t.rows.index(("Big_Wave", 641, 2))
    c = t.cols.index(("acc_rmse_mm",))
    cell = t.cells[(r, c)]
    assert cell.value == pytest.approx(g.acc_rmse_mm.median())
    assert cell.lo == pytest.approx(g.acc_rmse_mm.quantile(.25))
    assert cell.hi == pytest.approx(g.acc_rmse_mm.quantile(.75))
    assert cell.n == 4
    assert t.stat.short() == "median [Q1, Q3]"
    assert t.n_text == "n = 4 scans"


def test_default_layout_and_latex_structure(sweep):
    ts = _ts(_spec())
    t = build(ts, ds=sweep)
    assert ts.layout.col_keys == [METRIC]
    assert ts.layout.row_keys == ["shape", "height_mm", "decimation_magnitude"]
    tex = to_latex(t, ts)
    assert r"\begin{tabular}{l r r c c}" in tex
    assert r"\toprule" in tex and r"\bottomrule" in tex and r"\addlinespace" in tex
    assert r"\makecell{Accuracy\\RMSE (mm)\\{\footnotesize median [Q1, Q3]}}" in tex
    assert "$-$" in tex                                   # negative bias with a real minus
    assert len(t.rows) == 12


def test_columns_two_levels(sweep):
    ts = _ts(_spec())
    ts.layout.row_keys = ["height_mm", "decimation_magnitude"]
    ts.layout.col_keys = ["shape", METRIC]
    t = build(ts, ds=sweep)
    tex = to_latex(t, ts)
    assert r"\multicolumn{2}{c}{Big wave}" in tex
    assert r"\cmidrule(lr){3-4}" in tex and r"\cmidrule(lr){5-6}" in tex
    assert len(t.rows) == 6 and len(t.cols) == 4
    html = to_html(t, ts)
    assert 'colspan="2"' in html


def test_metric_down_rows(sweep):
    ts = _ts(_spec())
    ts.layout.row_keys = [METRIC, "height_mm"]
    ts.layout.col_keys = ["shape", "decimation_magnitude"]
    t = build(ts, ds=sweep)
    tex = to_latex(t, ts)
    assert "Accuracy RMSE (mm)" in tex
    assert r"\makecell{Metric\\{\footnotesize median [Q1, Q3]}}" in tex


@pytest.mark.parametrize("fmt,spread,expect", [
    ("auto", "iqr", r"\[\d\.\d\d, \d\.\d\d\]"),
    ("parens", "iqr", r"\(\d\.\d\d–\d\.\d\d\)"),
    ("pm", "iqr", r"± \d\.\d\d"),
    ("width", "iqr", r"\(\d\.\d\d\)"),
    ("auto", "std", r"± \d\.\d\d"),
    ("none", "std", r"^\d\.\d\d$"),
])
def test_spread_formats(sweep, fmt, spread, expect):
    import re
    from rstable.render import HtmlOut
    ts = _ts(_spec(func="mean" if spread == "std" else "median", spread=spread),
             spread_format=fmt)
    t = build(ts, ds=sweep)
    cell = next(c for c in t.cells.values() if c.metric == "acc_rmse_mm")
    centre, sp = cell_parts(cell, t, ts, HtmlOut())
    assert re.search(expect, f"{centre} {sp}".strip()), (centre, sp)


def test_separate_spread_column(sweep):
    ts = _ts(_spec(func="mean", spread="std"), spread_format="column")
    t = build(ts, ds=sweep)
    tex = to_latex(t, ts)
    assert r"\multicolumn{2}{c}" in tex and "& SD" in tex


def test_override_statistic(sweep):
    ts = _ts(_spec())
    ts.stats.inherit = False
    ts.stats.func, ts.stats.spread = "mean", "sem"
    t = build(ts, ds=sweep)
    assert t.stat.short() == "mean ± SEM" and t.stat.source == "override"
    assert t.figure_stat == "median with IQR"


def test_percent_and_decimals(sweep):
    spec = _spec()
    spec.mapping.y = ["completeness@2mm"]
    ts = _ts(spec)
    t = build(ts, ds=sweep)
    v = next(iter(t.cells.values())).value
    assert 50 < v < 80 and t.decimals["completeness@2mm"] == 1
    assert "(\\%)" in to_latex(t, ts)
    ts.format.decimals = {"completeness@2mm": 3}
    assert build(ts, ds=sweep).decimals["completeness@2mm"] == 3


def test_hidden_values_and_rename(sweep):
    ts = _ts(_spec())
    ts.layout.hidden = {"decimation_magnitude": ["4"]}
    ts.format.value_labels = {"decimation_magnitude=1": "Off"}
    t = build(ts, ds=sweep)
    assert all(r[2] != 4 for r in t.rows)
    assert "& Off &" in to_latex(t, ts)


def test_bold_best(sweep):
    ts = _ts(_spec(), bold_best=True)
    t = build(ts, ds=sweep)
    best = [c for c in t.cells.values() if c.best and c.metric == "acc_rmse_mm"]
    allv = [c.value for c in t.cells.values() if c.metric == "acc_rmse_mm"]
    assert len(best) >= 1 and best[0].value == pytest.approx(min(allv))
    assert r"\textbf{" in to_latex(t, ts)


def test_unaggregated_duplicates_are_numbered(sweep):
    ts = _ts(_spec(func="none", spread="none"))
    t = build(ts, ds=sweep)
    assert "__dup__" in t.row_keys
    assert any("numbered" in w for w in t.warnings)


def test_per_trial_summary():
    ds = dataset_from_frame(_summary())
    spec = PlotSpec(plot_type="scatter", mapping=Mapping(x="gt_axis_mm",
                                                         y=["plane_rms_mm", "fill_pct"]),
                    aggregation=Aggregation(func="none", stored_stat="median",
                                            stored_spread="iqr"))
    ts = _ts(spec)
    t = build(ts, ds=ds)
    assert t.stat.per_trial and t.stat.short() == "per-trial median [Q1, Q3]"
    assert t.n_text == "n = 500–503 frames"
    c = t.cells[(0, 0)]
    assert (c.value, c.lo, c.hi) == pytest.approx((604 / 500, 604 / 500 - .1, 604 / 500 + .15))


def test_caption_and_csv(sweep):
    spec = _spec()
    spec.filters = [Filter("rotation_label", values=[0, 90, 180, 270])]
    ts = _ts(spec, stat_place="both")
    ts.output.caption = "Filter comparison."
    t = build(ts, ds=sweep)
    tex = to_latex(t, ts)
    assert r"\caption{Filter comparison. Values are medians with the interquartile range" in tex
    df = to_frame(t, ts)
    assert {"value", "lo", "hi", "n", "text", "metric"} <= set(df.columns)
    assert len(df) == len(t.cells)


def test_wrap_and_colspec():
    assert wrap_label("Plane-fit RMS (mm)", 14) == ["Plane-fit", "RMS (mm)"]
    assert wrap_label("Fill rate|(%)", 14) == ["Fill rate", "(%)"]
    assert colspec(["r", "c", "c", "c", "c", "c"]) == "r *{5}{c}"


def test_save_conflict_and_reload(sweep, tmp_path, monkeypatch):
    ts = _ts(_spec())
    ts.output.folder = str(tmp_path)
    ts.output.filename = "dist"
    t = build(ts, ds=sweep)
    res = store.save_table(ts, t)
    assert (tmp_path / "dist.tex").exists() and (tmp_path / "dist.csv").exists()
    with pytest.raises(FileExistsError):
        store.save_table(ts, t)
    assert store.next_free_name(tmp_path, "dist") == "dist_2"
    ts2, _ = store.load_table(res.sidecar)
    assert ts2.to_dict() == ts.to_dict()


# ------------------------------------------------ real figures (if present) --
REAL = sorted(glob.glob(f"{FIGS}/**/*.rsplot.json", recursive=True))


@pytest.mark.skipif(not REAL, reason="thesis figures not available")
@pytest.mark.parametrize("path", REAL, ids=lambda p: os.path.basename(p))
def test_real_figures_build(path):
    ts, _ = store.from_sidecar(path)
    t = build(ts)
    assert t.cells
    to_latex(t, ts)
    to_html(t, ts)


@pytest.mark.skipif(not REAL or not store.tex_engine() or not shutil.which("pdftoppm"),
                    reason="needs thesis figures and LaTeX")
@pytest.mark.parametrize("fmt", ["auto", "column"])
def test_real_figures_compile(fmt):
    path = next(p for p in REAL if "Filter_Comparison.rsplot" in p) if any(
        "Filter_Comparison.rsplot" in p for p in REAL) else REAL[0]
    ts, _ = store.from_sidecar(path)
    ts.format.spread_format = fmt
    ts.format.bold_best = True
    t = build(ts)
    if len(t.metrics) > 2:
        ts.layout.metrics = t.metrics[:2]
        t = build(ts)
    res = store.compile_preview(to_latex(t, ts))
    assert not res.error, res.error
    assert res.png[:4] == b"\x89PNG"
