"""
Light-analysis metrics: collect every *_metrics.csv under a data directory,
extract the columns of interest, and plot depth performance vs ambient light.

Companion to Height_Analysis/plot_height_metrics.py and
Angle_Analysis/plot_angle_metrics.py -- same loading, outlier rejection,
summary and plot style. The x axis is the illuminance measured with the phone
(`lux:` in trial_info.txt), on a symlog scale because it spans 0 .. ~25 000 lx.
Series are the scene: indoor foam board, outdoor foam board, outdoor ground
(no board). The board and no-board trials measure different surfaces, so every
figure is drawn once per surface group (PLOT_GROUPS), each into its own
subfolder of Plots/, on the same lux axis so the two sets line up.

Detection failures: in direct sunlight (and sunlight under a shade) the white
foam board saturates and the tracked ROI wanders over the whole image, so the
per-frame error numbers of those trials describe whatever the ROI landed on,
not the board. Each trial is therefore checked for a usable detection (fill
and ROI stability, see DETECTION below). Failed trials are left out of the
accuracy / noise curves and marked with an x at their lux instead; they are
still drawn (hollow) in the detection and sensor-response figures, where their
numbers are real.

Re-running the failed trials with a fixed ROI: the capture tool can replay
the recordings with the ROI tracking switched off, e.g. (from
Code/Capture/tools/Depth_Quality)

    ./depth_quality --reprocess /run/media/joab/Seagate/roughness/Joab_Characterisation/Light_Error \
        --patch-size 0 --roi 498,218,284,284 \
        -D /run/media/joab/Seagate/roughness/Joab_Characterisation/Light_Error_FixedROI

498,218,284,284 is where the indoor board trials settled, and it sits inside
every other trial's ROI, so all trials get compared on the same pixels. Copy
the *_metrics.csv / trial_info.txt of the result into a folder and point
DATA_ROOT at it -- nothing else changes.

Run it straight from VS Code (Run Python File / F5, or Shift+Enter through the
`# %%` cells). No command-line arguments -- everything is configured in the
CONFIG block below.

Folder layout it expects:

    Data/
      20260929_120155/                      <- session
        summary.csv
        20260929_120155_t0_h902_p0.0_r0.0_Direct_Light_With_Board/
          ..._metrics.csv                   <- one row per frame
          trial_info.txt                    <- key: value metadata (incl. lux)
"""

# %% ---------------------------------------------------------------- CONFIG --
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D
from matplotlib.ticker import FixedLocator, FuncFormatter

# Root that gets walked recursively. Default: the Data/ folder next to this file.
DATA_ROOT = Path(__file__).resolve().parent / "Data"

# Where figures and the tidy CSVs are written.
OUT_DIR = Path(__file__).resolve().parent / "Plots"

# Columns pulled out of each metrics.csv.
VALUE_COLUMNS = [
    "gt_axis_mm",          # ground-truth distance to the target
    "z_err_median_pct",    # accuracy, scale-free
    "z_err_mean_mm",       # accuracy, absolute
    "z_err_median_mm",     # robust absolute accuracy (ignores outlier pixels)
    "z_err_rmse_mm",       # accuracy including the tails
    "std_z_mm",            # spatial noise inside the ROI
    "plane_rms_mm",        # flatness / plane-fit residual
    "plane_rms_pct",       # flatness, scale-free
    "subpixel_rms_px",     # plane residual in disparity terms
    "fill_pct",            # valid-pixel yield -- the usual first failure mode
    "dist_err_mm",         # error of the fitted plane distance
    "plane_pitch_deg",     # target orientation as measured
    "plane_roll_deg",
    "ir_mean",             # IR brightness -- the ambient light the sensor sees
    "exposure",            # auto-exposure [us] -- falls as the light rises
    "gain",
    "roi_w",               # tracked ROI size -- wanders when the target is lost
    "roi_h",
]

# Columns that must exist for a row to be usable.
REQUIRED_COLUMNS = ["gt_axis_mm", "z_err_median_pct", "z_err_mean_mm"]

# The capture pipeline repeats the last frame when a new one has not arrived
# (identical device_ts_ms). Those duplicates bias the per-trial statistics, so
# they are dropped by default. Set False to keep the raw stream.
DROP_REPEATED_FRAMES = True

# Discard the first N frames of each trial (auto-exposure settling).
SKIP_FIRST_FRAMES = 0

# --- detection ---------------------------------------------------------------
# A trial counts as "detected" when the target was actually measured: the
# median fill is at least MIN_FILL_PCT and the ROI width stays put (coefficient
# of variation across frames at most MAX_ROI_CV). With the tracked ROI, the
# board-in-sun trials had ~15-25 % fill and an ROI swinging between 8 and
# 1280 px wide; reprocessed with a fixed ROI on the board they drop to ~5 %
# fill. Every other trial holds > 85 % either way.
MIN_FILL_PCT = 60.0
MAX_ROI_CV = 0.10

# Manual overrides, keyed by trial-folder name or session stamp -- the rule
# above is applied first, then these win.
FORCE_FAILED: set[str] = set()
FORCE_DETECTED: set[str] = set()

# Draw failed trials on the accuracy / noise curves anyway (as hollow markers).
# Off by default: their numbers come from a wandering ROI and wreck the scale.
PLOT_FAILED_IN_CURVES = False

# --- outlier rejection -------------------------------------------------------
# Frames whose metrics sit more than OUTLIER_SIGMA deviations from the centre of
# their own trial are dropped. Method:
#   "mad"  robust: centre = median, scale = 1.4826 * median absolute deviation.
#          Recommended -- a single 1400 mm frame cannot hide itself.
#   "std"  the textbook mean +/- 3*std, applied iteratively (see below).
#   "none" keep every frame.
# Why iterate for "std": one wild frame inflates the very std it is measured
# against (a 1450 mm spike in a 4 mm trial pushes 3*std past 100 mm, so the
# spike passes its own test -- "masking"). Re-fitting mean/std on the survivors
# and repeating, up to OUTLIER_MAX_ITER times or until nothing new is cut,
# removes the mask. "mad" does not need this but still honours the setting.
OUTLIER_METHOD = "mad"        # "mad" | "std" | "none"
OUTLIER_SIGMA = 3.0
OUTLIER_MAX_ITER = 5

# Metrics that decide whether a frame is bad. A frame failing on any one of
# them is dropped whole -- if the depth of a frame is wrong, none of its other
# numbers are trustworthy either.
OUTLIER_COLUMNS = ["z_err_mean_mm", "plane_rms_mm"]

# Never cut more than this fraction of a trial. If a rule wants more, the trial
# is left untouched and a warning printed -- that means the trial is genuinely
# bad (or bimodal), not that it contains a few spikes.
OUTLIER_MAX_FRACTION = 0.25

# --- lux axis ----------------------------------------------------------------
# symlog: linear below LUX_LINTHRESH (so the 0 lx dark trial still has a place),
# logarithmic above it.
LUX_LINTHRESH = 10.0
LUX_TICKS = [0, 10, 100, 1_000, 10_000, 100_000]

# --- surface groups ----------------------------------------------------------
# The full figure set is drawn once per group, into OUT_DIR/<subfolder>.
#   key: (surfaces included, name used in titles, output subfolder)
# Add e.g. "all": (("foam board", "no board"), "all surfaces", "all") to also
# get the combined figures.
PLOT_GROUPS = {
    "board": (("foam board",), "foam board", "board"),
    "no_board": (("no board",), "no board", "no_board"),
}

SAVE_FIGURES = True
SHOW_FIGURES = True
DPI = 200

# ------------------------------------------------------------------ palette --
# Categorical slots 1-3 of the validated default palette: blue / orange / aqua.
# Each series also gets its own marker shape, so identity is not colour alone.
SERIES_COLORS = {"indoor, foam board": "#2a78d6",
                 "outdoor, foam board": "#eb6834",
                 "outdoor, no board": "#1baf7a"}
SERIES_MARKERS = {"indoor, foam board": "o",
                  "outdoor, foam board": "s",
                  "outdoor, no board": "D"}
SERIES_ORDER = list(SERIES_COLORS)
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
SURFACE = "#fcfcfb"

# Trial-folder names look like:
#   20260929_181926_t0_h902_p0.0_r0.0_Inside_Afternoon_BlindsClosed_Lights_foamBoard
NAME_RE = re.compile(
    r"^(?P<stamp>\d{8}_\d{6})_t(?P<trial>\d+)"
    r"_h(?P<height>\d+)"
    r"_p(?P<pitch>-?[\d.]+)"
    r"_r(?P<roll>-?[\d.]+)"
    r"_(?P<label>.+)$"
)

# Label tokens -> readable condition text (anything not listed is dropped).
LABEL_WORDS = {
    "direct": "direct sun", "shaded": "shaded", "shade": "under shade",
    "withshade": "under shade", "afternoon": "afternoon", "evening": "evening",
    "blindsopen": "blinds open", "blindsclosed": "blinds closed",
    "lights": "lights on", "nolights": "lights off",
}


# %% ------------------------------------------------------------- discovery --
def find_metrics_files(root: Path) -> list[Path]:
    """Every *_metrics.csv under `root`, skipping editor lock files."""
    files = [
        p
        for p in sorted(root.rglob("*_metrics.csv"))
        if not p.name.startswith(".") and not p.name.startswith("~")
    ]
    if not files:
        raise FileNotFoundError(f"No *_metrics.csv found under {root}")
    return files


def parse_trial_name(name: str) -> dict:
    """Pull session / trial / height / pose / label out of the folder name."""
    m = NAME_RE.match(name)
    if not m:
        return {"session": "", "trial": np.nan, "height_mm": np.nan,
                "pitch_set_deg": np.nan, "roll_set_deg": np.nan, "label": name}
    g = m.groupdict()
    return {
        "session": g["stamp"],
        "trial": int(g["trial"]),
        "height_mm": float(g["height"]),
        "pitch_set_deg": float(g["pitch"]),
        "roll_set_deg": float(g["roll"]),
        "label": g["label"],
    }


def read_trial_info(folder: Path) -> dict:
    """Parse the `key: value` header of trial_info.txt, if present.

    Also picks temporal_noise_mm out of the indented stats block -- it is only
    computed once per trial, so it is not in the per-frame CSV.
    """
    info_path = folder / "trial_info.txt"
    if not info_path.exists():
        return {}
    info: dict[str, str] = {}
    out: dict[str, float | str] = {}
    for line in info_path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        if line.startswith(" "):
            parts = line.split()
            if parts[0] == "temporal_noise_mm":
                try:
                    out["temporal_noise_mm"] = float(parts[1])
                except (ValueError, IndexError):
                    pass
            continue          # the rest of the stats block is per-frame data
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in info:       # e.g. "record:" paths contain colons; keep first
            continue
        info[key] = value.strip()
    for key in ("lux", "gt_perp_mm", "gt_axis_mm", "baseline_mm", "depth_scale_m",
                "patch_size_mm"):
        if key in info:
            try:
                out[f"info_{key}"] = float(info[key].split()[0])
            except (ValueError, IndexError):
                pass
    for key in ("preset", "serial", "resolution", "device"):
        if key in info:
            out[f"info_{key}"] = info[key]
    return out


def classify_scene(label: str) -> dict:
    """Environment, target surface, the series they make, and readable text."""
    low = label.lower()
    environment = "indoor" if "inside" in low else "outdoor"
    surface = "no board" if re.search(r"no[_ -]?board", low) else "foam board"
    words = [LABEL_WORDS[t] for t in low.split("_") if t in LABEL_WORDS]
    return {
        "environment": environment,
        "surface": surface,
        "series": f"{environment}, {surface}",
        "condition": ", ".join(dict.fromkeys(words)) or label,
    }


def check_detection(df: pd.DataFrame, trial_name: str, session: str) -> dict:
    """Did the trial actually measure the target? See DETECTION in CONFIG."""
    fill = float(df["fill_pct"].median()) if "fill_pct" in df.columns else np.nan
    roi_cv = np.nan
    if "roi_w" in df.columns and df["roi_w"].mean() > 0:
        roi_cv = float(df["roi_w"].std(ddof=0) / df["roi_w"].mean())
    detected = not (fill < MIN_FILL_PCT or roi_cv > MAX_ROI_CV)
    if trial_name in FORCE_FAILED or session in FORCE_FAILED:
        detected = False
    if trial_name in FORCE_DETECTED or session in FORCE_DETECTED:
        detected = True
    return {"fill_trial_pct": fill, "roi_w_cv": roi_cv, "detected": detected}


# %% -------------------------------------------------------------- outliers --
def _inlier_mask(values: pd.Series, method: str, sigma: float, max_iter: int) -> pd.Series:
    """Boolean mask of the values to KEEP, by sigma-clipping one metric."""
    x = pd.to_numeric(values, errors="coerce")
    keep = x.notna()
    if method == "none" or keep.sum() < 3:
        return keep

    for _ in range(max(1, max_iter)):
        sample = x[keep]
        if sample.size < 3:
            break
        if method == "mad":
            centre = sample.median()
            # 1.4826 rescales the MAD to a standard deviation for normal data,
            # so OUTLIER_SIGMA keeps its usual "3 sigma" meaning.
            scale = 1.4826 * (sample - centre).abs().median()
            if scale == 0:                      # degenerate: fall back to std
                scale = sample.std(ddof=0)
        else:
            centre = sample.mean()
            scale = sample.std(ddof=0)
        if not np.isfinite(scale) or scale == 0:
            break

        new_keep = x.notna() & ((x - centre).abs() <= sigma * scale)
        if new_keep.equals(keep):
            break                               # converged
        keep = new_keep
        if method == "mad":
            break                               # robust centre: one pass is enough
    return keep


def filter_outliers(df: pd.DataFrame, trial_name: str = "") -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split a single trial into (kept frames, rejected frames).

    A frame is rejected if ANY of OUTLIER_COLUMNS flags it. The guard rail in
    OUTLIER_MAX_FRACTION keeps the rule from eating a trial whose spread is
    wide for real reasons.
    """
    if OUTLIER_METHOD == "none":
        return df, df.iloc[0:0]

    cols = [c for c in OUTLIER_COLUMNS if c in df.columns]
    if not cols:
        return df, df.iloc[0:0]

    keep = pd.Series(True, index=df.index)
    for col in cols:
        keep &= _inlier_mask(df[col], OUTLIER_METHOD, OUTLIER_SIGMA, OUTLIER_MAX_ITER)

    n_cut = int((~keep).sum())
    if n_cut and n_cut > OUTLIER_MAX_FRACTION * len(df):
        print(f"  ! {trial_name}: outlier rule wanted {n_cut}/{len(df)} frames "
              f"(> {OUTLIER_MAX_FRACTION:.0%}) -- keeping the trial unfiltered")
        return df, df.iloc[0:0]

    return df[keep], df[~keep]


# %% ----------------------------------------------------------------- load --
def load_all(root: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load every trial under `root`.

    Returns (kept frames, rejected frames) -- both tidy, frame-level, with the
    trial metadata attached, so the rejects can be audited rather than vanishing.
    """
    frames, rejected = [], []
    for path in find_metrics_files(root):
        folder = path.parent
        try:
            df = pd.read_csv(path)
        except Exception as exc:                      # noqa: BLE001
            print(f"  ! skipped {path.name}: {exc}")
            continue

        missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
        if missing:
            print(f"  ! skipped {path.name}: missing {missing}")
            continue

        keep = [c for c in VALUE_COLUMNS if c in df.columns]
        extra = [c for c in ("frame", "timestamp_ms", "device_ts_ms") if c in df.columns]
        df = df[extra + keep].copy()

        n_raw = len(df)
        n_dupes = 0
        if DROP_REPEATED_FRAMES and "device_ts_ms" in df.columns:
            df = df.drop_duplicates(subset="device_ts_ms", keep="first")
            n_dupes = n_raw - len(df)
        if SKIP_FIRST_FRAMES:
            df = df.iloc[SKIP_FIRST_FRAMES:]
        if df.empty:
            print(f"  ! skipped {path.name}: no frames left after filtering")
            continue

        meta = parse_trial_name(folder.name)
        meta.update(read_trial_info(folder))
        meta.update(classify_scene(meta.get("label", folder.name)))
        # Judged on every frame, before outlier rejection trims the evidence.
        meta.update(check_detection(df, folder.name, meta.get("session", "")))

        df, cut = filter_outliers(df, folder.name)
        if df.empty:
            print(f"  ! skipped {path.name}: every frame flagged as an outlier")
            continue

        meta["lux"] = meta.get("info_lux", np.nan)
        meta["trial_name"] = folder.name
        meta["source"] = str(path)
        meta["n_frames_raw"] = n_raw
        meta["n_repeated_frames"] = n_dupes
        meta["n_outliers"] = len(cut)
        df = df.copy()
        for key, value in meta.items():
            df[key] = value

        if "timestamp_ms" in df.columns:
            df["t_s"] = (df["timestamp_ms"] - df["timestamp_ms"].iloc[0]) / 1000.0

        if not cut.empty:
            cut = cut.copy()
            for key, value in meta.items():
                cut[key] = value
            rejected.append(cut)

        frames.append(df)
        status = "ok    " if meta["detected"] else "FAILED"
        print(f"  + [{status}] {meta['lux']:>7.0f} lx  {folder.name}: "
              f"{len(df)}/{n_raw} frames kept ({n_dupes} repeated, {len(cut)} outliers), "
              f"fill {meta['fill_trial_pct']:.0f} %, ROI cv {meta['roi_w_cv']:.2f}")

    data = pd.concat(frames, ignore_index=True)
    # Prefer the ground truth recorded in the CSV; fall back to the folder name.
    data["gt_axis_mm"] = data["gt_axis_mm"].fillna(data["height_mm"])

    cut = (pd.concat(rejected, ignore_index=True) if rejected
           else pd.DataFrame(columns=data.columns))
    return data, cut


# Per-trial constants carried into the summary alongside the frame statistics.
TRIAL_COLUMNS = ["environment", "surface", "condition", "detected",
                 "fill_trial_pct", "roi_w_cv", "temporal_noise_mm", "gt_axis_mm",
                 "n_frames_raw", "n_repeated_frames", "n_outliers"]


def summarise(data: pd.DataFrame) -> pd.DataFrame:
    """Per-trial statistics: mean/std plus robust median and IQR."""
    metrics = [c for c in VALUE_COLUMNS if c in data.columns and c != "gt_axis_mm"]
    keys = ["series", "lux", "session", "trial", "trial_name", "label"]
    keys = [k for k in keys if k in data.columns]

    agg = {m: ["mean", "std", "median",
               lambda s: s.quantile(0.25), lambda s: s.quantile(0.75)]
           for m in metrics}
    out = data.groupby(keys, dropna=False).agg(agg)
    out.columns = [
        f"{m}_{ {'<lambda_0>': 'p25', '<lambda_1>': 'p75'}.get(stat, stat) }"
        for m, stat in out.columns
    ]
    out["n_frames"] = data.groupby(keys, dropna=False).size()
    out = out.reset_index()

    trial_cols = [c for c in TRIAL_COLUMNS if c in data.columns]
    per_trial = data.groupby("trial_name")[trial_cols].first().reset_index()
    out = out.merge(per_trial, on="trial_name", how="left")
    return out.sort_values(["series", "lux"]).reset_index(drop=True)


# %% ---------------------------------------------------------------- style --
def style_axes(ax, title: str = "", xlabel: str = "", ylabel: str = "") -> None:
    ax.set_facecolor(SURFACE)
    ax.grid(True, axis="y", color="#e6e5e1", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color("#d8d7d2")
    ax.tick_params(colors=INK_SECONDARY, labelsize=9, length=3)
    if title:
        ax.set_title(title, color=INK, fontsize=11, loc="left", pad=8)
    if xlabel:
        ax.set_xlabel(xlabel, color=INK_SECONDARY, fontsize=9)
    if ylabel:
        ax.set_ylabel(ylabel, color=INK_SECONDARY, fontsize=9)


def lux_axis(ax, lux_max: float) -> None:
    """symlog lux axis with plain-number ticks (0, 10, 100, 1k, 10k ...)."""
    ax.set_xscale("symlog", linthresh=LUX_LINTHRESH, linscale=0.6)
    ticks = [t for t in LUX_TICKS if t <= max(lux_max * 3, 100)]
    ax.xaxis.set_major_locator(FixedLocator(ticks))
    ax.xaxis.set_minor_locator(FixedLocator([]))
    ax.xaxis.set_major_formatter(FuncFormatter(
        lambda v, _: f"{v / 1000:.0f}k" if v >= 1000 else f"{v:.0f}"))
    ax.set_xlim(-2, max(lux_max * 1.6, 100))
    ax.set_xlabel("illuminance (phone lux meter)  [lx]", color=INK_SECONDARY,
                  fontsize=9)


def legend_for(fig, series, failed: bool = False, hollow: bool = False,
               left: bool = False, top: float = 1.0) -> None:
    handles = [
        Line2D([], [], color=SERIES_COLORS.get(s, INK_MUTED),
               marker=SERIES_MARKERS.get(s, "o"), markersize=7, linewidth=2, label=s)
        for s in series
    ]
    if failed:
        handles.append(Line2D([], [], color=INK_MUTED, marker="x", markersize=7,
                              linestyle="none", label="target not detected"))
    if hollow:
        handles.append(Line2D([], [], color=INK_MUTED, marker="o", markersize=7,
                              markerfacecolor=SURFACE, linestyle="none",
                              label="target not detected"))
    # Narrow figures have no room beside the title: tuck the legend under it.
    anchor = dict(loc="upper left", bbox_to_anchor=(0.0, top)) if left \
        else dict(loc="upper right")
    fig.legend(handles=handles, frameon=False, fontsize=9,
               labelcolor=INK_SECONDARY, ncol=len(handles), **anchor)


def series_in(data: pd.DataFrame) -> list[str]:
    present = list(dict.fromkeys(data["series"]))
    return [s for s in SERIES_ORDER if s in present] + \
           [s for s in present if s not in SERIES_ORDER]


def robust_ylim(ax, values, lo_pct=0.5, hi_pct=99.5, pad=0.08, tolerance=3.0) -> int:
    """Scale the y axis to the bulk of the data, not to a handful of spikes.

    The first frames of a trial can be off by a metre while auto-exposure and
    the depth filters settle; left in, they flatten every real feature. The
    spikes are still drawn (clipped at the edge) and counted in the corner note.
    Returns how many points fall outside the limits.
    """
    values = np.asarray(values, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        return 0
    lo, hi = np.percentile(values, [lo_pct, hi_pct])
    # If the extremes are already close to the bulk -- which is the normal case
    # once outlier rejection has run -- show everything rather than clipping
    # perfectly good frames and captioning them as off-scale.
    if hi > lo and (values.max() - values.min()) <= tolerance * (hi - lo):
        lo, hi = values.min(), values.max()
    if hi <= lo:
        lo, hi = values.min(), values.max()
    if hi <= lo:
        hi = lo + 1.0
    span = hi - lo
    ax.set_ylim(lo - pad * span, hi + pad * span)
    n_out = int(((values < lo) | (values > hi)).sum())
    if n_out:
        ax.text(0.99, 0.97, f"{n_out} frame(s) off-scale", transform=ax.transAxes,
                ha="right", va="top", fontsize=8, color=INK_MUTED)
    return n_out


def save(fig, name: str, subdir: str = "") -> None:
    if not SAVE_FIGURES:
        return
    out = OUT_DIR / subdir if subdir else OUT_DIR
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    print(f"  -> {path}")


# %% ----------------------------------------------------------------- plots --
def _draw_series(ax, sub: pd.DataFrame, metric: str, series: str, hollow: bool) -> None:
    """Median marker + IQR bar per trial, joined in lux order."""
    color = SERIES_COLORS.get(series, INK_MUTED)
    y = sub[f"{metric}_median"]
    yerr = None
    if f"{metric}_p25" in sub.columns:
        yerr = [(y - sub[f"{metric}_p25"]).clip(lower=0),
                (sub[f"{metric}_p75"] - y).clip(lower=0)]
    ax.errorbar(
        sub["lux"], y, yerr=yerr,
        color=color, ecolor=color, elinewidth=1.4, capsize=3,
        marker=SERIES_MARKERS.get(series, "o"), markersize=7,
        linewidth=0 if hollow else 2,
        markerfacecolor=SURFACE if hollow else color,
        markeredgecolor=color if hollow else SURFACE,
        markeredgewidth=1.5, zorder=3,
    )


def _mark_failed(ax, failed: pd.DataFrame) -> None:
    """An x on the lux axis for every trial whose target was not detected."""
    for _, row in failed.iterrows():
        ax.axvline(row["lux"], color=INK_MUTED, linewidth=0.8,
                   linestyle=(0, (2, 3)), zorder=0)
        ax.plot(row["lux"], 0.96, transform=ax.get_xaxis_transform(),
                marker="x", markersize=7, markeredgewidth=1.6,
                color=SERIES_COLORS.get(row["series"], INK_MUTED),
                clip_on=False, zorder=4)


def plot_metric_vs_lux(summary: pd.DataFrame, metrics, labels, fname, suptitle,
                       include_failed: bool = False, logy: set[str] = frozenset(),
                       hlines: dict[str, float] | None = None,
                       subdir: str = "", lux_max: float | None = None):
    """Small multiples: one metric per panel, lux on the shared x axis.

    Marker = median across frames, bar = inter-quartile range, so a handful of
    bad frames cannot drag the curve the way a mean +/- std would. Metrics with
    no per-frame spread (temporal_noise_mm) are drawn as a bare marker.

    With `include_failed`, trials whose target was not detected are drawn as
    hollow markers (use it where their numbers are still meaningful -- fill,
    exposure). Otherwise they are left out and marked with an x on the axis.
    `lux_max` fixes the right end of the lux axis, so figures drawn from
    different subsets of the trials share one scale.
    """
    def has(m):
        return f"{m}_median" in summary.columns or m in summary.columns

    metrics = [m for m in metrics if has(m)]
    summary = summary.copy()
    for m in metrics:                       # per-trial scalars -> same shape
        if f"{m}_median" not in summary.columns:
            summary[f"{m}_median"] = summary[m]

    ok = summary[summary["detected"]]
    failed = summary[~summary["detected"]]
    n = len(metrics)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.9), facecolor=SURFACE)
    axes = np.atleast_1d(axes)

    for ax, metric in zip(axes, metrics):
        for series in series_in(summary):
            sub = ok[ok["series"] == series].sort_values("lux")
            if not sub.empty:
                _draw_series(ax, sub, metric, series, hollow=False)
            if include_failed or PLOT_FAILED_IN_CURVES:
                sub = failed[failed["series"] == series]
                if not sub.empty:
                    _draw_series(ax, sub, metric, series, hollow=True)
        if not (include_failed or PLOT_FAILED_IN_CURVES):
            _mark_failed(ax, failed)
        if metric in logy:
            ax.set_yscale("log")
        if hlines and metric in hlines:
            ax.axhline(hlines[metric], color=INK_MUTED, linewidth=1,
                       linestyle=(0, (4, 4)), zorder=0)
        style_axes(ax, labels.get(metric, metric))
        lux_axis(ax, summary["lux"].max() if lux_max is None else lux_max)

    if suptitle:
        fig.suptitle(suptitle, color=INK, fontsize=13, x=0.005, ha="left", y=1.06)
    show_hollow = include_failed or PLOT_FAILED_IN_CURVES
    legend_for(fig, series_in(summary), failed=not failed.empty and not show_hollow,
               hollow=not failed.empty and show_hollow, left=n < 3)
    fig.tight_layout()
    save(fig, fname, subdir)
    return fig


def plot_condition_overview(summary: pd.DataFrame, metrics, labels,
                            fname="condition_overview", subdir: str = "",
                            title: str = "Every light condition"):
    """One bar per trial, brightest first, labelled with its condition.

    The lux figures put every trial on one axis; this one names them, so the
    lights-on / blinds-open comparisons can be read off directly.
    """
    metrics = [m for m in metrics if f"{m}_median" in summary.columns]
    rows = summary.sort_values("lux", ascending=False).reset_index(drop=True)
    n = len(rows)
    fig, axes = plt.subplots(1, len(metrics), figsize=(3.4 * len(metrics) + 3.2,
                                                      0.36 * n + 1.8),
                             facecolor=SURFACE, sharey=True)
    axes = np.atleast_1d(axes)
    y = np.arange(n)

    for ax, metric in zip(axes, metrics):
        # Error metrics of a failed trial are meaningless; fill is not.
        show_failed = metric == "fill_pct"
        for i, row in rows.iterrows():
            color = SERIES_COLORS.get(row["series"], INK_MUTED)
            if not row["detected"] and not show_failed:
                ax.text(0.02, i, "not detected", transform=ax.get_yaxis_transform(),
                        va="center", ha="left", fontsize=8, color=INK_MUTED)
                continue
            med = row[f"{metric}_median"]
            lo = max(med - row[f"{metric}_p25"], 0)
            hi = max(row[f"{metric}_p75"] - med, 0)
            ax.barh(i, med, height=0.62, color=color,
                    alpha=1.0 if row["detected"] else 0.35,
                    edgecolor=SURFACE, linewidth=2)
            ax.errorbar(med, i, xerr=[[lo], [hi]], color=INK_SECONDARY,
                        elinewidth=1, capsize=2, linestyle="none")
        ax.axvline(0, color="#d8d7d2", linewidth=1)
        style_axes(ax, labels.get(metric, metric))
        ax.grid(True, axis="x", color="#e6e5e1", linewidth=0.8)
        ax.grid(False, axis="y")

    axes[0].set_yticks(y)
    axes[0].set_yticklabels([f"{r['lux']:>5.0f} lx   {r['environment']}, "
                             f"{r['surface']} - {r['condition']}"
                             for _, r in rows.iterrows()], fontsize=8.5)
    axes[0].invert_yaxis()

    # Fixed headroom (in inches) for the title + legend, whatever the row count.
    fig.tight_layout(rect=(0, 0, 1, 1 - 0.75 / fig.get_figheight()))
    fig.suptitle(f"{title}, brightest first (bar = median, whisker = IQR)",
                 color=INK, fontsize=13, x=0.005, ha="left", y=0.995)
    legend_for(fig, series_in(summary), left=True,
               top=1 - 0.35 / fig.get_figheight())
    save(fig, fname, subdir)
    return fig


def plot_error_timeseries(data: pd.DataFrame, summary: pd.DataFrame,
                          metric="z_err_mean_mm", subdir: str = "", tag: str = ""):
    """Per-frame error over the length of each trial, one panel per trial."""
    rows = summary.sort_values("lux").reset_index(drop=True)
    n = len(rows)
    ncols = min(4, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.0 * ncols, 3.0 * nrows),
                             facecolor=SURFACE, squeeze=False)

    for ax, (_, row) in zip(axes.flat, rows.iterrows()):
        sub = data[data["trial_name"] == row["trial_name"]]
        x = sub["t_s"] if "t_s" in sub.columns else np.arange(len(sub))
        ax.plot(x, sub[metric], color=SERIES_COLORS.get(row["series"], INK_MUTED),
                linewidth=1.6, solid_capstyle="round")
        title = f"{row['lux']:.0f} lx - {row['condition']}"
        if not row["detected"]:
            title += "  (not detected)"
        style_axes(ax, title, "time in trial [s]", f"{metric} [mm]")
        ax.title.set_fontsize(9)
        robust_ylim(ax, sub[metric], lo_pct=1, hi_pct=99)
    for ax in axes.flat[n:]:
        ax.set_visible(False)

    fig.suptitle(f"Per-frame {metric} over each {tag} trial (dimmest first)",
                 color=INK, fontsize=13, x=0.005, ha="left", y=1.02)
    legend_for(fig, series_in(summary), left=ncols < 3)
    fig.tight_layout()
    save(fig, "error_timeseries", subdir)
    return fig


def plot_error_distribution(data: pd.DataFrame, summary: pd.DataFrame,
                            metric="z_err_mean_mm", subdir: str = "", tag: str = ""):
    """Frame-level spread per detected trial, dimmest to brightest."""
    rows = summary[summary["detected"]].sort_values("lux").reset_index(drop=True)
    if rows.empty:
        return None
    fig, ax = plt.subplots(figsize=(0.85 * len(rows) + 2.5, 4.2), facecolor=SURFACE)

    series = [data[data["trial_name"] == t][metric].dropna().values
              for t in rows["trial_name"]]
    bp = ax.boxplot(series, positions=range(len(rows)), widths=0.55,
                    patch_artist=True, showfliers=True, manage_ticks=False)
    for i, row in rows.iterrows():
        color = SERIES_COLORS.get(row["series"], INK_MUTED)
        bp["boxes"][i].set(facecolor=color, edgecolor=SURFACE, linewidth=2, alpha=0.9)
        for part in ("whiskers", "caps"):
            for line in bp[part][2 * i: 2 * i + 2]:
                line.set(color=color, linewidth=1.4)
        bp["fliers"][i].set(marker=".", markersize=3, markerfacecolor=color,
                            markeredgecolor="none", alpha=0.5)
        bp["medians"][i].set(color=SURFACE, linewidth=2)

    robust_ylim(ax, np.concatenate(series), lo_pct=0.5, hi_pct=99.5, pad=0.15)
    ax.axhline(0, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 4)), zorder=0)
    ax.set_xticks(range(len(rows)))
    ax.set_xticklabels([f"{r['lux']:.0f} lx\n{r['condition']}".replace(", ", "\n")
                        for _, r in rows.iterrows()], fontsize=7.5)
    style_axes(ax, f"Frame-level spread of {metric}\n"
                   f"(detected {tag} trials, dimmest first)", "", f"{metric} [mm]")
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    legend_for(fig, series_in(rows), left=True)
    save(fig, "error_distribution", subdir)
    return fig


def make_all_plots(data: pd.DataFrame, summary: pd.DataFrame, name: str,
                   subdir: str, lux_max: float) -> None:
    """The full figure set for one surface group (see PLOT_GROUPS)."""
    plot_metric_vs_lux(
        summary,
        ["z_err_median_mm", "z_err_median_pct", "dist_err_mm"],
        {"z_err_median_mm": "median z error [mm]",
         "z_err_median_pct": "median z error [% of range]",
         "dist_err_mm": "plane distance error [mm]"},
        "accuracy_vs_lux",
        f"Depth accuracy vs ambient light ({name})",
        subdir=subdir, lux_max=lux_max,
    )
    plot_metric_vs_lux(
        summary,
        ["plane_rms_mm", "std_z_mm", "temporal_noise_mm", "subpixel_rms_px"],
        {"plane_rms_mm": "plane-fit RMS [mm]",
         "std_z_mm": "ROI depth std [mm]",
         "temporal_noise_mm": "temporal noise [mm]",
         "subpixel_rms_px": "subpixel RMS [px]"},
        "noise_vs_lux",
        f"Spatial and temporal noise vs ambient light ({name})",
        subdir=subdir, lux_max=lux_max,
    )
    plot_metric_vs_lux(
        summary,
        ["fill_pct", "roi_w"],
        {"fill_pct": "valid pixels [%]",
         "roi_w": "ROI width [px]"},
        "detection_vs_lux",
        f"Target detection vs ambient light ({name})",
        subdir=subdir, lux_max=lux_max, include_failed=True,
        hlines={"fill_pct": MIN_FILL_PCT},
    )
    plot_metric_vs_lux(
        summary,
        ["exposure", "gain", "ir_mean"],
        {"exposure": "auto-exposure [us]",
         "gain": "gain",
         "ir_mean": "IR mean [DN]"},
        "sensor_response_vs_lux",
        f"Auto-exposure response vs ambient light ({name})",
        subdir=subdir, lux_max=lux_max, include_failed=True, logy={"exposure"},
    )
    plot_condition_overview(
        summary,
        ["z_err_median_mm", "plane_rms_mm", "fill_pct"],
        {"z_err_median_mm": "median z error [mm]",
         "plane_rms_mm": "plane-fit RMS [mm]",
         "fill_pct": "valid pixels [%]"},
        subdir=subdir, title=f"Every {name} light condition",
    )
    plot_error_timeseries(data, summary, subdir=subdir, tag=name)
    plot_error_distribution(data, summary, subdir=subdir, tag=name)


# %% ------------------------------------------------------------------ main --
def main() -> pd.DataFrame:
    print(f"Scanning {DATA_ROOT}")
    print(f"Outlier rejection: {OUTLIER_METHOD} at {OUTLIER_SIGMA} sigma "
          f"on {OUTLIER_COLUMNS}")
    print(f"Detection: fill >= {MIN_FILL_PCT:.0f} % and ROI width cv <= {MAX_ROI_CV}")
    data, rejected = load_all(DATA_ROOT)
    summary = summarise(data)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT_DIR / "all_frames.csv", index=False)
    rejected.to_csv(OUT_DIR / "rejected_frames.csv", index=False)
    summary.to_csv(OUT_DIR / "per_trial_summary.csv", index=False)
    n_failed = int((~summary["detected"]).sum())
    print(f"\n{len(data)} frames from {summary.shape[0]} trials "
          f"({len(rejected)} frames rejected as outliers, "
          f"{n_failed} trial(s) with the target not detected)")
    print(summary.sort_values("lux")[
        ["lux", "series", "condition", "detected", "n_frames", "fill_pct_median",
         "z_err_median_mm_median", "plane_rms_mm_median", "temporal_noise_mm",
         "exposure_median"]].to_string(index=False))

    # One lux scale for every group, so the board / no-board sets line up.
    lux_max = summary["lux"].max()
    for surfaces, name, subdir in PLOT_GROUPS.values():
        in_group = summary["surface"].isin(surfaces)
        if not in_group.any():
            print(f"  ! no {name} trials -- skipping that figure set")
            continue
        print(f"\n{name}: {int(in_group.sum())} trials -> {OUT_DIR / subdir}")
        make_all_plots(data[data["surface"].isin(surfaces)], summary[in_group],
                       name, subdir, lux_max)

    if SHOW_FIGURES:
        plt.show()
    return summary


if __name__ == "__main__":
    summary = main()
