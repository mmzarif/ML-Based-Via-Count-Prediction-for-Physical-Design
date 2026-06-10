# ML-Based Via Count Prediction for Physical Design

Predicts post-routing via counts per net from post-CTS placement features using machine learning. Built as part of CSE 241A (VLSI CAD) at UC San Diego.

---

## Overview

Routing is the most runtime-intensive step in physical design. This project trains a regression model to predict the number of vias a net will require after detailed routing, using only features available at the post-CTS stage — before routing begins.

**Design:** `aes_cipher_top` (TSMC 65GP)  
**Tool:** Siemens Aprisa (P&R)  
**Target:** Minimize RMSE of predicted vs. actual per-net via count

---

## Results

| Dataset | Utilization | Clock Period | RMSE |
|---------|------------|-------------|------|
| Training | 60% | 1.60 ns | 5.25 |
| Training | 70% | 1.60 ns | 6.09 |
| Training | 80% | 1.60 ns | 5.52 |
| Open Test | 65% | 1.60 ns | 4.94 |
| Open Test | 75% | 1.60 ns | 4.33 |

**Cross-validation RMSE (full training set): 3.84 vias/net**

---

## Model

`GradientBoostingRegressor` (scikit-learn), selected via ablation study across 6 model variants.

| Model | CV RMSE |
|-------|---------|
| LinearRegression (raw) | 4.14 |
| LinearRegression (engineered) | 3.94 |
| Ridge (engineered) | 3.94 |
| GradientBoosting (raw, depth=3) | 3.85 |
| **GradientBoosting (engineered, depth=4)** | **3.84** |
| RandomForest (engineered) | 3.95 |

Hyperparameters: `n_estimators=400, max_depth=4, learning_rate=0.08, subsample=0.8, min_samples_leaf=20`

---

## Features

### Raw (from post-CTS DEF)
| Feature | Description |
|---------|-------------|
| `util` | Initial floorplan utilization |
| `cp` | Target clock period (ns) |
| `bboxArea` | Net bounding box area (µm²) |
| `bboxAr` | Net bounding box aspect ratio |
| `numPins` | Number of pins on the net |

### Engineered
| Feature | Formula | Rationale |
|---------|---------|-----------|
| `bboxPerim` | `2*(W+H)` | Wire length scales with perimeter, not area |
| `logBboxArea` | `log1p(bboxArea)` | Via count is sub-linear in area |
| `pinDensity` | `numPins / bboxArea` | Crowded nets need more layer changes |
| `numPins²` | `numPins²` | High-fanout cost is super-linear |
| `areaPins` | `bboxArea × numPins` | Large high-fanout nets are disproportionately expensive |
| `util_cp` | `util × cp` | Joint effect of density and timing pressure |
| `sqrtArea` | `√bboxArea` | Direct wire length proxy |
| `bboxAr_numPins` | `bboxAr × numPins` | Elongated multi-sink nets force many layer transitions |

---

## Training Data

Generated a **273,212-sample** dataset by running Aprisa P&R across a 5×4 grid:

|  | 1.30 ns | 1.40 ns | 1.50 ns | 1.60 ns |
|--|---------|---------|---------|---------|
| **60%** | ✓ | ✓ | ✓ | ✓ |
| **65%** | ✓ | ✓ | ✓ | ✓ |
| **70%** | ✓ | ✓ | ✓ | ✓ |
| **75%** | ✓ | ✓ | ✓ | ✓ |
| **80%** | ✓ | ✓ | ✓ | ✓ |

Runs were parallelized using a semaphore-based bash job pool (`MAX_JOBS=4`), reducing total generation time by ~4×.

---

## Repository Structure

```
├── generate_features.py      # Parse post-CTS DEF → per-net feature CSV
├── generate_label.py         # Parse post-routed DEF → per-net via count CSV
├── merge_features_label.py   # Join features and labels on netName
├── build_training.sh         # Auto-discover DEFs, extract data, train model
├── run_parallel.sh           # Dispatch parallel Aprisa runs
├── patch_and_run.sh          # Single (util, cp) Aprisa run in isolated workdir
├── ml_train.py               # Train model with ablation study
├── ml_inference.py           # Run inference from saved model
├── ml_rmse.py                # Compute per-file and overall RMSE
├── training.csv              # 273,212-row training dataset
├── inference.csv             # Predictions for Table 1 and Table 2 cases
├── model.pkl                 # Trained GradientBoosting model
└── requirements.txt          # Python dependencies
```

---

## Usage

### Setup
```bash
# Clone and set up virtual environment
python3 -m venv ./venv
source ./venv/bin/activate
pip install -r requirements.txt
```

### Generate training data
```bash
# Runs Aprisa for all (util, cp) combinations in parallel
bash run_parallel.sh

# Extract features/labels from all DEFs and train model
bash build_training.sh
```

### Run inference and evaluate
```bash
# Generate predictions
python3 ml_inference.py \
    --input merged_60_1600.csv merged_70_1600.csv merged_80_1600.csv \
            merged_65_1600.csv merged_75_1600.csv \
    --model model.pkl \
    --out inference.csv

# Compute RMSE
python3 ml_rmse.py \
    --truth merged_60_1600.csv merged_70_1600.csv merged_80_1600.csv \
            merged_65_1600.csv merged_75_1600.csv \
    --infer inference.csv \
    --report
```

### Train with ablation study
```bash
python3 ml_train.py --train training.csv --model model.pkl --ablation
```

---

## Requirements

- Python 3.7+
- scikit-learn
- numpy
- Siemens Aprisa (for data generation only)
- ieng6 ECE cluster (UCSD) or equivalent Linux environment

---

## Notes

- DEF files output by Aprisa are gzip-compressed despite the `.def` extension — the parsers handle this automatically
- Only nets with 2–50 pins are included per project specification
- `numVias` is never used as an input feature during inference
