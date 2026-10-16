"""Render stage-(a) example figures headless into examples/stage_a/."""
from pathlib import Path

from rsplot.render import render
from rsplot.spec import Aggregation, DatasetRef, Export, Filter, Mapping, PlotSpec, Style

OUT = Path(__file__).resolve().parents[1] / "examples" / "stage_a"
OUT.mkdir(parents=True, exist_ok=True)
D = Path(__file__).resolve().parents[2]


def save(name, spec):
    res = render(spec)
    for ext in ("pdf", "png"):
        res.savefig(OUT / f"{name}.{ext}", dpi=200)
    print(f"{name}: {res.width_cm:g} x {res.height_cm:g} cm  width={res.latex_width}")
    print("   footnote:", res.footnote)
    for w in res.warnings:
        print("   WARNING:", w)
    return res


# 1. Planar summary: stored per-trial median + IQR
save("height_summary_median_iqr", PlotSpec(
    plot_type="line",
    dataset=DatasetRef(str(D / "Height_Analysis/Plots/per_trial_summary.csv")),
    mapping=Mapping(x="gt_axis_mm", y=["z_err_median_mm"]),
    aggregation=Aggregation(func="none", stored_stat="median", stored_spread="iqr"),
    options={"spread_display": "errorbars"}))

# 2. Planar per-frame: angle error vs set angle, colour = axis, median + IQR over frames
save("angle_frames_err_by_axis", PlotSpec(
    plot_type="line",
    dataset=DatasetRef(str(D / "Angle_Analysis/Plots/all_frames.csv")),
    mapping=Mapping(x="angle_set_deg", y=["angle_err_deg"], hue="axis"),
    aggregation=Aggregation(func="median", spread="iqr")))

# 3. Filter sweep: RMSE untrimmed vs trim5 side by side, other filters off
filters_off = [Filter("spatial_on", values=[False]), Filter("temporal_on", values=[False]),
               Filter("hole_filling_on", values=[False]), Filter("hdr_merge_on", values=[False])]
save("filter_decimation_rmse_vs_trim5", PlotSpec(
    plot_type="line",
    dataset=DatasetRef(str(D / "3D_Results/Filter_Results/V3/results.csv")),
    mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_mm", "acc_rmse_trim5_mm"],
                    y_mode="side_by_side", hue="shape"),
    filters=filters_off,
    aggregation=Aggregation(func="mean", spread="ci95"),
    export=Export(size_preset="thesis_full", height_cm=7.0)))

# 4. Same, all three RMSE variants overlaid, faceted by object
save("filter_decimation_rmse_variants_overlay", PlotSpec(
    plot_type="line",
    dataset=DatasetRef(str(D / "3D_Results/Filter_Results/V3/results.csv")),
    mapping=Mapping(x="decimation_magnitude",
                    y=["acc_rmse_mm", "acc_rmse_trim1_mm", "acc_rmse_trim5_mm"],
                    y_mode="overlay", facet="shape"),
    filters=filters_off,
    aggregation=Aggregation(func="median", spread="iqr"),
    export=Export(size_preset="thesis_full", height_cm=7.0)))

# 5. Not fixed on purpose: decimation only, everything else averaged -> flagged in footnote
save("filter_decimation_unfixed", PlotSpec(
    plot_type="line",
    dataset=DatasetRef(str(D / "3D_Results/Filter_Results/V3/results.csv")),
    mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_trim5_mm"], hue="shape"),
    aggregation=Aggregation(func="mean", spread="std")))

# 6. Fusion: scatter of every fused cloud
save("fusion_scatter_nscans", PlotSpec(
    plot_type="scatter",
    dataset=DatasetRef(str(D / "3D_Results/Combinations/results.csv")),
    mapping=Mapping(x="n_scans", y=["acc_rmse_mm"], hue="family", facet="wave"),
    aggregation=Aggregation(func="none"),
    style=Style(legend="outside bottom"),
    export=Export(size_preset="thesis_full", height_cm=8.0)))

# 7. Parameter study: metric vs metric, colour = preset
save("param_metric_vs_metric", PlotSpec(
    plot_type="scatter",
    dataset=DatasetRef(str(D.parent / "Code/Processing/Parameter_Sweep/results/"
                           "Parameter_Results/all_scans.csv")),
    mapping=Mapping(x="completeness_full@2mm", y=["acc_rmse_mm"], hue="resolution",
                    facet="object_label"),
    aggregation=Aggregation(func="none"),
    export=Export(size_preset="thesis_full", height_cm=7.0)))

# 8. Times text + stix maths, and the same figure through LaTeX (mathptmx)
for usetex in (False, True):
    spec = PlotSpec(
        plot_type="line",
        dataset=DatasetRef(str(D / "Angle_Analysis/Plots/per_trial_summary.csv")),
        mapping=Mapping(x="angle_set_deg", y=["angle_err_deg"], hue="axis"),
        aggregation=Aggregation(func="none", stored_stat="mean", stored_spread="std"),
        style=Style(labels={"angle_err_deg": r"Angle error $\Delta\theta$ (°)"},
                    subtitle=r"Times text 0123 with maths $\sigma_z = 1.2\,\mathrm{mm}$, "
                             r"$\theta_{\mathrm{set}} \approx 25^{\circ}$, $x^2 + y_i$"),
        export=Export(usetex=usetex))
    save("times_usetex" if usetex else "times_mathtext", spec)
