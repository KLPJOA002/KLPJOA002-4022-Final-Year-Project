"""Render stage-(d) examples: heatmaps and top-N rankings."""
from pathlib import Path

from rsplot.render import render
from rsplot.spec import Aggregation, DatasetRef, Export, Filter, Mapping, PlotSpec, Style

OUT = Path(__file__).resolve().parents[1] / "examples" / "stage_d"
OUT.mkdir(parents=True, exist_ok=True)
D = Path(__file__).resolve().parents[2]
FILTER = str(D / "3D_Results/Filter_Results/V3/results.csv")
FUSION = str(D / "3D_Results/Combinations/results.csv")
PARAM = str(D.parent / "Code/Processing/Parameter_Sweep/results/Parameter_Results/all_scans.csv")
RANK1 = str(D / "3D_Results/Filter_Results/V3/plots/ranking_1.csv")


def save(name, spec):
    res = render(spec)
    res.savefig(OUT / f"{name}.pdf")
    res.savefig(OUT / f"{name}.png", dpi=200)
    print(f"{name}: {res.width_cm:g} x {res.height_cm:g} cm\n   {res.footnote}")
    for w in res.warnings:
        print("   WARNING:", w)


# Parameter study: preset x resolution, faceted by object (n = 3 depth units per cell)
save("heatmap_param", PlotSpec(
    plot_type="heatmap", dataset=DatasetRef(PARAM),
    mapping=Mapping(x="preset", row="resolution", y=["acc_rmse_mm"], facet="object_label"),
    aggregation=Aggregation(func="mean"), options={"show_n": True},
    export=Export(size_preset="thesis_full", height_cm=7)))

# Filter sweep: spatial alpha x delta, spatial-only configs, difference from baseline
only_spatial = [Filter("spatial_on", values=[True]), Filter("temporal_on", values=[False]),
                Filter("decimation_on", values=[False]), Filter("hole_filling_on", values=[False]),
                Filter("hdr_merge_on", values=[False]), Filter("spatial_magnitude", values=[2.0]),
                Filter("spatial_holes_fill", values=[0.0])]
save("heatmap_spatial_vs_baseline", PlotSpec(
    plot_type="heatmap", dataset=DatasetRef(FILTER),
    mapping=Mapping(x="spatial_alpha", row="spatial_delta", y=["acc_rmse_trim5_mm"],
                    facet="shape"),
    filters=only_spatial, aggregation=Aggregation(func="mean"),
    options={"centre": "baseline", "show_as": "% change"},
    export=Export(size_preset="thesis_full", height_cm=8)))

# Ranking computed from the sweep, baseline shown for reference
save("ranking_filter_sweep", PlotSpec(
    plot_type="ranking", dataset=DatasetRef(FILTER),
    mapping=Mapping(x="config_label", y=["acc_rmse_trim5_mm"], hue="spatial_on"),
    aggregation=Aggregation(func="mean", spread="ci95"), options={"top_n": 12},
    export=Export(size_preset="thesis_full", height_cm=10)))

# Pre-computed ranking file
save("ranking_file", PlotSpec(
    plot_type="ranking", dataset=DatasetRef(RANK1),
    mapping=Mapping(x="config_label", y=["mean_acc_rmse_mm"]),
    aggregation=Aggregation(func="none"), options={"top_n": 10}))

# Fusion: best combos per object
save("ranking_fusion_by_wave", PlotSpec(
    plot_type="ranking", dataset=DatasetRef(FUSION),
    mapping=Mapping(x="combo_id", y=["acc_rmse_mm"], facet="wave"),
    filters=[Filter("status", values=["ok"])],
    aggregation=Aggregation(func="mean", spread="std"), options={"top_n": 8},
    export=Export(size_preset="thesis_full", height_cm=8)))
