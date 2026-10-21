# rstable — LaTeX results tables from rsplot figures

A local, point-and-click table maker that goes with `../Plotter` (rsplot). You pick a
figure made in rsplot. The table takes its data file, filters, grouping and statistic
and runs them through **rsplot's own pipeline**, so every value is exactly the point the
figure drew: centre, spread bounds and n. You export it as a booktabs/makecell table in
the thesis style.

## Run it

```sh
cd ~/Documents/4022/Data/Table_Maker
./run.sh                 # opens http://127.0.0.1:8081 (rsplot uses 8080, so both can run)
./run.sh --port 8091     # another port;  --no-browser  to not open a tab
```

It uses rsplot's virtual environment (`../Plotter/.venv`), so there is nothing to install.
`run.sh` re-launches on the host from VS Code's Flatpak terminal, so TeX Live is
available for the LaTeX preview.

## Making a table

1. **From figure** lists the figures rsplot saved (its *Recent* list, then every
   `*.rsplot.json` under `Report/uct-thesis-template/figs`). You can also use
   **rsplot's current figure**, which is the one open in rsplot even if it was never
   saved, or **Browse** for any `.rsplot.json`.
2. **Data tab**: the source figure and the statistic. By default the statistic is
   *Same as the figure*, for example median with IQR, or the per-trial median with the
   IQR over frames for the planar summary files. Turn that off to use another statistic,
   such as mean ± SD. The table then no longer matches the figure, and the status bar
   says so. Here you also choose which metrics are shown and in what order.
3. **Layout tab**: every grouping of the figure is a row or a column. That covers its
   x axis, colour, facets, heatmap rows and the metric. The order sets the nesting,
   outer first, and at most two groupings go across the columns. Example: object across
   the top and metrics under each object, giving `\multicolumn` and `\cmidrule`
   automatically. You can also hide or rename individual values, choose whether outer
   row labels repeat, and pick the gap between row groups (`\addlinespace` or
   `\midrule`).
4. **Format tab**:
   - **Spread shown as**:
     - `1.22 ± 0.05` for SD and SEM. For an interval it is half its width.
     - `1.22 [1.10, 1.31]`, which is the automatic choice for IQR, range and 95 % CI.
     - `1.22 (1.10–1.31)`.
     - `1.22 (0.21)`, the interval width.
     - A separate column.
     - Centre only.
   - **Name of the statistic**: put it under every column heading (for example
     `median [Q1, Q3]` or `mean ± SD`), in the caption, both, or nowhere.
   - **n**: as a range in the caption, as a column, or not shown.
   - Decimals: automatic (3 significant figures on the column's largest value), or set
     per metric.
   - Fractions shown as %.
   - A proper minus sign.
   - Bold for the best value. The direction comes from `labels.yaml` (`better:`); bias
     defaults to "closest to 0". Compare per column or within row groups.
   - Heading overrides (`|` forces a line break) and the automatic line length.
5. **Caption & output tab**: your caption, typed as LaTeX. The tool appends a sentence
   naming the statistic and n, and rsplot's *Fixed: …; Median taken over: …* text; both
   can be switched off. The same tab sets the label, placement, font size
   (`\small` …), `\tabcolsep`, `\makecell`, `\resizebox` and where to save.
6. **Preview**:
   - *Quick preview*: instant, in HTML.
   - *LaTeX preview*: typeset by xelatex with TeX Gyre Termes at 11 pt on the thesis's
     18 cm text width. A hairline shows that width, and you are warned when the table is
     wider.
   - **Copy LaTeX** copies the table environment.
7. **Save table** writes three files:
   - `<name>.tex`: the `table` environment, for `\input{...}`.
   - `<name>.csv`: the exact numbers (centre, lo, hi, n) with the formatted text.
   - `<name>.rstable.json`: everything needed to re-open the table.

   Existing files are never replaced silently. You get *Overwrite*, *Save as new name*
   or *Cancel*. The default folder is `Report/uct-thesis-template/tables`.

**Re-editing:** use **Recent tables** or **Open table**. The figure's settings are stored
inside the table file, so a table stays reproducible. If the figure was saved again
later, a banner offers **Re-read figure**. You are also told if the data file changed.

## Notes

- The table needs `booktabs` and `makecell`, which are already in `0_main.tex`.
- Box/violin and histogram figures draw raw rows. A table always gives one value per
  group, using the figure's statistic settings. If the figure did not aggregate
  (statistic "none") and several values land in one cell, they are numbered in a `#`
  column, and a warning suggests choosing a statistic.
- The 95 % CI is about the mean, whichever centre is shown. This is the same as rsplot.
- Labels, units and category names come from rsplot's `registry/labels.yaml` and from
  the figure's own renames, so tables and figures use the same wording.

## Files

```
rstable/spec.py    TableSpec: source figure (embedded PlotSpec), statistic, layout, format, output
rstable/table.py   figure spec -> rsplot pipeline -> Table (cells, rows/columns, statistic, n)
rstable/render.py  Table -> LaTeX (booktabs/makecell), HTML preview, tidy CSV
rstable/store.py   opening rsplot sessions, saving/loading tables, LaTeX preview (xelatex)
rstable/app.py     NiceGUI UI
tests/             headless tests (synthetic data + every saved thesis figure, incl. LaTeX)
tools/host.sh      run a command with rsplot's venv and both packages on PYTHONPATH
.state/            recent tables, last table, last folder
```

## Tests

```sh
tools/host.sh python -m pytest -q tests
```
