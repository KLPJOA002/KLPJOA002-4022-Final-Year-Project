# rsplot — figures for the RealSense characterisation and 3-D scanning results

A local, point-and-click figure maker. Every setting (data, metrics, filters,
aggregation, styling, size, saving) is a control in the browser UI; figures are
drawn with matplotlib and exported as thesis-ready PDF (vector, fonts embedded),
PNG and SVG, each with a settings file so the figure can be re-opened and edited.

## Run it

```sh
cd ~/Documents/4022/Data/Plotter
./run.sh                 # opens http://127.0.0.1:8080 in your browser; Ctrl+C stops it
./run.sh --port 8090     # another port;  --no-browser  to not open a tab
```

`run.sh` works from any terminal, including VS Code's Flatpak terminal (it re-launches
on the host so the host TeX Live is available for "Use LaTeX for text"). The app only
listens on 127.0.0.1.

**First start:** a list of the CSV files found in the project opens. Recognised files
are ticked except older copies (e.g. `Filter_Results/results.csv`, superseded by
`V3/`); `*_Old` folders and the raw per-trial `Data/` folders are skipped. Click
**Add selected to the list**. Later: **Add dataset** (pick any CSV — the detected family
is shown and can be overridden) or the search icon.

Setup from scratch (already done): `python3 -m venv .venv && .venv/bin/pip install -r
requirements.txt && .venv/bin/python tools/build_fonts.py` — run with the *host* Python
when inside Flatpak (`flatpak-spawn --host ...`).

## Making a figure

1. **Data tab** — plot type, metric(s) (★ = main metrics; RMSE untrimmed / trim 1 % /
   trim 5 % are checkboxes, shown overlaid or side by side), x axis, colour, small
   multiples, marker style, "separate by", aggregation (mean / median / min / max /
   count) and spread (SD, SEM, IQR, min–max, 95 % CI), secondary indicator panel
   (outlier fraction), and the plot type's own options.
2. **Filters tab** — add a filter on any column: tick values, or a range slider.
   Nothing is filtered by default and adding a filter changes nothing until you
   narrow it. Active filters appear as removable chips above the preview with the row
   count.
3. **Not fixed** (amber bar) — every factor that varies within a plotted point and is
   neither on an axis, colour or facet nor filtered is listed with its values, and is
   stated in the automatic footnote. Buttons: *Fix to one value*, *Colour by*, *Facet by*.
4. **Style tab** — preset (Thesis = Times/TeX Gyre Termes to match `mathptmx`, Slides,
   Poster, Thesis Garamond), title/subtitle/footnote, axis labels, renaming columns and
   categories, limits, log axes, ticks, grid, legend, palette (colour-blind safe,
   greyscale print mode), colour per series, markers, line widths, margins, font scale,
   *Reset to defaults*, and named presets (*Save the current look as a preset*).
5. **Size & text tab** — size preset (thesis full / caption / ⅔ / half width, slide,
   poster), width/height in cm, LaTeX text rendering, maths font, the thesis text width
   (18.0 cm) and maximum figure height (22 cm), screen calibration for **Actual size**
   (top right), which shows the figure at true scale inside the 18 cm text block.
6. **Save figure** — folder (Browse …), file name, PDF / PNG / SVG, PNG dpi, transparent
   background. Existing files are never replaced silently: *Overwrite*, *Save as
   name_2* or *Cancel*. The result dialog shows the `\includegraphics` line and a figure
   environment to copy (paths relative to `Report/uct-thesis-template` when saved inside
   it), plus the "what was fixed / averaged" text for the caption.

**Re-editing:** every save writes `<name>.rsplot.json` next to the figure (data file and
fingerprint, family, columns, filters, aggregation, style, size, tool version). Use
**Recent** or **Open settings** to load it back; you are told if the data file changed
since.

## Plot types

| Type | Notes |
|---|---|
| Line with spread | error bars (default), band, both or none; auto dodge so bars do not overlap |
| Scatter / metric vs metric | x may be a metric; per-point error bars when aggregated; trend line; jitter |
| Grouped bar | vertical / horizontal, error bars, value labels; hatching in greyscale |
| Box / violin | + individual points; whiskers 1.5 × IQR, min–max or 5–95 %; n per box |
| Histogram / CDF | step / filled / bars, density, shared bins, log x |
| Per-frame time series | one line per trial automatically; rolling median |
| Heatmap | two factor axes, cell values (+ n), grey = no data; colour centre on a value, the median, or a baseline configuration (matched on height/rotation etc. when the baseline has them), shown as value / difference / % change |
| Top-N ranking | from ranking files or computed from a sweep; best first by the metric's direction; minimum n; highlighted reference (e.g. *baseline (no filters)*); dots on a zoomed axis when values are close |

## Extending

**A dataset family** — add an entry to `rsplot/registry/families.yaml`: `detect` (columns
that must / must not be present; never file names), `factors`, `replicates`, `ids`,
`ignore` (glob patterns not loaded — keeps 250-column files light), `metrics_pinned`,
`defaults` (starting plot), optionally `baseline`, `rank_item`, `time_column`,
`series_unit`. Unknown files fall back to `generic` (auto-detected columns).

**Labels and units** — `rsplot/registry/labels.yaml`: `columns` (label, unit, `better:
lower|higher`, `fraction`), regex `patterns` (e.g. `completeness@Nmm`), category `values`,
`pinned_metrics`, RMSE/MAE/bias `variant_groups`. Any label can also be overridden per
figure in the UI.

**A plot type** — drop a module into `rsplot/plots/`:

```python
from . import VALUE, Option, register_plot

@register_plot("dots", "Dot plot", x="discrete", default_agg="mean",
               options=[Option("size", "float", 4.0, "Dot size", min=1, max=20)])
def dots(ctx):                      # ctx: one facet's axes + data, no column names
    for s in ctx.series():          # one series per colour / style group
        ctx.ax.plot(ctx.xpos(s.df), s.df[VALUE], "o", color=s.colour,
                    markersize=ctx.opts["size"])
        ctx.add_handle(s, kind="marker")
    ctx.set_categorical_xticks()
```

It appears in the UI with controls generated from its `options`; add a case to
`tests/test_plots.py::CASES` (a test fails until you do).

**A style preset** — `rsplot/style/presets.yaml`: `styles` (font family, LaTeX font
package, text sizes, line weights) and `sizes` (width as a fraction of the text width or
in cm, aspect, style). `rsplot/style/base.mplstyle` holds everything common (colours,
spines, ticks, PDF Type 42 font embedding). Changing either restyles every figure.
Personal presets saved from the UI are kept in `.state/style_presets.json`.

## Files

```
rsplot/registry/   families.yaml, labels.yaml, detection + label lookup
rsplot/data.py     loading (column pruning, cache), type normalisation, profiling
rsplot/spec.py     PlotSpec — the JSON-serialisable description of a figure
rsplot/pipeline.py filters, multi-metric melt, aggregation + spread, "not fixed" analysis, footnote
rsplot/render.py   PlotSpec -> matplotlib Figure (headless), layout, legend, colour bar
rsplot/plots/      plot-type plugins
rsplot/style/      base.mplstyle, presets.yaml, bundled TrueType fonts (+ licences)
rsplot/export.py   saving, sidecars, overwrite policy, LaTeX snippets, reloading
rsplot/ui/         NiceGUI app (app.py), file picker, UI-independent logic (session.py)
tests/             headless tests on small synthetic datasets (one per family)
tools/             build_fonts.py, host.sh, demo_stage_*.py, dev_server.sh, ui_check.py
.state/            your datasets, recent figures, presets, settings, last figure
```

## Tests

```sh
tools/host.sh python -m pytest -q tests
```

`tools/ui_check.py` (dev only) drives the running UI with headless Chromium via
Playwright and saves screenshots; it is not needed to use the app.

## Notes

- Fonts: the thesis uses `\usepackage{mathptmx}`; figures use TeX Gyre Termes (the same
  Nimbus Roman design), converted from TeX Live's OTF to TrueType by
  `tools/build_fonts.py`, because matplotlib cannot embed CFF-based OTF fonts validly in
  PDF. With "Use LaTeX for text" the text goes through `mathptmx` itself.
- Exported PDFs are PDF 1.4 with subset, searchable TrueType fonts (pdfLaTeX-safe).
- The data folders are only read; outputs go to the folder chosen in the Save dialog.
