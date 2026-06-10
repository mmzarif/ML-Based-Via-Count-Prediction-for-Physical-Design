"""
ml_inference.py
---------------
Load a saved model and run per-net via-count inference on one or more
feature CSV files.

IMPORTANT: numVias is NEVER used as an input feature during inference.
           The script will error-out if numVias is found as a feature
           column in the model metadata.

Usage
-----
  # Single CSV (reads features from training.csv, writes inference.csv)
  python3 ml_inference.py --input training.csv --model model.pkl --out inference.csv

  # Multiple CSVs (useful for evaluating test sets)
  python3 ml_inference.py \
      --input train_60_1600.csv train_70_1600.csv test_65_1600.csv \
      --model model.pkl \
      --out   inference.csv
"""

import argparse
import csv
import math
import pickle
import sys


# ---------------------------------------------------------------------------
# Feature engineering  (must match ml_train.py exactly)
# ---------------------------------------------------------------------------

def engineer_features(rows, use_engineered=True):
    import numpy as np
    X = []
    for r in rows:
        util  = float(r["util"])
        cp    = float(r["cp"])
        area  = float(r["bboxArea"])
        ar    = float(r["bboxAr"])
        np_   = float(r["numPins"])

        feats = [util, cp, area, ar, np_]

        if use_engineered:
            long_  = math.sqrt(area * ar)   if area > 0 else 0.0
            short_ = math.sqrt(area / ar)   if area > 0 else 0.0
            perim  = 2 * (long_ + short_)

            log_area       = math.log1p(area)
            pin_density    = np_ / (area + 1e-6)
            np2            = np_ * np_
            area_np        = area * np_
            util_cp        = util * cp
            sqrt_area      = math.sqrt(area)
            ar_np          = ar * np_

            feats += [perim, log_area, pin_density, np2,
                      area_np, util_cp, sqrt_area, ar_np]

        X.append(feats)
    import numpy as np
    return np.array(X, dtype="float64")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description="Run via-count inference")
    ap.add_argument("--input",  nargs="+", default=["training.csv"],
                    help="Input feature CSV(s) (training.csv or test_*.csv)")
    ap.add_argument("--model",  default="model.pkl",
                    help="Pickled model file (model.pkl or linearRegression.sav)")
    ap.add_argument("--out",    default="inference.csv",
                    help="Output inference CSV")
    args = ap.parse_args()

    # Load model
    try:
        with open(args.model, "rb") as f:
            payload = pickle.load(f)
    except FileNotFoundError:
        # Fall back to linearRegression.sav
        with open("linearRegression.sav", "rb") as f:
            payload = pickle.load(f)

    model          = payload["model"]
    use_engineered = payload.get("use_engineered", False)
    feat_names     = payload.get("feature_names", [])

    # Safety check: numVias must NOT be among features
    if "numVias" in feat_names:
        sys.exit("ERROR: numVias appears in model feature list — "
                 "this would be data leakage. Retrain without numVias.")

    # Read all input CSVs
    all_rows = []
    for path in args.input:
        with open(path, "r") as f:
            for row in csv.DictReader(f):
                all_rows.append(row)

    print(f"[ml_inference] {len(all_rows)} nets from {len(args.input)} file(s)")

    X = engineer_features(all_rows, use_engineered=use_engineered)
    y_pred = model.predict(X)

    # Clamp predictions to non-negative integers
    y_pred_int = [max(0, round(float(v))) for v in y_pred]

    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["netName", "numVias"])
        writer.writeheader()
        for row, pred in zip(all_rows, y_pred_int):
            writer.writerow({"netName": row["netName"], "numVias": pred})

    print(f"[ml_inference] Wrote {len(all_rows)} predictions -> {args.out}")


if __name__ == "__main__":
    main()
