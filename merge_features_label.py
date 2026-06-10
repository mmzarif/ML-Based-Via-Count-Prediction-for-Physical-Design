"""
merge_features_label.py
------------------------
Merge training.features.csv with training.label.csv on netName.
Output: training.csv with columns
  netName, util, cp, bboxArea, bboxAr, numPins, numVias

Usage:
  python3 merge_features_label.py \
      --features training.features.csv \
      --label    training.label.csv \
      --out      training.csv
"""

import argparse
import csv
import sys


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--features", default="training.features.csv")
    ap.add_argument("--label",    default="training.label.csv")
    ap.add_argument("--out",      default="training.csv")
    args = ap.parse_args()

    # Load labels into dict
    labels = {}
    with open(args.label, "r") as f:
        for row in csv.DictReader(f):
            labels[row["netName"]] = int(row["numVias"])

    kept   = 0
    missed = 0
    out_rows = []

    with open(args.features, "r") as f:
        for row in csv.DictReader(f):
            name = row["netName"]
            if name in labels:
                row["numVias"] = labels[name]
                out_rows.append(row)
                kept += 1
            else:
                missed += 1

    fieldnames = ["netName", "util", "cp", "bboxArea", "bboxAr", "numPins", "numVias"]
    with open(args.out, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"[merge] kept={kept}, missed={missed} -> {args.out}", flush=True)


if __name__ == "__main__":
    main()
