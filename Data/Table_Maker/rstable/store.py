"""Opening rsplot sessions, saving tables (.tex, .csv, .rstable.json), LaTeX preview."""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from dataclasses import dataclass, field
from pathlib import Path

from rsplot import export as rsx
from rsplot import state as rsstate

from . import __version__
from .render import safe_label, to_frame, to_latex
from .spec import Source, TableSpec
from .table import Table

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.environ.get("RSTABLE_STATE_DIR", ROOT / ".state"))
THESIS_ROOT = rsx.THESIS_ROOT
SIDECAR_SUFFIX = ".rstable.json"
_LOCK = threading.Lock()


# ------------------------------------------------------------------ state --
def _read(name: str, default):
    try:
        return json.loads((STATE_DIR / name).read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    with _LOCK:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = STATE_DIR / (name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(STATE_DIR / name)


def settings() -> dict:
    return {"last_folder": str(THESIS_ROOT / "tables"), **_read("settings.json", {})}


def update_settings(**kw) -> None:
    _write("settings.json", {**settings(), **kw})


def recent_tables() -> list[dict]:
    return _read("recent.json", [])


def _add_recent(sidecar: str, title: str) -> None:
    items = [r for r in recent_tables() if r["sidecar"] != sidecar]
    items.insert(0, {"sidecar": sidecar, "title": title})
    _write("recent.json", items[:50])


def save_last(ts: TableSpec) -> None:
    _write("last_table.json", ts.to_dict())


def last_table() -> TableSpec | None:
    d = _read("last_table.json", None)
    return TableSpec.from_dict(d) if d else None


# ------------------------------------------------------- rsplot sessions --
def rsplot_recent() -> list[dict]:
    """Figures saved by rsplot (newest first): [{sidecar, title, files, exists}]."""
    return [{**r, "exists": Path(r["sidecar"]).exists()} for r in rsstate.recent_figures()]


def rsplot_last() -> dict | None:
    """The figure currently (or last) open in rsplot, saved or not."""
    return rsstate.last_spec()


def from_sidecar(path: str | Path) -> tuple[TableSpec, list[str]]:
    """New table from a saved rsplot figure (.rsplot.json)."""
    lf = rsx.load_sidecar(path)
    path = Path(path)
    ts = TableSpec(source=Source(sidecar=str(path), sidecar_saved_at=lf.info.get("saved_at", ""),
                                 plot=lf.info["spec"]))
    stem = path.name[: -len(rsx.SIDECAR_SUFFIX)] if path.name.endswith(rsx.SIDECAR_SUFFIX) \
        else path.stem
    ts.output.filename = f"{stem}_table"
    ts.output.label = "tab:" + safe_label(stem)
    ts.output.folder = settings()["last_folder"]
    return ts, list(lf.notes)


def from_plot_spec(spec: dict, name: str = "table") -> TableSpec:
    """New table from an unsaved rsplot figure (rsplot's last figure)."""
    ts = TableSpec(source=Source(sidecar="", plot=spec))
    ts.output.filename = rsx.safe_filename(spec.get("export", {}).get("filename") or name) \
        + "_table"
    ts.output.label = "tab:" + safe_label(ts.output.filename[:-6])
    ts.output.folder = settings()["last_folder"]
    return ts


def refresh_from_sidecar(ts: TableSpec) -> list[str]:
    """Re-read the figure's sidecar (after the figure was changed and saved again)."""
    if not ts.source.sidecar:
        raise ValueError("This table was made from an unsaved figure; there is nothing "
                         "to re-read.")
    lf = rsx.load_sidecar(ts.source.sidecar)
    ts.source.plot = lf.info["spec"]
    ts.source.sidecar_saved_at = lf.info.get("saved_at", "")
    return list(lf.notes)


def source_notes(ts: TableSpec) -> list[str]:
    """Has the figure been re-saved, or the data file changed, since the table was made?"""
    notes = []
    sc = ts.source.sidecar
    if sc:
        p = Path(sc)
        if not p.exists():
            notes.append(f"The figure's settings file no longer exists: {p}")
        else:
            try:
                saved = json.loads(p.read_text()).get("saved_at", "")
            except (OSError, ValueError):
                saved = ""
            if saved and ts.source.sidecar_saved_at and saved != ts.source.sidecar_saved_at:
                notes.append(f"The figure was saved again ({saved}) after this table took its "
                             "settings. Use “Re-read figure” to follow it.")
    data = ts.source.plot.get("dataset", {}).get("path")
    if data and not Path(data).exists():
        notes.append(f"The data file no longer exists: {data}")
    return notes


# ------------------------------------------------------------------- save --
@dataclass
class SaveResult:
    files: list[str]
    sidecar: str
    input_line: str
    latex: str
    warnings: list[str] = field(default_factory=list)


def output_paths(folder: str | Path, filename: str, csv: bool = True) -> dict[str, Path]:
    folder = Path(folder).expanduser()
    base = rsx.safe_filename(filename or "table")
    out = {"tex": folder / f"{base}.tex", "sidecar": folder / f"{base}{SIDECAR_SUFFIX}"}
    if csv:
        out["csv"] = folder / f"{base}.csv"
    return out


def next_free_name(folder: str | Path, filename: str, csv: bool = True) -> str:
    base = rsx.safe_filename(filename or "table")
    m = re.match(r"^(.*?)_(\d+)$", base)
    stem, i = (m.group(1), int(m.group(2))) if m else (base, 1)
    while True:
        i += 1
        cand = f"{stem}_{i}"
        if not [p for p in output_paths(folder, cand, csv).values() if p.exists()]:
            return cand


def input_line(tex: Path) -> str:
    return f"\\input{{{rsx.latex_path(tex, THESIS_ROOT)}}}"


def save_table(ts: TableSpec, t: Table, overwrite: bool = False) -> SaveResult:
    """Write <name>.tex (the table environment, for \\input), <name>.csv (the numbers)
    and <name>.rstable.json (settings to re-open it). Never overwrites silently."""
    o = ts.output
    if not o.folder:
        raise ValueError("Choose an output folder.")
    o.filename = rsx.safe_filename(o.filename or "table")
    paths = output_paths(o.folder, o.filename, o.write_csv)
    clash = [p for p in paths.values() if p.exists()]
    if clash and not overwrite:
        raise FileExistsError("\n".join(str(p) for p in clash))
    Path(o.folder).expanduser().mkdir(parents=True, exist_ok=True)
    latex = to_latex(t, ts)
    src = ts.source.sidecar or "(unsaved rsplot figure)"
    header = (f"% Generated by rstable {__version__} on "
              f"{_dt.datetime.now().isoformat(timespec='seconds')}\n"
              f"% Figure: {src}\n% Data:   {ts.source.plot.get('dataset', {}).get('path', '')}\n"
              f"% Re-open: {paths['sidecar'].name}. Needs booktabs and makecell.\n")
    paths["tex"].write_text(header + latex)
    files = [str(paths["tex"])]
    if o.write_csv:
        to_frame(t, ts).to_csv(paths["csv"], index=False)
        files.append(str(paths["csv"]))
    side = {"tool": "rstable", "version": __version__,
            "saved_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "dataset": rsx.dataset_fingerprint(t.ds) if t.ds else {},
            "statistic": t.stat.short(), "n": t.n_text, "files": files,
            "latex_input": input_line(paths["tex"]), "spec": ts.to_dict()}
    paths["sidecar"].write_text(json.dumps(side, indent=2, default=str))
    _add_recent(str(paths["sidecar"]), f"{o.filename} — {t.stat.short()}")
    update_settings(last_folder=str(Path(o.folder).expanduser()))
    return SaveResult(files, str(paths["sidecar"]), input_line(paths["tex"]), latex,
                      list(t.warnings))


def load_table(path: str | Path) -> tuple[TableSpec, list[str]]:
    d = json.loads(Path(path).read_text())
    if d.get("tool") != "rstable" or "spec" not in d:
        raise ValueError(f"{Path(path).name} is not an rstable settings file.")
    ts = TableSpec.from_dict(d["spec"])
    notes = source_notes(ts)
    fp = d.get("dataset", {})
    p = Path(fp.get("path", ""))
    if fp.get("size") is not None and p.exists():
        st = p.stat()
        mtime = _dt.datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds")
        if st.st_size != fp["size"] or mtime != fp.get("mtime"):
            notes.append("The data file has changed since this table was saved "
                         f"(saved {fp.get('mtime')}, now {mtime}); the values may differ.")
    return ts, notes


# --------------------------------------------------------- LaTeX preview --
PREAMBLE_XE = r"""\documentclass[11pt]{article}
\usepackage[a4paper,margin=1.5cm]{geometry}
\usepackage{amsmath}
\usepackage{unicode-math}
\usepackage{fontspec}
\setmainfont{TeX Gyre Termes}
\setmathfont{TeX Gyre Termes Math}
"""
PREAMBLE_PDF = r"""\documentclass[11pt]{article}
\usepackage[a4paper,margin=1.5cm]{geometry}
\usepackage{mathptmx}
"""
PREAMBLE_COMMON = r"""\usepackage{graphicx,booktabs,makecell,multirow,array,gensymb,caption}
\pagestyle{empty}
\begin{document}
\noindent\rule{\textwidth}{0.2pt}\par
"""


@dataclass
class Compiled:
    png: bytes = b""
    error: str = ""
    overfull: bool = False
    engine: str = ""


def tex_engine() -> str | None:
    for e in ("xelatex", "pdflatex"):
        if shutil.which(e):
            return e
    return None


def compile_preview(latex: str, dpi: int = 160) -> Compiled:
    """Typeset the table on a page with the thesis text width (18 cm, Termes) and
    return a cropped PNG. A hairline above shows the text width."""
    engine = tex_engine()
    if engine is None or not shutil.which("pdftoppm"):
        return Compiled(error="LaTeX (xelatex/pdflatex) or pdftoppm not found. Start the app "
                              "from a normal terminal with ./run.sh.")
    pre = PREAMBLE_XE if engine == "xelatex" else PREAMBLE_PDF
    body = re.sub(r"\\begin\{table\}(\[[^\]]*\])?", lambda m: r"\begin{table}[h!]", latex, count=1)
    doc = pre + PREAMBLE_COMMON + body + "\n\\end{document}\n"
    with tempfile.TemporaryDirectory(prefix="rstable_") as tmp:
        tmp = Path(tmp)
        (tmp / "t.tex").write_text(doc)
        try:
            r = subprocess.run([engine, "-interaction=nonstopmode", "-halt-on-error", "t.tex"],
                               cwd=tmp, capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.SubprocessError) as e:
            return Compiled(error=str(e), engine=engine)
        log = (tmp / "t.log").read_text(errors="replace") if (tmp / "t.log").exists() else ""
        if r.returncode != 0 or not (tmp / "t.pdf").exists():
            err = [ln for ln in log.splitlines() if ln.startswith("!")]
            ctx = ""
            if err:
                i = log.splitlines().index(err[0])
                ctx = "\n".join(log.splitlines()[i:i + 6])
            return Compiled(error=ctx or (r.stdout[-1500:] or "LaTeX failed."), engine=engine)
        overfull = bool(re.search(r"Overfull \\hbox \((\d+\.?\d*)pt", log)) and any(
            float(m) > 1.0 for m in re.findall(r"Overfull \\hbox \((\d+\.?\d*)pt", log))
        subprocess.run(["pdftoppm", "-png", "-r", str(dpi), "-singlefile", "-f", "1", "-l", "1",
                        "t.pdf", "t"], cwd=tmp, capture_output=True, timeout=60)
        png = (tmp / "t.png").read_bytes() if (tmp / "t.png").exists() else b""
        return Compiled(_crop(png), "", overfull, engine)


def _crop(png: bytes) -> bytes:
    if not png:
        return png
    import io
    from PIL import Image, ImageChops
    im = Image.open(io.BytesIO(png)).convert("RGB")
    bg = Image.new("RGB", im.size, (255, 255, 255))
    box = ImageChops.difference(im, bg).getbbox()
    if box:
        pad = 12
        box = (max(box[0] - pad, 0), max(box[1] - pad, 0), min(box[2] + pad, im.width),
               min(box[3] + pad, im.height))
        im = im.crop(box)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()
