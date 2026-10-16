"""Server-side file / folder picker dialog (the browser cannot see local paths)."""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Callable

from nicegui import ui

HIDDEN = ["*_Old", ".*", "__pycache__", ".venv"]


def pick_path(start: str | Path, on_pick: Callable[[Path], None], *, mode: str = "file",
              patterns: tuple[str, ...] = ("*.csv",), title: str = "Choose a file") -> None:
    """Open a dialog. mode = "file" (click a matching file) or "folder" (choose current dir)."""
    cur = {"dir": Path(start).expanduser()}
    if cur["dir"].is_file():
        cur["dir"] = cur["dir"].parent
    while not cur["dir"].exists() and cur["dir"] != cur["dir"].parent:
        cur["dir"] = cur["dir"].parent
    show_hidden = {"on": False}

    with ui.dialog() as dlg, ui.card().classes("w-[44rem] max-w-full"):
        ui.label(title).classes("text-lg font-medium")
        with ui.row().classes("w-full items-center no-wrap"):
            ui.button(icon="arrow_upward", on_click=lambda: go(cur["dir"].parent)) \
                .props("flat dense").tooltip("Parent folder")
            path_in = ui.input(value=str(cur["dir"])).classes("grow").props("dense")
            path_in.on("keydown.enter", lambda: go(Path(path_in.value)))
            ui.switch("Show _Old / hidden", value=False,
                      on_change=lambda e: (show_hidden.update(on=e.value), listing.refresh()))
        if mode == "file":
            ui.label("Folders open on click; click a file to choose it.") \
                .classes("text-xs text-gray-500")

        @ui.refreshable
        def listing():
            d = cur["dir"]
            try:
                entries = sorted(d.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            except OSError as e:
                ui.label(f"Cannot open folder: {e}").classes("text-negative")
                return
            with ui.scroll_area().classes("h-96 w-full border rounded"):
                for p in entries:
                    if not show_hidden["on"] and any(fnmatch.fnmatch(p.name, h) for h in HIDDEN):
                        continue
                    if p.is_dir():
                        with ui.item(on_click=lambda p=p: go(p)).props("dense"), \
                                ui.row().classes("items-center w-full no-wrap gap-2"):
                            ui.icon("folder", color="amber-8")
                            ui.label(p.name)
                    elif mode == "file" and any(fnmatch.fnmatch(p.name, pt) for pt in patterns):
                        with ui.item(on_click=lambda p=p: choose(p)).props("dense"), \
                                ui.row().classes("items-center w-full no-wrap gap-2"):
                            ui.icon("description", color="blue-8")
                            ui.label(p.name).classes("grow")
                            ui.label(_size(p)).classes("text-xs text-gray-500")

        def go(p: Path):
            if p.is_dir():
                cur["dir"] = p
                path_in.value = str(p)
                listing.refresh()
            elif p.is_file() and mode == "file":
                choose(p)
            else:
                ui.notify(f"Not a folder: {p}", type="warning")

        def choose(p: Path):
            dlg.close()
            on_pick(p)

        listing()
        with ui.row().classes("w-full justify-end"):
            ui.button("Cancel", on_click=dlg.close).props("flat")
            if mode == "folder":
                ui.button("Use this folder", on_click=lambda: choose(cur["dir"]))
    dlg.open()


def _size(p: Path) -> str:
    try:
        n = p.stat().st_size
    except OSError:
        return ""
    for unit in ("B", "kB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
