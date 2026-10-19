"""Saving figures: files, JSON sidecars, overwrite policy, LaTeX snippets (headless)."""
from __future__ import annotations

import datetime as _dt
import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, state
from . import style as st
from . import registry as reg
from .data import Dataset
from .render import get_dataset, render, render_strip
from .spec import PlotSpec

FORMATS = ("pdf", "png", "svg")
SIDECAR_SUFFIX = ".rsplot.json"
THESIS_ROOT = state.ROOT.parents[1] / "Report" / "uct-thesis-template"


@dataclass
class SaveResult:
    files: list[str]
    sidecar: str
    latex: str
    figure_env: str
    caption: str
    warnings: list[str] = field(default_factory=list)


# --------------------------------------------------------------- naming --
def safe_filename(name: str) -> str:
    """LaTeX- and filesystem-safe base name (no extension, no spaces or odd characters)."""
    name = Path(name).name
    for ext in (*FORMATS, "rsplot.json", "json"):
        if name.lower().endswith("." + ext):
            name = name[: -len(ext) - 1]
    name = re.sub(r"[^\w\-.]+", "_", name.strip()).strip("._")
    return re.sub(r"_+", "_", name) or "figure"


def suggest_filename(spec: PlotSpec) -> str:
    m = spec.mapping
    parts = [spec.plot_type, *(m.y[:2] or ["figure"])]
    if m.x:
        parts += ["vs", m.x]
    if m.hue:
        parts += ["by", m.hue]
    return safe_filename("_".join(parts).replace("@", "at"))


def output_paths(folder: str | Path, filename: str, formats) -> dict[str, Path]:
    folder = Path(folder).expanduser()
    base = safe_filename(filename)
    out = {f: folder / f"{base}.{f}" for f in formats if f in FORMATS}
    out["sidecar"] = folder / f"{base}{SIDECAR_SUFFIX}"
    return out


def existing(paths: dict[str, Path]) -> list[Path]:
    return [p for p in paths.values() if p.exists()]


def next_free_name(folder: str | Path, filename: str, formats) -> str:
    """name_2, name_3, ... such that none of the output files exist."""
    base = safe_filename(filename)
    m = re.match(r"^(.*?)_(\d+)$", base)
    stem, i = (m.group(1), int(m.group(2))) if m else (base, 1)
    while True:
        i += 1
        cand = f"{stem}_{i}"
        if not existing(output_paths(folder, cand, formats)):
            return cand


# ----------------------------------------------------------------- LaTeX --
def latex_path(file: Path, thesis_root: Path = THESIS_ROOT) -> str:
    """Path as written in \\includegraphics: relative to the thesis main folder when
    the figure is inside it, without extension (pdfLaTeX picks the .pdf)."""
    file = Path(file).resolve()
    try:
        rel = file.relative_to(Path(thesis_root).resolve())
        return rel.with_suffix("").as_posix()
    except ValueError:
        return file.with_suffix("").as_posix()


def latex_snippets(file: Path, width: str, caption: str, label: str) -> tuple[str, str]:
    path = latex_path(file)
    inc = f"\\includegraphics[width={width}]{{{path}}}"
    env = "\n".join([
        "\\begin{figure}[htbp]",
        "    \\centering",
        f"    {inc}",
        f"    \\caption{{{_tex_text(caption) if caption else 'Caption.'}}}",
        f"    \\label{{fig:{label}}}",
        "\\end{figure}"])
    return inc, env


def _tex_text(s: str) -> str:
    rep = {"%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_", "°": r"\textdegree{}",
           "±": r"$\pm$", "≥": r"$\geq$", "≤": r"$\leq$", "∈": r"$\in$", "×": r"$\times$",
           "−": "--", "–": "--", "µ": r"\textmu{}", "²": r"\textsuperscript{2}"}
    return "".join(rep.get(ch, ch) for ch in s)


# ------------------------------------------------------------------ save --
def dataset_fingerprint(ds: Dataset) -> dict:
    p = Path(ds.path)
    try:
        st = p.stat()
        return {"path": str(p), "family": ds.family.key, "size": st.st_size,
                "mtime": _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                "n_rows": ds.n_rows}
    except OSError:
        return {"path": str(p), "family": ds.family.key}


def save_figure(spec: PlotSpec, ds: Dataset | None = None, overwrite: bool = False,
                settings: dict | None = None) -> SaveResult:
    """Render at final resolution and write every requested format plus a sidecar.

    Raises FileExistsError (listing the files) unless `overwrite` — files are never
    replaced silently.
    """
    e = spec.export
    if not e.folder:
        raise ValueError("Choose an output folder.")
    formats = [f for f in (e.formats or ["pdf"]) if f in FORMATS] or ["pdf"]
    name = safe_filename(e.filename or suggest_filename(spec))
    paths = output_paths(e.folder, name, formats)
    clash = existing(paths)
    if clash and not overwrite:
        raise FileExistsError("\n".join(str(p) for p in clash))
    Path(e.folder).expanduser().mkdir(parents=True, exist_ok=True)
    ds = ds or get_dataset(spec)
    res = render(spec, ds=ds, settings=settings, dpi=100)
    title = spec.style.title or name
    meta_pdf = {"Creator": f"rsplot {__version__}", "Title": title,
                "Subject": res.footnote[:500]}
    files = _write_formats(res, paths, formats, e, title, res.footnote)
    spec_saved = spec.copy()
    spec_saved.export.filename = name
    main_file = paths.get("pdf") or paths[formats[0]]
    # Footnote off: its content belongs in the caption; otherwise it is in the figure.
    caption = res.auto_footnote if spec.style.footnote_mode == "off" else ""
    inc, env = latex_snippets(main_file, res.latex_width, caption, name.replace("_", "-"))
    _write_sidecar(paths["sidecar"], spec_saved, ds, res, files, inc)
    return SaveResult(files, str(paths["sidecar"]), inc, env, res.auto_footnote, res.warnings)


def _write_formats(res, paths, formats, e, title, subject="", **extra) -> list[str]:
    files = []
    for f in formats:
        p = paths[f]
        kw = {"dpi": e.dpi, "transparent": e.transparent, **extra}
        if f == "pdf":
            kw["metadata"] = {"Creator": f"rsplot {__version__}", "Title": title,
                              "Subject": subject[:500]}
        elif f == "png":
            kw["metadata"] = {"Software": f"rsplot {__version__}", "Title": title}
        elif f == "svg":
            kw["metadata"] = {"Creator": f"rsplot {__version__}", "Title": title}
        res.savefig(p, format=f, **kw)
        files.append(str(p))
    return files


def _write_sidecar(path, spec_saved, ds, res, files, inc, **extra):
    e = spec_saved.export
    sidecar = {
        "tool": "rsplot", "version": __version__,
        "saved_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "dataset": dataset_fingerprint(ds),
        "family_title": ds.family.title,
        "size_cm": [res.width_cm, res.height_cm],
        "files": files,
        "latex": inc,
        "footnote": res.footnote,
        "warnings": res.warnings,
        "columns_used": _columns_used(spec_saved),
        **extra,
        "spec": spec_saved.to_dict(),
    }
    Path(path).write_text(json.dumps(sidecar, indent=2, default=str))
    state.add_recent(str(path), _recent_title(spec_saved, ds), files)
    state.update_settings(last_folder=str(Path(e.folder).expanduser()))


# --------------------------------------------------------- split panels --
def _margins_cm(res, rect=(0, 0, 1, 1)) -> tuple[float, float, float, float]:
    """(left, right, bottom, top) in cm between a panel's layout `rect` and its plot
    area(s): the room its tick labels, axis labels and padding need."""
    fig = res.fig
    boxes = [ax.get_window_extent() for ax in fig.axes if ax.axison]
    if not boxes:
        return 0.0, 0.0, 0.0, 0.0
    cm = 2.54 / fig.dpi
    W, H = res.width_cm, res.height_cm
    rx0, ry0, rw, rh = rect
    x0, x1 = min(b.x0 for b in boxes) * cm, max(b.x1 for b in boxes) * cm
    y0, y1 = min(b.y0 for b in boxes) * cm, max(b.y1 for b in boxes) * cm
    return (x0 - rx0 * W, (rx0 + rw) * W - x1, y0 - ry0 * H, (ry0 + rh) * H - y1)


def panel_fraction(cols: int) -> float:
    """Fraction of \\textwidth per subfigure so `cols` of them fit on one line."""
    return math.floor((0.99 / cols - 0.01) * 100) / 100


def save_panels(spec: PlotSpec, ds: Dataset | None = None, overwrite: bool = False,
                settings: dict | None = None) -> SaveResult:
    """Faceted figure -> one file per panel (<name>_p1, _p2, ...), a separate legend /
    colour-bar file, one sidecar and a LaTeX subfigure grid that arranges them.

    Panels share the full figure's colours, category order and (when shared) axis
    limits. `export.panel_labels` = "outer" keeps axis labels on the outer panels of
    the LaTeX grid only; "every" labels each panel. Raises FileExistsError like
    save_figure.
    """
    e = spec.export
    if not e.folder:
        raise ValueError("Choose an output folder.")
    settings = settings or state.settings()
    formats = [f for f in (e.formats or ["pdf"]) if f in FORMATS] or ["pdf"]
    name = safe_filename(e.filename or suggest_filename(spec))
    ds = ds or get_dataset(spec)
    full = render(spec, ds=ds, settings=settings, dpi=100)
    n = len(full.panels)
    if n < 2:
        raise ValueError("This figure has a single panel; save it as a single image.")
    grid_rows, grid_cols = full.grid
    cols = max(1, min(e.panel_cols or grid_cols, n))
    rows = math.ceil(n / cols)
    frac = panel_fraction(cols)
    tw = settings["textwidth_cm"]
    pw = round(frac * tw, 2)
    ph = round(max(full.height_cm / grid_rows, 3.0), 2)

    names = [f"{name}_p{i + 1}" for i in range(n)]
    strips = []                                   # (file stem, kind, item)
    if full.legend_items:
        strips.append((f"{name}_legend", "legend", full.legend_items))
    for k, cb in enumerate(full.colorbars):
        suffix = "" if len(full.colorbars) == 1 else f"_{k + 1}"
        strips.append((f"{name}_colorbar{suffix}", "colorbar", cb))
    all_paths = {nm: output_paths(e.folder, nm, formats) for nm in names + [s[0] for s in strips]}
    for p in all_paths.values():
        p.pop("sidecar")
    main_paths = output_paths(e.folder, name, formats)
    clash = existing(main_paths) + [q for p in all_paths.values() for q in existing(p)]
    if clash and not overwrite:
        raise FileExistsError("\n".join(str(p) for p in clash))
    Path(e.folder).expanduser().mkdir(parents=True, exist_ok=True)

    title = spec.style.title or name
    pspec = spec.copy()
    pspec.export.width_cm, pspec.export.height_cm = pw, ph
    pspec.style.footnote_mode, pspec.style.show_title, pspec.style.subtitle = "off", False, ""
    outer = e.panel_labels != "every"
    panels = []
    for i, info in enumerate(full.panels):
        r, c = divmod(i, cols)
        panels.append({"index": i,
                       "pos": (r, c, rows, cols, i + cols >= n) if outer else (0, 0, 1, 1, True),
                       "xlim": info["xlim"] if spec.style.sharex else None,
                       "ylim": info["ylim"] if spec.style.sharey else None})

    def draw(i, w, h, rect=None):
        ps = pspec.copy()
        ps.export.width_cm, ps.export.height_cm = w, h
        return render(ps, ds=ds, settings=settings, dpi=100,
                      panel={**panels[i], "rect": rect})

    sizes = [(pw, ph)] * n
    rects = [(0, 0, 1, 1)] * n
    results = [draw(i, pw, ph) for i in range(n)]
    if outer:
        # Outer panels carry the labels. Every panel of a grid column gets that
        # column's widest left / right margins, every panel of a row that row's
        # tallest top / bottom margins; a panel needing less is padded inside (its
        # layout rect), so all plot areas are the same size and line up.
        # Twice: label sizes change with the panel size (e.g. tick labels un-rotate).
        for _ in range(2):
            m = [_margins_cm(res, rects[i]) for i, res in enumerate(results)]
            cidx = [i % cols for i in range(n)]
            ridx = [i // cols for i in range(n)]
            L = [max(m[i][0] for i in range(n) if cidx[i] == j) for j in range(cols)]
            R = [max(m[i][1] for i in range(n) if cidx[i] == j) for j in range(cols)]
            B = [max(m[i][2] for i in range(n) if ridx[i] == k) for k in range(rows)]
            T = [max(m[i][3] for i in range(n) if ridx[i] == k) for k in range(rows)]
            aw = (cols * pw - sum(L) - sum(R)) / cols
            ah = ph - min(t + b for t, b in zip(T, B))
            col_w = [round(L[j] + aw + R[j], 2) for j in range(cols)]
            row_h = [round(T[k] + ah + B[k], 2) for k in range(rows)]
            sizes, rects = [], []
            for i in range(n):
                j, k = cidx[i], ridx[i]
                W, H = col_w[j], row_h[k]
                left, right = L[j] - m[i][0], R[j] - m[i][1]
                bottom, top = B[k] - m[i][2], T[k] - m[i][3]
                sizes.append((W, H))
                rects.append((left / W, bottom / H, 1 - (left + right) / W,
                              1 - (bottom + top) / H))
            results = [draw(i, *sizes[i], rects[i]) for i in range(n)]
    files, warnings = [], list(full.warnings)
    for i, (info, res) in enumerate(zip(full.panels, results)):
        warnings += [w for w in res.warnings if w not in warnings]
        files += _write_formats(res, all_paths[names[i]], formats, e,
                                f"{title} ({info['title'] or i + 1})")
    for stem, kind, item in strips:
        res = render_strip(pspec, full, tw, **{kind: item})
        files += _write_formats(res, all_paths[stem], formats, e, f"{title} ({kind})",
                                bbox_inches="tight", pad_inches=0.02)

    main_fmt = "pdf" if "pdf" in formats else formats[0]
    label = name.replace("_", "-")
    lines = []
    for i, info in enumerate(full.panels):
        width = st.latex_width(sizes[i][0], tw)
        sub = "\n".join([
            f"    \\begin{{subfigure}}[t]{{{width}}}",
            "        \\centering",
            f"        \\includegraphics[width=\\linewidth]"
            f"{{{latex_path(all_paths[names[i]][main_fmt])}}}",
            f"        \\caption{{{_tex_text(info['title'])}}}",
            f"        \\label{{fig:{label}-{i + 1}}}",
            "    \\end{subfigure}"])
        end = i == n - 1
        if end and n % cols:       # keep the last row's panels under their columns
            sub += "".join(f"\\hfill\n    \\begin{{subfigure}}[t]"
                           f"{{{st.latex_width(sizes[j % cols][0], tw)}}}\\mbox{{}}"
                           "\\end{subfigure}" for j in range(n, n + cols - n % cols))
        lines.append(sub + ("" if end else "\\hfill" if (i + 1) % cols else "\n    \\par\\medskip"))
    for stem, _, _ in strips:
        lines.append(f"    \\par\\medskip\n    \\includegraphics{{{latex_path(all_paths[stem][main_fmt])}}}")
    grid = "\n".join(lines)
    caption = full.auto_footnote
    env = "\n".join(["\\begin{figure}[htbp]", "    \\centering", grid,
                      f"    \\caption{{{_tex_text(caption) if caption else 'Caption.'}}}",
                      f"    \\label{{fig:{label}}}", "\\end{figure}"])
    spec_saved = spec.copy()
    spec_saved.export.filename = name
    spec_saved.export.grid_mode = "panels"
    _write_sidecar(main_paths["sidecar"], spec_saved, ds, full, files, grid,
                   panels={"cols": cols, "size_cm": sizes, "rects": rects,
                           "labels": e.panel_labels,
                           "files": [str(all_paths[nm][main_fmt]) for nm in names]})
    return SaveResult(files, str(main_paths["sidecar"]), grid, env, caption, warnings)


def _columns_used(spec: PlotSpec) -> list[str]:
    """Columns the figure actually depends on (mapping fields the plot type ignores and
    disabled filters are left out)."""
    from .plots import PLOT_TYPES, load_plugins
    from .render import _drop_unused_roles
    load_plugins()
    m = _drop_unused_roles(spec, PLOT_TYPES[spec.plot_type]).mapping
    cols = (m.x, *m.y, m.hue, m.facet, m.style, m.row, m.secondary, *m.by,
            *[f.column for f in spec.filters if f.enabled])
    return sorted({c for c in cols if c})


def _recent_title(spec: PlotSpec, ds: Dataset) -> str:
    ys = ", ".join(reg.axis_label(y).split(" (")[0] for y in spec.mapping.y[:2])
    return f"{spec.export.filename} — {ds.family.title}: {ys}"


# ------------------------------------------------------------------ load --
@dataclass
class LoadedFigure:
    spec: PlotSpec
    info: dict
    notes: list[str]


def load_sidecar(path: str | Path) -> LoadedFigure:
    """Read a sidecar back into a PlotSpec; notes say if the data file changed since."""
    d = json.loads(Path(path).read_text())
    if d.get("tool") != "rsplot" or "spec" not in d:
        raise ValueError(f"{Path(path).name} is not an rsplot figure-settings file.")
    spec = PlotSpec.from_dict(d["spec"])
    notes = []
    fp = d.get("dataset", {})
    p = Path(spec.dataset.path)
    if not p.exists():
        notes.append(f"The data file no longer exists: {p}")
    elif fp.get("size") is not None:
        st = p.stat()
        mtime = _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        if st.st_size != fp["size"] or mtime != fp.get("mtime"):
            notes.append("The data file has changed since this figure was saved "
                         f"(saved {fp.get('mtime')}, now {mtime}); the figure may differ.")
    if d.get("version") != __version__:
        notes.append(f"Saved with rsplot {d.get('version')}; this is {__version__}.")
    return LoadedFigure(spec, d, notes)
