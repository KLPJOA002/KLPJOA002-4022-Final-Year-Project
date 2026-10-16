"""Convert the TeX Live TeX Gyre Termes / EB Garamond / Fira Sans OTFs (CFF) to TrueType.

matplotlib's Type 42 PDF embedding expects TrueType (glyf) outlines; given a
CFF-flavoured OTF it writes the CFF data into a TrueType font slot, which is not
valid PDF. Converting once with fontTools (cu2qu) avoids that. TeX Gyre Termes
(GUST Font License) is the Times clone matching pdfLaTeX's mathptmx; EB Garamond
and Fira Sans are under the SIL Open Font License. All permit this conversion.

Run:  .venv/bin/python tools/build_fonts.py
"""
from pathlib import Path
import shutil
import sys

from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

TEXLIVE = Path("/usr/share/texlive/texmf-dist")
SOURCES = {
    "termes": ["texgyretermes-regular", "texgyretermes-italic", "texgyretermes-bold",
               "texgyretermes-bolditalic"],
    "ebgaramond": ["EBGaramond-Regular", "EBGaramond-Italic", "EBGaramond-Bold",
                   "EBGaramond-BoldItalic", "EBGaramond-Medium", "EBGaramond-SemiBold"],
    "fira": ["FiraSans-Regular", "FiraSans-Italic", "FiraSans-Bold", "FiraSans-BoldItalic"],
}
LICENSES = {"termes": "doc/fonts/tex-gyre/GUST-FONT-LICENSE.txt",
            "fira": "doc/fonts/fira*/LICENSE*"}
OUT = Path(__file__).resolve().parents[1] / "rsplot" / "style" / "fonts"


def otf_to_ttf(font: TTFont, max_err: float = 1.0) -> None:
    order = font.getGlyphOrder()
    glyphset = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = order
    glyf.glyphs = {}
    for name in order:
        pen = TTGlyphPen(glyphset)
        glyphset[name].draw(Cu2QuPen(pen, max_err, reverse_direction=True))
        glyf.glyphs[name] = pen.glyph()
    font["loca"] = newTable("loca")
    font["glyf"] = glyf
    del font["CFF "]
    if "VORG" in font:
        del font["VORG"]
    glyf.compile(font)
    hmtx = font["hmtx"]
    for name, g in glyf.glyphs.items():
        if hasattr(g, "xMin"):
            hmtx[name] = (hmtx[name][0], g.xMin)
    maxp = newTable("maxp")
    maxp.tableVersion = 0x00010000
    for attr in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs",
                 "maxInstructionDefs", "maxStackElements", "maxSizeOfInstructions",
                 "maxComponentElements"):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    font["maxp"] = maxp
    post = font["post"]
    post.formatType = 2.0
    post.extraNames = []
    post.mapping = {}
    post.glyphOrder = order
    font["head"].glyphDataFormat = 0
    font.sfntVersion = "\x00\x01\x00\x00"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    roots = [TEXLIVE, Path("/run/host") / TEXLIVE.relative_to("/")]
    root = next((r for r in roots if r.exists()), None)
    if root is None:
        print("TeX Live fonts not found. Download static TTFs instead:\n"
              "  EB Garamond: https://fonts.google.com/specimen/EB+Garamond\n"
              "  Fira Sans:   https://fonts.google.com/specimen/Fira+Sans\n"
              f"and copy the .ttf files into {OUT}")
        return 1
    for pkg, names in SOURCES.items():
        for name in names:
            src = next(root.glob(f"fonts/opentype/**/{name}.otf"), None)
            if src is None:
                print("missing", name)
                continue
            font = TTFont(src)
            otf_to_ttf(font)
            font.save(OUT / f"{name}.ttf")
            print("wrote", OUT / f"{name}.ttf")
        lic = next(root.glob(LICENSES.get(pkg, f"doc/fonts/{pkg}*/OFL.txt")), None)
        if lic:
            shutil.copy(lic, OUT / f"LICENSE-{pkg}.txt")
    return 0


if __name__ == "__main__":
    sys.exit(main())
