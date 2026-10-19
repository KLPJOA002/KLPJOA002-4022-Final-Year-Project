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


def _panel_spec(frames, tmp_path, labels="outer"):
    csv = tmp_path / "scans.csv"
    frames["param_scans"].to_csv(csv, index=False)
    spec = PlotSpec(plot_type="heatmap",
                    mapping=Mapping(x="resolution", row="preset", facet="depth_units_mm",
                                    y=["acc_rmse_mm", "fscore@2mm"], y_mode="side_by_side"),
                    aggregation=Aggregation(func="mean"))
    spec.dataset.path = str(csv)
    spec.export.folder = str(tmp_path / "out")
    spec.export.filename = "heat"
    spec.export.formats = ["pdf"]
    spec.export.panel_labels = labels
    return spec


@pytest.mark.parametrize("labels", ["outer", "every"])
def test_save_panels_files_and_subfigures(frames, tmp_path, labels):
    r = ex.save_panels(_panel_spec(frames, tmp_path, labels))
    out = tmp_path / "out"
    names = sorted(p.name for p in out.iterdir())
    assert names == ["heat.rsplot.json", "heat_colorbar_1.pdf", "heat_colorbar_2.pdf",
                     "heat_p1.pdf", "heat_p2.pdf", "heat_p3.pdf", "heat_p4.pdf"]
    assert r.figure_env.count("\\begin{subfigure}") == 4
    assert r.figure_env.count("\\includegraphics{") == 2          # colour bars
    assert "\\caption{Accuracy RMSE, 0.1}" in r.figure_env
    side = json.loads((out / "heat.rsplot.json").read_text())
    assert side["spec"]["export"]["grid_mode"] == "panels"
    widths = [float(w) for w in __import__("re").findall(r"subfigure\}\[t\]\{([\d.]+)", r.figure_env)]
    if labels == "every":
        assert len(set(widths)) == 1
    else:                                  # first column carries the row labels: wider
        assert widths[0] > widths[1] and widths[0] == widths[2] and sum(widths[:2]) <= 1
    with pytest.raises(FileExistsError):
        ex.save_panels(_panel_spec(frames, tmp_path, labels))


def test_save_panels_share_colour_range(frames, tmp_path):
    from rsplot.render import render
    spec = _panel_spec(frames, tmp_path)
    full = render(spec)
    norms = {(c.colorbar_mappable.norm.vmin, c.colorbar_mappable.norm.vmax)
             for c in full.colorbars}
    spec.style.footnote_mode = "off"
    for i in range(4):
        res = render(spec, panel={"index": i})
        mesh = res.fig.axes[0].collections[0]
        assert (mesh.norm.vmin, mesh.norm.vmax) in norms


def test_save_panels_needs_facets(csv_dataset, tmp_path):
    with pytest.raises(ValueError):
        ex.save_panels(_spec(csv_dataset, tmp_path / "o", formats=["pdf"]))


def _visible(labels):
    return [t for t in labels if t.get_visible() and t.get_text()]


@pytest.mark.parametrize("labels", ["outer", "every"])
def test_panels_hide_inner_tick_labels(frames, tmp_path, labels):
    from rsplot.render import render
    spec = _panel_spec(frames, tmp_path, labels)
    spec.plot_type = "bar"
    spec.mapping = Mapping(x="preset", y=["acc_rmse_mm", "fscore@2mm", "acc_rmse_trim5_mm",
                                          "completeness_full@2mm"],
                           y_mode="side_by_side", hue="object")
    spec.style.footnote_mode = "off"
    for i in range(4):
        r, c = divmod(i, 2)
        pos = (r, c, 2, 2, r == 1) if labels == "outer" else (0, 0, 1, 1, True)
        ax = render(spec, panel={"index": i, "pos": pos}).fig.axes[0]
        assert ax.xaxis.get_tick_params()["labelbottom"] == (labels == "every" or r == 1)
        assert ax.yaxis.get_tick_params()["labelleft"]          # one metric per panel


def test_panels_hide_inner_y_ticks_when_shared(frames, tmp_path):
    from rsplot.render import render
    spec = _panel_spec(frames, tmp_path)
    spec.plot_type = "bar"
    spec.mapping = Mapping(x="preset", y=["acc_rmse_mm"], hue="object", facet="resolution")
    spec.style.footnote_mode = "off"
    for i, c in enumerate((0, 1)):
        ax = render(spec, panel={"index": i, "pos": (0, c, 1, 2, True)}).fig.axes[0]
        assert ax.yaxis.get_tick_params()["labelleft"] == (c == 0)
        assert _visible(ax.get_xticklabels())


def test_panels_align_down_columns_and_across_rows(frames, tmp_path):
    import re
    from rsplot.render import render
    spec = _panel_spec(frames, tmp_path)
    spec.plot_type = "bar"
    spec.mapping = Mapping(x="preset", y=["acc_rmse_mm", "fscore@2mm", "acc_rmse_trim5_mm",
                                          "completeness_full@2mm"],
                           y_mode="side_by_side", hue="object")
    spec.style.labels = {"acc_rmse_trim5_mm": "A very long metric name that has to wrap (mm)"}
    spec.export.panel_cols = 2
    r = ex.save_panels(spec)
    widths = re.findall(r"subfigure\}\[t\]\{([\d.]+)", r.figure_env)
    assert widths[0] == widths[2] and widths[1] == widths[3]
    side = json.loads((tmp_path / "out" / "heat.rsplot.json").read_text())["panels"]
    spec.style.footnote_mode, spec.style.show_title = "off", False
    edges = []                                   # (left, top) of the plot area in cm
    for i, ((w, h), rect) in enumerate(zip(side["size_cm"], side["rects"])):
        rr, c = divmod(i, 2)
        spec.export.width_cm, spec.export.height_cm = w, h
        res = render(spec, panel={"index": i, "pos": (rr, c, 2, 2, rr == 1), "rect": rect})
        b = res.fig.axes[0].get_window_extent()
        edges.append((b.x0 * 2.54 / res.fig.dpi, h - b.y1 * 2.54 / res.fig.dpi))
    assert abs(edges[0][0] - edges[2][0]) < 0.05 and abs(edges[1][0] - edges[3][0]) < 0.05
    assert abs(edges[0][1] - edges[1][1]) < 0.05 and abs(edges[2][1] - edges[3][1]) < 0.05
