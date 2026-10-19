"""Render every registered plot type headless on each suitable family."""
import pytest

from rsplot.plots import load_plugins
from rsplot.render import render
from rsplot.spec import Aggregation, Mapping, PlotSpec

CASES = {
    "line": [("planar_frames", Mapping(x="gt_axis_mm", y=["z_err_median_mm"], hue="condition"),
              "median", "iqr"),
             ("filter_sweep", Mapping(x="decimation_magnitude",
                                      y=["acc_rmse_mm", "acc_rmse_trim5_mm"],
                                      y_mode="side_by_side", hue="shape"), "mean", "ci95"),
             ("planar_summary", Mapping(x="gt_axis_mm", y=["fill_pct"]), "none", "none")],
    "scatter": [("fusion", Mapping(x="n_scans", y=["acc_rmse_mm"], hue="family", facet="wave"),
                 "none", "none"),
                ("param_scans", Mapping(x="completeness_full@2mm", y=["acc_rmse_mm"],
                                        hue="resolution"), "none", "none"),
                ("filter_sweep", Mapping(x="fscore@2mm", y=["acc_rmse_trim5_mm"],
                                         hue="spatial_on", by=["config_label"]), "mean", "std")],
    "bar": [("param_scans", Mapping(x="preset", y=["acc_rmse_mm"], hue="resolution",
                                    facet="object_label"), "mean", "minmax"),
            ("filter_ranking", Mapping(x="config_label", y=["mean_acc_rmse_mm"]), "none", "none"),
            ("fusion", Mapping(x="family", y=["acc_rmse_mm", "acc_rmse_trim5_mm"]), "mean",
             "std")],
    "box": [("filter_sweep", Mapping(x="decimation_magnitude", y=["acc_rmse_trim5_mm"],
                                     hue="shape"), "none", "none"),
            ("planar_frames", Mapping(x="gt_axis_mm", y=["plane_rms_mm"]), "none", "none"),
            ("fusion", Mapping(y=["acc_rmse_mm"], hue="wave"), "none", "none")],
    "hist": [("filter_sweep", Mapping(y=["acc_rmse_mm", "acc_rmse_trim5_mm"], facet="shape"),
              "none", "none"),
             ("planar_frames", Mapping(y=["z_err_median_mm"], hue="condition"), "none", "none")],
    "timeseries": [("planar_frames", Mapping(x="t_s", y=["z_err_median_mm"], hue="condition"),
                    "none", "none")],
    "heatmap": [("param_scans", Mapping(x="preset", row="resolution", y=["acc_rmse_mm"],
                                        facet="object_label"), "mean", "none"),
                ("filter_sweep", Mapping(x="decimation_magnitude", row="height_mm",
                                         y=["acc_rmse_mm", "acc_rmse_trim5_mm"],
                                         y_mode="side_by_side"), "median", "none")],
    "ranking": [("filter_sweep", Mapping(x="config_label", y=["acc_rmse_trim5_mm"],
                                         hue="spatial_on"), "mean", "ci95"),
                ("filter_ranking", Mapping(x="config_label", y=["mean_acc_rmse_mm"]), "none",
                 "none"),
                ("fusion", Mapping(x="combo_id", y=["acc_rmse_mm"], facet="wave"), "mean",
                 "std")],
}

TRENDS = ["linear", "quadratic", "cubic", "exponential", "logarithmic", "power",
          "smooth (LOWESS)", "moving median"]
OPTION_VARIANTS = [*[("scatter", {"trend": k}) for k in TRENDS],
                   *[("line", {"trend": k, "trend_label": "equation + R²"}) for k in TRENDS],
                   ("scatter", {"trend": "quadratic", "trend_band": True, "trend_scope": "all data",
                                "trend_label": "R²"}),
                   ("line", {"trend": "linear", "trend_data": "all rows", "trend_extend": True}),("bar", {"orientation": "horizontal", "value_labels": True}),
                   ("box", {"kind": "violin", "strip": True}), ("box", {"kind": "both"}),
                   ("hist", {"kind": "cdf"}), ("hist", {"histtype": "bars", "density": True}),
                   ("timeseries", {"window": 5}), ("line", {"spread_display": "band"}),
                   ("line", {"capsize": 0, "dodge": 0.2}),
                   ("heatmap", {"centre": "median", "show_as": "difference", "show_n": True}),
                   ("heatmap", {"centre": "value", "centre_value": 2.0, "cmap": "RdBu_r"}),
                   ("ranking", {"mark": "bars", "show_bar_n": True, "top_n": 3}),
                   ("ranking", {"mark": "dots", "order": "highest first"})]


def _cases():
    load_plugins()
    for ptype, cases in CASES.items():
        for fam, mapping, func, spread in cases:
            yield pytest.param(ptype, fam, mapping, func, spread, id=f"{ptype}-{fam}")


@pytest.mark.parametrize("ptype,family,mapping,func,spread", list(_cases()))
@pytest.mark.parametrize("preset", ["thesis_caption", "slide_16_9"])
def test_render(datasets, ptype, family, mapping, func, spread, preset, tmp_path):
    spec = PlotSpec(plot_type=ptype, mapping=mapping,
                    aggregation=Aggregation(func=func, spread=spread))
    spec.export.size_preset = preset
    if preset.startswith("slide"):
        spec.style.preset = "slides"
    res = render(spec, ds=datasets[family])
    assert res.fig.axes
    res.savefig(tmp_path / "out.pdf")
    res.savefig(tmp_path / "out.png", dpi=72)
    assert (tmp_path / "out.pdf").stat().st_size > 1000


def test_every_plot_type_has_a_case():
    assert set(load_plugins()) <= set(CASES), "add a test case for each new plot type"


@pytest.mark.parametrize("ptype,options", OPTION_VARIANTS)
def test_option_variants(datasets, ptype, options):
    family, mapping, func, spread = CASES[ptype][0]
    spec = PlotSpec(plot_type=ptype, mapping=mapping,
                    aggregation=Aggregation(func=func, spread=spread), options=options)
    assert render(spec, ds=datasets[family]).fig.axes


def test_secondary_panel(datasets):
    spec = PlotSpec(plot_type="line",
                    mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_mm"], hue="shape",
                                    facet="shape", secondary="outlier_fraction"),
                    aggregation=Aggregation(func="mean", spread="std"))
    res = render(spec, ds=datasets["filter_sweep"])
    assert len([a for a in res.fig.axes if a.axison]) == 4   # 2 facets x (main + panel)
    assert "Lower panel: outlier fraction" in res.footnote


def test_secondary_unsupported_warns(datasets):
    spec = PlotSpec(plot_type="hist", mapping=Mapping(y=["acc_rmse_mm"],
                                                      secondary="outlier_fraction"))
    assert any("no secondary" in w for w in render(spec, ds=datasets["filter_sweep"]).warnings)


def test_box_legend_n_is_per_box(datasets):
    spec = PlotSpec(plot_type="box", mapping=Mapping(x="decimation_magnitude",
                                                     y=["acc_rmse_trim5_mm"], hue="shape"))
    res = render(spec, ds=datasets["filter_sweep"])
    figs = [res.fig, *res.fig.subfigs]
    texts = [t.get_text() for f in figs for leg in f.legends for t in leg.get_texts()]
    assert any("(n = 7–8)" in t or "(n = 8)" in t for t in texts), texts
    assert "per box" in res.footnote


def test_timeseries_one_line_per_trial(datasets):
    spec = PlotSpec(plot_type="timeseries", mapping=Mapping(x="t_s", y=["z_err_median_mm"]))
    res = render(spec, ds=datasets["planar_frames"])
    assert len(res.fig.axes[0].get_lines()) == 6           # 6 trials in the fixture


def _ranked_labels(res):
    ax = res.fig.axes[0]
    return [t.get_text() for t in ax.get_yticklabels()]


def test_heatmap_baseline_centre(datasets):
    # one row per panel: the baseline is computed per panel (here per object)
    spec = PlotSpec(plot_type="heatmap",
                    mapping=Mapping(x="decimation_magnitude", facet="shape", y=["acc_rmse_mm"]),
                    aggregation=Aggregation(func="mean"),
                    options={"centre": "baseline", "baseline_column": "decimation_magnitude",
                             "baseline_value": 1, "show_as": "difference"})
    res = render(spec, ds=datasets["filter_sweep"])
    for ax in [a for a in res.fig.axes if a.texts]:
        first = ax.texts[0].get_text()      # decimation 1 = the baseline itself
        assert first in ("+0.00", "−0.00", "+0.000", "−0.000"), first
    assert "difference from the baseline" in res.footnote


def test_heatmap_missing_baseline_warns(datasets):
    spec = PlotSpec(plot_type="heatmap",
                    mapping=Mapping(x="decimation_magnitude", row="shape", y=["acc_rmse_mm"]),
                    aggregation=Aggregation(func="mean"), options={"centre": "baseline"})
    res = render(spec, ds=datasets["filter_sweep"])   # family baseline label is not in fixture
    assert any("No baseline rows" in w for w in res.warnings)


def test_ranking_order_min_n_and_highlight(datasets):
    ds = datasets["filter_sweep"]
    spec = PlotSpec(plot_type="ranking", mapping=Mapping(x="config_label", y=["acc_rmse_mm"]),
                    aggregation=Aggregation(func="mean", spread="std"),
                    options={"top_n": 2, "highlight": "dec4"})
    labels = _ranked_labels(render(spec, ds=ds))
    means = ds.frame().groupby("config_label")["acc_rmse_mm"].mean().sort_values()
    assert labels[:2] == [means.index[0], means.index[1]]
    assert labels[-1] == "dec4 — reference"
    spec.options = {"order": "highest first", "top_n": 1}
    assert _ranked_labels(render(spec, ds=ds)) == [means.index[-1]]
    spec.options = {"min_n": 1000}
    res = render(spec, ds=ds)
    assert any("were not ranked" in w for w in res.warnings)


def test_ranking_error_column(datasets):
    spec = PlotSpec(plot_type="ranking",
                    mapping=Mapping(x="config_label", y=["mean_acc_rmse_mm"]),
                    options={"error_column": "std_acc_rmse_mm", "top_n": 3})
    res = render(spec, ds=datasets["filter_ranking"])
    assert any(c.__class__.__name__ == "LineCollection" for c in res.fig.axes[0].collections)


def test_unused_roles_do_not_split_groups(datasets):
    """A heatmap 'row' left in the mapping must not change a ranking's groups."""
    spec = PlotSpec(plot_type="ranking",
                    mapping=Mapping(x="config_label", y=["acc_rmse_mm"], row="height_mm"),
                    aggregation=Aggregation(func="mean", spread="std"))
    res = render(spec, ds=datasets["filter_sweep"])
    assert res.pre.data["__n__"].max() == 8     # 2 shapes x 2 heights x 2 rotations


def test_heatmap_baseline_matched_per_row(datasets):
    spec = PlotSpec(plot_type="heatmap",
                    mapping=Mapping(x="decimation_magnitude", row="height_mm", y=["acc_rmse_mm"]),
                    aggregation=Aggregation(func="mean"),
                    options={"centre": "baseline", "baseline_column": "decimation_magnitude",
                             "baseline_value": 1, "show_as": "difference"})
    res = render(spec, ds=datasets["filter_sweep"])
    ax = res.fig.axes[0]
    first_col = [t.get_text() for t in ax.texts if abs(t.get_position()[0]) < 1e-9]
    assert first_col and all(t in ("+0.00", "−0.00", "+0.000", "−0.000") for t in first_col)
    assert "at the same height" in res.footnote


def test_ranking_grows_to_fit_labels(datasets):
    spec = PlotSpec(plot_type="ranking", mapping=Mapping(x="combo_id", y=["acc_rmse_mm"],
                                                         facet="wave"),
                    aggregation=Aggregation(func="mean"), options={"top_n": 9, "min_n": 1})
    auto = render(spec, ds=datasets["fusion"])
    assert auto.height_cm > 10.8
    spec.export.height_cm = 6
    small = render(spec, ds=datasets["fusion"])
    assert small.height_cm == 6 and any("overlap" in w for w in small.warnings)


def test_empty_category_label(datasets):
    spec = PlotSpec(mapping=Mapping(x="tilt_deg", y=["acc_rmse_mm"], hue="rotation_deg"),
                    aggregation=Aggregation(func="median"))
    res = render(spec, ds=datasets["fusion"])
    figs = [res.fig, *res.fig.subfigs]
    texts = [t.get_text() for f in figs for leg in f.legends for t in leg.get_texts()]
    assert any(t.startswith("several (fused set)") for t in texts), texts
    assert not any(t.startswith("nan") for t in texts)


def test_trend_footnote_and_legend(datasets):
    spec = PlotSpec(plot_type="scatter",
                    mapping=Mapping(x="completeness_full@2mm", y=["acc_rmse_mm"],
                                    hue="resolution"),
                    options={"trend": "power", "trend_label": "equation + R²"})
    res = render(spec, ds=datasets["param_scans"])
    assert "Dashed lines: power-law fit" in res.footnote and "R²" in res.footnote
    figs = [res.fig, *res.fig.subfigs]
    texts = [t.get_text() for f in figs for leg in f.legends for t in leg.get_texts()]
    assert any("trend (y = " in t and "R² = " in t for t in texts), texts
    # with panels, each fitted line is labelled on the plot instead of the legend
    spec.mapping.facet = "object_label"
    res = render(spec, ds=datasets["param_scans"])
    texts = [t.get_text() for f in [res.fig, *res.fig.subfigs] for leg in f.legends
             for t in leg.get_texts()]
    assert not any("trend" in t for t in texts)
    notes = [t.get_text() for ax in res.fig.axes for t in ax.texts]
    assert sum("R² = " in t for t in notes) >= 4


def test_trend_on_categorical_x_warns(datasets):
    spec = PlotSpec(plot_type="line", mapping=Mapping(x="preset", y=["acc_rmse_mm"]),
                    aggregation=Aggregation(func="mean"), options={"trend": "linear"})
    res = render(spec, ds=datasets["param_scans"])
    assert any("numeric x axis" in w for w in res.warnings)


def _heat_grid(**style):
    spec = PlotSpec(plot_type="heatmap",
                    mapping=Mapping(x="resolution", row="preset", facet="depth_units_mm",
                                    y=["acc_rmse_mm", "fscore@2mm"], y_mode="side_by_side"),
                    aggregation=Aggregation(func="mean"))
    for k, v in style.items():
        setattr(spec.style, k, v)
    return spec


def test_heatmap_grid_shares_labels_and_colour_bars(datasets):
    res = render(_heat_grid(), ds=datasets["param_scans"])
    panels = [a for a in res.fig.axes if a.get_label() != "<colorbar>"]
    bars = [a for a in res.fig.axes if a.get_label() == "<colorbar>"]
    assert len(panels) == 4 and len(bars) == 2          # one colour bar per metric
    grid = {(round(a.get_position().y0, 2), round(a.get_position().x0, 2)): a for a in panels}
    left = min(x for _, x in grid)
    for (y, x), ax in grid.items():
        ticks = [t for t in ax.get_yticklabels() if t.get_visible() and t.get_text()]
        has_ticks = bool(ticks) and ax.yaxis.get_tick_params()["labelleft"]
        assert has_ticks == (x == left), (y, x)
        assert bool(ax.get_ylabel()) == (x == left)


def test_heatmap_grid_unshared_labels_every_panel(datasets):
    res = render(_heat_grid(sharey=False), ds=datasets["param_scans"])
    panels = [a for a in res.fig.axes if a.get_label() != "<colorbar>"]
    assert all(a.get_ylabel() for a in panels)


def test_value_labels_scoped_by_column(datasets):
    spec = PlotSpec(plot_type="heatmap",
                    mapping=Mapping(x="resolution", row="preset", y=["acc_rmse_mm"]),
                    aggregation=Aggregation(func="mean"))
    spec.style.value_labels = {"preset=high_accuracy": "HA", "640x360": "nHD"}
    ax = render(spec, ds=datasets["param_scans"]).fig.axes[0]
    rows = [t.get_text() for t in ax.get_yticklabels()]
    cols = [t.get_text() for t in ax.get_xticklabels()]
    assert "HA" in rows and "nHD" in cols                 # scoped key and plain (old) key
    spec.style.value_labels = {"resolution=high_accuracy": "HA"}
    ax = render(spec, ds=datasets["param_scans"]).fig.axes[0]
    assert "HA" not in [t.get_text() for t in ax.get_yticklabels()]   # other column only
