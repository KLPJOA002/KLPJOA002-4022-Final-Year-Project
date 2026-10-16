# Rotation x tilt combination sweep: summary

Rows: 1092 (ok 1015, failed 51, suspect 26). Primary metric: `acc_rmse_mm` (lower is better). Figures: `analysis/figures/`.

## Failed / suspect jobs

| wave | height | combo_id | n_scans | status | failure_stage | failure_reason |
|---|---|---|---|---|---|---|
| Big_Wave | 641mm | rot-0-45_tilt-0-pm25 | 6 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 641mm | rot-45-135_tilt-0-pm25 | 6 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 641mm | rot-0-45-90_tilt-0-pm25 | 9 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 641mm | rot-all_tilt-0-pm25 | 12 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 641mm | single_r0_a25 | 1 | suspect |  | covers only 63% of the reference (< 85%) |
| Big_Wave | 641mm | single_r135_a-15 | 1 | failed | seed | seed: seed: no object found above the table plane |
| Big_Wave | 641mm | single_r135_a10 | 1 | suspect |  | covers only 54% of the reference (< 85%) |
| Big_Wave | 641mm | single_r45_a-15 | 1 | suspect |  | covers only 36% of the reference (< 85%) |
| Big_Wave | 641mm | single_r45_a10 | 1 | suspect |  | covers only 55% of the reference (< 85%) |
| Big_Wave | 641mm | single_r90_a0 | 1 | suspect |  | covers only 29% of the reference (< 85%) |
| Big_Wave | 701mm | rot-45-135_tilt-0-pm25 | 6 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 701mm | rot-0-45-90_tilt-0-pm25 | 9 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 701mm | rot-all_tilt-0-pm25 | 12 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 701mm | single_r0_a25 | 1 | suspect |  | covers only 62% of the reference (< 85%) |
| Big_Wave | 763mm | rot-45-135_tilt-0-pm25 | 6 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-0-45-90_tilt-0-pm25 | 9 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-0-90_tilt-0-pm10-pm20 | 10 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-all_tilt-0-pm25 | 12 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-0-90_tilt-0-pm10-pm20-pm25 | 14 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-0-45-90_tilt-0-pm10-pm20 | 15 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-all_tilt-0-pm10-pm20 | 20 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-0-45-90_tilt-0-pm10-pm20-pm25 | 21 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | rot-all_tilt-0-pm10-pm20-pm25 | 28 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 763mm | single_r0_a25 | 1 | suspect |  | covers only 64% of the reference (< 85%) |
| Big_Wave | 810mm | rot-0_tilt-0-pm25 | 3 | suspect |  | covers only 85% of the reference (< 85%) |
| Big_Wave | 810mm | rot-0-45-90_tilt-0-pm25 | 9 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 810mm | rot-all_tilt-0-pm25 | 12 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 810mm | single_r0_a25 | 1 | suspect |  | covers only 82% of the reference (< 85%) |
| Big_Wave | 863mm | rot-0_tilt-0-pm25 | 3 | suspect |  | covers only 83% of the reference (< 85%) |
| Big_Wave | 863mm | rot-0-45-90_tilt-0-pm25 | 9 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 863mm | rot-all_tilt-0-pm25 | 12 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 863mm | single_r0_a25 | 1 | suspect |  | covers only 81% of the reference (< 85%) |
| Big_Wave | 933mm | rot-0-90_tilt-0 | 2 | suspect |  | covers only 66% of the reference (< 85%) |
| Big_Wave | 933mm | rot-0-90_tilt-0-pm10 | 6 | suspect |  | covers only 82% of the reference (< 85%) |
| Big_Wave | 933mm | rot-0-45-90_tilt-0-pm25 | 9 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 933mm | rot-0-90_tilt-0-pm10-pm20 | 10 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 933mm | rot-all_tilt-0-pm25 | 12 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 933mm | rot-0-45_tilt-0-pm10-pm20-pm25 | 14 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 933mm | rot-0-90_tilt-0-pm10-pm20-pm25 | 14 | failed | fuse | fuse: timed out after 3600 s |
| Big_Wave | 933mm | rot-0-45-90_tilt-0-pm10-pm20 | 15 | failed | fuse | fuse: timed out after 3600 s |


## Key numbers (median over heights)

| wave | all-44 acc_rmse_mm | all-44 fuse min | single median | best single (median over heights) | best single scan | best fused combo | best fused acc_rmse_mm |
|---|---|---|---|---|---|---|---|
| Big_Wave | 1.820 | 9.629 | 2.281 | 1.947 | single_r0_a20 | rot-all_tilt-0-pm10-pm20-pm25 | 1.532 |
| Small_Wave | 2.529 | 7.985 | 2.681 | 2.347 | single_r0_a20 | rot-45-135_tilt-0-pm10-pm20-pm25 | 2.435 |


## Smallest subset within 5% of all-44 (acc_rmse_mm)

| wave | height_mm | all44_acc_rmse_mm | all44_fuse_s | smallest_combo | n_scans | acc_rmse_mm | fuse_s | n_candidates_within |
|---|---|---|---|---|---|---|---|---|
| Big_Wave | 641 | 1.147 | 577.600 | rot-0-90_tilt-0-pos | 12 | 1.173 | 427.050 | 11 |
| Big_Wave | 701 | 1.344 | 577.910 | rot-0-45_tilt-0-pm25 | 6 | 1.296 | 3060.870 | 16 |
| Big_Wave | 763 | 3.875 | 2818.380 | single_r0_a20 | 1 | 1.750 | 0.000 | 80 |
| Big_Wave | 810 | 1.755 | 415.310 | rot-0_tilt-0-pos | 6 | 1.732 | 110.040 | 8 |
| Big_Wave | 863 | 1.885 | 431.990 | rot-0_tilt-0-pos | 6 | 1.902 | 58.240 | 15 |
| Big_Wave | 933 | 3.525 | 1298.450 | single_r0_a25 | 1 | 2.199 | 0.000 | 73 |
| Small_Wave | 641 | 1.933 | 747.770 | single_r135_a25 | 1 | 1.920 | 0.000 | 23 |
| Small_Wave | 701 | 2.153 | 471.240 | single_r90_a25 | 1 | 2.105 | 0.000 | 18 |
| Small_Wave | 763 | 2.432 | 543.160 | single_r45_a25 | 1 | 2.203 | 0.000 | 29 |
| Small_Wave | 810 | 2.626 | 451.330 | single_r135_a25 | 1 | 2.288 | 0.000 | 45 |
| Small_Wave | 863 | 2.720 | 408.740 | single_r0_a20 | 1 | 2.510 | 0.000 | 36 |
| Small_Wave | 933 | 2.935 | 486.910 | single_r0_a-25 | 1 | 2.577 | 0.000 | 45 |


Most frequent smallest subsets: `single_r0_a20` (2x), `rot-0_tilt-0-pos` (2x), `single_r135_a25` (2x), `rot-0-90_tilt-0-pos` (1x), `rot-0-45_tilt-0-pm25` (1x)

Tilt sign: fusing only positive tilts (6 per rotation) vs all 11 tilts changes `acc_rmse_mm` by a median of +0.005 over (wave, height).

## Best 3 combinations per height

| wave | height_mm | rank | combo_id | family | n_scans | acc_rmse_mm | fuse_s | total_s |
|---|---|---|---|---|---|---|---|---|
| Big_Wave | 641 | 1 | rot-all_tilt-0-pos | tilt | 24 | 1.102 | 488.910 | 507.820 |
| Big_Wave | 641 | 2 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.127 | 374.610 | 398.670 |
| Big_Wave | 641 | 3 | rot-all_tilt-all | all | 44 | 1.147 | 577.600 | 601.320 |
| Big_Wave | 701 | 1 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.296 | 264.250 | 273.280 |
| Big_Wave | 701 | 2 | rot-0-45_tilt-0-pm25 | joint | 6 | 1.296 | 3060.870 | 3089.100 |
| Big_Wave | 701 | 3 | rot-0-45-90_tilt-0-pm10-pm20-pm25 | joint | 21 | 1.307 | 310.060 | 332.790 |
| Big_Wave | 763 | 1 | rot-45-135_tilt-0-pm10-pm20-pm25 | joint | 14 | 1.528 | 240.460 | 262.490 |
| Big_Wave | 763 | 2 | rot-45-135_tilt-all | rotation | 22 | 1.559 | 174.490 | 189.550 |
| Big_Wave | 763 | 3 | rot-45-135_tilt-0-pos | joint | 12 | 1.588 | 245.040 | 274.300 |
| Big_Wave | 810 | 1 | rot-0_tilt-0-pos | joint | 6 | 1.732 | 110.040 | 128.550 |
| Big_Wave | 810 | 2 | rot-all_tilt-all | all | 44 | 1.755 | 415.310 | 437.580 |
| Big_Wave | 810 | 3 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.769 | 446.660 | 490.300 |
| Big_Wave | 863 | 1 | rot-all_tilt-all | all | 44 | 1.885 | 431.990 | 455.650 |
| Big_Wave | 863 | 2 | rot-all_tilt-0-pm10-pm20-pm25 | tilt | 28 | 1.889 | 455.110 | 489.530 |
| Big_Wave | 863 | 3 | rot-0_tilt-0-pos | joint | 6 | 1.902 | 58.240 | 76.480 |
| Big_Wave | 933 | 1 | single_r0_a25 | single | 1 | 2.199 | 0.000 | 9.130 |
| Big_Wave | 933 | 2 | rot-45-135_tilt-all | rotation | 22 | 2.250 | 124.290 | 127.810 |
| Big_Wave | 933 | 3 | rot-45-135_tilt-0-pos | joint | 12 | 2.276 | 278.840 | 305.880 |
| Small_Wave | 641 | 1 | rot-0-45_tilt-0-pos | joint | 12 | 1.887 | 319.690 | 347.800 |
| Small_Wave | 641 | 2 | rot-0-45_tilt-all | rotation | 22 | 1.896 | 397.980 | 423.460 |
| Small_Wave | 641 | 3 | rot-0-45_tilt-0-pm10-pm20-pm25 | joint | 14 | 1.898 | 351.310 | 380.480 |
| Small_Wave | 701 | 1 | single_r90_a25 | single | 1 | 2.105 | 0.000 | 10.460 |
| Small_Wave | 701 | 2 | rot-45-135_tilt-all | rotation | 22 | 2.119 | 302.300 | 324.010 |
| Small_Wave | 701 | 3 | rot-all_tilt-0-pos | tilt | 24 | 2.131 | 451.100 | 473.350 |
| Small_Wave | 763 | 1 | single_r45_a25 | single | 1 | 2.203 | 0.000 | 12.670 |
| Small_Wave | 763 | 2 | single_r0_a-25 | single | 1 | 2.281 | 0.000 | 9.250 |
| Small_Wave | 763 | 3 | single_r0_a20 | single | 1 | 2.293 | 0.000 | 9.840 |
| Small_Wave | 810 | 1 | single_r135_a25 | single | 1 | 2.288 | 0.000 | 11.550 |
| Small_Wave | 810 | 2 | single_r0_a-20 | single | 1 | 2.306 | 0.000 | 10.110 |
| Small_Wave | 810 | 3 | single_r0_a25 | single | 1 | 2.324 | 0.000 | 9.250 |
| Small_Wave | 863 | 1 | single_r0_a20 | single | 1 | 2.510 | 0.000 | 10.790 |
| Small_Wave | 863 | 2 | single_r45_a-20 | single | 1 | 2.551 | 0.000 | 13.380 |
| Small_Wave | 863 | 3 | single_r45_a25 | single | 1 | 2.596 | 0.000 | 12.050 |
| Small_Wave | 933 | 1 | single_r0_a-25 | single | 1 | 2.577 | 0.000 | 11.750 |
| Small_Wave | 933 | 2 | single_r0_a20 | single | 1 | 2.680 | 0.000 | 11.530 |
| Small_Wave | 933 | 3 | single_r0_a5 | single | 1 | 2.809 | 0.000 | 12.290 |


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
