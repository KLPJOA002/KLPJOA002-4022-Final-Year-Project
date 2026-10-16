"""rsplot UI (NiceGUI): every figure setting is a control; the preview re-renders live.

Run:  ./run.sh            (or: python -m rsplot.ui.app [--port 8080] [--no-browser])
"""
from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from nicegui import background_tasks, run, ui

from .. import __version__
from .. import export as ex
from .. import registry as reg
from .. import state
from .. import style as st
from ..data import Dataset, load_dataset, sniff
from ..pipeline import filter_text
from ..plots import PLOT_TYPES, load_plugins
from ..spec import AGG_FUNCS, LEGEND_LOCS, SPREAD_LABELS, SPREADS, Filter, PlotSpec, Style
from . import session as S
from .files import pick_path

DEBOUNCE_S = 0.25
FIT_TARGET_PX = 1500           # preview raster width in "fit" mode
PALETTES = {"default": "Colour-blind safe (default)", "greyscale": "Greyscale (print)",
            "tab10": "Matplotlib tab10", "rs_sequential": "Sequential blue (ordered values)",
            "viridis": "Viridis", "cividis": "Cividis", "Set2": "Set2"}
MARKERS = {"o": "● circle", "s": "■ square", "^": "▲ triangle", "D": "◆ diamond",
           "v": "▼ down", "x": "× cross", "none": "(no markers)"}
LINESTYLES = {"-": "solid", "--": "dashed", ":": "dotted", "-.": "dash-dot"}


def in_page(coro_fn):
    """Run an async method inside the page's root container, so it can create UI
    (notifications, dialogs) even when started from a background task or dialog."""
    import functools

    @functools.wraps(coro_fn)
    async def wrapper(self, *a, **kw):
        with self.root:
            return await coro_fn(self, *a, **kw)
    return wrapper


class App:
    def __init__(self):
        load_plugins()
        self.ds: Dataset | None = None
        self.spec: PlotSpec | None = None
        self.version = 0
        self.mode = "fit"                     # fit | actual
        self.pv = S.Preview()
        self.settings = state.settings()

    # ================================================================ layout ==
    def build(self):
        ui.add_head_html("""<style>
            .rs-sec {font-size: 0.72rem; text-transform: uppercase; letter-spacing: .06em;
                     color: #6b7280; margin-top: .6rem;}
            .q-field--dense .q-field__label {font-size: .85rem;}
            .rs-block {border-left: 1px dashed #9ca3af; border-right: 1px dashed #9ca3af;}
        </style>""")
        with ui.header().classes("items-center bg-slate-800 py-1 gap-2"):
            ui.label("rsplot").classes("text-lg font-semibold")
            self.dataset_bar()
            ui.space()
            ui.button("Recent", icon="history", on_click=self.recent_dialog) \
                .props("flat dense no-caps color=white")
            ui.button("Open settings", icon="file_open", on_click=self.open_settings_dialog) \
                .props("flat dense no-caps color=white") \
                .tooltip("Re-open a saved figure from its .rsplot.json file")
            ui.button("Save figure", icon="save", on_click=self.save_dialog) \
                .props("unelevated dense no-caps color=green-7")
            ui.toggle({"fit": "Fit", "actual": "Actual size"}, value=self.mode,
                      on_change=lambda e: self.set_mode(e.value)) \
                .props("dense no-caps unelevated color=blue-grey-7 toggle-color=white "
                       "toggle-text-color=blue-grey-10 text-color=white")
        with ui.left_drawer(value=True).props("width=460 bordered").classes("p-0"):
            with ui.tabs().classes("w-full").props("dense no-caps") as tabs:
                t_data = ui.tab("Data")
                t_filt = ui.tab("Filters")
                t_style = ui.tab("Style")
                t_size = ui.tab("Size & text")
            with ui.tab_panels(tabs, value=t_data).classes("w-full"):
                with ui.tab_panel(t_data).classes("p-3"):
                    self.data_panel()
                with ui.tab_panel(t_filt).classes("p-3"):
                    self.filter_panel()
                with ui.tab_panel(t_style).classes("p-3"):
                    self.style_panel()
                with ui.tab_panel(t_size).classes("p-3"):
                    self.size_panel()
        with ui.column().classes("w-full p-3 gap-2") as self.root:
            self.status_area()
            self.preview_box = ui.column().classes("w-full items-center")
            with self.preview_box:
                self.preview_holder()
        ui.timer(0.1, self.startup, once=True)

    # ============================================================== datasets ==
    @ui.refreshable
    def dataset_bar(self):
        items = state.datasets()
        opts = {d["path"]: f'{d.get("name") or S.dataset_name(d["path"])}  ·  '
                f'{reg.family(d.get("family")).title}' for d in items}
        cur = str(self.ds.path) if self.ds else None
        ui.select(opts, value=cur if cur in opts else None, label="Dataset",
                  on_change=lambda e: e.value and self.open_dataset(e.value)) \
            .props("dense dark options-dense outlined").classes("w-[32rem]")
        ui.button("Add dataset", icon="add", on_click=self.add_dataset_dialog) \
            .props("flat dense no-caps color=white")
        ui.button(icon="travel_explore", on_click=self.find_dialog) \
            .props("flat dense color=white").tooltip("Find datasets in the project")
        if cur in opts:
            ui.button(icon="delete_outline", on_click=lambda: self.remove_dataset(cur)) \
                .props("flat dense color=white").tooltip("Remove from list (file is kept)")

    @in_page
    async def startup(self):
        last = state.last_spec()
        items = state.datasets()
        if last and Path(last.get("dataset", {}).get("path", "")).exists():
            spec = PlotSpec.from_dict(last)
            await self.open_dataset(spec.dataset.path, spec=spec)
        elif items:
            await self.open_dataset(items[0]["path"])
        else:
            self.find_dialog()

    @in_page
    async def open_dataset(self, path: str, spec: PlotSpec | None = None,
                           family: str | None = None):
        entry = next((d for d in state.datasets() if d["path"] == path), None)
        family = family or (spec.dataset.family if spec else None) or (
            entry or {}).get("family")
        n = ui.notification(f"Loading {Path(path).name} …", spinner=True, timeout=None)
        try:
            ds = await run.io_bound(load_dataset, path, family)
        except Exception as e:
            n.dismiss()
            ui.notify(f"Could not load {path}: {e}", type="negative", multi_line=True)
            return
        n.dismiss()
        if entry is None:
            state.add_dataset(path, ds.family.key, S.dataset_name(path))
        self.ds = ds
        self.spec = spec or S.default_spec(ds, family, keep=self.spec)
        self.spec.dataset.path = str(ds.path)
        self.spec.dataset.family = family or ds.family.key
        self.refresh_all()
        self.changed()

    def remove_dataset(self, path: str):
        state.remove_dataset(path)
        self.dataset_bar.refresh()

    def add_dataset_dialog(self):
        start = Path(self.spec.dataset.path).parent if self.spec else S.PROJECT
        pick_path(start, self.confirm_dataset, mode="file", patterns=("*.csv",),
                  title="Add dataset: choose a CSV file")

    def confirm_dataset(self, path: Path):
        try:
            fam = sniff(path)
        except Exception as e:
            ui.notify(f"Cannot read {path.name}: {e}", type="negative")
            return
        fams = {k: f"{f.title} ({k})" for k, f in reg.families().items()}
        with ui.dialog() as dlg, ui.card().classes("w-[36rem]"):
            ui.label("Add dataset").classes("text-lg font-medium")
            ui.label(str(path)).classes("text-xs text-gray-600 break-all")
            ui.label(f"Detected from its columns: {fam.title}").classes("text-positive")
            fsel = ui.select(fams, value=fam.key, label="Family (override if wrong)") \
                .classes("w-full")
            name = ui.input("Name in the list", value=S.dataset_name(str(path))).classes("w-full")

            async def add():
                state.add_dataset(str(path.resolve()), fsel.value, name.value)
                dlg.close()
                self.dataset_bar.refresh()
                await self.open_dataset(str(path.resolve()), family=fsel.value)
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button("Add and open", on_click=add)
        dlg.open()

    def find_dialog(self):
        with ui.dialog() as dlg, ui.card().classes("w-[60rem] max-w-full"):
            ui.label("Datasets found in the project").classes("text-lg font-medium")
            ui.label("Folders named *_Old and the raw per-trial Data/ folders are skipped; "
                     "use “Add dataset” to pick any other file.").classes("text-xs text-gray-500")
            box = ui.column().classes("w-full")
            with box:
                ui.spinner(size="lg")

            async def load():
                cands = await run.io_bound(S.find_candidates)
                known = {d["path"] for d in state.datasets()}
                box.clear()
                with box:
                    cols = [{"name": "rel", "label": "File", "field": "rel", "align": "left"},
                            {"name": "title", "label": "Detected family", "field": "title",
                             "align": "left"},
                            {"name": "note", "label": "", "field": "note", "align": "left",
                             "classes": "text-orange-9 text-xs"}]
                    rows = [dict(c, id=c["path"]) for c in cands if c["family"] != "generic"] \
                        + [dict(c, id=c["path"]) for c in cands if c["family"] == "generic"]
                    table = ui.table(columns=cols, rows=rows, row_key="id", selection="multiple",
                                     pagination=15).classes("w-full").props("dense flat")
                    table.selected = [r for r in rows if r["path"] in known] if known else \
                        [r for r in rows if r["suggest"]]
                    ui.label("Ticked: every recognised file except older copies. "
                             "Generic tables (unrecognised columns) are listed last.") \
                        .classes("text-xs text-gray-500")

                    def add():
                        for r in table.selected:
                            state.add_dataset(r["path"], r["family"], S.dataset_name(r["path"]))
                        dlg.close()
                        self.dataset_bar.refresh()
                        if table.selected and self.ds is None:
                            background_tasks.create(self.open_dataset(table.selected[0]["path"]))
                    with ui.row().classes("w-full justify-end"):
                        ui.button("Cancel", on_click=dlg.close).props("flat")
                        ui.button("Add selected to the list", on_click=add)
            background_tasks.create(load())
        dlg.open()

    # =========================================================== change flow ==
    def refresh_all(self):
        self.dataset_bar.refresh()
        self.data_panel.refresh()
        self.filter_panel.refresh()
        self.style_panel.refresh()
        self.size_panel.refresh()

    def changed(self, *panels):
        """Spec changed: refresh the named panels now, re-render after a short pause."""
        for p in panels:
            getattr(self, p).refresh()
        self.version += 1
        background_tasks.create(self._render_later(self.version))

    async def _render_later(self, v: int):
        await asyncio.sleep(DEBOUNCE_S)
        if v != self.version or self.spec is None or self.ds is None:
            return
        spec, ds = self.spec.copy(), self.ds
        self.busy.set_visibility(True)
        pv = await run.io_bound(S.preview, spec, ds, self.preview_dpi(spec))
        if v != self.version:
            return
        self.busy.set_visibility(False)
        self.pv = pv
        state.save_last_spec(spec.to_dict())
        self.status_area.refresh()
        self.preview_holder.refresh()

    def preview_dpi(self, spec: PlotSpec) -> float:
        w_cm, _ = st.figure_size_cm(spec.export, self.settings["textwidth_cm"])
        if self.mode == "actual":
            return self.settings["screen_px_per_cm"] * st.CM_PER_IN * 2   # crisp on HiDPI
        return max(90, min(300, FIT_TARGET_PX / (w_cm / st.CM_PER_IN)))

    def set_mode(self, mode):
        self.mode = mode
        self.changed()

    # ================================================================ preview ==
    @ui.refreshable
    def preview_holder(self):
        pv = self.pv
        self.busy = ui.spinner(size="md").classes("absolute right-6 top-24")
        self.busy.set_visibility(False)
        if self.spec is None:
            ui.label("Add or choose a dataset to start.").classes("text-gray-500 mt-20")
            return
        if pv.error:
            with ui.card().classes("bg-red-50 w-full"):
                ui.label("The figure could not be drawn").classes("text-negative font-medium")
                ui.label(pv.error).classes("font-mono text-sm whitespace-pre-wrap")
            return
        if not pv.png_b64:
            ui.spinner(size="xl").classes("mt-20")
            return
        src = f"data:image/png;base64,{pv.png_b64}"
        if self.mode == "actual":
            ppc = self.settings["screen_px_per_cm"]
            tw = self.settings["textwidth_cm"]
            with ui.column().classes("rs-block items-center bg-white py-4") \
                    .style(f"width:{tw * ppc:.0f}px"):
                ui.label(f"{tw:g} cm text block · figure {pv.width_cm:g} × {pv.height_cm:g} cm "
                         "at 100 %").classes("text-xs text-gray-500")
                ui.element("img").props(f'src="{src}"').style(
                    f"width:{pv.width_cm * ppc:.0f}px; max-width:none; "
                    "box-shadow:0 0 0 1px #e5e7eb")
        else:
            ui.element("img").props(f'src="{src}"').style(
                "max-width:100%; max-height:calc(100vh - 210px); width:auto; height:auto; "
                "box-shadow:0 1px 4px rgba(0,0,0,.15); background:white")
        ui.label(f"{pv.width_cm:g} × {pv.height_cm:g} cm  ·  include with "
                 f"\\includegraphics[width={pv.latex_width}]{{…}}") \
            .classes("text-xs text-gray-500")

    @ui.refreshable
    def status_area(self):
        if self.spec is None:
            return
        pv, spec = self.pv, self.spec
        with ui.row().classes("w-full items-center gap-1"):
            if pv.n_total:
                txt = f"{pv.n_filtered:,} of {pv.n_total:,} rows"
                if pv.n_nan_x:
                    txt += f" · {pv.n_nan_x:,} without a {pv.x_label.lower()} value"
                if pv.n_nan:
                    txt += f" · {pv.n_nan:,} without a value"
                ui.badge(txt, color="slate-600").classes("text-sm py-1 px-2")
            for i, f in enumerate(spec.filters):
                if not f.enabled:
                    continue
                ui.chip(filter_text(f, spec.style.labels), icon="filter_alt", removable=True,
                        color="blue-1", text_color="blue-10",
                        on_value_change=lambda e, i=i: self.remove_filter(i)) \
                    .props("dense").classes("text-xs")
        unf = [n for n in pv.notes if n.status == "unfixed"]
        if unf:
            with ui.expansion(f"{len(unf)} factor{'s' if len(unf) > 1 else ''} not fixed — "
                              f"{unf[0].action}", icon="warning", value=False) \
                    .classes("w-full bg-amber-50 rounded").props("dense header-class=text-amber-10"):
                for n in unf:
                    vals = ", ".join(reg.value_label(v) for v in n.values[:12])
                    more = " …" if len(n.values) > 12 else ""
                    with ui.row().classes("items-center w-full gap-1 no-wrap"):
                        ui.label(f"{reg.axis_label(n.column).split(' (')[0]}: {n.n_values} "
                                 f"values ({vals}{more}) are being {n.action.split()[0]}") \
                            .classes("text-sm grow")
                        ui.button("Fix to one value", on_click=lambda c=n.column: self.quick_fix(c)) \
                            .props("flat dense no-caps size=sm")
                        ui.button("Colour by", on_click=lambda c=n.column: self.quick_role("hue", c)) \
                            .props("flat dense no-caps size=sm")
                        ui.button("Facet by", on_click=lambda c=n.column: self.quick_role("facet", c)) \
                            .props("flat dense no-caps size=sm")
        for w in pv.warnings:
            with ui.row().classes("items-center gap-1"):
                ui.icon("info", color="orange-8")
                ui.label(w).classes("text-sm text-orange-10")

    def remove_filter(self, i: int):
        if 0 <= i < len(self.spec.filters):
            self.spec.filters.pop(i)
        self.changed("filter_panel")

    def quick_fix(self, col):
        S.fix_to_one(self.ds, self.spec, col)
        self.changed("filter_panel")

    def quick_role(self, role, col):
        setattr(self.spec.mapping, role, col)
        self.changed("data_panel")

    # ============================================================ data panel ==
    @ui.refreshable
    def data_panel(self):
        if self.spec is None or self.ds is None:
            ui.label("No dataset open.").classes("text-gray-500")
            return
        ds, spec, m = self.ds, self.spec, self.spec.mapping
        pt = PLOT_TYPES[spec.plot_type]
        ui.label(f"{ds.family.title} · {ds.n_rows:,} rows · {len(ds.loaded)} of "
                 f"{len(ds.columns)} columns loaded").classes("text-xs text-gray-500")

        ui.select({k: p.label for k, p in PLOT_TYPES.items()}, value=spec.plot_type,
                  label="Plot type", on_change=lambda e: self.set_plot_type(e.value)) \
            .classes("w-full").props("dense")

        ui.label("Metric (y)").classes("rs-sec")
        mopts = S.metric_options(ds, include_sparse=True)
        ui.select(mopts, value=[y for y in m.y if y in mopts], multiple=True, with_input=True,
                  label="Metric(s) — ★ = main metrics",
                  on_change=lambda e: self.set_y(e.value)) \
            .classes("w-full").props("dense use-chips options-dense")
        groups = S.variants(ds)
        main = {k: g for k, g in groups.items() if k == "rmse"}
        other = {k: g for k, g in groups.items() if k != "rmse"}
        for key, g in main.items():
            self.variant_row(g)
        if other:
            with ui.expansion("Other variants (MAE, signed bias)").classes("w-full") \
                    .props("dense"):
                for key, g in other.items():
                    self.variant_row(g)
        if len(m.y) > 1:
            ui.toggle({"overlay": "Overlaid", "side_by_side": "Side by side"}, value=m.y_mode,
                      on_change=lambda e: self.set_attr(m, "y_mode", e.value)) \
                .props("dense no-caps")
        sec_opts = {None: "(none)", **{c: S.column_label(ds, c) for c in
                                       reg.labels_yaml().get("secondary_indicators", [])
                                       if c in ds.profile}}
        if pt.secondary and len(sec_opts) > 1:
            ui.select(sec_opts, value=m.secondary, label="Secondary indicator (panel below)",
                      on_change=lambda e: self.set_attr(m, "secondary", e.value)) \
                .classes("w-full").props("dense")

        ui.label("Mapping").classes("rs-sec")
        if pt.x != "none":
            xs = ds.x_candidates()
            ui.select(S.options(ds, xs, none=pt.x != "numeric"), value=m.x, label="x axis",
                      with_input=True, on_change=lambda e: self.set_attr(m, "x", e.value)) \
                .classes("w-full").props("dense options-dense")
        facs = [f for f in ds.factors() if ds.profile[f].discrete]
        if "row" in pt.roles:
            ui.select(S.options(ds, facs), value=m.row, label="Heatmap rows", with_input=True,
                      on_change=lambda e: self.set_attr(m, "row", e.value)) \
                .classes("w-full").props("dense options-dense")
        if "hue" in pt.roles:
            ui.select(S.options(ds, facs), value=m.hue, label="Colour (hue)", with_input=True,
                      on_change=lambda e: self.set_attr(m, "hue", e.value, "style_panel")) \
                .classes("w-full").props("dense options-dense")
        if "facet" in pt.roles:
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.select(S.options(ds, facs), value=m.facet, label="Small multiples (facet)",
                          with_input=True,
                          on_change=lambda e: self.set_attr(m, "facet", e.value)) \
                    .classes("grow").props("dense options-dense")
                ui.number("Columns", value=m.facet_cols or None, min=0, max=8, step=1,
                          placeholder="auto",
                          on_change=lambda e: self.set_attr(m, "facet_cols", int(e.value or 0))) \
                    .classes("w-24").props("dense")
        if "style" in pt.roles:
            ui.select(S.options(ds, facs), value=m.style, label="Marker / line style",
                      with_input=True, on_change=lambda e: self.set_attr(m, "style", e.value)) \
                .classes("w-full").props("dense options-dense")
        by_opts = S.options(ds, ds.factors() + ds.replicate_columns(), none=False)
        ui.select(by_opts, value=[b for b in m.by if b in by_opts], multiple=True,
                  with_input=True, label="Separate by (no colour, e.g. one line per trial)",
                  on_change=lambda e: self.set_attr(m, "by", list(e.value or []))) \
            .classes("w-full").props("dense use-chips options-dense")

        ui.label("Aggregation & spread").classes("rs-sec")
        if pt.needs_raw:
            ui.label("This plot shows every row; there is nothing to aggregate.") \
                .classes("text-xs text-gray-500")
        else:
            a = spec.aggregation
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.select({f: f.capitalize() if f != "none" else "None (every row)"
                           for f in AGG_FUNCS}, value=a.func, label="Aggregate",
                          on_change=lambda e: self.set_attr(a, "func", e.value)) \
                    .classes("grow").props("dense")
                ui.select({s: SPREAD_LABELS[s] for s in SPREADS}, value=a.spread,
                          label="Spread", on_change=lambda e: self.set_attr(a, "spread", e.value)) \
                    .classes("grow").props("dense")
            if ds.is_summary():
                with ui.row().classes("w-full no-wrap gap-2"):
                    ui.select({"median": "Stored median", "mean": "Stored mean"},
                              value=a.stored_stat, label="Per-trial value",
                              on_change=lambda e: self.set_attr(a, "stored_stat", e.value)) \
                        .classes("grow").props("dense")
                    ui.select({"iqr": "Stored IQR", "std": "Stored ± SD", "none": "None"},
                              value=a.stored_spread, label="Per-trial spread",
                              on_change=lambda e: self.set_attr(a, "stored_spread", e.value)) \
                        .classes("grow").props("dense")
                ui.label("Summary file: with “Aggregate = None” each point is one trial with "
                         "its stored statistics.").classes("text-xs text-gray-500")

        if pt.options:
            ui.label(f"{pt.label} options").classes("rs-sec")
            self.option_controls(pt)

    def variant_row(self, g):
        m = self.spec.mapping
        chosen = [k for k, c in g["members"].items() if c in m.y]
        with ui.row().classes("items-center gap-2 no-wrap w-full"):
            ui.label(f'{g["title"]}').classes("text-sm w-32")
            for k in g["members"]:
                ui.checkbox(S.VARIANT_SHORT.get(k, k), value=k in chosen,
                            on_change=lambda e, k=k, g=g: self.toggle_variant(
                                g["members"], k, e.value)).props("dense")

    def option_controls(self, pt):
        opts = self.spec.options
        cur_of = lambda o: opts.get(o.name, o.default)
        dependents = {d for o in pt.options for d in list((o.show_if or {}).keys()) + [o.of]}
        for o in pt.options:
            if o.show_if and not all(cur_of(next(x for x in pt.options if x.name == k)) in v
                                     for k, v in o.show_if.items()):
                continue
            cur = cur_of(o)
            refresh = o.name in dependents
            set_ = lambda v, n=o.name, t=o.type, r=refresh: self.set_option(n, v, t, r)
            if o.type == "bool":
                ui.switch(o.label, value=bool(cur), on_change=lambda e, s=set_: s(e.value)) \
                    .props("dense")
            elif o.type == "choice":
                ui.select(o.choices, value=cur, label=o.label,
                          on_change=lambda e, s=set_: s(e.value)).classes("w-full").props("dense")
            elif o.type == "column":
                cols = self.ds.metrics() if o.choices == ["metrics"] else self.ds.factors()
                ui.select(S.options(self.ds, cols), value=cur, label=o.label, with_input=True,
                          on_change=lambda e, s=set_: s(e.value)) \
                    .classes("w-full").props("dense options-dense").tooltip(o.help or o.label)
            elif o.type == "value":
                col = self.spec.mapping.x if o.of == "@x" else opts.get(o.of)
                if col is None and o.of and self.ds.family.baseline:
                    col = self.ds.family.baseline.get("column")
                    cur = cur if cur is not None else self.ds.family.baseline.get("value")
                vals = (self.ds.profile[col].values or []) if col in self.ds.profile else []
                vopts = {None: "(none)", **{v: reg.value_label(v) for v in vals}}
                ui.select(vopts, value=cur if cur in vopts else None, label=o.label,
                          with_input=True, on_change=lambda e, s=set_: s(e.value)) \
                    .classes("w-full").props("dense options-dense")
            else:
                step = 1 if o.type == "int" else (0.05 if (o.max or 10) <= 1 else 0.5)
                ui.number(o.label, value=cur, min=o.min, max=o.max, step=step,
                          placeholder="auto" if o.default is None else None,
                          on_change=lambda e, s=set_: s(e.value)).classes("w-full") \
                    .props("dense clearable").tooltip(o.help or o.label)

    # ---- setters ----
    def set_attr(self, obj, attr, value, *panels):
        setattr(obj, attr, value)
        self.changed(*panels)

    def set_option(self, name, value, typ, refresh=False):
        if value is not None and typ == "int":
            value = int(value)
        self.spec.options[name] = value
        self.changed(*(["data_panel"] if refresh else []))

    def set_plot_type(self, name):
        old = PLOT_TYPES[self.spec.plot_type]
        new = PLOT_TYPES[name]
        self.spec.plot_type = name
        self.spec.options = {k: v for k, v in self.spec.options.items()
                             if k in new.option_defaults()}
        if new.x == "none":
            self.spec.mapping.x = None
        elif self.spec.mapping.x is None and self.ds:
            self.spec.mapping.x = (self.ds.family.time_column if name == "timeseries"
                                   and self.ds.family.time_column in self.ds.profile
                                   else (self.ds.x_candidates() or [None])[0])
        ds, m = self.ds, self.spec.mapping
        if name == "ranking" and ds and ds.family.rank_item in ds.profile:
            m.x = ds.family.rank_item
            if m.hue and not m.facet:          # colour would split items: one ranking each
                m.facet, m.hue = m.hue, None
        if name == "heatmap" and ds:
            few = [f for f in ds.factors() if ds.profile[f].discrete and not ds.profile[f].constant
                   and ds.profile[f].n_unique <= 30]
            if m.x not in few:
                m.x = next((f for f in few if f not in (m.row, m.facet)), None)
            if m.row not in few:
                m.row = None
        if name == "heatmap" and ds and m.row is None:
            facs = [f for f in ds.factors() if ds.profile[f].discrete and f != m.x
                    and f not in (m.facet, m.hue) and not ds.profile[f].constant
                    and ds.profile[f].n_unique <= 30]
            m.row = facs[0] if facs else None
        if name in ("heatmap", "ranking") and self.spec.aggregation.func == "none" and \
                ds and not ds.family.key.endswith(("ranking", "best", "smallest")):
            self.spec.aggregation.func = "mean"
        if old.needs_raw and not new.needs_raw and self.spec.aggregation.func == "none":
            self.spec.aggregation.func = new.default_agg
            self.spec.aggregation.spread = new.default_spread
        self.changed("data_panel")

    def set_y(self, values):
        self.spec.mapping.y = list(values or [])
        self.changed("data_panel", "style_panel")

    def toggle_variant(self, members, key, on):
        chosen = [k for k, c in members.items() if c in self.spec.mapping.y]
        chosen = [k for k in members if (k in chosen and k != key) or (k == key and on)]
        S.set_variants(self.spec, members, chosen)
        self.changed("data_panel", "style_panel")

    # ========================================================== filter panel ==
    @ui.refreshable
    def filter_panel(self):
        if self.spec is None or self.ds is None:
            return
        ds, spec = self.ds, self.spec
        ui.label("Filters keep only the rows you choose. Nothing is filtered by default.") \
            .classes("text-xs text-gray-500")
        ui.select(S.filter_columns(ds), label="Add a filter on column …", with_input=True,
                  on_change=lambda e: e.value and self.add_filter(e.value)) \
            .classes("w-full").props("dense options-dense")
        for i, f in enumerate(spec.filters):
            if f.column not in ds.profile:
                continue
            self.filter_card(i, f)
        if spec.filters:
            ui.button("Clear all filters", icon="filter_alt_off",
                      on_click=self.clear_filters).props("flat dense no-caps")

    def filter_card(self, i: int, f: Filter):
        p = self.ds.profile[f.column]
        with ui.card().classes("w-full p-2 gap-1").props("flat bordered"):
            with ui.row().classes("w-full items-center no-wrap"):
                ui.label(reg.axis_label(f.column)).classes("font-medium grow text-sm")
                ui.switch(value=f.enabled, on_change=lambda e: self.set_attr(f, "enabled", e.value)) \
                    .props("dense").tooltip("Enable / disable this filter")
                ui.button(icon="close", on_click=lambda: self.remove_filter(i)) \
                    .props("flat dense round size=sm")
            if f.kind == "range":
                lo0, hi0 = p.vmin, p.vmax
                step = (hi0 - lo0) / 200 if hi0 > lo0 else 1
                lo = lo0 if f.lo is None else f.lo
                hi = hi0 if f.hi is None else f.hi
                rng = ui.range(min=lo0, max=hi0, step=step, value={"min": lo, "max": hi}) \
                    .props("label dense")
                with ui.row().classes("w-full no-wrap gap-2"):
                    n_lo = ui.number("from", value=lo).classes("grow").props("dense")
                    n_hi = ui.number("to", value=hi).classes("grow").props("dense")

                def from_range(e, f=f):
                    f.lo, f.hi = e.value["min"], e.value["max"]
                    n_lo.value, n_hi.value = f.lo, f.hi
                    self.changed()

                def from_numbers(_=None, f=f):
                    f.lo, f.hi = n_lo.value, n_hi.value
                    self.changed()
                rng.on_value_change(from_range)
                n_lo.on("blur", from_numbers)
                n_hi.on("blur", from_numbers)
                if p.values is not None:
                    ui.button("Pick values instead", on_click=lambda: self.switch_filter_kind(i, "in")) \
                        .props("flat dense no-caps size=sm")
            else:
                opts = {v: reg.value_label(v, self.spec.style.value_labels) for v in p.values}
                sel = ui.select(opts, value=[v for v in (f.values or []) if v in opts],
                                multiple=True, with_input=True,
                                on_change=lambda e, f=f: self.set_attr(f, "values", list(e.value))) \
                    .classes("w-full").props("dense use-chips options-dense")
                with ui.row().classes("gap-1 items-center"):
                    ui.button("All", on_click=lambda s=sel: s.set_value(list(opts))) \
                        .props("flat dense no-caps size=sm")
                    ui.button("None", on_click=lambda s=sel: s.set_value([])) \
                        .props("flat dense no-caps size=sm")
                    if p.kind == "numeric":
                        ui.button("Use a range", on_click=lambda: self.switch_filter_kind(i, "range")) \
                            .props("flat dense no-caps size=sm")
            if p.non_null < 1:
                ui.checkbox(f"Keep rows with no value ({(1 - p.non_null) * 100:.0f} %)",
                            value=f.keep_nan,
                            on_change=lambda e, f=f: self.set_attr(f, "keep_nan", e.value)) \
                    .props("dense size=sm").classes("text-xs")

    def add_filter(self, col):
        self.spec.filters = [f for f in self.spec.filters if f.column != col]
        self.spec.filters.append(S.new_filter(self.ds, col))
        self.changed("filter_panel")

    def switch_filter_kind(self, i, kind):
        f = self.spec.filters[i]
        p = self.ds.profile[f.column]
        if kind == "range":
            self.spec.filters[i] = Filter(f.column, kind="range", lo=p.vmin, hi=p.vmax,
                                          keep_nan=f.keep_nan)
        else:
            self.spec.filters[i] = Filter(f.column, kind="in", values=list(p.values or []),
                                          keep_nan=f.keep_nan)
        self.changed("filter_panel")

    def clear_filters(self):
        self.spec.filters = []
        self.changed("filter_panel")

    # =========================================================== style panel ==
    @ui.refreshable
    def style_panel(self):
        if self.spec is None or self.ds is None:
            return
        s = self.spec.style
        with ui.row().classes("w-full items-center no-wrap gap-2"):
            ui.select({k: k.replace("_", " ").capitalize() for k in st.presets()["styles"]},
                      value=s.preset, label="Style preset (fonts, sizes, line weights)",
                      on_change=lambda e: self.set_attr(s, "preset", e.value)) \
                .classes("grow").props("dense")
            ui.button("Reset to defaults", icon="restart_alt", on_click=self.reset_style) \
                .props("flat dense no-caps")
        self.preset_row()

        with ui.expansion("Text & labels", icon="title", value=True).classes("w-full"):
            ui.switch("Show title (off for thesis: the caption is the title)",
                      value=s.show_title,
                      on_change=lambda e: self.set_attr(s, "show_title", e.value)).props("dense")
            self.text_input("Title", s, "title")
            self.text_input("Subtitle", s, "subtitle")
            ui.select({"auto": "Automatic (states what was fixed / averaged)",
                       "custom": "Custom text", "off": "Off"}, value=s.footnote_mode,
                      label="Footnote", on_change=lambda e: self.set_attr(
                          s, "footnote_mode", e.value, "style_panel")) \
                .classes("w-full").props("dense")
            if s.footnote_mode == "custom":
                ui.textarea("Footnote text", value=s.footnote or self.pv.footnote,
                            on_change=lambda e: self.set_attr(s, "footnote", e.value)) \
                    .classes("w-full").props("dense autogrow")
            self.text_input("x-axis label", s, "xlabel", none_if_empty=True,
                            placeholder=reg.axis_label(self.spec.mapping.x) or "automatic")
            self.text_input("y-axis label", s, "ylabel", none_if_empty=True,
                            placeholder="automatic")
            self.label_overrides()

        with ui.expansion("Axes", icon="straighten").classes("w-full"):
            for ax in ("x", "y"):
                lim = getattr(s, f"{ax}lim") or [None, None]
                with ui.row().classes("w-full no-wrap gap-2 items-center"):
                    ui.number(f"{ax} min", value=lim[0], placeholder="auto",
                              on_change=lambda e, ax=ax: self.set_lim(ax, 0, e.value)) \
                        .classes("grow").props("dense clearable")
                    ui.number(f"{ax} max", value=lim[1], placeholder="auto",
                              on_change=lambda e, ax=ax: self.set_lim(ax, 1, e.value)) \
                        .classes("grow").props("dense clearable")
                    ui.switch("log", value=getattr(s, f"{ax}log"),
                              on_change=lambda e, ax=ax: self.set_attr(s, f"{ax}log", e.value)) \
                        .props("dense")
                with ui.row().classes("w-full no-wrap gap-2"):
                    ui.number(f"{ax} ticks (approx.)", value=getattr(s, f"{ax}_ticks") or None,
                              min=0, max=20, step=1, placeholder="auto",
                              on_change=lambda e, ax=ax: self.set_attr(
                                  s, f"{ax}_ticks", int(e.value or 0))) \
                        .classes("grow").props("dense clearable")
                    ui.input(f"{ax} tick format", value=getattr(s, f"{ax}_tick_format"),
                             placeholder="e.g. {x:.1f}",
                             on_change=lambda e, ax=ax: self.set_attr(
                                 s, f"{ax}_tick_format", e.value)) \
                        .classes("grow").props("dense debounce=600")
            with ui.row().classes("gap-3"):
                ui.switch("Grid", value=s.grid, on_change=lambda e: self.set_attr(s, "grid", e.value)) \
                    .props("dense")
                ui.switch("Fractions as %", value=s.fraction_as_percent,
                          on_change=lambda e: self.set_attr(s, "fraction_as_percent", e.value)) \
                    .props("dense")
                ui.switch("Share x", value=s.sharex,
                          on_change=lambda e: self.set_attr(s, "sharex", e.value)).props("dense")
                ui.switch("Share y", value=s.sharey,
                          on_change=lambda e: self.set_attr(s, "sharey", e.value)).props("dense")

        with ui.expansion("Legend & n", icon="list").classes("w-full"):
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.select({l: l.capitalize() for l in LEGEND_LOCS}, value=s.legend,
                          label="Legend position",
                          on_change=lambda e: self.set_attr(s, "legend", e.value)) \
                    .classes("grow").props("dense")
                ui.number("Columns", value=s.legend_cols or None, min=0, max=10, step=1,
                          placeholder="auto",
                          on_change=lambda e: self.set_attr(s, "legend_cols", int(e.value or 0))) \
                    .classes("w-24").props("dense clearable")
            with ui.row().classes("gap-3"):
                ui.switch("Legend title", value=s.legend_title,
                          on_change=lambda e: self.set_attr(s, "legend_title", e.value)) \
                    .props("dense")
                ui.switch("Show n", value=s.show_n,
                          on_change=lambda e: self.set_attr(s, "show_n", e.value)).props("dense")
                ui.switch("Annotations", value=s.annotate,
                          on_change=lambda e: self.set_attr(s, "annotate", e.value)) \
                    .props("dense").tooltip("Direct labels on lines / values on bars")

        with ui.expansion("Colours & marks", icon="palette").classes("w-full"):
            with ui.row().classes("w-full no-wrap gap-2 items-center"):
                ui.select(PALETTES, value=s.palette, label="Palette",
                          on_change=lambda e: self.set_attr(s, "palette", e.value, "style_panel")) \
                    .classes("grow").props("dense")
                ui.switch("Greyscale print mode", value=s.greyscale,
                          on_change=lambda e: self.set_attr(s, "greyscale", e.value, "style_panel")) \
                    .props("dense")
            self.colour_pickers()
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.select(MARKERS, value=s.marker if s.marker in MARKERS else "o", label="Marker",
                          on_change=lambda e: self.set_attr(s, "marker", e.value)) \
                    .classes("grow").props("dense")
                ui.select(LINESTYLES, value=s.linestyle if s.linestyle in LINESTYLES else "-",
                          label="Line style",
                          on_change=lambda e: self.set_attr(s, "linestyle", e.value)) \
                    .classes("grow").props("dense")
            sp = st.style_preset(s.preset)
            with ui.row().classes("w-full no-wrap gap-2"):
                ui.number("Marker size", value=s.marker_size, min=0.5, max=20, step=0.5,
                          placeholder=f'{sp["marker_size"]:g} (preset)',
                          on_change=lambda e: self.set_attr(s, "marker_size", e.value)) \
                    .classes("grow").props("dense clearable")
                ui.number("Line width", value=s.line_width, min=0.2, max=6, step=0.1,
                          placeholder=f'{sp["line_width"]:g} (preset)',
                          on_change=lambda e: self.set_attr(s, "line_width", e.value)) \
                    .classes("grow").props("dense clearable")
            ui.label("Band / fill opacity").classes("text-xs text-gray-500")
            ui.slider(min=0.02, max=0.8, step=0.02, value=s.band_alpha,
                      on_change=lambda e: self.set_attr(s, "band_alpha", e.value)).props("label")

        with ui.expansion("Margins & fonts", icon="crop_free").classes("w-full"):
            ui.toggle({"tight": "Tight", "normal": "Normal", "loose": "Loose"}, value=s.margin,
                      on_change=lambda e: self.set_attr(s, "margin", e.value)).props("dense no-caps")
            ui.number("Axis padding (%)", value=s.pad_pct, min=0, max=40, step=1,
                      placeholder="from Tight / Normal / Loose",
                      on_change=lambda e: self.set_attr(s, "pad_pct", e.value)) \
                .classes("w-full").props("dense clearable")
            ui.number("Font scale", value=s.font_scale, min=0.6, max=2.0, step=0.05,
                      on_change=lambda e: self.set_attr(s, "font_scale", e.value or 1.0)) \
                .classes("w-full").props("dense") \
                .tooltip("Multiplies every text size; never below the preset minimum")
            ui.switch("Tidy category names (underscores → spaces)", value=s.prettify_values,
                      on_change=lambda e: self.set_attr(s, "prettify_values", e.value)) \
                .props("dense")

    # ------------------------------------------------------------- presets --
    BUILTIN_PRESETS = {"Thesis": ("thesis", "thesis_caption"),
                       "Thesis (full width)": ("thesis", "thesis_full"),
                       "Slides": ("slides", "slide_16_9"), "Poster": ("poster", "poster")}
    PRESET_EXPORT_KEYS = ("size_preset", "width_cm", "height_cm", "usetex", "mathtext", "dpi",
                          "formats", "transparent")

    def preset_row(self):
        user = state.user_presets()
        opts = {f"builtin:{k}": f"{k} (built-in)" for k in self.BUILTIN_PRESETS}
        opts.update({f"user:{k}": k for k in user})
        with ui.row().classes("w-full items-center no-wrap gap-1"):
            sel = ui.select(opts, label="Named presets (style + size)", value=None) \
                .classes("grow").props("dense")
            ui.button(icon="download", on_click=lambda: self.apply_preset(sel.value)) \
                .props("flat dense round").tooltip("Apply the selected preset")
            ui.button(icon="add", on_click=self.save_preset_dialog) \
                .props("flat dense round").tooltip("Save the current look as a preset")
            ui.button(icon="delete_outline", on_click=lambda: self.delete_preset(sel.value)) \
                .props("flat dense round").tooltip("Delete the selected user preset")

    def apply_preset(self, key):
        if not key:
            ui.notify("Choose a preset first.")
            return
        kind, name = key.split(":", 1)
        if kind == "builtin":
            style_name, size = self.BUILTIN_PRESETS[name]
            self.spec.style = Style(preset=style_name, labels=self.spec.style.labels,
                                    value_labels=self.spec.style.value_labels)
            e = self.spec.export
            e.size_preset, e.width_cm, e.height_cm = size, None, None
        else:
            data = state.user_presets().get(name)
            if not data:
                return
            keep = self.spec.style
            self.spec.style = Style(**{k: v for k, v in data["style"].items()
                                       if k in Style.__dataclass_fields__})
            self.spec.style.labels, self.spec.style.value_labels = keep.labels, keep.value_labels
            for k, v in data.get("export", {}).items():
                setattr(self.spec.export, k, v)
        ui.notify(f"Applied preset “{name}”.")
        self.changed("style_panel", "size_panel")

    def save_preset_dialog(self):
        with ui.dialog() as dlg, ui.card().classes("w-96"):
            ui.label("Save style preset").classes("text-lg font-medium")
            ui.label("Stores fonts, sizes, colours, legend and margin settings plus the figure "
                     "size — not the data, labels or filters.").classes("text-xs text-gray-500")
            name = ui.input("Preset name", placeholder="e.g. thesis small panels").classes("w-full")

            def save():
                if not name.value.strip():
                    return
                style = self.spec.copy().style.__dict__.copy()
                style.update(labels={}, value_labels={}, title="", subtitle="", footnote="",
                             xlabel=None, ylabel=None, xlim=None, ylim=None)
                export = {k: getattr(self.spec.export, k) for k in self.PRESET_EXPORT_KEYS}
                state.save_user_preset(name.value.strip(), {"style": style, "export": export})
                dlg.close()
                ui.notify(f"Saved preset “{name.value.strip()}”.", type="positive")
                self.style_panel.refresh()
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button("Save", on_click=save)
        dlg.open()

    def delete_preset(self, key):
        if not key or not key.startswith("user:"):
            ui.notify("Only your own presets can be deleted.")
            return
        state.delete_user_preset(key.split(":", 1)[1])
        self.style_panel.refresh()

    def text_input(self, label, obj, attr, none_if_empty=False, placeholder=None):
        def set_(e):
            v = e.value
            setattr(obj, attr, (v or None) if none_if_empty else (v or ""))
            self.changed()
        ui.input(label, value=getattr(obj, attr) or "", placeholder=placeholder,
                 on_change=set_).classes("w-full").props("dense debounce=500 clearable")

    def columns_in_use(self):
        m = self.spec.mapping
        cols = [m.x, *m.y, m.hue, m.facet, m.style, m.row, m.secondary]
        return [c for c in dict.fromkeys(cols) if c and c != "__metric__"]

    def label_overrides(self):
        s = self.spec.style
        with ui.expansion("Rename columns and categories", icon="edit").classes("w-full") \
                .props("dense"):
            for col in self.columns_in_use():
                def set_(e, col=col):
                    if e.value:
                        s.labels[col] = e.value
                    else:
                        s.labels.pop(col, None)
                    self.changed()
                ui.input(col, value=s.labels.get(col, ""), placeholder=reg.axis_label(col),
                         on_change=set_).classes("w-full").props("dense debounce=500 clearable")
            levels = self.hue_levels()
            if levels:
                ui.label("Category names (colour groups)").classes("rs-sec")
                for v in levels:
                    key = reg._value_key(v)

                    def set_v(e, key=key):
                        if e.value:
                            s.value_labels[key] = e.value
                        else:
                            s.value_labels.pop(key, None)
                        self.changed()
                    ui.input(key, value=s.value_labels.get(key, ""),
                             placeholder=reg.value_label(v, None, s.prettify_values),
                             on_change=set_v).classes("w-full").props("dense debounce=500 clearable")

    def hue_levels(self) -> list:
        h = self.spec.mapping.hue
        if h and h in self.ds.profile and self.ds.profile[h].values is not None:
            return self.ds.profile[h].values[:24]
        if not h and len(self.spec.mapping.y) > 1 and self.spec.mapping.y_mode == "overlay":
            return list(self.spec.mapping.y)
        return []

    def colour_pickers(self):
        s = self.spec.style
        levels = self.hue_levels()
        if not levels:
            levels_keys = [("__single__", "Series colour")]
        else:
            levels_keys = [(reg._value_key(v), reg.value_label(v, s.value_labels))
                           if v not in self.spec.mapping.y else (v, reg.axis_label(v))
                           for v in levels]
        base = st.palette(s, len(levels_keys))
        with ui.expansion("Colour per series", icon="format_color_fill").classes("w-full") \
                .props("dense"):
            for (key, label), default in zip(levels_keys, base):
                def set_c(e, key=key):
                    if e.value:
                        s.colors[key] = e.value
                    else:
                        s.colors.pop(key, None)
                    self.changed()
                ui.color_input(label, value=s.colors.get(key, default), on_change=set_c) \
                    .classes("w-full").props("dense")
            ui.button("Back to palette colours", on_click=self.reset_colours) \
                .props("flat dense no-caps size=sm")

    def reset_colours(self):
        self.spec.style.colors = {}
        self.changed("style_panel")

    def set_lim(self, ax, i, value):
        s = self.spec.style
        lim = list(getattr(s, f"{ax}lim") or [None, None])
        lim[i] = value
        setattr(s, f"{ax}lim", lim if any(v is not None for v in lim) else None)
        self.changed()

    def reset_style(self):
        self.spec.style = Style(preset=self.spec.style.preset)
        self.spec.options = {}
        self.changed("style_panel", "data_panel")

    # ============================================================ size panel ==
    @ui.refreshable
    def size_panel(self):
        if self.spec is None:
            return
        e, settings = self.spec.export, self.settings
        sizes = st.size_presets()
        ui.select({k: v["label"] for k, v in sizes.items()}, value=e.size_preset,
                  label="Size preset", on_change=lambda ev: self.set_size_preset(ev.value)) \
            .classes("w-full").props("dense")
        w0, h0 = st.figure_size_cm(type(e)(size_preset=e.size_preset), settings["textwidth_cm"])
        with ui.row().classes("w-full no-wrap gap-2"):
            ui.number("Width (cm)", value=e.width_cm, min=2, max=60, step=0.1,
                      placeholder=f"{w0:g} (preset)",
                      on_change=lambda ev: self.set_attr(e, "width_cm", ev.value, "size_panel")) \
                .classes("grow").props("dense clearable")
            ui.number("Height (cm)", value=e.height_cm, min=2, max=60, step=0.1,
                      placeholder=f"{h0:g} (preset)",
                      on_change=lambda ev: self.set_attr(e, "height_cm", ev.value, "size_panel")) \
                .classes("grow").props("dense clearable")
        w, h = st.figure_size_cm(e, settings["textwidth_cm"])
        ui.label(f"Figure: {w:g} × {h:g} cm → \\includegraphics[width="
                 f"{st.latex_width(w, settings['textwidth_cm'])}]").classes("text-xs text-gray-500")

        ui.label("Text rendering").classes("rs-sec")
        ok, msg = S.tex_available()
        sw = ui.switch("Use LaTeX for text (usetex, exact match to the thesis; slower)",
                       value=e.usetex and ok,
                       on_change=lambda ev: self.set_attr(e, "usetex", ev.value)).props("dense")
        sw.tooltip(msg)
        if not ok:
            sw.disable()
            ui.label(msg).classes("text-xs text-orange-10")
        ui.select({"stix": "STIX (Times-style, matches mathptmx)", "cm": "Computer Modern",
                   "custom": "Same as text font"}, value=e.mathtext,
                  label="Maths font for $…$ (without usetex)",
                  on_change=lambda ev: self.set_attr(e, "mathtext", ev.value)) \
            .classes("w-full").props("dense")

        ui.label("Document settings").classes("rs-sec")
        with ui.row().classes("w-full no-wrap gap-2"):
            ui.number("Text width (cm)", value=settings["textwidth_cm"], min=5, max=40, step=0.1,
                      on_change=lambda ev: self.set_setting("textwidth_cm", ev.value)) \
                .classes("grow").props("dense").tooltip(r"\textwidth of the thesis (18.0 cm)")
            ui.number("Max figure height (cm)", value=settings["thesis_max_height_cm"], min=5,
                      max=40, step=0.5,
                      on_change=lambda ev: self.set_setting("thesis_max_height_cm", ev.value)) \
                .classes("grow").props("dense")

        ui.label("Actual-size preview").classes("rs-sec")
        ui.label(f"Screen scale: {settings['screen_px_per_cm']:.1f} px per cm").classes("text-sm")
        ui.button("Calibrate screen …", icon="straighten", on_click=self.calibrate) \
            .props("flat dense no-caps")
        ui.label(f"rsplot {__version__}").classes("text-xs text-gray-400 mt-4")

    def set_size_preset(self, key):
        e = self.spec.export
        e.size_preset = key
        e.width_cm = e.height_cm = None
        style = st.size_presets()[key].get("style")
        if style and style != self.spec.style.preset and not (
                style == "thesis" and self.spec.style.preset.startswith("thesis")):
            self.spec.style.preset = style
        self.changed("size_panel", "style_panel")

    def set_setting(self, key, value):
        if value is None:
            return
        self.settings = state.update_settings(**{key: float(value)})
        self.changed("size_panel")

    def calibrate(self):
        ppc = {"v": self.settings["screen_px_per_cm"]}
        with ui.dialog() as dlg, ui.card().classes("w-[44rem]"):
            ui.label("Calibrate the actual-size preview").classes("text-lg font-medium")
            ui.label("Hold a ruler against the bar and move the slider until the bar is "
                     "exactly 10 cm long.").classes("text-sm")
            bar = ui.element("div").style(
                f"height:18px;background:#1f2937;width:{ppc['v'] * 10:.0f}px")
            lab = ui.label()

            def upd(e):
                ppc["v"] = e.value
                bar.style(f"height:18px;background:#1f2937;width:{e.value * 10:.0f}px")
                lab.set_text(f"{e.value:.1f} px per cm")
            ui.slider(min=20, max=70, step=0.1, value=ppc["v"], on_change=upd).classes("w-full")
            lab.set_text(f"{ppc['v']:.1f} px per cm")

            def save():
                self.settings = state.update_settings(screen_px_per_cm=ppc["v"])
                dlg.close()
                self.changed("size_panel")
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button("Save", on_click=save)
        dlg.open()


    # ===================================================== save & reopen ==
    def save_dialog(self):
        if self.spec is None or self.ds is None:
            ui.notify("Open a dataset first.")
            return
        e = self.spec.export
        folder = {"v": e.folder or self.settings["last_folder"]}
        with ui.dialog() as dlg, ui.card().classes("w-[40rem]"):
            ui.label("Save figure").classes("text-lg font-medium")
            with ui.row().classes("w-full no-wrap items-end gap-2"):
                f_in = ui.input("Output folder", value=folder["v"]).classes("grow") \
                    .props("dense")
                ui.button("Browse …", icon="folder_open",
                          on_click=lambda: pick_path(f_in.value or S.PROJECT,
                                                     lambda p: f_in.set_value(str(p)),
                                                     mode="folder", title="Choose output folder")) \
                    .props("flat dense no-caps")
            name_in = ui.input("File name (without extension)",
                               value=e.filename or ex.suggest_filename(self.spec)) \
                .classes("w-full").props("dense")
            hint = ui.label().classes("text-xs text-gray-500")

            def upd_hint():
                hint.set_text(f"Saved as {ex.safe_filename(name_in.value)}.<format>  +  "
                              f"{ex.safe_filename(name_in.value)}{ex.SIDECAR_SUFFIX} (settings)")
            name_in.on_value_change(lambda _: upd_hint())
            upd_hint()
            with ui.row().classes("items-center gap-4"):
                fmts = {f: ui.checkbox(f.upper(), value=f in (e.formats or ["pdf"]))
                        for f in ex.FORMATS}
                dpi = ui.number("PNG dpi", value=e.dpi, min=72, max=1200, step=50) \
                    .classes("w-28").props("dense")
                transp = ui.switch("Transparent background", value=e.transparent).props("dense")
            ui.label("PDF: vector, fonts embedded (TrueType), PDF 1.4 for pdfLaTeX.") \
                .classes("text-xs text-gray-500")

            async def do_save(overwrite=False, name=None):
                e.folder = f_in.value.strip()
                e.filename = ex.safe_filename(name or name_in.value)
                e.formats = [f for f, cb in fmts.items() if cb.value] or ["pdf"]
                e.dpi = int(dpi.value or 300)
                e.transparent = bool(transp.value)
                spec, ds = self.spec.copy(), self.ds
                try:
                    res = await run.io_bound(ex.save_figure, spec, ds, overwrite)
                except FileExistsError as err:
                    self.conflict_dialog(str(err).splitlines(), e, do_save)
                    return
                except Exception as err:
                    ui.notify(f"Could not save: {err}", type="negative", multi_line=True)
                    return
                dlg.close()
                self.settings = state.settings()
                state.save_last_spec(self.spec.to_dict())
                self.saved_dialog(res)
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button("Save", icon="save", on_click=lambda: do_save())
        dlg.open()

    def conflict_dialog(self, files, e, do_save):
        alt = ex.next_free_name(e.folder, e.filename, e.formats)
        with ui.dialog() as dlg, ui.card().classes("w-[36rem]"):
            ui.label("These files already exist").classes("text-lg font-medium text-negative")
            for f in files:
                ui.label(f).classes("text-xs font-mono break-all")

            async def choose(kind):
                dlg.close()
                if kind == "overwrite":
                    await do_save(overwrite=True, name=e.filename)
                elif kind == "suffix":
                    await do_save(name=alt)
            with ui.row().classes("w-full justify-end"):
                ui.button("Cancel", on_click=dlg.close).props("flat")
                ui.button(f"Save as {alt}", on_click=lambda: choose("suffix")).props("outline")
                ui.button("Overwrite", on_click=lambda: choose("overwrite")).props("color=negative")
        dlg.open()

    def saved_dialog(self, res):
        with ui.dialog() as dlg, ui.card().classes("w-[46rem]"):
            ui.label("Figure saved").classes("text-lg font-medium text-positive")
            for f in res.files:
                ui.label(f).classes("text-xs font-mono break-all")
            ui.label(f"Settings: {res.sidecar}").classes("text-xs font-mono break-all text-gray-500")
            for w in res.warnings:
                ui.label(w).classes("text-xs text-orange-10")
            for title, text in (("Include in LaTeX", res.latex),
                                ("Figure environment", res.figure_env)):
                with ui.row().classes("w-full items-center justify-between mt-2"):
                    ui.label(title).classes("rs-sec")
                    ui.button("Copy", icon="content_copy",
                              on_click=lambda t=text: (ui.clipboard.write(t),
                                                       ui.notify("Copied"))) \
                        .props("flat dense no-caps size=sm")
                ui.code(text, language="latex").classes("w-full text-xs") \
                    .style("white-space: pre-wrap; word-break: break-all")
            if res.caption:
                with ui.row().classes("w-full items-center justify-between mt-2"):
                    ui.label("Caption text (what was fixed / averaged)").classes("rs-sec")
                    ui.button("Copy", icon="content_copy",
                              on_click=lambda: (ui.clipboard.write(res.caption),
                                                ui.notify("Copied"))) \
                        .props("flat dense no-caps size=sm")
                ui.label(res.caption).classes("text-xs text-gray-700")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dlg.close)
        dlg.open()

    def recent_dialog(self):
        items = state.recent_figures()
        with ui.dialog() as dlg, ui.card().classes("w-[50rem] max-w-full"):
            ui.label("Recent figures").classes("text-lg font-medium")
            if not items:
                ui.label("No figures saved yet.").classes("text-gray-500")
            with ui.scroll_area().classes("h-96 w-full"):
                for r in items:
                    ok = Path(r["sidecar"]).exists()
                    with ui.row().classes("w-full items-center no-wrap border-b py-1"):
                        with ui.column().classes("grow gap-0"):
                            ui.label(r["title"]).classes("text-sm")
                            ui.label(r["sidecar"]).classes("text-xs text-gray-500 break-all")
                        if ok:
                            ui.button("Open", on_click=lambda p=r["sidecar"]: (
                                dlg.close(), background_tasks.create(self.load_figure(p)))) \
                                .props("flat dense no-caps")
                        else:
                            ui.label("missing").classes("text-xs text-negative")
            with ui.row().classes("w-full justify-end"):
                ui.button("Close", on_click=dlg.close).props("flat")
        dlg.open()

    def open_settings_dialog(self):
        start = self.spec.export.folder if self.spec and self.spec.export.folder else \
            self.settings["last_folder"]
        pick_path(start, lambda p: background_tasks.create(self.load_figure(str(p))),
                  mode="file", patterns=("*" + ex.SIDECAR_SUFFIX,),
                  title="Open figure settings (.rsplot.json)")

    @in_page
    async def load_figure(self, path):
        try:
            lf = ex.load_sidecar(path)
        except Exception as err:
            ui.notify(f"Cannot open {Path(path).name}: {err}", type="negative")
            return
        for n in lf.notes:
            ui.notify(n, type="warning", multi_line=True, timeout=8000)
        if not Path(lf.spec.dataset.path).exists():
            return
        await self.open_dataset(lf.spec.dataset.path, spec=lf.spec, family=lf.spec.dataset.family)
        ui.notify(f"Loaded {Path(path).name}", type="positive")


# ===================================================================== main ==
def main(argv=None):
    ap = argparse.ArgumentParser(description="rsplot: figure maker for the thesis data")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser tab")
    args, _ = ap.parse_known_args(argv)

    @ui.page("/")
    def index():
        App().build()

    # localhost only: the app can browse local files, so never expose it on the network
    ui.run(title="rsplot", host="127.0.0.1", port=args.port, show=not args.no_browser,
           reload=False,
           favicon="📈", show_welcome_message=True)


if __name__ in {"__main__", "__mp_main__"}:
    main()
