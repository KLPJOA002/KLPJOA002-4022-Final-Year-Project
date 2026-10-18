# Rotation x tilt combination sweep: summary

Rows: 1092 (ok 1073, suspect 16, failed 3). Primary metric: `acc_rmse_mm` (lower is better). Figures: `analysis/figures/`.

## Failed / suspect jobs

| wave | height | combo_id | n_scans | status | failure_stage | failure_reason |
|---|---|---|---|---|---|---|
| Big_Wave | 641mm | single_r0_a25 | 1 | suspect |  | covers only 63% of the reference (< 85%) |
| Big_Wave | 641mm | single_r135_a-15 | 1 | failed | seed | seed: seed: no object found above the table plane |
| Big_Wave | 641mm | single_r135_a10 | 1 | suspect |  | covers only 54% of the reference (< 85%) |
| Big_Wave | 641mm | single_r45_a-15 | 1 | suspect |  | covers only 52% of the reference (< 85%) |
| Big_Wave | 641mm | single_r45_a10 | 1 | suspect |  | covers only 55% of the reference (< 85%) |
| Big_Wave | 641mm | single_r90_a0 | 1 | suspect |  | covers only 29% of the reference (< 85%) |
| Big_Wave | 701mm | single_r0_a25 | 1 | suspect |  | covers only 62% of the reference (< 85%) |
| Big_Wave | 763mm | single_r0_a25 | 1 | suspect |  | covers only 61% of the reference (< 85%) |
| Big_Wave | 810mm | single_r0_a25 | 1 | suspect |  | covers only 82% of the reference (< 85%) |
| Big_Wave | 863mm | single_r0_a25 | 1 | suspect |  | covers only 80% of the reference (< 85%) |
| Big_Wave | 933mm | single_r0_a25 | 1 | suspect |  | covers only 52% of the reference (< 85%) |
| Small_Wave | 641mm | single_r0_a25 | 1 | suspect |  | covers only 67% of the reference (< 85%) |
| Small_Wave | 641mm | single_r135_a10 | 1 | suspect |  | covers only 58% of the reference (< 85%) |
| Small_Wave | 641mm | single_r45_a-10 | 1 | suspect |  | covers only 75% of the reference (< 85%) |
| Small_Wave | 641mm | single_r45_a-15 | 1 | failed | crop | crop: no usable cropped scans (r45_a-15) |
| Small_Wave | 641mm | single_r45_a10 | 1 | failed | seed | seed: seed: no object found above the table plane |
| Small_Wave | 641mm | single_r90_a0 | 1 | suspect |  | covers only 57% of the reference (< 85%) |
| Small_Wave | 863mm | single_r0_a25 | 1 | suspect |  | covers only 82% of the reference (< 85%) |
| Small_Wave | 933mm | single_r0_a25 | 1 | suspect |  | covers only 79% of the reference (< 85%) |


## Key numbers (median over heights)

| wave | all-44 acc_rmse_mm | all-44 fuse min | single median | best single (median over heights) | best single scan | best fused combo | best fused acc_rmse_mm |
|---|---|---|---|---|---|---|---|
| Big_Wave | 1.660 | 4.060 | 2.284 | 1.947 | single_r0_a20 | rot-all_tilt-0-pos | 1.640 |
| Small_Wave | 2.529 | 3.985 | 2.683 | 2.347 | single_r0_a20 | rot-0-45_tilt-0-pm25 | 2.467 |


## Smallest subset within 5% of all-44 (acc_rmse_mm)

| wave | height_mm | all44_acc_rmse_mm | all44_fuse_s | smallest_combo | n_scans | acc_rmse_mm | fuse_s | n_candidates_within |
|---|---|---|---|---|---|---|---|---|
| Big_Wave | 641 | 1.147 | 349.660 | rot-45-135_tilt-0-pm25 | 6 | 1.157 | 80.440 | 13 |
| Big_Wave | 701 | 1.344 | 295.110 | rot-0-45_tilt-0-pm25 | 6 | 1.307 | 61.070 | 21 |
| Big_Wave | 763 | 1.565 | 252.640 | rot-45-135_tilt-0-pm25 | 6 | 1.613 | 57.460 | 17 |
| Big_Wave | 810 | 1.755 | 234.600 | rot-45-135_tilt-0-pm25 | 6 | 1.774 | 50.600 | 16 |
| Big_Wave | 863 | 1.885 | 225.750 | rot-0_tilt-0-pos | 6 | 1.919 | 57.110 | 16 |
| Big_Wave | 933 | 2.313 | 193.130 | rot-0-45_tilt-0-pm25 | 6 | 2.345 | 31.740 | 20 |
| Small_Wave | 641 | 1.931 | 338.390 | single_r135_a25 | 1 | 1.920 | 0.000 | 25 |
| Small_Wave | 701 | 2.153 | 304.460 | single_r90_a25 | 1 | 2.105 | 0.000 | 21 |
| Small_Wave | 763 | 2.432 | 248.000 | single_r45_a25 | 1 | 2.203 | 0.000 | 36 |
| Small_Wave | 810 | 2.626 | 230.200 | single_r135_a25 | 1 | 2.288 | 0.000 | 48 |
| Small_Wave | 863 | 2.720 | 225.740 | single_r0_a20 | 1 | 2.510 | 0.000 | 38 |
| Small_Wave | 933 | 2.935 | 199.520 | single_r0_a-25 | 1 | 2.577 | 0.000 | 46 |


Most frequent smallest subsets: `rot-45-135_tilt-0-pm25` (3x), `rot-0-45_tilt-0-pm25` (2x), `single_r135_a25` (2x), `rot-0_tilt-0-pos` (1x), `single_r90_a25` (1x)

Tilt sign: fusing only positive tilts (6 per rotation) vs all 11 tilts changes `acc_rmse_mm` by a median of -0.005 over (wave, height).

## Best 3 combinations per height

| wave | height_mm | rank | combo_id | family | n_scans | acc_rmse_mm | fuse_s | total_s |
|---|---|---|---|---|---|---|---|---|
| Big_Wave | 641 | 1 | rot-all_tilt-0-pos | tilt | 24 | 1.112 | 240.050 | 271.370 |
| Big_Wave | 641 | 2 | rot-all_tilt-0-pm25 | tilt | 12 | 1.118 | 163.320 | 180.030 |
| Big_Wave | 641 | 3 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.141 | 253.890 | 280.640 |
| Big_Wave | 701 | 1 | rot-0-45-90_tilt-0-pm25 | joint | 9 | 1.257 | 111.980 | 124.510 |
| Big_Wave | 701 | 2 | rot-all_tilt-0-pm25 | tilt | 12 | 1.258 | 138.180 | 155.180 |
| Big_Wave | 701 | 3 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.292 | 226.480 | 269.090 |
| Big_Wave | 763 | 1 | rot-all_tilt-0-pos | tilt | 24 | 1.536 | 192.640 | 216.560 |
| Big_Wave | 763 | 2 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.540 | 202.380 | 228.880 |
| Big_Wave | 763 | 3 | rot-45-135_tilt-all | rotation | 22 | 1.552 | 189.770 | 202.500 |
| Big_Wave | 810 | 1 | rot-all_tilt-0-pos | tilt | 24 | 1.744 | 182.490 | 206.190 |
| Big_Wave | 810 | 2 | rot-all_tilt-all | all | 44 | 1.755 | 234.600 | 252.630 |
| Big_Wave | 810 | 3 | rot-all_tilt-0-pm25 | tilt | 12 | 1.759 | 111.120 | 124.140 |
| Big_Wave | 863 | 1 | rot-all_tilt-all | all | 44 | 1.885 | 225.750 | 241.630 |
| Big_Wave | 863 | 2 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.892 | 176.160 | 198.090 |
| Big_Wave | 863 | 3 | rot-0_tilt-0-pos | joint | 6 | 1.919 | 57.110 | 72.340 |
| Big_Wave | 933 | 1 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 2.299 | 162.290 | 186.070 |
| Big_Wave | 933 | 2 | rot-all_tilt-all | all | 44 | 2.313 | 193.130 | 212.590 |
| Big_Wave | 933 | 3 | rot-all_tilt-0-pos | tilt | 24 | 2.325 | 149.480 | 178.280 |
| Small_Wave | 641 | 1 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.915 | 255.640 | 281.100 |
| Small_Wave | 641 | 2 | single_r135_a25 | single | 1 | 1.920 | 0.000 | 27.070 |
| Small_Wave | 641 | 3 | rot-all_tilt-0-pos | tilt | 24 | 1.923 | 248.080 | 278.170 |
| Small_Wave | 701 | 1 | single_r90_a25 | single | 1 | 2.105 | 0.000 | 11.060 |
| Small_Wave | 701 | 2 | rot-45-135_tilt-all | rotation | 22 | 2.125 | 211.520 | 230.620 |
| Small_Wave | 701 | 3 | rot-all_tilt-0-pos | tilt | 24 | 2.135 | 228.520 | 260.290 |
| Small_Wave | 763 | 1 | single_r45_a25 | single | 1 | 2.203 | 0.000 | 11.030 |
| Small_Wave | 763 | 2 | single_r0_a-25 | single | 1 | 2.281 | 0.000 | 9.270 |
| Small_Wave | 763 | 3 | single_r0_a20 | single | 1 | 2.293 | 0.000 | 9.740 |
| Small_Wave | 810 | 1 | single_r135_a25 | single | 1 | 2.288 | 0.000 | 11.450 |
| Small_Wave | 810 | 2 | single_r0_a-20 | single | 1 | 2.306 | 0.000 | 11.310 |
| Small_Wave | 810 | 3 | single_r0_a25 | single | 1 | 2.324 | 0.000 | 8.960 |
| Small_Wave | 863 | 1 | single_r0_a20 | single | 1 | 2.510 | 0.000 | 10.240 |
| Small_Wave | 863 | 2 | single_r45_a-20 | single | 1 | 2.551 | 0.000 | 11.520 |
| Small_Wave | 863 | 3 | single_r45_a25 | single | 1 | 2.596 | 0.000 | 11.640 |
| Small_Wave | 933 | 1 | single_r0_a-25 | single | 1 | 2.577 | 0.000 | 11.260 |
| Small_Wave | 933 | 2 | single_r0_a20 | single | 1 | 2.680 | 0.000 | 11.720 |
| Small_Wave | 933 | 3 | single_r0_a5 | single | 1 | 2.809 | 0.000 | 11.690 |


## Caveats on the metrics

- **Single scans are not like-for-like with fused clouds.** fuse_scans resamples onto a `fusion-cell` height-field grid, averages overlapping scans and smooths (MLS), which lowers random error by itself. Single scans are scored as cropped, at native density. Compare single vs fused with that in mind; fused vs fused comparisons share the same resampling.
- **Completeness and density metrics depend on point count**: `completeness@τ` is measured from reference samples to the nearest scan point, so sparser clouds lose completeness even when accurate. Fused clouds all share one grid spacing; single scans do not.
- **Accuracy RMSE is computed only over scored points**: a combination that leaves holes (e.g. steep wave flanks no scan saw) can show a lower RMSE by having fewer hard points. Read it together with `covered_fraction` / `completeness_full@1mm`.
- Each (wave, height, combination) is one fusion of one capture; differences smaller than the spread between neighbouring heights are probably noise.

## Figures

- `height_rotation_acc_rmse_mm`
- `height_tilt_acc_rmse_mm`
- `height_overview_acc_rmse_mm`
- `nscans_acc_rmse_mm`
- `heatmap_acc_rmse_mm`
- `height_rotation_acc_rmse_trim5_mm`
- `height_tilt_acc_rmse_trim5_mm`
- `height_overview_acc_rmse_trim5_mm`
- `nscans_acc_rmse_trim5_mm`
- `heatmap_acc_rmse_trim5_mm`
- `height_rotation_signed_std_mm`
- `height_tilt_signed_std_mm`
- `height_overview_signed_std_mm`
- `nscans_signed_std_mm`
- `heatmap_signed_std_mm`
- `height_rotation_z_bias_mm`
- `height_tilt_z_bias_mm`
- `height_overview_z_bias_mm`
- `nscans_z_bias_mm`
- `heatmap_z_bias_mm`
- `height_rotation_completeness_full_1mm`
- `height_tilt_completeness_full_1mm`
- `height_overview_completeness_full_1mm`
- `nscans_completeness_full_1mm`
- `heatmap_completeness_full_1mm`
- `height_rotation_covered_fraction`
- `height_tilt_covered_fraction`
- `height_overview_covered_fraction`
- `nscans_covered_fraction`
- `heatmap_covered_fraction`
- `height_rotation_chamfer_mm`
- `height_tilt_chamfer_mm`
- `height_overview_chamfer_mm`
- `nscans_chamfer_mm`
- `heatmap_chamfer_mm`
- `angle_single_vs_tilt_acc_rmse_mm`
- `angle_single_vs_rotation_acc_rmse_mm`
- `angle_fused_tilt_acc_rmse_mm`
- `angle_fused_rotation_acc_rmse_mm`
- `angle_single_vs_tilt_completeness_full_1mm`
- `angle_single_vs_rotation_completeness_full_1mm`
- `angle_fused_tilt_completeness_full_1mm`
- `angle_fused_rotation_completeness_full_1mm`
- `runtime_acc_rmse_mm`
