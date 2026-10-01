"""
Height-analysis metrics: collect every *_metrics.csv under a data directory,
extract the columns of interest, and plot depth error vs ground-truth height.

Run it straight from VS Code (Run Python File / F5, or Shift+Enter through the
`# %%` cells). No command-line arguments -- everything is configured in the
CONFIG block below.

Folder layout it expects:

    Data/
      20260916_172440/                      <- session
        summary.csv
        20260916_172440_t0_h799_p0.0_r0.0_Evening_lights_noshade/
          ..._metrics.csv                   <- one row per frame
          trial_info.txt                    <- key: value metadata
"""

# %% ---------------------------------------------------------------- CONFIG --
from __future__ import annotations

import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.lines import Line2D

# Root that gets walked recursively. Default: the Data/ folder next to this file.
DATA_ROOT = Path(__file__).resolve().parent / "Data" / "Collection_2"

# Where figures and the tidy CSVs are written.
OUT_DIR = Path(__file__).resolve().parent / "Plots"

# Columns pulled out of each metrics.csv. The first three are the ones asked
# for; the rest are the extras that turned out to be worth looking at.
VALUE_COLUMNS = [
    "gt_axis_mm",          # ground-truth distance to the target (the x axis)
    "z_err_median_pct",    # accuracy, scale-free -- comparable across heights
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
    "ir_mean",             # IR brightness -- proxy for ambient light load
    "exposure",
    "gain",
]

# Columns that must exist for a row to be usable.
REQUIRED_COLUMNS = ["gt_axis_mm", "z_err_median_pct", "z_err_mean_mm"]

# The capture pipeline repeats the last frame when a new one has not arrived
# (identical device_ts_ms). Those duplicates bias the per-trial statistics, so
# they are dropped by default. Set False to keep the raw stream.
DROP_REPEATED_FRAMES = True

# Discard the first N frames of each trial (auto-exposure settling).
SKIP_FIRST_FRAMES = 0

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

SAVE_FIGURES = True
SHOW_FIGURES = True
DPI = 200

# ------------------------------------------------------------------ palette --
# Categorical slots 1 and 2 of the validated default palette: blue / orange.
SERIES_COLORS = {"lights": "#eb6834", "no lights": "#2a78d6"}
SERIES_ORDER = ["lights", "no lights"]
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
SURFACE = "#fcfcfb"

# Trial-folder names look like:
#   20260916_174029_t0_h901_p0.0_r0.0_Hihest_Evening_lights_noshade
NAME_RE = re.compile(
    r"^(?P<stamp>\d{8}_\d{6})_t(?P<trial>\d+)"
    r"_h(?P<height>\d+)"
    r"_p(?P<pitch>-?[\d.]+)"
    r"_r(?P<roll>-?[\d.]+)"
    r"_(?P<label>.+)$"
)


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
    """Parse the `key: value` header of trial_info.txt, if present."""
    info_path = folder / "trial_info.txt"
    if not info_path.exists():
        return {}
    info: dict[str, str] = {}
    for line in info_path.read_text(errors="replace").splitlines():
        if not line.strip() or line.startswith(" "):
            continue          # the trailing stats block is indented -- skip it
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        key = key.strip()
        if key in info:       # e.g. "record:" paths contain colons; keep first
            continue
        info[key] = value.strip()
    out: dict[str, float | str] = {}
    for key in ("lux", "gt_perp_mm", "gt_axis_mm", "baseline_mm", "depth_scale_m"):
        if key in info:
            try:
                out[f"info_{key}"] = float(info[key])
            except ValueError:
                pass
    for key in ("preset", "serial", "resolution", "device"):
        if key in info:
            out[f"info_{key}"] = info[key]
    return out


def classify_condition(label: str, lux: float | None) -> str:
    """lights vs no lights -- from the folder label, cross-checked with lux."""
    low = label.lower()
    if re.search(r"no[_ -]?lights?", low):
        return "no lights"
    if "light" in low:
        return "lights"
    if lux is not None and not np.isnan(lux):
        return "lights" if lux > 10 else "no lights"
    return "unknown"


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

        df, cut = filter_outliers(df, folder.name)
        if df.empty:
            print(f"  ! skipped {path.name}: every frame flagged as an outlier")
            continue

        meta = parse_trial_name(folder.name)
        meta.update(read_trial_info(folder))
        meta["condition"] = classify_condition(
            meta.get("label", folder.name), meta.get("info_lux")
        )
        meta["trial_name"] = folder.name
        meta["source"] = str(path)
        meta["n_frames_raw"] = n_raw
        meta["n_repeated_frames"] = n_dupes
        meta["n_outliers"] = len(cut)
        for key, value in meta.items():
            df[key] = value

        if "timestamp_ms" in df.columns:
            df["t_s"] = (df["timestamp_ms"] - df["timestamp_ms"].iloc[0]) / 1000.0

        if not cut.empty:
            for key, value in meta.items():
                cut[key] = value
            rejected.append(cut)

        frames.append(df)
        print(f"  + {folder.name}: {len(df)}/{n_raw} frames kept "
              f"({n_dupes} repeated, {len(cut)} outliers)")

    data = pd.concat(frames, ignore_index=True)
    # Prefer the ground truth recorded in the CSV; fall back to the folder name.
    data["gt_axis_mm"] = data["gt_axis_mm"].fillna(data["height_mm"])

    cut = (pd.concat(rejected, ignore_index=True) if rejected
           else pd.DataFrame(columns=data.columns))
    return data, cut


def summarise(data: pd.DataFrame) -> pd.DataFrame:
    """Per-trial statistics: mean/std plus robust median and IQR."""
    metrics = [c for c in VALUE_COLUMNS if c in data.columns and c != "gt_axis_mm"]
    keys = ["condition", "gt_axis_mm", "session", "trial", "trial_name", "label"]
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
    return out.reset_index().sort_values(["condition", "gt_axis_mm"])


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


def legend_for(fig, conditions) -> None:
    handles = [
        Line2D([], [], color=SERIES_COLORS.get(c, INK_MUTED), marker="o",
               markersize=7, linewidth=2, label=c)
        for c in conditions
    ]
    fig.legend(handles=handles, loc="upper right", frameon=False,
               fontsize=9, labelcolor=INK_SECONDARY, ncol=len(handles))


def conditions_in(data: pd.DataFrame) -> list[str]:
    present = list(dict.fromkeys(data["condition"]))
    return [c for c in SERIES_ORDER if c in present] + \
           [c for c in present if c not in SERIES_ORDER]


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


def save(fig, name: str) -> None:
    if not SAVE_FIGURES:
        return
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{name}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight", facecolor=SURFACE)
    print(f"  -> {path}")


# %% ----------------------------------------------------------------- plots --
def plot_metric_vs_height(summary: pd.DataFrame, metrics, labels, fname, suptitle):
    """Small multiples: one metric per panel, height on the shared x axis.

    Marker = median across frames, bar = inter-quartile range, so a handful of
    bad frames cannot drag the curve the way a mean +/- std would.
    """
    metrics = [m for m in metrics if f"{m}_median" in summary.columns]
    n = len(metrics)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.9), facecolor=SURFACE)
    axes = np.atleast_1d(axes)

    for ax, metric in zip(axes, metrics):
        for cond in conditions_in(summary):
            sub = summary[summary["condition"] == cond].sort_values("gt_axis_mm")
            if sub.empty:
                continue
            color = SERIES_COLORS.get(cond, INK_MUTED)
            lo = (sub[f"{metric}_median"] - sub[f"{metric}_p25"]).clip(lower=0)
            hi = (sub[f"{metric}_p75"] - sub[f"{metric}_median"]).clip(lower=0)
            ax.errorbar(
                sub["gt_axis_mm"], sub[f"{metric}_median"], yerr=[lo, hi],
                color=color, ecolor=color, elinewidth=1.4, capsize=3,
                marker="o", markersize=7, linewidth=2,
                markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
            )
        style_axes(ax, labels.get(metric, metric),
                   "ground-truth distance  gt_axis_mm  [mm]")

    if suptitle:
        fig.suptitle(suptitle, color=INK, fontsize=13, x=0.005, ha="left", y=1.06)
    legend_for(fig, conditions_in(summary))
    fig.tight_layout()
    save(fig, fname)
    return fig


def plot_error_timeseries(data: pd.DataFrame, metric="z_err_mean_mm"):
    """Per-frame error over the length of each trial, one panel per height."""
    heights = sorted(data["gt_axis_mm"].dropna().unique())
    n = len(heights)
    ncols = min(3, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.4 * ncols, 3.2 * nrows),
                             facecolor=SURFACE, squeeze=False)

    for ax, height in zip(axes.flat, heights):
        at_height = data[data["gt_axis_mm"] == height]
        for cond in conditions_in(at_height):
            sub = at_height[at_height["condition"] == cond]
            x = sub["t_s"] if "t_s" in sub.columns else np.arange(len(sub))
            ax.plot(x, sub[metric], color=SERIES_COLORS.get(cond, INK_MUTED),
                    linewidth=1.6, solid_capstyle="round")
        style_axes(ax, f"{height:.0f} mm", "time in trial [s]", f"{metric} [mm]")
        robust_ylim(ax, at_height[metric], lo_pct=1, hi_pct=99)
    for ax in axes.flat[n:]:
        ax.set_visible(False)

    fig.suptitle(f"Per-frame {metric} over each trial",
                 color=INK, fontsize=13, x=0.005, ha="left", y=1.02)
    legend_for(fig, conditions_in(data))
    fig.tight_layout()
    save(fig, "error_timeseries")
    return fig


def plot_error_distribution(data: pd.DataFrame, metric="z_err_mean_mm"):
    """Frame-level spread per height: how stable is the reading, not just where."""
    heights = sorted(data["gt_axis_mm"].dropna().unique())
    conds = conditions_in(data)
    fig, ax = plt.subplots(figsize=(1.9 * len(heights) + 2, 4.2), facecolor=SURFACE)

    width = 0.34
    for i, cond in enumerate(conds):
        offset = (i - (len(conds) - 1) / 2) * (width + 0.04)
        series = [data[(data["gt_axis_mm"] == h) & (data["condition"] == cond)][metric]
                  .dropna().values for h in heights]
        positions = [j + offset for j, s in enumerate(series) if len(s)]
        series = [s for s in series if len(s)]
        if not series:
            continue
        color = SERIES_COLORS.get(cond, INK_MUTED)
        bp = ax.boxplot(series, positions=positions, widths=width,
                        patch_artist=True, showfliers=True, manage_ticks=False,
                        flierprops=dict(marker=".", markersize=3,
                                        markerfacecolor=color, markeredgecolor="none",
                                        alpha=0.5))
        for box in bp["boxes"]:
            box.set(facecolor=color, edgecolor=SURFACE, linewidth=2, alpha=0.9)
        for part in ("whiskers", "caps"):
            for line in bp[part]:
                line.set(color=color, linewidth=1.4)
        for median in bp["medians"]:
            median.set(color=SURFACE, linewidth=2)

    robust_ylim(ax, data[metric], lo_pct=0.5, hi_pct=99.5, pad=0.15)
    ax.axhline(0, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 4)), zorder=0)
    ax.set_xticks(range(len(heights)))
    ax.set_xticklabels([f"{h:.0f}" for h in heights])
    style_axes(ax, f"Frame-level spread of {metric}",
               "ground-truth distance  gt_axis_mm  [mm]", f"{metric} [mm]")
    legend_for(fig, conds)
    fig.tight_layout()
    save(fig, "error_distribution")
    return fig


# %% ------------------------------------------------------------------ main --
def main() -> pd.DataFrame:
    print(f"Scanning {DATA_ROOT}")
    print(f"Outlier rejection: {OUTLIER_METHOD} at {OUTLIER_SIGMA} sigma "
          f"on {OUTLIER_COLUMNS}")
    data, rejected = load_all(DATA_ROOT)
    summary = summarise(data)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    data.to_csv(OUT_DIR / "all_frames.csv", index=False)
    rejected.to_csv(OUT_DIR / "rejected_frames.csv", index=False)
    summary.to_csv(OUT_DIR / "per_trial_summary.csv", index=False)
    print(f"\n{len(data)} frames from {summary.shape[0]} trials "
          f"({len(rejected)} frames rejected as outliers)")
    print(summary[["condition", "gt_axis_mm", "n_frames",
                   "z_err_median_pct_median", "z_err_mean_mm_median"]]
          .to_string(index=False))

    plot_metric_vs_height(
        summary,
        ["z_err_median_pct", "z_err_mean_mm", "z_err_median_mm"],
        {"z_err_median_pct": "median z error [% of range]",
         "z_err_mean_mm": "mean z error [mm]",
         "z_err_median_mm": "median z error [mm]"},
        "accuracy_vs_height",
        "Depth accuracy vs ground-truth distance",
    )
    plot_metric_vs_height(
        summary,
        ["fill_pct", "plane_rms_mm", "std_z_mm", "ir_mean"],
        {"fill_pct": "valid pixels [%]",
         "plane_rms_mm": "plane-fit RMS [mm]",
         "std_z_mm": "ROI depth std [mm]",
         "ir_mean": "IR mean [DN]"},
        "quality_vs_height",
        "Yield, flatness, noise and IR level vs ground-truth distance",
    )
    plot_error_timeseries(data)
    plot_error_distribution(data)

    if SHOW_FIGURES:
        plt.show()
    return summary


if __name__ == "__main__":
    summary = main()
