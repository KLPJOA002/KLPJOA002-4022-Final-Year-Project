"""rstable UI (NiceGUI): build a LaTeX results table from an rsplot figure session.

Run:  ./run.sh            (or: python -m rstable.app [--port 8081] [--no-browser])
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import functools
from pathlib import Path

from nicegui import background_tasks, run, ui

from rsplot import export as rsx
from rsplot import registry as reg
from rsplot.pipeline import METRIC, X_VALUE
from rsplot.spec import SPREAD_LABELS
from rsplot.ui.files import pick_path

from . import __version__
from . import store
from .render import PREVIEW_CSS, to_html, to_latex
from .spec import (BEST_MODES, FONT_SIZES, GROUP_SEPARATORS, N_MODES, SPREAD_FORMATS,
                   STAT_PLACES, TableSpec)
from .table import DUP, Table, build, key_label, value_text

DEBOUNCE_S = 0.2
LATEX_DEBOUNCE_S = 0.8
FUNCS = {"mean": "Mean", "median": "Median", "min": "Minimum", "max": "Maximum",
         "count": "Count"}
STORED_STATS = {"median": "Per-trial median", "mean": "Per-trial mean"}
STORED_SPREADS = {"iqr": "IQR over frames", "std": "± SD over frames", "none": "None"}
BEST_LABELS = {"auto": "Automatic", "lower": "Lower is better", "higher": "Higher is better",
               "zero": "Closest to 0", "none": "Do not mark"}


def in_page(coro_fn):
    @functools.wraps(coro_fn)
    async def wrapper(self, *a, **kw):
        with self.root:
            return await coro_fn(self, *a, **kw)
    return wrapper


class App:
    def __init__(self):
        self.ts: TableSpec | None = None
        self.t: Table | None = None
        self.error = ""
        self.notes: list[str] = []
        self.view = "html"
        self.version = 0
        self.latex_version = 0
        self.compiled: store.Compiled | None = None
        self.compiling = False

    # ================================================================ layout ==
    def build(self):
        ui.add_head_html(f"<style>{PREVIEW_CSS}"
                         ".rs-sec {font-size:.72rem;text-transform:uppercase;letter-spacing:.06em;"
                         "color:#6b7280;margin-top:.6rem;}"
                         ".rs-hint {font-size:.75rem;color:#6b7280;}</style>")
        with ui.header().classes("items-center bg-slate-800 py-1 gap-2"):
            ui.label("rstable").classes("text-lg font-semibold")
            self.source_chip()
            ui.space()
            ui.button("From figure", icon="insert_chart", on_click=self.source_dialog) \
                .props("flat dense no-caps color=white") \
                .tooltip("Start a table from a figure made in rsplot")
            ui.button("Recent tables", icon="history", on_click=self.recent_dialog) \
                .props("flat dense no-caps color=white")
            ui.button("Open table", icon="file_open", on_click=self.open_table_dialog) \
                .props("flat dense no-caps color=white") \
                .tooltip("Re-open a saved table from its .rstable.json file")
            ui.button("Save table", icon="save", on_click=self.save_dialog) \
                .props("unelevated dense no-caps color=green-7")
        with ui.left_drawer(value=True).props("width=470 bordered").classes("p-0"):
            with ui.tabs().classes("w-full").props("dense no-caps") as tabs:
                t_data = ui.tab("Data")
                t_lay = ui.tab("Layout")
                t_fmt = ui.tab("Format")
                t_out = ui.tab("Caption & output")
            with ui.tab_panels(tabs, value=t_data).classes("w-full"):
                with ui.tab_panel(t_data).classes("p-3"):
                    self.data_panel()
                with ui.tab_panel(t_lay).classes("p-3"):
                    self.layout_panel()
                with ui.tab_panel(t_fmt).classes("p-3"):
                    self.format_panel()
                with ui.tab_panel(t_out).classes("p-3"):
                    self.output_panel()
        with ui.column().classes("w-full p-3 gap-2") as self.root:
            self.status_area()
            with ui.row().classes("items-center gap-2"):
                ui.toggle({"html": "Quick preview", "latex": "LaTeX preview (thesis width)"},
                          value=self.view, on_change=lambda e: self.set_view(e.value)) \
                    .props("dense no-caps unelevated")
                ui.button("Copy LaTeX", icon="content_copy", on_click=self.copy_latex) \
                    .props("outline dense no-caps")
            self.preview()
            with ui.expansion("LaTeX source", icon="code", value=True).classes("w-full"):
                self.latex_source()
        ui.timer(0.1, self.startup, once=True)

    @in_page
    async def startup(self):
        ts = store.last_table()
        if ts is not None and ts.source.plot:
            self.ts = ts
            self.notes = store.source_notes(ts)
            await self.update(panels=True)
        else:
            self.source_dialog()

    # ============================================================== updating ==
    def changed(self, panels: bool = False):
        background_tasks.create(self.update(panels=panels))

    @in_page
    async def update(self, panels: bool = False):
        if self.ts is None:
            return
        self.version += 1
        v = self.version
        await asyncio.sleep(DEBOUNCE_S)
        if v != self.version:
            return
        ts = self.ts
        try:
            t = await run.io_bound(build, ts)
            self.t, self.error = t, ""
            store.save_last(ts)
        except Exception as e:   # shown in the preview pane instead of crashing the UI
            import traceback
            traceback.print_exc()
            self.t, self.error = None, f"{type(e).__name__}: {e}"
        if v != self.version:
            return
        self.compiled = None
        self.status_area.refresh()
        self.preview.refresh()
        self.latex_source.refresh()
        self.source_chip.refresh()
        if panels:
            self.refresh_panels()
        if self.view == "latex":
            await self.compile_latex()

    def refresh_panels(self):
        self.data_panel.refresh()
        self.layout_panel.refresh()
        self.format_panel.refresh()
        self.output_panel.refresh()

    def set_view(self, v):
        self.view = v
        self.preview.refresh()
        if v == "latex" and self.compiled is None:
            background_tasks.create(self.compile_latex())

    @in_page
    async def compile_latex(self):
        if self.t is None:
            return
        self.latex_version += 1
        v = self.latex_version
        await asyncio.sleep(LATEX_DEBOUNCE_S)
        if v != self.latex_version or self.t is None:
            return
        self.compiling = True
        self.preview.refresh()
        latex = to_latex(self.t, self.ts)
        res = await run.io_bound(store.compile_preview, latex)
        if v != self.latex_version:
            return
        self.compiled, self.compiling = res, False
        self.preview.refresh()

    # ================================================================ header ==
    @ui.refreshable
    def source_chip(self):
        if self.ts is None:
            ui.label("No figure loaded").classes("text-sm text-gray-300")
            return
        sc = self.ts.source.sidecar
        name = Path(sc).name if sc else "rsplot's unsaved figure"
        ptype = self.ts.source.plot.get("plot_type", "?")
        ui.label(f"{name}  ·  {ptype}").classes("text-sm text-gray-200") \
            .tooltip(sc or "Taken from rsplot's last figure")

    # =========================================================== status area ==
    @ui.refreshable
    def status_area(self):
        if self.ts is None:
            ui.label("Start with “From figure” to choose a figure made in rsplot.") \
                .classes("text-gray-500")
            return
        for n in self.notes:
            with ui.row().classes("w-full bg-amber-50 border border-amber-300 rounded px-3 py-1 "
                                  "items-center no-wrap"):
                ui.icon("info", color="amber-8")
                ui.label(n).classes("text-sm grow")
                if "saved again" in n:
                    ui.button("Re-read figure", on_click=self.reread_figure) \
                        .props("flat dense no-caps")
        if self.error:
            with ui.row().classes("w-full bg-red-50 border border-red-300 rounded px-3 py-2"):
                ui.icon("error", color="negative")
                ui.label(self.error).classes("text-sm text-negative")
            return
        t = self.t
        if t is None:
            return
        with ui.row().classes("w-full items-center gap-2"):
            ui.chip(f"Statistic: {t.stat.short()}", icon="functions") \
                .props("outline dense color=blue-grey-8")
            if t.n_text:
                ui.chip(t.n_text, icon="tag").props("outline dense color=blue-grey-8")
            ui.chip(f"{len(t.rows)} rows × {len(t.cols)} value columns", icon="table_rows") \
                .props("outline dense color=blue-grey-8")
            src = "as in the figure" if t.stat.source == "figure" else \
                f"changed from the figure's {t.figure_stat}"
            ui.label(src).classes("text-xs text-gray-500")
        for w in t.warnings:
            with ui.row().classes("w-full bg-amber-50 border border-amber-300 rounded px-3 py-1 "
                                  "items-center no-wrap"):
                ui.icon("warning", color="amber-8")
                ui.label(w).classes("text-sm")

    # ================================================================ preview ==
    @ui.refreshable
    def preview(self):
        with ui.card().classes("w-full p-0 bg-white").props("flat bordered"):
            if self.t is None:
                ui.label("No table yet.").classes("p-4 text-gray-500")
                return
            if self.view == "html":
                ui.html(to_html(self.t, self.ts), sanitize=False).classes("w-full")
                return
            c = self.compiled
            if self.compiling or c is None:
                with ui.row().classes("p-4 items-center"):
                    ui.spinner()
                    ui.label("Typesetting with LaTeX …").classes("text-gray-500")
                return
            if c.error:
                ui.label(f"LaTeX failed ({c.engine}):").classes("p-3 text-negative")
                ui.code(c.error).classes("w-full")
                return
            if c.overfull:
                ui.label("The table is wider than the text width (18 cm): shorten headings, "
                         "use a smaller font, reduce the column gap or move a factor to the "
                         "columns / rows.").classes("p-2 text-amber-9 text-sm")
            b64 = base64.b64encode(c.png).decode()
            ui.html(f'<img src="data:image/png;base64,{b64}" style="max-width:100%;'
                    f'image-rendering:auto">', sanitize=False).classes("p-2 w-full")
            ui.label(f"Typeset with {c.engine}, TeX Gyre Termes at 11 pt; the hairline marks "
                     "the thesis text width.").classes("rs-hint px-3 pb-2")

    @ui.refreshable
    def latex_source(self):
        if self.t is None:
            return
        ui.code(to_latex(self.t, self.ts), language="latex").classes("w-full text-xs")
        ui.label("Needs \\usepackage{booktabs} and \\usepackage{makecell} (both already in "
                 "0_main.tex).").classes("rs-hint")

    def copy_latex(self):
        if self.t is None:
            return
        ui.clipboard.write(to_latex(self.t, self.ts))
        ui.notify("LaTeX copied", type="positive")

    # ============================================================ data panel ==
    @ui.refreshable
    def data_panel(self):
        ts, t = self.ts, self.t
        if ts is None:
            ui.label("No figure loaded.").classes("text-gray-500")
            return
        plot = ts.source.plot
        ui.label("Figure").classes("rs-sec")
        ui.label(ts.source.sidecar or "rsplot's last (unsaved) figure") \
            .classes("text-xs break-all")
        ui.label(f"Plot type: {plot.get('plot_type')}  ·  data: "
                 f"{Path(plot.get('dataset', {}).get('path', '')).name}") \
            .classes("text-xs text-gray-600")
        if ts.source.sidecar:
            ui.button("Re-read figure", icon="refresh", on_click=self.reread_figure) \
                .props("flat dense no-caps").tooltip("Take the figure's settings again from "
                                                     "its .rsplot.json (after re-saving it)")

        ui.label("Statistic").classes("rs-sec")
        st = ts.stats
        fig = t.figure_stat if t else ""
        ui.switch(f"Same as the figure{f' ({fig})' if fig else ''}", value=st.inherit,
                  on_change=lambda e: (setattr(st, "inherit", e.value),
                                       self.changed(panels=True)))
        if not st.inherit:
            summary = t is not None and t.ds is not None and t.ds.is_summary()
            with ui.row().classes("w-full gap-2 no-wrap"):
                ui.select(FUNCS, value=st.func, label="Value",
                          on_change=lambda e: (setattr(st, "func", e.value), self.changed())) \
                    .props("dense outlined").classes("grow")
                ui.select({k: v for k, v in SPREAD_LABELS.items()}, value=st.spread,
                          label="Spread",
                          on_change=lambda e: (setattr(st, "spread", e.value), self.changed())) \
                    .props("dense outlined").classes("grow")
            if summary:
                ui.label("Per-trial files: the stored statistic of each trial (used when "
                         "Value is not aggregating trials)").classes("rs-hint")
                with ui.row().classes("w-full gap-2 no-wrap"):
                    ui.select(STORED_STATS, value=st.stored_stat, label="Stored value",
                              on_change=lambda e: (setattr(st, "stored_stat", e.value),
                                                   self.changed())) \
                        .props("dense outlined").classes("grow")
                    ui.select(STORED_SPREADS, value=st.stored_spread, label="Stored spread",
                              on_change=lambda e: (setattr(st, "stored_spread", e.value),
                                                   self.changed())) \
                        .props("dense outlined").classes("grow")
            ui.label("The table then no longer shows exactly what the figure plotted.") \
                .classes("rs-hint text-amber-9")

        ui.label("Metrics").classes("rs-sec")
        if t is None:
            return
        all_metrics = list(dict.fromkeys(ts.layout.metrics + [m for m in
                                                              _plot_metrics(ts)]))
        for i, m in enumerate(all_metrics):
            on = m in ts.layout.metrics
            with ui.row().classes("w-full items-center no-wrap gap-1"):
                ui.checkbox(reg.axis_label(m), value=on,
                            on_change=lambda e, m=m: self.toggle_metric(m, e.value)) \
                    .classes("grow text-sm")
                ui.button(icon="arrow_upward", on_click=lambda m=m: self.move_metric(m, -1)) \
                    .props("flat dense size=sm").set_enabled(on and i > 0)
                ui.button(icon="arrow_downward", on_click=lambda m=m: self.move_metric(m, 1)) \
                    .props("flat dense size=sm").set_enabled(on)

    def toggle_metric(self, m, on):
        ms = self.ts.layout.metrics
        if on and m not in ms:
            ms.append(m)
        elif not on and m in ms:
            if len(ms) == 1:
                ui.notify("Keep at least one metric.", type="warning")
                self.data_panel.refresh()
                return
            ms.remove(m)
        self.changed(panels=True)

    def move_metric(self, m, d):
        ms = self.ts.layout.metrics
        if m not in ms:
            return
        i = ms.index(m)
        j = min(max(i + d, 0), len(ms) - 1)
        ms[i], ms[j] = ms[j], ms[i]
        self.changed(panels=True)

    async def reread_figure(self):
        try:
            notes = store.refresh_from_sidecar(self.ts)
        except Exception as e:
            ui.notify(str(e), type="negative")
            return
        self.notes = notes
        ui.notify("Figure settings re-read", type="positive")
        await self.update(panels=True)

    # ========================================================== layout panel ==
    @ui.refreshable
    def layout_panel(self):
        ts, t = self.ts, self.t
        if ts is None or t is None:
            ui.label("No table yet.").classes("text-gray-500")
            return
        lay = ts.layout
        ui.label("Rows and columns").classes("rs-sec")
        ui.label("Every grouping of the figure (axis, colour, facets, metric) is a row or "
                 "column; order = nesting (outer first). At most two go across the columns.") \
            .classes("rs-hint")
        for where, keys in (("rows", lay.row_keys), ("cols", lay.col_keys)):
            ui.label("Down the rows" if where == "rows" else "Across the columns") \
                .classes("text-sm font-medium mt-2")
            if not keys:
                ui.label("(none)").classes("rs-hint")
            for i, k in enumerate(keys):
                with ui.row().classes("w-full items-center no-wrap gap-1 border-b"):
                    ui.label(self.key_name(k)).classes("grow text-sm")
                    ui.button(icon="arrow_upward", on_click=lambda k=k: self.move_key(k, -1)) \
                        .props("flat dense size=sm").set_enabled(i > 0)
                    ui.button(icon="arrow_downward", on_click=lambda k=k: self.move_key(k, 1)) \
                        .props("flat dense size=sm").set_enabled(i < len(keys) - 1)
                    if where == "rows" and k != X_VALUE:
                        ui.button("→ columns", on_click=lambda k=k: self.swap_key(k)) \
                            .props("flat dense no-caps size=sm")
                    elif where == "cols":
                        ui.button("→ rows", on_click=lambda k=k: self.swap_key(k)) \
                            .props("flat dense no-caps size=sm")
        ui.button("Swap rows and columns", icon="swap_horiz", on_click=self.transpose) \
            .props("flat dense no-caps").classes("mt-1")

        ui.label("Row labels").classes("rs-sec")
        ui.switch("Repeat the outer labels on every row", value=lay.repeat_labels,
                  on_change=lambda e: (setattr(lay, "repeat_labels", e.value), self.changed()))
        ui.select(GROUP_SEPARATORS, value=lay.group_sep, label="Between groups of the first row",
                  on_change=lambda e: (setattr(lay, "group_sep", e.value), self.changed())) \
            .props("dense outlined").classes("w-full")

        ui.label("Values shown (and renamed)").classes("rs-sec")
        fm = ts.format
        for k, vals in t.all_values.items():
            hidden = set(lay.hidden.get(k, []))
            with ui.expansion(f"{self.key_name(k)}  ({len(vals) - len(hidden & set(map(_vk, vals)))}"
                              f" of {len(vals)})").classes("w-full").props("dense"):
                for v in vals:
                    vk = _vk(v)
                    rk = reg.value_key(k, v) if v is not None else f"{k}=n/a"
                    with ui.row().classes("w-full items-center no-wrap gap-1"):
                        ui.checkbox(value=vk not in hidden,
                                    on_change=lambda e, k=k, vk=vk: self.hide(k, vk, not e.value))
                        auto = value_text(k, v, t.plot, None)
                        ui.input(value=fm.value_labels.get(rk, ""), placeholder=auto,
                                 on_change=lambda e, rk=rk: self.rename_value(rk, e.value)) \
                            .props("dense").classes("grow")

    def key_name(self, k):
        if self.t is None:
            return k
        return key_label(k, self.t.plot, x_metric=self.t.x_metric).split(" (")[0]

    def move_key(self, k, d):
        lay = self.ts.layout
        lst = lay.row_keys if k in lay.row_keys else lay.col_keys
        i = lst.index(k)
        j = min(max(i + d, 0), len(lst) - 1)
        lst[i], lst[j] = lst[j], lst[i]
        self.changed(panels=True)

    def swap_key(self, k):
        lay = self.ts.layout
        if k in lay.row_keys:
            if len(lay.col_keys) >= 2:
                ui.notify("At most two groupings can go across the columns.", type="warning")
                return
            lay.row_keys.remove(k)
            lay.col_keys.insert(0, k)
        else:
            lay.col_keys.remove(k)
            lay.row_keys.append(k)
        self.changed(panels=True)

    def transpose(self):
        lay = self.ts.layout
        rows = [k for k in lay.row_keys if k not in (DUP, X_VALUE)]
        if len(rows) > 2:
            ui.notify("More than two row groupings: move them one at a time.", type="warning")
            return
        keep = [k for k in lay.row_keys if k in (DUP, X_VALUE)]
        lay.row_keys, lay.col_keys = keep + list(lay.col_keys), rows
        self.changed(panels=True)

    def hide(self, k, vk, hide):
        h = self.ts.layout.hidden.setdefault(k, [])
        if hide and vk not in h:
            h.append(vk)
        elif not hide and vk in h:
            h.remove(vk)
        self.changed()

    def rename_value(self, rk, text):
        if text:
            self.ts.format.value_labels[rk] = text
        else:
            self.ts.format.value_labels.pop(rk, None)
        self.changed()

    # ========================================================== format panel ==
    @ui.refreshable
    def format_panel(self):
        ts, t = self.ts, self.t
        if ts is None or t is None:
            ui.label("No table yet.").classes("text-gray-500")
            return
        fm = ts.format
        ui.label("Spread").classes("rs-sec")
        ui.select(SPREAD_FORMATS, value=fm.spread_format, label="Shown as",
                  on_change=lambda e: (setattr(fm, "spread_format", e.value), self.changed())) \
            .props("dense outlined").classes("w-full")
        ui.switch("Spread in a smaller font", value=fm.spread_small,
                  on_change=lambda e: (setattr(fm, "spread_small", e.value), self.changed()))
        ui.select(STAT_PLACES, value=fm.stat_place, label="Name of the statistic",
                  on_change=lambda e: (setattr(fm, "stat_place", e.value), self.changed())) \
            .props("dense outlined").classes("w-full")
        ui.select(N_MODES, value=fm.n_mode, label="Number of values (n)",
                  on_change=lambda e: (setattr(fm, "n_mode", e.value), self.changed())) \
            .props("dense outlined").classes("w-full")

        ui.label("Numbers").classes("rs-sec")
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.number("Automatic: significant figures", value=fm.sig_figs, min=1, max=6,
                      step=1, on_change=lambda e: e.value and (
                          setattr(fm, "sig_figs", int(e.value)), self.changed())) \
                .props("dense outlined").classes("grow")
            ui.number("Max decimals", value=fm.max_decimals, min=0, max=8, step=1,
                      on_change=lambda e: e.value is not None and (
                          setattr(fm, "max_decimals", int(e.value)), self.changed())) \
                .props("dense outlined").classes("w-32")
        pct = fm.percent if fm.percent is not None else (t.plot.style.fraction_as_percent
                                                         if t.plot else True)
        ui.switch("Fractions as %", value=pct,
                  on_change=lambda e: (setattr(fm, "percent", e.value), self.changed()))
        ui.switch("Proper minus sign (−, not -)", value=fm.math_minus,
                  on_change=lambda e: (setattr(fm, "math_minus", e.value), self.changed()))
        ui.label("Decimals per metric (empty = automatic)").classes("rs-hint mt-1")
        for m in t.metrics:
            with ui.row().classes("w-full items-center no-wrap gap-2"):
                ui.label(reg.axis_label(m).split(" (")[0]).classes("grow text-sm")
                ui.number(value=fm.decimals.get(m), min=0, max=8, step=1,
                          placeholder=str(t.decimals.get(m, "")),
                          on_change=lambda e, m=m: self.set_decimals(m, e.value)) \
                    .props("dense outlined").classes("w-24")

        ui.label("Best values").classes("rs-sec")
        ui.switch("Bold the best value", value=fm.bold_best,
                  on_change=lambda e: (setattr(fm, "bold_best", e.value),
                                       self.changed(panels=True)))
        if fm.bold_best:
            ui.select({"column": "In each column (whole table)",
                       "group": "Within each group of the first row"}, value=fm.best_scope,
                      label="Compare", on_change=lambda e: (setattr(fm, "best_scope", e.value),
                                                            self.changed())) \
                .props("dense outlined").classes("w-full")
            from .table import best_mode
            for m in t.metrics:
                auto = BEST_LABELS[best_mode(m)]
                opts = {k: (f"Automatic ({auto.lower()})" if k == "auto" else BEST_LABELS[k])
                        for k in BEST_MODES}
                ui.select(opts, value=fm.best.get(m, "auto"),
                          label=reg.axis_label(m).split(" (")[0],
                          on_change=lambda e, m=m: (fm.best.__setitem__(m, e.value),
                                                    self.changed())) \
                    .props("dense outlined").classes("w-full")

        ui.label("Headings").classes("rs-sec")
        ui.label("Empty = automatic. Use | for a line break.").classes("rs-hint")
        ui.number("Automatic line length (0 = one line)", value=fm.wrap, min=0, max=60, step=1,
                  on_change=lambda e: e.value is not None and (
                      setattr(fm, "wrap", int(e.value)), self.changed())) \
            .props("dense outlined").classes("w-full")
        heads = [k for k in t.row_keys if k != METRIC] + \
                [k for k in t.col_keys if k != METRIC]
        if not t.col_keys:
            heads.append("__value__")
        for k in heads:
            auto = "Value" if k == "__value__" else key_label(k, t.plot, x_metric=t.x_metric)
            ui.input(self.key_name(k) if k != "__value__" else "Value column",
                     value=fm.header_labels.get(k, ""), placeholder=auto,
                     on_change=lambda e, k=k: self.set_header(k, e.value)) \
                .props("dense").classes("w-full")
        for m in t.metrics:
            auto = reg.axis_label(m, t.plot.style.labels if t.plot else None,
                                  percent=t.percent.get(m, False))
            ui.input(reg.axis_label(m).split(" (")[0], value=fm.header_labels.get(m, ""),
                     placeholder=auto, on_change=lambda e, m=m: self.set_header(m, e.value)) \
                .props("dense").classes("w-full")

    def set_decimals(self, m, v):
        if v is None or v == "":
            self.ts.format.decimals.pop(m, None)
        else:
            self.ts.format.decimals[m] = int(v)
        self.changed()

    def set_header(self, k, text):
        if text:
            self.ts.format.header_labels[k] = text
        else:
            self.ts.format.header_labels.pop(k, None)
        self.changed()

    # ========================================================== output panel ==
    @ui.refreshable
    def output_panel(self):
        ts = self.ts
        if ts is None:
            ui.label("No table yet.").classes("text-gray-500")
            return
        o = ts.output
        ui.label("Caption").classes("rs-sec")
        ui.textarea("Your caption (LaTeX)", value=o.caption,
                    on_change=lambda e: (setattr(o, "caption", e.value), self.changed())) \
            .props("dense outlined autogrow").classes("w-full")
        ui.switch("Append the statistic / n sentence", value=o.caption_auto,
                  on_change=lambda e: (setattr(o, "caption_auto", e.value), self.changed()))
        ui.switch("Append what was fixed / averaged (from rsplot)", value=o.caption_detail,
                  on_change=lambda e: (setattr(o, "caption_detail", e.value), self.changed()))
        ui.input("Label", value=o.label,
                 on_change=lambda e: (setattr(o, "label", e.value), self.changed())) \
            .props("dense").classes("w-full")

        ui.label("Typesetting").classes("rs-sec")
        with ui.row().classes("w-full gap-2 no-wrap"):
            ui.select(FONT_SIZES, value=o.font_size, label="Font size",
                      on_change=lambda e: (setattr(o, "font_size", e.value), self.changed())) \
                .props("dense outlined").classes("grow")
            ui.input("Placement", value=o.placement,
                     on_change=lambda e: (setattr(o, "placement", e.value), self.changed())) \
                .props("dense outlined").classes("w-28")
            ui.number("Column gap (pt)", value=o.tabcolsep, min=0, max=30, step=0.5,
                      on_change=lambda e: (setattr(o, "tabcolsep", e.value), self.changed())) \
                .props("dense outlined clearable").classes("w-36") \
                .tooltip("\\tabcolsep; empty = LaTeX default (6 pt)")
        ui.switch("Multi-line headings (\\makecell)", value=o.makecell,
                  on_change=lambda e: (setattr(o, "makecell", e.value), self.changed()))
        ui.switch("Scale to the text width (\\resizebox)", value=o.resize,
                  on_change=lambda e: (setattr(o, "resize", e.value), self.changed()))

        ui.label("Saving").classes("rs-sec")
        with ui.row().classes("w-full items-center no-wrap gap-1"):
            fin = ui.input("Folder", value=o.folder,
                           on_change=lambda e: setattr(o, "folder", e.value)) \
                .props("dense").classes("grow")
            ui.button(icon="folder_open", on_click=lambda: pick_path(
                o.folder or store.settings()["last_folder"],
                lambda p: (setattr(o, "folder", str(p)), fin.set_value(str(p))),
                mode="folder", title="Folder for the table")).props("flat dense")
        ui.input("File name", value=o.filename,
                 on_change=lambda e: setattr(o, "filename", e.value)) \
            .props("dense").classes("w-full")
        ui.switch("Also write the numbers as CSV", value=o.write_csv,
                  on_change=lambda e: setattr(o, "write_csv", e.value))

    # =============================================================== sources ==
    def source_dialog(self):
        recent = store.rsplot_recent()
        seen = {r["sidecar"] for r in recent}
        figs = rsx.THESIS_ROOT / "figs"
        found = sorted(str(p) for p in figs.rglob("*" + rsx.SIDECAR_SUFFIX)) \
            if figs.exists() else []
        items = [r for r in recent if r["exists"]] + [
            {"sidecar": p, "title": Path(p).name[: -len(rsx.SIDECAR_SUFFIX)], "exists": True}
            for p in found if p not in seen]
        with ui.dialog() as dlg, ui.card().classes("w-[54rem] max-w-full"):
            ui.label("Make a table from an rsplot figure").classes("text-lg font-medium")
            ui.label("The table uses the figure's data, filters, grouping and statistic, so "
                     "its numbers are exactly the plotted ones.").classes("rs-hint")
            with ui.row().classes("gap-2"):
                ui.button("rsplot's current figure", icon="bolt",
                          on_click=lambda: (dlg.close(), self.open_last_plot())) \
                    .props("outline no-caps").tooltip("The figure open in rsplot now (or last), "
                                                      "even if it was never saved")
                ui.button("Browse for .rsplot.json …", icon="folder_open",
                          on_click=lambda: (dlg.close(), pick_path(
                              figs if figs.exists() else Path.home(),
                              lambda p: background_tasks.create(self.open_figure(str(p))),
                              mode="file", patterns=("*" + rsx.SIDECAR_SUFFIX,),
                              title="Open a figure's settings (.rsplot.json)"))) \
                    .props("outline no-caps")
            ui.label("Saved figures (recent first, then the thesis figs folder)") \
                .classes("rs-sec")
            with ui.scroll_area().classes("h-96 w-full"):
                if not items:
                    ui.label("No saved figures found.").classes("text-gray-500")
                for r in items:
                    with ui.row().classes("w-full items-center no-wrap border-b py-1"):
                        with ui.column().classes("grow gap-0"):
                            ui.label(r["title"]).classes("text-sm")
                            ui.label(_short(r["sidecar"])).classes("text-xs text-gray-500 "
                                                                   "break-all")
                        ui.button("Use", on_click=lambda p=r["sidecar"]: (
                            dlg.close(), background_tasks.create(self.open_figure(p)))) \
                            .props("flat dense no-caps")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    @in_page
    async def open_figure(self, path):
        try:
            ts, notes = store.from_sidecar(path)
        except Exception as e:
            ui.notify(f"Cannot open {Path(path).name}: {e}", type="negative")
            return
        await self._start(ts, notes, f"Table from {Path(path).name}")

    def open_last_plot(self):
        spec = store.rsplot_last()
        if not spec:
            ui.notify("rsplot has no current figure.", type="warning")
            return
        background_tasks.create(self._start(store.from_plot_spec(spec), [],
                                            "Table from rsplot's current figure"))

    @in_page
    async def _start(self, ts, notes, msg):
        self.ts, self.notes = ts, notes
        for n in notes:
            ui.notify(n, type="warning", multi_line=True, timeout=8000)
        await self.update(panels=True)
        if self.t is not None:
            ui.notify(msg, type="positive")

    def recent_dialog(self):
        items = store.recent_tables()
        with ui.dialog() as dlg, ui.card().classes("w-[50rem] max-w-full"):
            ui.label("Recent tables").classes("text-lg font-medium")
            if not items:
                ui.label("No tables saved yet.").classes("text-gray-500")
            with ui.scroll_area().classes("h-96 w-full"):
                for r in items:
                    ok = Path(r["sidecar"]).exists()
                    with ui.row().classes("w-full items-center no-wrap border-b py-1"):
                        with ui.column().classes("grow gap-0"):
                            ui.label(r["title"]).classes("text-sm")
                            ui.label(_short(r["sidecar"])).classes("text-xs text-gray-500 "
                                                                   "break-all")
                        if ok:
                            ui.button("Open", on_click=lambda p=r["sidecar"]: (
                                dlg.close(), background_tasks.create(self.load_table(p)))) \
                                .props("flat dense no-caps")
                        else:
                            ui.label("missing").classes("text-xs text-negative")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    def open_table_dialog(self):
        start = (self.ts.output.folder if self.ts and self.ts.output.folder
                 else store.settings()["last_folder"])
        pick_path(start, lambda p: background_tasks.create(self.load_table(str(p))),
                  mode="file", patterns=("*" + store.SIDECAR_SUFFIX,),
                  title="Open table settings (.rstable.json)")

    @in_page
    async def load_table(self, path):
        try:
            ts, notes = store.load_table(path)
        except Exception as e:
            ui.notify(f"Cannot open {Path(path).name}: {e}", type="negative")
            return
        await self._start(ts, notes, f"Loaded {Path(path).name}")

    # ================================================================== save ==
    def save_dialog(self):
        if self.t is None:
            ui.notify("Nothing to save yet.", type="warning")
            return
        o = self.ts.output
        if not o.folder:
            o.folder = store.settings()["last_folder"]
        with ui.dialog() as dlg, ui.card().classes("w-[40rem] max-w-full"):
            ui.label("Save table").classes("text-lg font-medium")
            with ui.row().classes("w-full items-center no-wrap gap-1"):
                fin = ui.input("Folder", value=o.folder,
                               on_change=lambda e: setattr(o, "folder", e.value)) \
                    .props("dense").classes("grow")
                ui.button(icon="folder_open", on_click=lambda: pick_path(
                    o.folder, lambda p: (setattr(o, "folder", str(p)), fin.set_value(str(p))),
                    mode="folder", title="Folder for the table")).props("flat dense")
            ui.input("File name", value=o.filename,
                     on_change=lambda e: setattr(o, "filename", e.value)) \
                .props("dense").classes("w-full")
            ui.switch("Also write the numbers as CSV", value=o.write_csv,
                      on_change=lambda e: setattr(o, "write_csv", e.value))
            ui.label("Writes <name>.tex (for \\input), <name>.rstable.json (to re-open) and "
                     "optionally <name>.csv.").classes("rs-hint")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button("Save", on_click=lambda: (dlg.close(), self.do_save())) \
                    .props("unelevated color=green-7")
        dlg.open()

    def do_save(self, overwrite: bool = False):
        try:
            res = store.save_table(self.ts, self.t, overwrite=overwrite)
        except FileExistsError as e:
            self.conflict_dialog(str(e))
            return
        except Exception as e:
            ui.notify(f"Saving failed: {e}", type="negative", multi_line=True)
            return
        self.output_panel.refresh()
        with ui.dialog() as dlg, ui.card().classes("w-[48rem] max-w-full"):
            ui.label("Table saved").classes("text-lg font-medium text-positive")
            for f in res.files + [res.sidecar]:
                ui.label(f).classes("text-xs break-all")
            ui.label("In the thesis:").classes("rs-sec")
            ui.code(res.input_line, language="latex").classes("w-full")
            with ui.row().classes("w-full justify-end"):
                ui.button("Copy \\input line", icon="content_copy",
                          on_click=lambda: (ui.clipboard.write(res.input_line),
                                            ui.notify("Copied"))).props("flat no-caps")
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    def conflict_dialog(self, files: str):
        o = self.ts.output
        with ui.dialog() as dlg, ui.card().classes("w-[40rem] max-w-full"):
            ui.label("These files already exist").classes("text-lg font-medium")
            ui.label(files).classes("text-xs whitespace-pre-wrap break-all")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button("Save as new name", on_click=lambda: (
                    dlg.close(), setattr(o, "filename",
                                         store.next_free_name(o.folder, o.filename,
                                                              o.write_csv)),
                    self.do_save())).props("flat no-caps")
                ui.button("Overwrite", on_click=lambda: (dlg.close(), self.do_save(True))) \
                    .props("unelevated color=negative no-caps")
        dlg.open()


# ================================================================ helpers ==
def _vk(v) -> str:
    from .table import _vkey
    return _vkey(v)


def _plot_metrics(ts: TableSpec) -> list[str]:
    return list(ts.source.plot.get("mapping", {}).get("y", []))


def _short(p: str) -> str:
    try:
        return str(Path(p).relative_to(rsx.THESIS_ROOT.parent.parent))
    except ValueError:
        return p


# =================================================================== main ==
def main(argv=None):
    ap = argparse.ArgumentParser(description="rstable: LaTeX tables from rsplot figures")
    ap.add_argument("--port", type=int, default=8081)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args, _ = ap.parse_known_args(argv)

    @ui.page("/")
    def index():
        App().build()

    # localhost only: the app can browse local files, so never expose it on the network
    ui.run(title="rstable", host="127.0.0.1", port=args.port, show=not args.no_browser,
           reload=False, favicon="📋", show_welcome_message=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
