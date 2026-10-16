"""Saving, sidecars, overwrite policy and reloading."""
import json

import pytest

from rsplot import export as ex
from rsplot import state
from rsplot.spec import Aggregation, Filter, Mapping, PlotSpec


@pytest.fixture()
def csv_dataset(frames, tmp_path):
    p = tmp_path / "data" / "results.csv"
    p.parent.mkdir()
    frames["filter_sweep"].to_csv(p, index=False)
    return p


def _spec(csv, folder, **kw):
    spec = PlotSpec(mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_mm"], hue="shape"),
                    filters=[Filter("spatial_on", values=[False])],
                    aggregation=Aggregation(func="mean", spread="std"))
    spec.dataset.path = str(csv)
    spec.export.folder = str(folder)
    spec.export.filename = kw.get("name", "my figure")
    spec.export.formats = kw.get("formats", ["pdf", "png", "svg"])
    return spec


def test_save_writes_files_sidecar_and_snippet(csv_dataset, tmp_path):
    out = tmp_path / "out"
    r = ex.save_figure(_spec(csv_dataset, out))
    names = sorted(p.name for p in out.iterdir())
    assert names == ["my_figure.pdf", "my_figure.png", "my_figure.rsplot.json", "my_figure.svg"]
    assert (out / "my_figure.pdf").read_bytes()[:8] == b"%PDF-1.4"
    side = json.loads((out / "my_figure.rsplot.json").read_text())
    assert side["dataset"]["family"] == "filter_sweep" and side["spec"]["filters"]
    assert side["version"] and side["files"] and "acc_rmse_mm" in side["columns_used"]
    assert r.latex.startswith(r"\includegraphics[width=0.8\textwidth]{")
    assert "\\begin{figure}" in r.figure_env and "fig:my-figure" in r.figure_env
    assert state.recent_figures()[0]["sidecar"] == r.sidecar


def test_never_overwrites_silently(csv_dataset, tmp_path):
    spec = _spec(csv_dataset, tmp_path / "o", formats=["pdf"])
    ex.save_figure(spec)
    with pytest.raises(FileExistsError):
        ex.save_figure(spec)
    assert ex.next_free_name(spec.export.folder, "my_figure", ["pdf"]) == "my_figure_2"
    ex.save_figure(spec, overwrite=True)


def test_sidecar_roundtrip_and_change_detection(csv_dataset, tmp_path):
    spec = _spec(csv_dataset, tmp_path / "o", formats=["png"])
    r = ex.save_figure(spec)
    loaded = ex.load_sidecar(r.sidecar)
    assert loaded.spec.mapping == spec.mapping
    assert loaded.spec.filters == spec.filters and not loaded.notes
    csv_dataset.write_text(csv_dataset.read_text() + csv_dataset.read_text().splitlines()[1] + "\n")
    assert any("changed" in n for n in ex.load_sidecar(r.sidecar).notes)


def test_latex_path_relative_to_thesis(tmp_path):
    f = ex.THESIS_ROOT / "figs" / "ch5" / "x.pdf"
    assert ex.latex_path(f) == "figs/ch5/x"
    assert ex.latex_path(tmp_path / "y.pdf").endswith("/y")


def test_safe_filename():
    assert ex.safe_filename("RMSE vs height (mm).pdf") == "RMSE_vs_height_mm"
    assert ex.safe_filename("a@b/c d") == "c_d"


def test_caption_carries_footnote_when_footnote_off(csv_dataset, tmp_path):
    spec = _spec(csv_dataset, tmp_path / "o", formats=["pdf"])
    spec.style.footnote_mode = "off"
    r = ex.save_figure(spec)
    assert "Averaged over" in r.figure_env and "\\caption{Mean" in r.figure_env
