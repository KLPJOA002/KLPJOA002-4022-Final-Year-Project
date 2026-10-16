"""Persistent app state in Plotter/.state/ (settings, datasets, recent figures, presets)."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATE_DIR = Path(os.environ.get("RSPLOT_STATE_DIR", ROOT / ".state"))
_LOCK = threading.Lock()

DEFAULT_SETTINGS = {
    "textwidth_cm": 18.0,
    "thesis_max_height_cm": 22.0,
    "screen_px_per_cm": 37.8,      # browser CSS default (96 px/in); calibrate in the UI
    "last_folder": str(ROOT.parents[1] / "Report" / "uct-thesis-template" / "figs"),
    "mathtext_default": "stix",
}


def _path(name: str) -> Path:
    return STATE_DIR / name


def _read(name: str, default):
    p = _path(name)
    try:
        return json.loads(p.read_text())
    except (OSError, ValueError):
        return default


def _write(name: str, data) -> None:
    with _LOCK:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _path(name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, default=str))
        tmp.replace(_path(name))


# --------------------------------------------------------------- settings --
def settings() -> dict:
    return {**DEFAULT_SETTINGS, **_read("settings.json", {})}


def update_settings(**kw) -> dict:
    s = settings()
    s.update(kw)
    _write("settings.json", s)
    return s


# --------------------------------------------------------------- datasets --
def datasets() -> list[dict]:
    """Registered datasets: [{path, family, name}]."""
    return _read("datasets.json", [])


def add_dataset(path: str, family: str, name: str | None = None) -> list[dict]:
    items = [d for d in datasets() if d["path"] != path]
    items.append({"path": path, "family": family, "name": name or Path(path).parent.name
                  + "/" + Path(path).name})
    _write("datasets.json", items)
    return items


def remove_dataset(path: str) -> list[dict]:
    items = [d for d in datasets() if d["path"] != path]
    _write("datasets.json", items)
    return items


# --------------------------------------------------------- recent figures --
def recent_figures() -> list[dict]:
    return _read("recent.json", [])


def add_recent(sidecar: str, title: str, files: list[str]) -> None:
    items = [r for r in recent_figures() if r["sidecar"] != sidecar]
    items.insert(0, {"sidecar": sidecar, "title": title, "files": files})
    _write("recent.json", items[:50])


# ---------------------------------------------------------- style presets --
def user_presets() -> dict[str, dict]:
    return _read("style_presets.json", {})


def save_user_preset(name: str, data: dict) -> None:
    p = user_presets()
    p[name] = data
    _write("style_presets.json", p)


def delete_user_preset(name: str) -> None:
    p = user_presets()
    p.pop(name, None)
    _write("style_presets.json", p)


# ------------------------------------------------------------- last figure --
def last_spec() -> dict | None:
    return _read("last_spec.json", None)


def save_last_spec(spec: dict) -> None:
    _write("last_spec.json", spec)
