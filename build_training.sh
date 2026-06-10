#!/usr/bin/env bash
# build_training.sh
# -----------------
# Extracts features + labels from all available DEFs and trains the ML model.
# Run from rundir.
#
# Usage:
#   bash build_training.sh

set -euo pipefail

RUNDIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN_DIR="${RUNDIR}/../design"

module load python-3.6.2 2>/dev/null || true

# -----------------------------------------------------------------------
# Find all available (util, cp) pairs by scanning existing routed DEFs.
# Naming convention: aes_cipher_top_XX_YYYY_routed.def
# -----------------------------------------------------------------------
echo "=== Scanning design dir for available DEFs ==="
TRAIN_CSVS=()

for ROUTED_DEF in "${DESIGN_DIR}"/aes_cipher_top_*_routed.def; do
    BASENAME=$(basename "${ROUTED_DEF}")

    # Extract XX and YYYY from filename
    XX=$(echo   "${BASENAME}" | sed 's/aes_cipher_top_\([0-9]*\)_\([0-9]*\)_routed.def/\1/')
    YYYY=$(echo "${BASENAME}" | sed 's/aes_cipher_top_\([0-9]*\)_\([0-9]*\)_routed.def/\2/')

    CTS_DEF="${DESIGN_DIR}/aes_cipher_top_${XX}_${YYYY}_cts.def"

    # Skip if the matching CTS DEF doesn't exist
    if [[ ! -f "${CTS_DEF}" ]]; then
        echo "  [SKIP] No CTS DEF for ${XX}_${YYYY}"
        continue
    fi

    UTIL_FRAC=$(python3 -c "print(int('${XX}')/100)")
    CP_NS=$(python3 -c "print(int('${YYYY}')/1000)")

    FEAT_CSV="${RUNDIR}/features_${XX}_${YYYY}.csv"
    LABEL_CSV="${RUNDIR}/label_${XX}_${YYYY}.csv"
    MERGED_CSV="${RUNDIR}/merged_${XX}_${YYYY}.csv"

    echo ""
    echo "--- util=${XX}%  cp=${CP_NS}ns ---"

    python3 "${RUNDIR}/generate_features.py" \
        --def  "${CTS_DEF}" \
        --util "${UTIL_FRAC}" \
        --cp   "${CP_NS}" \
        --out  "${FEAT_CSV}"

    python3 "${RUNDIR}/generate_label.py" \
        --def  "${ROUTED_DEF}" \
        --out  "${LABEL_CSV}"

    python3 "${RUNDIR}/merge_features_label.py" \
        --features "${FEAT_CSV}" \
        --label    "${LABEL_CSV}" \
        --out      "${MERGED_CSV}"

    TRAIN_CSVS+=("${MERGED_CSV}")
done

if [[ ${#TRAIN_CSVS[@]} -eq 0 ]]; then
    echo "ERROR: No DEF pairs found in ${DESIGN_DIR}"
    exit 1
fi

echo ""
echo "=== Combining ${#TRAIN_CSVS[@]} datasets into training.csv ==="
python3 - "${TRAIN_CSVS[@]}" << 'PYEOF'
import csv, sys

files = sys.argv[1:]
fieldnames = ["netName","util","cp","bboxArea","bboxAr","numPins","numVias"]
rows = []
for f in files:
    with open(f) as fh:
        rows += list(csv.DictReader(fh))

with open("training.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)

print(f"  {len(rows)} total rows from {len(files)} files -> training.csv")
PYEOF

echo ""
echo "=== Training ML model ==="
python3 "${RUNDIR}/ml_train.py" \
    --train training.csv \
    --model model.pkl \
    --ablation

echo ""
echo "=== Done. ==="
echo "  training.csv and model.pkl are in ${RUNDIR}"
