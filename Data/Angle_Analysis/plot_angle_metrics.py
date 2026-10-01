"""
Angle-analysis metrics: collect every *_metrics.csv under a data directory,
extract the columns of interest, and plot depth error vs target tilt angle.

The tilt angle is taken two ways and every figure is drawn against both:
  Plots/set_angle/  x = the set angle from the folder name
  Plots/imu_angle/  x = the angle the camera's IMU measured (from accel_x/y/z)
Plots/imu_vs_set.png compares the two, to help decide which set to use.

Companion to Height_Analysis/plot_height_metrics.py -- same loading, outlier
rejection, summary and plot style; the x axis is the set tilt angle and the
two series are the pitch sweep and the roll sweep instead of lights/no lights.

Run it straight from VS Code (Run Python File / F5, or Shift+Enter through the
`# %%` cells). No command-line arguments -- everything is configured in the
CONFIG block below.

Folder layout it expects:

    Data/
      Pitch/                                <- swept axis (Pitch or Roll)
        20260924_114241/                    <- session
          summary.csv
          20260924_114241_t0_h662_p1.6_r-0.9_ROI_test/
            ..._metrics.csv                 <- one row per frame
            trial_info.txt                  <- key: value metadata
      Roll/
        ...
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
DATA_ROOT = Path(__file__).resolve().parent / "Data"

# Where figures and the tidy CSVs are written.
OUT_DIR = Path(__file__).resolve().parent / "Plots"

# Columns pulled out of each metrics.csv.
VALUE_COLUMNS = [
    "gt_axis_mm",          # ground-truth distance along the optical axis
    "z_err_median_pct",    # accuracy, scale-free -- the range drifts with tilt
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
    "plane_tilt_deg",
    "ir_mean",             # IR brightness -- rises as the target tilts
    "exposure",
    "gain",
    "accel_x",             # IMU accelerometer [m/s^2] -- gravity gives the tilt
    "accel_y",
    "accel_z",
]

# Columns that must exist for a row to be usable.
REQUIRED_COLUMNS = ["gt_axis_mm", "z_err_median_pct", "z_err_mean_mm",
                    "plane_pitch_deg", "plane_roll_deg"]

# The camera's plane-fit angle convention vs the set angle in the folder name.
# Both already match (set p-20.0 -> plane_pitch_deg -20.7). The measured angle
# is multiplied by this before being compared; flip a sign if a convention
# changes.
ANGLE_SIGN = {"pitch": 1.0, "roll": 1.0}

# Correct a set angle that was typed wrong in the folder name, keyed by session
# stamp. e.g. roll session 20260924_150104 is named r6.2 (same as the session
# before it) but measures ~8.6 deg -- if that was a typo:
#   SET_ANGLE_OVERRIDES = {"20260924_150104": 8.5}
SET_ANGLE_OVERRIDES: dict[str, float] = {"20260924_150104": 8.6}

# --- IMU tilt ----------------------------------------------------------------
# The camera's accelerometer is logged per frame (accel_x/y/z). At rest it only
# sees gravity, so the tilt about each axis is
#     angle = sign * atan2(a_axis, sqrt(a_other1^2 + a_other2^2))
# Pitch tilts gravity into accel_y, roll into accel_x. Pitch needs a sign flip
# to match the set angle (set p-20.0 -> +accel_y), roll does not. Flip a sign
# here if the IMU is mounted differently.
IMU_AXES = {"pitch": ("accel_y", -1.0), "roll": ("accel_x", 1.0)}

# Each trial is placed on the IMU x axis at the median of its per-frame IMU
# angle (the camera is static, so this averages out accelerometer noise).
# Every figure is drawn twice -- once per x axis below -- into its own subfolder
# of OUT_DIR, so either set of plots can be used if the IMU turns out to be
# uncalibrated (or the set angles turn out to be wrong).
#   key: (x column, name used in labels, output subfolder)
X_AXES = {
    "set": ("angle_set_deg", "set", "set_angle"),
    "imu": ("angle_imu_trial_deg", "IMU", "imu_angle"),
}

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
SERIES_COLORS = {"pitch": "#2a78d6", "roll": "#eb6834"}
SERIES_ORDER = ["pitch", "roll"]
INK = "#0b0b0b"
INK_SECONDARY = "#52514e"
INK_MUTED = "#8a8880"
SURFACE = "#fcfcfb"

# Trial-folder names look like:
#   20260924_114241_t0_h662_p1.6_r-0.9_ROI_test
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


def classify_axis(path: Path, meta: dict) -> str:
    """pitch vs roll -- from a Pitch/ or Roll/ ancestor folder, else the label,
    else whichever set angle is larger."""
    for part in reversed(path.parts):
        low = part.lower()
        if low in ("pitch", "roll"):
            return low
    low = meta.get("label", "").lower()
    if "pitch" in low:
        return "pitch"
    if "roll" in low:
        return "roll"
    p, r = meta.get("pitch_set_deg", np.nan), meta.get("roll_set_deg", np.nan)
    if np.isnan(p) or np.isnan(r):
        return "unknown"
    return "pitch" if abs(p) >= abs(r) else "roll"


def imu_angle(df: pd.DataFrame, axis: str) -> pd.Series:
    """Per-frame tilt about `axis` [deg] from the accelerometer's gravity vector."""
    col, sign = IMU_AXES[axis]
    accel = ["accel_x", "accel_y", "accel_z"]
    if not all(c in df.columns for c in accel):
        return pd.Series(np.nan, index=df.index)
    rest = [c for c in accel if c != col]
    return sign * np.degrees(np.arctan2(df[col], np.hypot(df[rest[0]], df[rest[1]])))


def add_angle_columns(df: pd.DataFrame, axis: str, meta: dict) -> None:
    """Measured angle on the swept axis, its error, and the off-axis crosstalk.

    angle_set_deg        the swept axis's set angle (x axis of the "set" plots)
    angle_imu_deg        per-frame IMU angle on that axis
    angle_imu_trial_deg  trial median of angle_imu_deg (x axis of the "imu" plots)
    angle_meas_deg       plane-fit angle on that axis, sign-matched to the set one
    angle_err_deg        plane-fit - set
    angle_err_imu_deg    plane-fit - IMU
    imu_minus_set_deg    IMU - set (how far the two x axes disagree)
    off_axis_meas_deg    plane-fit angle on the OTHER axis (should stay ~ constant)
    off_axis_imu_deg     IMU angle on the OTHER axis
    """
    if axis not in ("pitch", "roll"):
        return
    other = "roll" if axis == "pitch" else "pitch"
    df["angle_set_deg"] = SET_ANGLE_OVERRIDES.get(meta.get("session"),
                                                  meta[f"{axis}_set_deg"])
    df["angle_imu_deg"] = imu_angle(df, axis)
    df["angle_imu_trial_deg"] = meta["angle_imu_trial_deg"]
    df["angle_meas_deg"] = ANGLE_SIGN[axis] * df[f"plane_{axis}_deg"]
    df["angle_err_deg"] = df["angle_meas_deg"] - df["angle_set_deg"]
    df["angle_err_imu_deg"] = df["angle_meas_deg"] - df["angle_imu_deg"]
    df["imu_minus_set_deg"] = df["angle_imu_deg"] - df["angle_set_deg"]
    df["off_axis_meas_deg"] = ANGLE_SIGN[other] * df[f"plane_{other}_deg"]
    df["off_axis_imu_deg"] = imu_angle(df, other)


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
        meta["axis"] = classify_axis(path.relative_to(root), meta)
        meta["trial_name"] = folder.name
        meta["source"] = str(path)
        meta["n_frames_raw"] = n_raw
        meta["n_repeated_frames"] = n_dupes
        meta["n_outliers"] = len(cut)
        # One IMU angle per trial, from the kept frames only.
        meta["angle_imu_trial_deg"] = (
            float(imu_angle(df, meta["axis"]).median())
            if meta["axis"] in IMU_AXES else np.nan)
        df = df.copy()
        for key, value in meta.items():
            df[key] = value
        add_angle_columns(df, meta["axis"], meta)

        if "timestamp_ms" in df.columns:
            df["t_s"] = (df["timestamp_ms"] - df["timestamp_ms"].iloc[0]) / 1000.0

        if not cut.empty:
            cut = cut.copy()
            for key, value in meta.items():
                cut[key] = value
            add_angle_columns(cut, meta["axis"], meta)
            rejected.append(cut)

        frames.append(df)
        print(f"  + [{meta['axis']:>5}] {folder.name}: {len(df)}/{n_raw} frames kept "
              f"({n_dupes} repeated, {len(cut)} outliers), "
              f"IMU {meta['angle_imu_trial_deg']:.2f} deg")

    data = pd.concat(frames, ignore_index=True)
    # Prefer the ground truth recorded in the CSV; fall back to the folder name.
    data["gt_axis_mm"] = data["gt_axis_mm"].fillna(data["height_mm"])

    cut = (pd.concat(rejected, ignore_index=True) if rejected
           else pd.DataFrame(columns=data.columns))
    return data, cut


ANGLE_METRICS = ["angle_imu_deg", "angle_meas_deg", "angle_err_deg",
                 "angle_err_imu_deg", "imu_minus_set_deg",
                 "off_axis_meas_deg", "off_axis_imu_deg"]


def summarise(data: pd.DataFrame) -> pd.DataFrame:
    """Per-trial statistics: mean/std plus robust median and IQR."""
    metrics = [c for c in VALUE_COLUMNS + ANGLE_METRICS if c in data.columns]
    keys = ["axis", "angle_set_deg", "angle_imu_trial_deg",
            "session", "trial", "trial_name", "label"]
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
    return out.reset_index().sort_values(["axis", "angle_set_deg"])


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


def legend_for(fig, series) -> None:
    handles = [
        Line2D([], [], color=SERIES_COLORS.get(s, INK_MUTED), marker="o",
               markersize=7, linewidth=2, label=s)
        for s in series
    ]
    fig.legend(handles=handles, loc="upper right", frameon=False,
               fontsize=9, labelcolor=INK_SECONDARY, ncol=len(handles))


def axes_in(data: pd.DataFrame) -> list[str]:
    present = list(dict.fromkeys(data["axis"]))
    return [a for a in SERIES_ORDER if a in present] + \
           [a for a in present if a not in SERIES_ORDER]


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
def plot_metric_vs_angle(summary: pd.DataFrame, metrics, labels, fname, suptitle,
                         xmode: str = "set", identity: bool = False,
                         subdir: str | None = None):
    """Small multiples: one metric per panel, tilt angle on the shared x axis.

    `xmode` picks the x axis from X_AXES ("set" or "imu").
    Marker = median across frames, bar = inter-quartile range, so a handful of
    bad frames cannot drag the curve the way a mean +/- std would.
    With `identity`, a dashed y = x reference is drawn in the first panel
    (for measured-vs-reference angle). `subdir` overrides the output folder.
    """
    x_col, x_name, default_subdir = X_AXES[xmode]
    subdir = default_subdir if subdir is None else subdir
    metrics = [m for m in metrics if f"{m}_median" in summary.columns]
    n = len(metrics)
    fig, axes = plt.subplots(1, n, figsize=(4.2 * n, 3.9), facecolor=SURFACE)
    axes = np.atleast_1d(axes)

    for ax, metric in zip(axes, metrics):
        for axis in axes_in(summary):
            sub = summary[summary["axis"] == axis].sort_values(x_col)
            if sub.empty:
                continue
            color = SERIES_COLORS.get(axis, INK_MUTED)
            lo = (sub[f"{metric}_median"] - sub[f"{metric}_p25"]).clip(lower=0)
            hi = (sub[f"{metric}_p75"] - sub[f"{metric}_median"]).clip(lower=0)
            ax.errorbar(
                sub[x_col], sub[f"{metric}_median"], yerr=[lo, hi],
                color=color, ecolor=color, elinewidth=1.4, capsize=3,
                marker="o", markersize=7, linewidth=2,
                markeredgecolor=SURFACE, markeredgewidth=1.5, zorder=3,
            )
        style_axes(ax, labels.get(metric, metric), f"{x_name} tilt angle  [deg]")

    if identity:
        ax0 = axes[0]
        lims = [min(ax0.get_xlim()[0], ax0.get_ylim()[0]),
                max(ax0.get_xlim()[1], ax0.get_ylim()[1])]
        ax0.plot(lims, lims, color=INK_MUTED, linewidth=1,
                 linestyle=(0, (4, 4)), zorder=0)
        ax0.set_xlim(lims)
        ax0.set_ylim(lims)

    if suptitle:
        fig.suptitle(suptitle, color=INK, fontsize=13, x=0.005, ha="left", y=1.06)
    legend_for(fig, axes_in(summary))
    fig.tight_layout()
    save(fig, fname, subdir)
    return fig


def plot_error_timeseries(data: pd.DataFrame, axis: str, metric="z_err_mean_mm",
                          xmode: str = "set"):
    """Per-frame error over the length of each trial, one panel per angle."""
    x_col, x_name, subdir = X_AXES[xmode]
    data = data[data["axis"] == axis]
    angles = sorted(data[x_col].dropna().unique())
    n = len(angles)
    if n == 0:
        return None
    ncols = min(4, n)
    nrows = int(np.ceil(n / ncols))
    fig, axes = plt.subplots(nrows, ncols, figsize=(4.0 * ncols, 3.0 * nrows),
                             facecolor=SURFACE, squeeze=False)

    color = SERIES_COLORS.get(axis, INK_MUTED)
    for ax, angle in zip(axes.flat, angles):
        at_angle = data[data[x_col] == angle]
        # Two trials can share a set angle -- draw each separately.
        for _, sub in at_angle.groupby("trial_name"):
            x = sub["t_s"] if "t_s" in sub.columns else np.arange(len(sub))
            ax.plot(x, sub[metric], color=color, linewidth=1.6,
                    solid_capstyle="round")
        style_axes(ax, f"{axis} {angle:.1f} deg ({x_name})", "time in trial [s]",
                   f"{metric} [mm]")
        robust_ylim(ax, at_angle[metric], lo_pct=1, hi_pct=99)
    for ax in axes.flat[n:]:
        ax.set_visible(False)

    fig.suptitle(f"Per-frame {metric} over each {axis} trial",
                 color=INK, fontsize=13, x=0.005, ha="left", y=1.02)
    fig.tight_layout()
    save(fig, f"error_timeseries_{axis}", subdir)
    return fig


def plot_error_distribution(data: pd.DataFrame, metric="z_err_mean_mm",
                            xmode: str = "set"):
    """Frame-level spread per angle: how stable is the reading, not just where.

    One row per swept axis, since the pitch and roll sweeps do not share
    angles.
    """
    x_col, x_name, subdir = X_AXES[xmode]
    axes_list = axes_in(data)
    n_max = max(data[data["axis"] == a][x_col].nunique() for a in axes_list)
    fig, axs = plt.subplots(len(axes_list), 1,
                            figsize=(0.75 * n_max + 2.5, 3.6 * len(axes_list)),
                            facecolor=SURFACE, squeeze=False)

    for ax, axis in zip(axs[:, 0], axes_list):
        sub = data[data["axis"] == axis]
        angles = sorted(sub[x_col].dropna().unique())
        series = [sub[sub[x_col] == a][metric].dropna().values for a in angles]
        color = SERIES_COLORS.get(axis, INK_MUTED)
        bp = ax.boxplot(series, positions=range(len(angles)), widths=0.55,
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

        robust_ylim(ax, sub[metric], lo_pct=0.5, hi_pct=99.5, pad=0.15)
        ax.axhline(0, color=INK_MUTED, linewidth=1, linestyle=(0, (4, 4)), zorder=0)
        ax.set_xticks(range(len(angles)))
        ax.set_xticklabels([f"{a:.1f}" for a in angles])
        style_axes(ax, f"{axis}: frame-level spread of {metric}",
                   f"{x_name} {axis} angle  [deg]", f"{metric} [mm]")

    legend_for(fig, axes_list)
    fig.tight_layout()
    save(fig, "error_distribution", subdir)
    return fig


def make_all_plots(data: pd.DataFrame, summary: pd.DataFrame, xmode: str) -> None:
    """The full figure set against one x axis (see X_AXES)."""
    _, x_name, _ = X_AXES[xmode]
    err_col = "angle_err_deg" if xmode == "set" else "angle_err_imu_deg"
    plot_metric_vs_angle(
        summary,
        ["angle_meas_deg", err_col, "off_axis_meas_deg"],
        {"angle_meas_deg": "plane-fit angle [deg]",
         err_col: f"angle error, plane-fit - {x_name} [deg]",
         "off_axis_meas_deg": "off-axis angle (crosstalk) [deg]"},
        "angle_tracking",
        f"Plane-fit angle vs {x_name} tilt angle",
        xmode=xmode, identity=True,
    )
    plot_metric_vs_angle(
        summary,
        ["z_err_median_pct", "z_err_mean_mm", "z_err_median_mm", "dist_err_mm"],
        {"z_err_median_pct": "median z error [% of range]",
         "z_err_mean_mm": "mean z error [mm]",
         "z_err_median_mm": "median z error [mm]",
         "dist_err_mm": "plane distance error [mm]"},
        "accuracy_vs_angle",
        f"Depth accuracy vs {x_name} tilt angle",
        xmode=xmode,
    )
    plot_metric_vs_angle(
        summary,
        ["fill_pct", "plane_rms_mm", "std_z_mm", "ir_mean"],
        {"fill_pct": "valid pixels [%]",
         "plane_rms_mm": "plane-fit RMS [mm]",
         "std_z_mm": "ROI depth std [mm]",
         "ir_mean": "IR mean [DN]"},
        "quality_vs_angle",
        f"Yield, flatness, noise and IR level vs {x_name} tilt angle",
        xmode=xmode,
    )
    for axis in axes_in(data):
        plot_error_timeseries(data, axis, xmode=xmode)
    plot_error_distribution(data, xmode=xmode)


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
    print(summary[["axis", "angle_set_deg", "angle_imu_trial_deg", "n_frames",
                   "gt_axis_mm_median", "angle_meas_deg_median",
                   "z_err_median_pct_median", "z_err_mean_mm_median"]]
          .to_string(index=False))

    # How the two candidate x axes compare -- read this first to decide which
    # set of plots to trust.
    plot_metric_vs_angle(
        summary,
        ["angle_imu_deg", "imu_minus_set_deg", "off_axis_imu_deg"],
        {"angle_imu_deg": "IMU angle [deg]",
         "imu_minus_set_deg": "IMU - set [deg]",
         "off_axis_imu_deg": "IMU off-axis angle [deg]"},
        "imu_vs_set",
        "IMU tilt angle vs set tilt angle",
        xmode="set", identity=True, subdir="",
    )
    for xmode in X_AXES:
        make_all_plots(data, summary, xmode)

    if SHOW_FIGURES:
        plt.show()
    return summary


if __name__ == "__main__":
    summary = main()
