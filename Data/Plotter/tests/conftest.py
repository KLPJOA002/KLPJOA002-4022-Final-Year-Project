"""Small synthetic datasets, one per family, mimicking the real column layouts."""
import itertools
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("RSPLOT_STATE_DIR", tempfile.mkdtemp(prefix="rsplot_state_"))

from rsplot.data import dataset_from_frame  # noqa: E402

RNG = np.random.default_rng(42)


def _planar_frames():
    rows = []
    for trial, (h, cond) in enumerate(itertools.product([600, 700, 800], ["lights", "no lights"])):
        for f in range(40):
            err = 4 + h / 200 + RNG.normal(0, 0.2)
            rows.append(dict(frame=f, t_s=f / 30, gt_axis_mm=h, height_mm=h, condition=cond,
                             trial_name=f"T{trial}", session=f"S{trial}", trial=0,
                             z_err_median_mm=err, z_err_rmse_mm=err + 0.3,
                             plane_rms_mm=1 + RNG.normal(0, 0.1), fill_pct=99 - RNG.random(),
                             detected="True"))
    return pd.DataFrame(rows)


def _planar_summary():
    rows = []
    for i, h in enumerate([600, 650, 700, 750]):
        r = dict(trial_name=f"T{i}", session=f"S{i}", trial=0, gt_axis_mm=h, condition="lights",
                 n_frames=500 + i)
        for m in ("z_err_median_mm", "plane_rms_mm", "fill_pct", "std_z_mm"):
            base = h / 100
            r.update({f"{m}_mean": base, f"{m}_std": 0.1, f"{m}_median": base,
                      f"{m}_p25": base - 0.1, f"{m}_p75": base + 0.15})
        rows.append(r)
    return pd.DataFrame(rows)


def _filter_sweep():
    rows = []
    configs = list(itertools.product([1, 2, 4], [False, True]))
    for ci, (dec, sp) in enumerate(configs):
        for shape, h, rot in itertools.product(["Big_Wave", "Small_Wave"], [641, 701], [0, 90]):
            rmse = 2 + 0.1 * dec - 0.2 * sp + (0.4 if shape == "Small_Wave" else 0)
            rmse += RNG.normal(0, 0.1)
            rows.append(dict(
                config_id=f"c{ci}", config_label=f"dec{dec}" + (" | sp" if sp else ""),
                scan_id=f"A{rot}", scan_key=f"{shape}_{h}_{rot}", status="ok", shape=shape,
                height_mm=h, rotation_label=rot, tilt_deg=0, decimation_on=dec > 1,
                decimation_magnitude=dec, spatial_on=sp, spatial_alpha=0.5 if sp else np.nan,
                temporal_on=False, hole_filling_on=False, hdr_merge_on=False,
                acc_rmse_mm=rmse + 0.5, acc_rmse_trim1_mm=rmse + 0.2, acc_rmse_trim5_mm=rmse,
                signed_bias_mm=RNG.normal(0, 0.2), outlier_fraction=RNG.random() * 0.05,
                **{"completeness@2mm": 0.6 + RNG.random() * 0.1,
                   "fscore@2mm": 0.7 + RNG.random() * 0.1},
                covered_fraction=0.95))
    df = pd.DataFrame(rows)
    df.loc[0, ["acc_rmse_mm", "acc_rmse_trim5_mm"]] = np.nan   # a skipped row
    return df


def _fusion():
    rows = []
    for wave, h, fam, n in itertools.product(["Big_Wave", "Small_Wave"], [641, 701],
                                              ["rotation", "tilt", "joint"], [2, 4, 8]):
        tilts = "-10;0;10" if fam in ("tilt", "joint") else "0"
        rots = "0;90" if fam in ("rotation", "joint") else "0"
        rows.append(dict(wave=wave, height_mm=h, combo_id=f"{fam}-{n}", family=fam,
                         rot_family="0-90", tilt_family="0", n_scans=n, kind="fused",
                         tilts=tilts, rotations=rots, n_tilts=tilts.count(";") + 1,
                         n_rotations=rots.count(";") + 1,
                         status="ok", acc_rmse_mm=2.5 - 0.1 * n + RNG.normal(0, 0.1),
                         acc_rmse_trim5_mm=2.2 - 0.1 * n, fuse_s=10 * n, total_s=12 * n,
                         covered_fraction=0.9))
    for wave, h, rot, tilt in itertools.product(["Big_Wave", "Small_Wave"], [641, 701],
                                                [0, 90], [-10, 0, 10]):
        rows.append(dict(wave=wave, height_mm=h, combo_id=f"single_r{rot}_a{tilt}",
                         family="single", rot_family=str(rot), tilt_family=str(tilt),
                         n_scans=1, kind="single", tilts=str(tilt), rotations=str(rot),
                         n_tilts=1, n_rotations=1, status="ok",
                         acc_rmse_mm=2.6 + 0.02 * abs(tilt) + RNG.normal(0, 0.05),
                         acc_rmse_trim5_mm=2.3, fuse_s=0, total_s=5, covered_fraction=0.8))
    return pd.DataFrame(rows)


def _param_scans():
    rows = []
    for obj, res, du, preset in itertools.product(
            ["Big_Pyramid", "Big_Wave"], ["640x360", "1280x720"], [0.1, 1.0],
            ["default", "high_accuracy", "high_density"]):
        rows.append({"object": obj, "object_label": obj.split("_")[1], "resolution": res,
                     "depth_units_mm": du, "preset": preset, "status": "ok",
                     "valid_pixel_fraction": 0.9, "acc_rmse_mm": 1.5 + RNG.random(),
                     "acc_rmse_trim5_mm": 1.3 + RNG.random(), "fscore@2mm": RNG.random(),
                     "completeness_full@2mm": RNG.random(), "info.device.Name": "D456"})
    return pd.DataFrame(rows)


def _filter_ranking():
    return pd.DataFrame({"config_id": [f"c{i}" for i in range(8)],
                         "config_label": [f"cfg {i}" for i in range(8)],
                         "n_scans": 60, "n_ok": 58, "ok_fraction": 58 / 60,
                         "mean_acc_rmse_mm": np.linspace(2.0, 2.8, 8),
                         "std_acc_rmse_mm": 0.3, "score": np.linspace(0, 0.3, 8)})


FRAMES = {"planar_frames": _planar_frames, "planar_summary": _planar_summary,
          "filter_sweep": _filter_sweep, "fusion": _fusion, "param_scans": _param_scans,
          "filter_ranking": _filter_ranking}


@pytest.fixture(scope="session")
def frames():
    return {k: f() for k, f in FRAMES.items()}


@pytest.fixture(scope="session")
def datasets(frames):
    return {k: dataset_from_frame(df) for k, df in frames.items()}
