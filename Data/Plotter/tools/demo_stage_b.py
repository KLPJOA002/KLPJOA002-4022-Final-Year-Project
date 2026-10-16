"""Render stage-(b) example figures (bar, box/violin, hist/CDF, time series, secondary panel)."""
from pathlib import Path

from rsplot.render import render
from rsplot.spec import Aggregation, DatasetRef, Export, Filter, Mapping, PlotSpec, Style

OUT = Path(__file__).resolve().parents[1] / "examples" / "stage_b"
OUT.mkdir(parents=True, exist_ok=True)
D = Path(__file__).resolve().parents[2]
FILTER = str(D / "3D_Results/Filter_Results/V3/results.csv")
FUSION = str(D / "3D_Results/Combinations/results.csv")
PARAM = str(D.parent / "Code/Processing/Parameter_Sweep/results/Parameter_Results/all_scans.csv")
OFF = [Filter("spatial_on", values=[False]), Filter("temporal_on", values=[False]),
       Filter("hole_filling_on", values=[False]), Filter("hdr_merge_on", values=[False])]


def save(name, spec):
    res = render(spec)
    res.savefig(OUT / f"{name}.pdf")
    res.savefig(OUT / f"{name}.png", dpi=200)
    print(f"{name}: {res.width_cm:g} x {res.height_cm:g} cm\n   {res.footnote}")
    for w in res.warnings:
        print("   WARNING:", w)


save("bar_param_preset_resolution", PlotSpec(
    plot_type="bar", dataset=DatasetRef(PARAM),
    mapping=Mapping(x="preset", y=["acc_rmse_mm"], hue="resolution", facet="object_label"),
    aggregation=Aggregation(func="mean", spread="minmax"),
    style=Style(legend="outside top"),
    export=Export(size_preset="thesis_full", height_cm=8)))

save("barh_fusion_family", PlotSpec(
    plot_type="bar", dataset=DatasetRef(FUSION),
    mapping=Mapping(x="family", y=["acc_rmse_trim5_mm"], hue="wave"),
    filters=[Filter("status", values=["ok"])],
    aggregation=Aggregation(func="mean", spread="std"),
    options={"orientation": "horizontal", "value_labels": True}))

save("box_filter_decimation_strip", PlotSpec(
    plot_type="box", dataset=DatasetRef(FILTER),
    mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_trim5_mm"], hue="shape"),
    filters=OFF, options={"strip": True},
    export=Export(size_preset="thesis_full", height_cm=8)))

save("violin_height_plane_rms", PlotSpec(
    plot_type="box", dataset=DatasetRef(str(D / "Height_Analysis/Plots/all_frames.csv")),
    mapping=Mapping(x="gt_axis_mm", y=["plane_rms_mm"]),
    options={"kind": "violin"}))

save("cdf_filter_rmse_variants", PlotSpec(
    plot_type="hist", dataset=DatasetRef(FILTER),
    mapping=Mapping(y=["acc_rmse_mm", "acc_rmse_trim1_mm", "acc_rmse_trim5_mm"], facet="shape"),
    filters=[Filter("status", values=["ok"])],
    style=Style(xlog=True), options={"kind": "cdf"},
    export=Export(size_preset="thesis_full", height_cm=7)))

save("hist_angle_error", PlotSpec(
    plot_type="hist", dataset=DatasetRef(str(D / "Angle_Analysis/Plots/all_frames.csv")),
    mapping=Mapping(y=["angle_err_deg"], hue="axis"),
    options={"bins": 40, "histtype": "filled"}))

save("timeseries_height", PlotSpec(
    plot_type="timeseries", dataset=DatasetRef(str(D / "Height_Analysis/Plots/all_frames.csv")),
    mapping=Mapping(x="t_s", y=["z_err_rmse_mm"], hue="gt_axis_mm"),
    options={"window": 15},
    export=Export(size_preset="thesis_full", height_cm=8)))

save("line_with_outlier_panel", PlotSpec(
    plot_type="line", dataset=DatasetRef(FILTER),
    mapping=Mapping(x="decimation_magnitude", y=["acc_rmse_mm", "acc_rmse_trim5_mm"],
                    y_mode="side_by_side", hue="shape", secondary="outlier_fraction"),
    filters=OFF, aggregation=Aggregation(func="mean", spread="ci95"),
    export=Export(size_preset="thesis_full", height_cm=9)))

save("greyscale_rmse_variants", PlotSpec(
    plot_type="line", dataset=DatasetRef(FILTER),
    mapping=Mapping(x="decimation_magnitude",
                    y=["acc_rmse_mm", "acc_rmse_trim1_mm", "acc_rmse_trim5_mm"], facet="shape"),
    filters=OFF, aggregation=Aggregation(func="median", spread="iqr"),
    style=Style(greyscale=True),
    export=Export(size_preset="thesis_full", height_cm=7)))
