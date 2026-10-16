"""Saving figures: files, JSON sidecars, overwrite policy, LaTeX snippets (headless)."""
from __future__ import annotations

import datetime as _dt
import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import __version__, state
from . import registry as reg
from .data import Dataset
from .render import get_dataset, render
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
    files = []
    for f in formats:
        p = paths[f]
        kw = {"dpi": e.dpi, "transparent": e.transparent}
        if f == "pdf":
            kw["metadata"] = meta_pdf
        elif f == "png":
            kw["metadata"] = {"Software": f"rsplot {__version__}", "Title": title}
        elif f == "svg":
            kw["metadata"] = {"Creator": f"rsplot {__version__}", "Title": title}
        res.savefig(p, format=f, **kw)
        files.append(str(p))
    spec_saved = spec.copy()
    spec_saved.export.filename = name
    main_file = paths.get("pdf") or paths[formats[0]]
    # Footnote off: its content belongs in the caption; otherwise it is in the figure.
    caption = res.auto_footnote if spec.style.footnote_mode == "off" else ""
    inc, env = latex_snippets(main_file, res.latex_width, caption, name.replace("_", "-"))
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
        "columns_used": _columns_used(spec),
        "spec": spec_saved.to_dict(),
    }
    paths["sidecar"].write_text(json.dumps(sidecar, indent=2, default=str))
    state.add_recent(str(paths["sidecar"]), _recent_title(spec_saved, ds), files)
    state.update_settings(last_folder=str(Path(e.folder).expanduser()))
    return SaveResult(files, str(paths["sidecar"]), inc, env, res.auto_footnote, res.warnings)


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
