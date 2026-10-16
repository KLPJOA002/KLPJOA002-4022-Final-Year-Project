"""Print detected family and column counts for every known data file."""
import glob
import sys
import time

from rsplot import data

FILES = [
    "../Height_Analysis/Plots/all_frames.csv", "../Height_Analysis/Plots/per_trial_summary.csv",
    "../Height_Analysis/Plots/rejected_frames.csv",
    "../Angle_Analysis/Plots/all_frames.csv", "../Angle_Analysis/Plots/per_trial_summary.csv",
    "../Light_Analysis/Plots/all_frames.csv", "../Light_Analysis/Plots/per_trial_summary.csv",
    "../3D_Results/Filter_Results/V3/results.csv", "../3D_Results/Filter_Results/V3/plots/ranking_1.csv",
    "../3D_Results/Filter_Results/V3/plots/summary_best_per_metric.csv",
    "../3D_Results/Combinations/results.csv", "../3D_Results/Combinations/analysis/ranking_top10.csv",
    "../3D_Results/Combinations/analysis/smallest_within_5pct.csv", "../3D_Results/Combinations/sessions.csv",
    "../3D_Results/Single_Vs_Fused/results.csv",
    "../../Code/Processing/Parameter_Sweep/results/Parameter_Results/all_scans.csv",
    "../../Code/Processing/Parameter_Sweep/results/Parameter_Results/subset_scans.csv",
] + sorted(glob.glob("../../Code/Processing/Parameter_Sweep/results/Parameter_Results/rankings/*.csv"))

for f in sys.argv[1:] or FILES:
    t = time.time()
    ds = data.load_dataset(f)
    print(f"{ds.family.key:16s} {ds.n_rows:6d} rows {len(ds.loaded):3d}/{len(ds.columns):3d} cols "
          f"metrics={len(ds.metrics()):3d} factors={len(ds.factors()):2d} {time.time() - t:5.2f}s  "
          f"{f.split('../')[-1]}")
