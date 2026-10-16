| metric | shapes | best configuration | best mean | baseline mean | change | scans ok |
|---|---|---|---|---|---|---|
| Accuracy RMSE (mm) | all | `tp a0.1 d20 p0 | hf0` | 2.412 | 2.497 | -3.1% | 60/60 |
| Accuracy RMSE (mm) | Big_Wave | `dec2 | tp a0.1 d20 p0 | hf0` | 2.188 | 2.293 | -5.0% | 29/30 |
| Accuracy RMSE (mm) | Small_Wave | `tp a0.1 d20 p3 | hf1` | 2.643 | 2.702 | -2.0% | 30/30 |
| Accuracy RMSE, worst 5% trimmed (mm) | all | `tp a0.1 d20 p3 | hf0` | 2.106 | 2.17 | -2.6% | 60/60 |
| Accuracy RMSE, worst 5% trimmed (mm) | Big_Wave | `tp a0.1 d20 p0 | hf0` | 1.878 | 1.964 | -3.6% | 30/30 |
| Accuracy RMSE, worst 5% trimmed (mm) | Small_Wave | `tp a0.4 d20 p3` | 2.327 | 2.376 | -1.9% | 30/30 |
| Signed error std (mm) | all | `tp a0.1 d20 p0 | hf0` | 2.405 | 2.49 | -3.1% | 60/60 |
| Signed error std (mm) | Big_Wave | `dec2 | tp a0.1 d20 p0 | hf0` | 2.179 | 2.286 | -5.1% | 29/30 |
| Signed error std (mm) | Small_Wave | `tp a0.1 d20 p3 | hf1` | 2.637 | 2.695 | -2.0% | 30/30 |
| |Signed bias| (mm) | all | `sp m2 a1 d20 h0` | 0.1562 | 0.1606 | -0.7% | 60/60 |
| |Signed bias| (mm) | Big_Wave | `baseline (no filters)` | 0.1442 | 0.1442 | +0.0% | 30/30 |
| |Signed bias| (mm) | Small_Wave | `sp m2 a1 d20 h0` | 0.1683 | 0.177 | -1.6% | 30/30 |
| Vertical (Z) RMSE (mm) | all | `tp a0.25 d20 p0` | 4.647 | 4.807 | -2.9% | 60/60 |
| Vertical (Z) RMSE (mm) | Big_Wave | `dec2 | tp a0.25 d20 p0` | 4.141 | 4.292 | -2.8% | 30/30 |
| Vertical (Z) RMSE (mm) | Small_Wave | `tp a0.25 d20 p0` | 5.11 | 5.321 | -3.2% | 30/30 |
| Covered fraction of reference | all | `tp a0.1 d20 p0 | hf2` | 0.9908 | 0.9885 | +0.2% | 60/60 |
| Covered fraction of reference | Big_Wave | `tp a0.4 d20 p4` | 0.9941 | 0.9925 | +0.2% | 30/30 |
| Covered fraction of reference | Small_Wave | `tp a0.1 d20 p0 | hf2` | 0.9875 | 0.9845 | +0.3% | 30/30 |
| Completeness @2 mm, whole part | all | `tp a0.4 d5 p3` | 0.4822 | 0.4703 | +2.9% | 60/60 |
| Completeness @2 mm, whole part | Big_Wave | `tp a0.4 d5 p3` | 0.5772 | 0.5573 | +4.5% | 30/30 |
| Completeness @2 mm, whole part | Small_Wave | `tp a0.4 d10 p3` | 0.3883 | 0.3833 | +1.6% | 30/30 |
| F-score @2 mm | all | `tp a0.4 d20 p4` | 0.535 | 0.5249 | +2.3% | 60/60 |
| F-score @2 mm | Big_Wave | `hf0` | 0.6124 | 0.598 | +3.6% | 30/30 |
| F-score @2 mm | Small_Wave | `tp a0.4 d10 p3` | 0.4573 | 0.4519 | +1.5% | 30/30 |
| Outlier fraction (> 5 mm) | all | `tp a0.4 d50 p3` | 0.04776 | 0.05519 | -15.3% | 60/60 |
| Outlier fraction (> 5 mm) | Big_Wave | `sp m1 a0.75 d30 h0 | tp a0.1 d20 p0 | hf0` | 0.0302 | 0.04085 | -26.2% | 30/30 |
| Outlier fraction (> 5 mm) | Small_Wave | `tp a0.1 d20 p3 | hf1` | 0.06325 | 0.06954 | -8.3% | 30/30 |
| Point density (pts/cm²) | all | `sp m2 a0.25 d30 h0 | tp a0.5 d20 p3` | 52.76 | 47.92 | +5.8% | 53/60 |
| Point density (pts/cm²) | Big_Wave | `sp m3 a0.25 d30 h0 | tp a0.1 d20 p3` | 56.31 | 53.48 | +4.7% | 29/30 |
| Point density (pts/cm²) | Small_Wave | `sp m3 a0.25 d8 h0 | tp a0.5 d20 p3` | 48.55 | 42.36 | +8.2% | 24/30 |
