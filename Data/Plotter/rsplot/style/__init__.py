"""Central style: fonts, rcParams, palettes, colormaps and size presets."""
from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

import matplotlib as mpl
import yaml
from matplotlib import font_manager
from matplotlib.colors import LinearSegmentedColormap, to_hex

HERE = Path(__file__).resolve().parent
FONT_DIR = HERE / "fonts"
CM_PER_IN = 2.54


@lru_cache(maxsize=1)
def presets() -> dict:
    return yaml.safe_load((HERE / "presets.yaml").read_text())


@lru_cache(maxsize=1)
def register_fonts() -> list[str]:
    """Register bundled TTFs with matplotlib; returns the family names found."""
    fm = font_manager.fontManager
    names = set()
    for f in sorted(FONT_DIR.glob("*.ttf")):
        fm.addfont(str(f))
        names.add(font_manager.FontProperties(fname=str(f)).get_name())
    # Bundled TrueType files must win over same-named system fonts (e.g. the host's
    # CFF-flavoured texgyretermes-*.otf), which would break Type 42 PDF embedding.
    bundled = str(FONT_DIR)
    fm.ttflist = [e for e in fm.ttflist
                  if e.name not in names or str(e.fname).startswith(bundled)]
    fm._findfont_cached.cache_clear()
    _register_cmaps()
    return sorted(names)


def _register_cmaps() -> None:
    c = presets()["colours"]
    for name, cols in (("rs_sequential", c["sequential"]), ("rs_diverging", c["diverging"])):
        if name not in mpl.colormaps:
            cmap = LinearSegmentedColormap.from_list(name, cols)
            mpl.colormaps.register(cmap)
            mpl.colormaps.register(cmap.reversed(), name=name + "_r")


def style_preset(name: str) -> dict:
    return presets()["styles"].get(name, presets()["styles"]["thesis"])


def size_presets() -> dict:
    return presets()["sizes"]


def figure_size_cm(export, textwidth_cm: float) -> tuple[float, float]:
    """(width, height) in cm for an Export spec."""
    p = size_presets().get(export.size_preset, size_presets()["thesis_caption"])
    width = export.width_cm
    if width is None:
        width = p["width_cm"] if "width_cm" in p else round(p["fraction"] * textwidth_cm, 2)
    height = export.height_cm if export.height_cm is not None else round(width * p["aspect"], 2)
    return float(width), float(height)


def latex_width(width_cm: float, textwidth_cm: float) -> str:
    """Width argument for \\includegraphics that places the figure at 100 % scale."""
    frac = width_cm / textwidth_cm
    if abs(frac - 1) < 1e-3:
        return r"\textwidth"
    if frac <= 1:
        return f"{frac:.4g}" + r"\textwidth"
    return f"{width_cm:g}cm"


# ---------------------------------------------------------------- rcParams --
def rc_params(style, export) -> dict:
    """Full rcParams dict for a Style + Export spec (applied inside rc_context)."""
    register_fonts()
    rc = dict(mpl.rc_params_from_file(str(HERE / "base.mplstyle"),
                                      use_default_template=True))
    sp = style_preset(style.preset)
    col = presets()["colours"]
    s = {k: max(v * style.font_scale, sp["sizes"]["min"]) for k, v in sp["sizes"].items()}
    lw = style.line_width or sp["line_width"]
    family = sp["font_family"]
    rc.update({
        "font.family": [family, "DejaVu Sans" if sp["sans"] else "DejaVu Serif"],
        "font.serif": [family, "DejaVu Serif"] if not sp["sans"] else rc["font.serif"],
        "font.sans-serif": [family, "DejaVu Sans"] if sp["sans"] else rc["font.sans-serif"],
        "font.size": s["label"],
        "axes.labelsize": s["label"],
        "axes.titlesize": s["title"],
        "xtick.labelsize": s["tick"],
        "ytick.labelsize": s["tick"],
        "legend.fontsize": s["legend"],
        "legend.title_fontsize": s["legend"],
        "figure.titlesize": s["title"],
        "axes.linewidth": sp["axes_line_width"],
        "xtick.major.width": sp["tick_width"],
        "ytick.major.width": sp["tick_width"],
        "lines.linewidth": lw,
        "lines.markersize": style.marker_size or sp["marker_size"],
        "errorbar.capsize": sp["capsize"],
        "axes.grid": bool(style.grid),
        "axes.labelcolor": col["ink"],
        "text.color": col["ink"],
        "axes.edgecolor": col["ink_secondary"],
        "xtick.color": col["ink_secondary"],
        "ytick.color": col["ink_secondary"],
        "xtick.labelcolor": col["ink_secondary"],
        "ytick.labelcolor": col["ink_secondary"],
        "legend.labelcolor": col["ink_secondary"],
        "grid.color": col["grid"],
        "savefig.dpi": export.dpi,
        "savefig.transparent": bool(export.transparent),
    })
    rc.update(mathtext_rc(export.mathtext, family))
    if export.usetex:
        rc.update(usetex_rc(sp))
    return rc


def mathtext_rc(mode: str, family: str) -> dict:
    if mode == "custom":
        return {"mathtext.fontset": "custom", "mathtext.rm": family,
                "mathtext.it": f"{family}:italic", "mathtext.bf": f"{family}:bold",
                "mathtext.sf": family, "mathtext.default": "it"}
    return {"mathtext.fontset": mode if mode in ("cm", "stix", "stixsans", "dejavuserif")
            else "cm", "mathtext.default": "it"}


def usetex_rc(preset: dict) -> dict:
    """LaTeX text rendering using the style preset's font package (e.g. mathptmx)."""
    font_pkg = preset.get("usetex_preamble", r"\usepackage{mathptmx}")
    return {
        "text.usetex": True,
        "text.latex.preamble": "\n".join([
            r"\usepackage[T1]{fontenc}", r"\usepackage[utf8]{inputenc}",
            font_pkg, r"\usepackage{amsmath}", r"\usepackage{gensymb}",
            r"\usepackage{textcomp}"]),
    }


@lru_cache(maxsize=1)
def tex_status() -> tuple[bool, str]:
    """(available, message) for usetex: needs latex, dvipng and the font packages."""
    missing = [t for t in ("latex", "dvipng", "kpsewhich") if not shutil.which(t)]
    if missing:
        return False, ("TeX not found on PATH (" + ", ".join(missing) + "). If VS Code runs "
                       "as a Flatpak, start the app from a normal terminal with ./run.sh.")
    try:
        out = subprocess.run(["kpsewhich", "mathptmx.sty", "gensymb.sty"],
                             capture_output=True, text=True, timeout=10).stdout
    except (OSError, subprocess.SubprocessError) as e:
        return False, f"kpsewhich failed: {e}"
    if "mathptmx.sty" not in out or "gensymb.sty" not in out:
        return False, "LaTeX found but mathptmx.sty or gensymb.sty is missing."
    return True, "LaTeX (mathptmx, gensymb) available."


# ------------------------------------------------------------------ text --
_TEX_MAP = {
    "\\": r"\textbackslash{}", "%": r"\%", "&": r"\&", "#": r"\#", "_": r"\_",
    "{": r"\{", "}": r"\}", "$": r"\$", "^": r"\^{}", "~": r"\~{}",
    "°": r"\degree{}", "µ": r"\textmu{}", "²": r"\textsuperscript{2}", "³": r"\textsuperscript{3}",
    "±": r"$\pm$", "×": r"$\times$", "−": r"$-$", "α": r"$\alpha$", "β": r"$\beta$",
    "δ": r"$\delta$", "σ": r"$\sigma$", "θ": r"$\theta$", "Δ": r"$\Delta$",
    "≥": r"$\geq$", "≤": r"$\leq$", "≈": r"$\approx$", "∈": r"$\in$",
}
_TEX_RE = re.compile("|".join(re.escape(k) for k in _TEX_MAP))


def tex_escape(text: str) -> str:
    """Escape LaTeX specials (single pass) outside $...$ maths, for usetex."""
    if not text:
        return text
    parts = re.split(r"(?<!\\)(\$[^$]*\$)", text) if text.count("$") % 2 == 0 else [text]
    out = []
    for p in parts:
        if len(p) > 1 and p.startswith("$") and p.endswith("$"):
            out.append(p)
        else:
            out.append(_TEX_RE.sub(lambda m: _TEX_MAP[m.group(0)], p))
    return "".join(out)


_MATH_DIGITS = re.compile(r"(?<![\\A-Za-z])(\d+(?:\.\d+)?)")


def mathtext_escape(text: str) -> str:
    """Prepare text for mathtext: literal $ if unbalanced; upright digits inside maths.

    LaTeX sets digits upright even in maths; mathtext (default "it") would slant
    them, so "$\\sigma = 1.2$" becomes "$\\sigma = \\mathrm{1.2}$".
    """
    if not text or "$" not in text:
        return text
    if text.count("$") % 2 == 1:
        return text.replace("$", r"\$")
    return _upright_digits(text)


@lru_cache(maxsize=2048)
def _upright_digits(text: str) -> str:
    from matplotlib.mathtext import MathTextParser
    parts = re.split(r"(\$[^$]*\$)", text)
    out = []
    for p in parts:
        if p.startswith("$") and p.endswith("$") and len(p) > 1:
            q = "$" + _MATH_DIGITS.sub(r"\\mathrm{\1}", p[1:-1]) + "$"
            try:
                MathTextParser("path").parse(q)
                p = q
            except ValueError:
                pass   # e.g. \hspace{3}: keep the user's maths unchanged
        out.append(p)
    return "".join(out)


# --------------------------------------------------------------- palettes --
def palette(style, n: int) -> list[str]:
    c = presets()["colours"]
    if style.greyscale or style.palette == "greyscale":
        base = c["greyscale"]
    elif style.palette in ("default", "", None):
        base = c["palette"]
    else:
        cmap = mpl.colormaps.get(style.palette)
        if cmap is None:
            base = c["palette"]
        elif getattr(cmap, "N", 256) <= 20:   # qualitative map: take its colours in order
            base = [to_hex(cmap(i)) for i in range(cmap.N)]
        else:
            base = [to_hex(cmap(0.15 + 0.7 * i / max(n - 1, 1))) for i in range(n)]
    return [base[i % len(base)] for i in range(n)]


def markers() -> list[str]:
    return list(presets()["colours"]["markers"])


def linestyles() -> list:
    out = []
    for ls in presets()["colours"]["linestyles"]:
        out.append((ls[0], tuple(ls[1])) if isinstance(ls, list) else ls)
    return out


def ink() -> str:
    return presets()["colours"]["ink"]


def ink_secondary() -> str:
    return presets()["colours"]["ink_secondary"]
