"""UI-independent session logic."""
from pathlib import Path

from rsplot.pipeline import filter_is_noop, prepare
from rsplot.spec import PlotSpec
from rsplot.ui import session as S


def test_default_spec_uses_family_defaults(datasets):
    spec = S.default_spec(datasets["filter_sweep"])
    assert spec.mapping.x == "decimation_magnitude" and spec.mapping.hue == "shape"
    assert spec.mapping.y == ["acc_rmse_mm"] and spec.filters == []


def test_default_spec_keeps_style_but_not_labels(datasets):
    old = S.default_spec(datasets["filter_sweep"])
    old.style.preset, old.style.labels = "slides", {"acc_rmse_mm": "x"}
    new = S.default_spec(datasets["fusion"], keep=old)
    assert new.style.preset == "slides" and new.style.labels == {}


def test_new_filter_changes_nothing(datasets):
    ds = datasets["filter_sweep"]
    base = prepare(ds, S.default_spec(ds)).n_filtered
    for col in ("acc_rmse_mm", "spatial_alpha", "shape", "decimation_magnitude", "spatial_on"):
        spec = S.default_spec(ds)
        f = S.new_filter(ds, col)
        spec.filters = [f]
        assert filter_is_noop(ds, f), col
        assert prepare(ds, spec).n_filtered == base, col


def test_fix_to_one(datasets):
    ds = datasets["filter_sweep"]
    spec = S.default_spec(ds)
    S.fix_to_one(ds, spec, "height_mm")
    assert spec.filters[0].values == [641]


def test_variant_toggle_keeps_order(datasets):
    spec = PlotSpec()
    spec.mapping.y = ["fscore@2mm", "acc_rmse_mm"]
    g = S.variants(datasets["filter_sweep"])["rmse"]["members"]
    S.set_variants(spec, g, ["untrimmed", "trim5"])
    assert spec.mapping.y == ["fscore@2mm", "acc_rmse_mm", "acc_rmse_trim5_mm"]
    S.set_variants(spec, g, ["trim1"])
    assert spec.mapping.y == ["fscore@2mm", "acc_rmse_trim1_mm"]


def test_preview_returns_png_or_error(datasets):
    ds = datasets["planar_frames"]
    pv = S.preview(S.default_spec(ds), ds, dpi=60)
    assert pv.png_b64 and not pv.error and pv.n_total == len(ds.frame())
    bad = S.default_spec(ds)
    bad.mapping.x = "no_such_column"
    assert "no_such_column" in S.preview(bad, ds, dpi=60).error


def test_find_candidates_skips_old_and_raw(tmp_path):
    (tmp_path / "A_Analysis" / "Data" / "t1").mkdir(parents=True)
    (tmp_path / "A_Analysis" / "Data" / "t1" / "raw.csv").write_text("a,b\n1,2\n")
    (tmp_path / "A_Analysis" / "Plots").mkdir()
    (tmp_path / "A_Analysis" / "Plots" / "keep.csv").write_text("a,b\n1,2\n")
    (tmp_path / "Pitch_Old").mkdir()
    (tmp_path / "Pitch_Old" / "old.csv").write_text("a,b\n1,2\n")
    found = [c["path"] for c in S.find_candidates([tmp_path])]
    assert len(found) == 1 and found[0].endswith("keep.csv")


def test_superseded_files_not_suggested(tmp_path):
    for rel in ("R/results.csv", "R/plots/ranking_1.csv", "R/V3/results.csv",
                "R/V3/plots/ranking_1.csv"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text("config_id,config_label,scan_id,decimation_on\n1,a,b,True\n")
    c = {Path(x["path"]).relative_to(tmp_path).as_posix(): x for x in S.find_candidates([tmp_path])}
    assert c["R/results.csv"]["note"].endswith("V3") and not c["R/results.csv"]["suggest"]
    assert not c["R/plots/ranking_1.csv"]["suggest"]
    assert c["R/V3/results.csv"]["suggest"] and c["R/V3/plots/ranking_1.csv"]["suggest"]
