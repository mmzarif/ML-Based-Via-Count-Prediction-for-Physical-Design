#!/usr/bin/env bash
# patch_and_run.sh
# ----------------
# Runs ONE (util%, clock_period_ns) Aprisa case.
# Called by run_parallel.sh — you can also call it directly to debug one case.
#
# Usage:
#   bash patch_and_run.sh <util_pct> <cp_ns> <rundir_src> <design_out_dir>
#
# Example:
#   bash patch_and_run.sh 60 1.30 ~/mp_2/mp_2/rundir ~/mp_2/mp_2/design

set -euo pipefail

UTIL_PCT="$1"       # e.g. 60
CP_NS="$2"          # e.g. 1.30
RUNDIR_SRC="$3"     # the original rundir (has run_aprisa.sh, aes_cipher_top.sdc, scripts/)
DESIGN_DIR="$4"     # where to deposit the final DEFs

# --- Derived tokens ---
XX=$(printf "%02d" "${UTIL_PCT}")
YYYY=$(python3 -c "print(f'{float(\"${CP_NS}\")*1000:.0f}')")
UTIL_FRAC=$(python3 -c "print(f'{int(\"${UTIL_PCT}\")/100:.2f}')")
HALF_CP=$(python3 -c "print(f'{float(\"${CP_NS}\")/2:.4f}')")

CTS_OUT="${DESIGN_DIR}/aes_cipher_top_${XX}_${YYYY}_cts.def"
RTE_OUT="${DESIGN_DIR}/aes_cipher_top_${XX}_${YYYY}_routed.def"
LOG="${DESIGN_DIR}/aprisa_${XX}_${YYYY}.log"

# --- Skip if already done ---
if [[ -f "${CTS_OUT}" && -f "${RTE_OUT}" ]]; then
    echo "[${XX}_${YYYY}] SKIP — DEFs already exist."
    exit 0
fi

echo "[${XX}_${YYYY}] START  util=${UTIL_PCT}%  cp=${CP_NS}ns"

# --- Fresh isolated working directory in /tmp ---
# Each case gets its own full copy of rundir so nothing collides.
WORK=$(mktemp -d "/tmp/aprisa_${XX}_${YYYY}_XXXX")
cp -r "${RUNDIR_SRC}/." "${WORK}/"
cd "${WORK}"

# --- Patch scripts/proj_variables.tcl ---
sed -i "s/-utilization [0-9.]*/-utilization ${UTIL_FRAC}/g" scripts/proj_variables.tcl

# --- Patch aes_cipher_top.sdc ---
sed -i "s/-period [0-9.]*/-period ${CP_NS}/g"                         aes_cipher_top.sdc
sed -i "s/-waveform {[0-9.]* [0-9.]*}/-waveform {0.0 ${HALF_CP}}/g"  aes_cipher_top.sdc

# --- Log the patched lines so you can verify ---
{
    echo "=== CASE: util=${UTIL_PCT}%  cp=${CP_NS}ns ==="
    echo ""
    echo "--- scripts/proj_variables.tcl INIT_FP_OPTIONS ---"
    grep "INIT_FP_OPTIONS" scripts/proj_variables.tcl
    echo ""
    echo "--- aes_cipher_top.sdc create_clock ---"
    grep "create_clock" aes_cipher_top.sdc
    echo ""
    echo "=== Aprisa output ==="
} > "${LOG}"

# --- Run Aprisa ---
# Replicate run_aprisa.sh exactly, but always inside our isolated WORK dir.
module load aprisa-2025.1
AP="AP"
mkdir -p default

${AP} -8  scripts/init.tcl    -log init.log    -sum_log init.sum    -wd ./default >> "${LOG}" 2>&1
${AP} -8  scripts/place.tcl   -log place.log   -sum_log place.sum   -wd ./default >> "${LOG}" 2>&1
${AP} -8  scripts/cts.tcl     -log cts.log     -sum_log cts.sum     -wd ./default >> "${LOG}" 2>&1
${AP} -8  scripts/cts_opt.tcl -log cts_opt.log -sum_log cts_opt.sum -wd ./default >> "${LOG}" 2>&1
${AP} -16 scripts/route.tcl   -log route.log   -sum_log route.sum   -wd ./default >> "${LOG}" 2>&1
${AP} -8  scripts/export.tcl  -log export.log  -sum_log export.sum  -wd ./default >> "${LOG}" 2>&1

# --- Locate output DEFs ---
# proj_variables.tcl defines:
#   set DEF_OUTPUT_CTS   $OUTPUT/aes_cipher_top_cts.def
#   set DEF_OUTPUT_ROUTE $OUTPUT/aes_cipher_top_routed.def
# $OUTPUT = ./default/output/
CTS_SRC="${WORK}/default/output/aes_cipher_top_cts.def"
RTE_SRC="${WORK}/default/output/aes_cipher_top_routed.def"

if [[ ! -f "${CTS_SRC}" ]]; then
    echo "[${XX}_${YYYY}] ERROR — CTS DEF not found at ${CTS_SRC}. See ${LOG}"
    exit 1
fi
if [[ ! -f "${RTE_SRC}" ]]; then
    echo "[${XX}_${YYYY}] ERROR — Routed DEF not found at ${RTE_SRC}. See ${LOG}"
    exit 1
fi

cp "${CTS_SRC}" "${CTS_OUT}"
cp "${RTE_SRC}" "${RTE_OUT}"

echo "[${XX}_${YYYY}] DONE -> $(basename ${CTS_OUT})  $(basename ${RTE_OUT})"

# --- Clean up /tmp ---
cd /tmp && rm -rf "${WORK}"
