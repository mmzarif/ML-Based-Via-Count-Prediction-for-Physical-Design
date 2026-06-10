"""
ml_rmse.py
----------
Compute RMSE between ground-truth (training.csv / test_*.csv) and
the inference results (inference.csv).

Metric 2 from the spec:
  RMSE = RMSE_1 (training) + RMSE_2 (open testing)

Usage
-----
  # Full Metric-2 evaluation
  python3 ml_rmse.py \
      --truth  training.csv test_65_1600.csv test_75_1600.csv \
      --infer  inference.csv \
      --report

  # Quick single-file check
  python3 ml_rmse.py --truth training.csv --infer inference.csv
"""

import argparse
import csv
import math
import sys


def load_csv_as_dict(path, key_col, val_col):
    """Load CSV, return dict key -> float(val)."""
    d = {}
    with open(path, "r") as f:
        for row in csv.DictReader(f):
            d[row[key_col]] = float(row[val_col])
    return d


def rmse_from_dicts(truth_dict, pred_dict):
    """Compute RMSE over keys present in both dicts."""
    common = set(truth_dict) & set(pred_dict)
    if not common:
        return float("nan"), 0
    sq_sum = sum((truth_dict[k] - pred_dict[k]) ** 2 for k in common)
    return math.sqrt(sq_sum / len(common)), len(common)


def main():
    ap = argparse.ArgumentParser(description="Compute RMSE for via-count predictions")
    ap.add_argument("--truth",  nargs="+", required=True,
                    help="Ground-truth CSV(s) with netName,numVias columns")
    ap.add_argument("--infer",  default="inference.csv",
                    help="Inference CSV with netName,numVias columns")
    ap.add_argument("--report", action="store_true",
                    help="Print per-file breakdown")
    args = ap.parse_args()

    # Load predictions
    pred_dict = load_csv_as_dict(args.infer, "netName", "numVias")

    all_sq_errors = []
    rmse_per_file = []

    for path in args.truth:
        truth_dict = load_csv_as_dict(path, "netName", "numVias")
        r, n = rmse_from_dicts(truth_dict, pred_dict)
        rmse_per_file.append((path, r, n))

        # Accumulate squared errors
        common = set(truth_dict) & set(pred_dict)
        for k in common:
            all_sq_errors.append((truth_dict[k] - pred_dict[k]) ** 2)

    # Per-file output
    if args.report or len(args.truth) > 1:
        print(f"\n{'File':<45} {'RMSE':>10} {'N':>8}")
        print("-" * 66)
        for path, r, n in rmse_per_file:
            print(f"{path:<45} {r:>10.4f} {n:>8}")

    # Overall RMSE
    if all_sq_errors:
        overall = math.sqrt(sum(all_sq_errors) / len(all_sq_errors))
        print(f"\nOverall RMSE ({len(all_sq_errors)} nets): {overall:.4f}")
    else:
        print("No matching nets found between truth and predictions.")

    # Metric 2 convenience: sum of per-file RMSE values
    if len(rmse_per_file) >= 2:
        metric2 = sum(r for _, r, _ in rmse_per_file)
        print(f"Metric 2 (sum of per-file RMSE): {metric2:.4f}")


if __name__ == "__main__":
    main()
