| metric | shapes | best configuration | best mean | baseline mean | change | scans ok |
|---|---|---|---|---|---|---|
| Accuracy RMSE (mm) | all | `tp a0.1 d20 p0 | hf0` | 2.412 | 2.497 | -3.1% | 60/60 |
| Accuracy RMSE (mm) | Big_Wave | `dec2 | tp a0.1 d20 p0 | hf0` | 2.188 | 2.293 | -5.0% | 29/30 |
| Accuracy RMSE (mm) | Small_Wave | `tp a0.4 d20 p4` | 2.642 | 2.701 | -2.0% | 30/30 |
| Accuracy RMSE, worst 5% trimmed (mm) | all | `tp a0.1 d20 p0 | hf0` | 2.106 | 2.171 | -2.6% | 60/60 |
| Accuracy RMSE, worst 5% trimmed (mm) | Big_Wave | `tp a0.1 d20 p0 | hf0` | 1.878 | 1.964 | -3.6% | 30/30 |
| Accuracy RMSE, worst 5% trimmed (mm) | Small_Wave | `tp a0.4 d20 p4` | 2.325 | 2.377 | -1.9% | 30/30 |
| Signed error std (mm) | all | `tp a0.1 d20 p0 | hf0` | 2.405 | 2.49 | -3.1% | 60/60 |
| Signed error std (mm) | Big_Wave | `dec2 | tp a0.1 d20 p0 | hf0` | 2.179 | 2.285 | -5.0% | 29/30 |
| Signed error std (mm) | Small_Wave | `tp a0.4 d20 p4` | 2.636 | 2.695 | -2.0% | 30/30 |
| |Signed bias| (mm) | all | `sp m2 a0.5 d1 h0` | 0.1562 | 0.159 | -1.3% | 60/60 |
| |Signed bias| (mm) | Big_Wave | `sp m2 a0.5 d1 h0` | 0.1441 | 0.1442 | -0.4% | 30/30 |
| |Signed bias| (mm) | Small_Wave | `sp m2 a0.5 d1 h0` | 0.1682 | 0.1738 | -2.1% | 30/30 |
| Vertical (Z) RMSE (mm) | all | `tp a0.25 d20 p0` | 4.647 | 4.791 | -2.8% | 60/60 |
| Vertical (Z) RMSE (mm) | Big_Wave | `dec2 | tp a0.25 d20 p0` | 4.141 | 4.293 | -2.8% | 30/30 |
| Vertical (Z) RMSE (mm) | Small_Wave | `tp a0.25 d20 p0` | 5.11 | 5.288 | -2.9% | 30/30 |
| Covered fraction of reference | all | `tp a0.4 d20 p4` | 0.9909 | 0.9884 | +0.3% | 60/60 |
| Covered fraction of reference | Big_Wave | `tp a0.4 d20 p4` | 0.9941 | 0.9925 | +0.2% | 30/30 |
| Covered fraction of reference | Small_Wave | `tp a0.4 d20 p4` | 0.9877 | 0.9843 | +0.4% | 30/30 |
| Completeness @2 mm, whole part | all | `tp a0.4 d5 p3` | 0.4825 | 0.4706 | +2.8% | 60/60 |
| Completeness @2 mm, whole part | Big_Wave | `hf0` | 0.5779 | 0.5572 | +4.9% | 29/30 |
| Completeness @2 mm, whole part | Small_Wave | `tp a0.1 d20 p0 | hf2` | 0.3885 | 0.384 | +1.3% | 30/30 |
| F-score @2 mm | all | `tp a0.4 d20 p4` | 0.5349 | 0.5253 | +2.2% | 60/60 |
| F-score @2 mm | Big_Wave | `hf0` | 0.6166 | 0.598 | +4.1% | 29/30 |
| F-score @2 mm | Small_Wave | `tp a0.4 d10 p3` | 0.4561 | 0.4527 | +1.0% | 30/30 |
| Outlier fraction (> 5 mm) | all | `tp a0.4 d50 p3` | 0.04771 | 0.05538 | -15.4% | 60/60 |
| Outlier fraction (> 5 mm) | Big_Wave | `sp m1 a0.75 d30 h0 | tp a0.1 d20 p0 | hf0` | 0.03018 | 0.04086 | -26.2% | 30/30 |
| Outlier fraction (> 5 mm) | Small_Wave | `tp a0.1 d20 p3` | 0.06341 | 0.0699 | -7.6% | 30/30 |
| Point density (pts/cm²) | all | `sp m2 a0.25 d30 h0 | tp a0.1 d20 p3` | 52.42 | 47.93 | +5.7% | 54/60 |
| Point density (pts/cm²) | Big_Wave | `sp m3 a0.25 d30 h0 | tp a0.1 d20 p3` | 56.31 | 53.48 | +4.7% | 29/30 |
| Point density (pts/cm²) | Small_Wave | `sp m3 a0.25 d8 h0 | tp a0.5 d20 p3` | 48.56 | 42.37 | +8.2% | 24/30 |
