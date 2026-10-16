"""Registry, pipeline and renderer behaviour (headless)."""
import numpy as np
import pytest

from rsplot import registry as reg
from rsplot.pipeline import N, prepare, unfixed
from rsplot.render import render
from rsplot.spec import Aggregation, Filter, Mapping, PlotSpec


@pytest.mark.parametrize("family", ["planar_frames", "planar_summary", "filter_sweep",
                                    "fusion", "param_scans", "filter_ranking"])
def test_family_detection(frames, family):
    assert reg.detect_family(list(frames[family].columns)).key == family


def test_unknown_file_is_generic():
    assert reg.detect_family(["a", "b", "value"]).key == "generic"


def test_pinned_metrics_first(datasets):
    m = datasets["filter_sweep"].metrics()
    assert m[:3] == ["acc_rmse_mm", "acc_rmse_trim1_mm", "acc_rmse_trim5_mm"]


def test_labels():
    assert reg.axis_label("fill_pct") == "Valid pixels (%)"
    assert reg.axis_label("acc_rmse_mm") == "Accuracy RMSE (mm)"
    assert reg.axis_label("completeness@2mm", percent=True) == "Completeness at 2 mm (%)"
    assert reg.axis_label("plane_pitch_deg") == "Measured plane pitch (°)"
    assert reg.axis_label("some_new_col_mm") == "Some new col (mm)"
    assert reg.axis_label("acc_rmse_mm", {"acc_rmse_mm": "RMSE"}) == "RMSE"
    assert reg.value_label("640x360") == "640 × 360"


def test_boolean_strings_normalised(datasets):
    assert datasets["planar_frames"].profile["detected"].kind == "boolean"


def test_summary_uses_stored_statistics(datasets):
    ds = datasets["planar_summary"]
    assert "z_err_median_mm" in ds.metrics()
    spec = PlotSpec(mapping=Mapping(x="gt_axis_mm", y=["z_err_median_mm"]),
                    aggregation=Aggregation(func="none", stored_stat="median",
                                            stored_spread="iqr"))
    pre = prepare(ds, spec)
    row = pre.data.iloc[0]
    assert row["__lo__"] < row["__value__"] < row["__hi__"]
    assert row[N] >= 500


def test_unfixed_factor_is_flagged(datasets):
    ds = datasets["filter_sweep"]
    spec = PlotSpec(mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_mm"], hue="shape"),
                    aggregation=Aggregation(func="mean", spread="std"))
    pre = prepare(ds, spec)
    flagged = {n.column for n in unfixed(pre)}
    assert {"spatial_on", "height_mm", "rotation_label"} <= flagged
    # determined by x (decimation_on follows decimation_magnitude): not flagged
    assert "decimation_on" not in flagged
    assert "Averaged over" in pre.footnote and "1 rows without a value" in pre.footnote


def test_filter_fixes_factor(datasets):
    ds = datasets["filter_sweep"]
    spec = PlotSpec(mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_mm"], hue="shape"),
                    filters=[Filter("spatial_on", values=[False])],
                    aggregation=Aggregation(func="mean", spread="ci95"))
    pre = prepare(ds, spec)
    assert "spatial_on" not in {n.column for n in unfixed(pre)}
    assert "Spatial filter on = Off" in pre.footnote
    assert pre.n_filtered == len(ds.frame()) // 2


def test_range_filter(datasets):
    ds = datasets["fusion"]
    spec = PlotSpec(mapping=Mapping(x="n_scans", y=["acc_rmse_mm"]),
                    filters=[Filter("n_scans", kind="range", lo=3, hi=None)])
    assert prepare(ds, spec).n_filtered == (ds.frame()["n_scans"] >= 3).sum()


def test_multi_metric_overlay_and_side_by_side(datasets):
    ds = datasets["filter_sweep"]
    y = ["acc_rmse_mm", "acc_rmse_trim5_mm"]
    over = prepare(ds, PlotSpec(mapping=Mapping(x="decimation_magnitude", y=y),
                                aggregation=Aggregation(func="mean")))
    assert over.roles["hue"] == "__metric__"
    side = prepare(ds, PlotSpec(mapping=Mapping(x="decimation_magnitude", y=y, hue="shape",
                                                y_mode="side_by_side"),
                                aggregation=Aggregation(func="mean")))
    assert side.roles["facet_col"] == "__metric__" and side.roles["hue"] == "shape"


def test_single_value_groups_warn_no_spread(datasets):
    ds = datasets["param_scans"]
    spec = PlotSpec(mapping=Mapping(x="preset", y=["acc_rmse_mm"], hue="resolution",
                                    facet="object_label", by=["depth_units_mm"]),
                    aggregation=Aggregation(func="mean", spread="std"))
    pre = prepare(ds, spec)
    assert any("single value" in w for w in pre.warnings)


def test_render_size_and_latex_width(datasets):
    spec = PlotSpec(mapping=Mapping(x="gt_axis_mm", y=["z_err_median_mm"], hue="condition"),
                    aggregation=Aggregation(func="median", spread="iqr"))
    res = render(spec, ds=datasets["planar_frames"])
    w, h = res.fig.get_size_inches() * 2.54
    assert abs(w - 14.4) < 1e-6 and abs(h - 10.8) < 1e-6
    assert res.latex_width == r"0.8\textwidth"


def test_height_warning(datasets):
    spec = PlotSpec(mapping=Mapping(x="gt_axis_mm", y=["z_err_median_mm"]))
    spec.export.height_cm = 25
    res = render(spec, ds=datasets["planar_frames"])
    assert any("exceeds the thesis maximum" in w for w in res.warnings)


def test_empty_after_filter_renders(datasets):
    spec = PlotSpec(mapping=Mapping(x="gt_axis_mm", y=["z_err_median_mm"]),
                    filters=[Filter("condition", values=["nonexistent"])])
    res = render(spec, ds=datasets["planar_frames"])
    assert res.pre.data.empty


def test_spec_roundtrip():
    spec = PlotSpec(mapping=Mapping(x="a", y=["b", "c"]), filters=[Filter("d", values=[1])])
    d = spec.to_dict()
    d["unknown_future_key"] = 1
    d["style"]["also_unknown"] = 2
    assert PlotSpec.from_dict(d).to_dict() == spec.to_dict()


def test_bundled_truetype_font_wins():
    """System OTF (CFF) copies of the thesis font must not shadow the bundled TTF."""
    from matplotlib import font_manager
    from rsplot import style as st
    st.register_fonts()
    family = st.style_preset("thesis")["font_family"]
    path = font_manager.findfont(font_manager.FontProperties(family=family))
    assert path.startswith(str(st.FONT_DIR)) and path.endswith(".ttf")


def test_derived_tilt_and_rotation_are_numeric(datasets):
    ds = datasets["fusion"]
    df = ds.frame()
    assert ds.profile["tilt_deg"].kind == "numeric" and "tilt_deg" in ds.factors()
    assert df.loc[df.tilts == "-10;0;10", "tilt_deg"].isna().all()       # fused tilt set
    assert set(df.loc[df.kind == "single", "tilt_deg"]) == {-10.0, 0.0, 10.0}
    assert set(df.loc[df.kind == "single", "rotation_deg"]) == {0.0, 90.0}


def test_rows_without_x_value_are_excluded(datasets):
    ds = datasets["fusion"]
    spec = PlotSpec(mapping=Mapping(x="tilt_deg", y=["acc_rmse_mm"], hue="rotation_deg"),
                    filters=[Filter("kind", values=["single"])],
                    aggregation=Aggregation(func="median", spread="iqr"))
    pre = prepare(ds, spec)
    assert pre.n_nan_x == 0 and sorted(pre.data["__x__"].unique()) == [-10, 0, 10]
    assert pre.data[N].max() == 4                     # 2 objects x 2 heights per point
    spec.filters = []
    pre = prepare(ds, spec)
    n_sets = int((ds.frame()["n_tilts"] > 1).sum())
    assert pre.n_nan_x == n_sets and f"{n_sets} rows without a tilt value" in pre.footnote
    assert not pre.data["__x__"].isna().any()
