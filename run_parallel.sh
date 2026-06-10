#!/usr/bin/env bash
# run_parallel.sh
# ---------------
# Dispatches all (util, cp) Aprisa runs in parallel.
#
# Run from inside rundir:
#   cd ~/mp_2/mp_2/rundir
#   bash run_parallel.sh

set -euo pipefail

# rundir = wherever this script lives (and where run_aprisa.sh, scripts/, sdc live)
RUNDIR_SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESIGN_DIR="${RUNDIR_SRC}/../design"

mkdir -p "${DESIGN_DIR}"

# -----------------------------------------------------------------------
# MAX_JOBS: how many Aprisa runs at once.
# Each run uses -8 or -16 threads internally, so be conservative.
# Check node load first:  uptime
# Safe default on ieng6:  4
# -----------------------------------------------------------------------
MAX_JOBS=4

# -----------------------------------------------------------------------
# Cases to generate.
# The 1.60ns cases are already provided — they are commented out.
# We generate the three missing clock periods across all five utilizations.
# -----------------------------------------------------------------------
CASES=(
    "60  1.30"
    "65  1.30"
    "70  1.30"
    "75  1.30"
    "80  1.30"

    "60  1.40"
    "65  1.40"
    "70  1.40"
    "75  1.40"
    "80  1.40"

    "60  1.50"
    "65  1.50"
    "70  1.50"
    "75  1.50"
    "80  1.50"
)

# -----------------------------------------------------------------------
# Job pool
# -----------------------------------------------------------------------
PIDS=()
FAILED_CASES=()

wait_for_slot() {
    while (( ${#PIDS[@]} >= MAX_JOBS )); do
        NEW_PIDS=()
        for pid in "${PIDS[@]}"; do
            if kill -0 "${pid}" 2>/dev/null; then
                NEW_PIDS+=("${pid}")
            else
                if ! wait "${pid}"; then
                    FAILED_CASES+=("${pid}")
                fi
            fi
        done
        PIDS=("${NEW_PIDS[@]+"${NEW_PIDS[@]}"}")
        (( ${#PIDS[@]} >= MAX_JOBS )) && sleep 10
    done
}

echo "=============================================="
echo " Launching ${#CASES[@]} cases  (MAX_JOBS=${MAX_JOBS})"
echo " RUNDIR_SRC : ${RUNDIR_SRC}"
echo " DESIGN_DIR : ${DESIGN_DIR}"
echo "=============================================="

for CASE in "${CASES[@]}"; do
    read -r UTIL CP <<< "${CASE}"
    wait_for_slot

    echo "[dispatch] util=${UTIL}%  cp=${CP}ns"
    bash "${RUNDIR_SRC}/patch_and_run.sh" \
        "${UTIL}" "${CP}" "${RUNDIR_SRC}" "${DESIGN_DIR}" &
    PIDS+=($!)
done

echo ""
echo "All cases dispatched — waiting for remaining jobs..."
for pid in "${PIDS[@]+"${PIDS[@]}"}"; do
    if ! wait "${pid}"; then
        FAILED_CASES+=("${pid}")
    fi
done

# -----------------------------------------------------------------------
# Summary
# -----------------------------------------------------------------------
echo ""
echo "=============================================="
echo " Run complete."
echo ""
echo " DEFs in ${DESIGN_DIR}:"
ls "${DESIGN_DIR}"/*.def 2>/dev/null | sed 's|.*/||' | sort || echo "  (none)"

if (( ${#FAILED_CASES[@]} > 0 )); then
    echo ""
    echo " FAILED PIDs: ${FAILED_CASES[*]}"
    echo " Check logs:  ls ${DESIGN_DIR}/aprisa_*.log"
    exit 1
fi
echo "=============================================="
