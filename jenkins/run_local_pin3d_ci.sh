#!/usr/bin/env bash
set -euo pipefail

# Local emulation of Jenkins Pin3D CI stages.
# Run from repository root:
#   bash jenkins/run_local_pin3d_ci.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

ORFS_EXPECTED_BRANCH="${ORFS_EXPECTED_BRANCH:-maple/pin3Dflow}"
OPENROAD_RESEARCH_URL="${OPENROAD_RESEARCH_URL:-https://github.com/ieee-ceda-datc/OpenROAD-Research.git}"
OPENROAD_RESEARCH_BRANCH="${OPENROAD_RESEARCH_BRANCH:-arxiv}"
PIN3D_DIR="${PIN3D_DIR:-flow-Pin3D}"
PIN3D_CMD="${PIN3D_CMD:-python3 run_experiments.py --run-CI}"
METRICS_SUMMARY="${METRICS_SUMMARY:-ci_metrics_summary.csv}"
METRICS_GOLDEN="${METRICS_GOLDEN:-test/ci_metrics_golden.csv}"
FAIL_ON_REGRESSION="${FAIL_ON_REGRESSION:-1}"
CHECKOUT_OPENROAD="${CHECKOUT_OPENROAD:-0}"
CLEAN_OPENROAD_DIR="${CLEAN_OPENROAD_DIR:-1}"

echo "[Config] ROOT_DIR=${ROOT_DIR}"
echo "[Config] ORFS_EXPECTED_BRANCH=${ORFS_EXPECTED_BRANCH}"
echo "[Config] OPENROAD_RESEARCH_BRANCH=${OPENROAD_RESEARCH_BRANCH}"
echo "[Config] PIN3D_DIR=${PIN3D_DIR}"
echo "[Config] PIN3D_CMD=${PIN3D_CMD}"

if ! command -v git >/dev/null 2>&1; then
  echo "[Error] git not found in PATH." >&2
  exit 1
fi
if ! command -v python3 >/dev/null 2>&1; then
  echo "[Error] python3 not found in PATH." >&2
  exit 1
fi

CURRENT_BRANCH="$(git rev-parse --abbrev-ref HEAD || true)"
if [[ -n "${CURRENT_BRANCH}" && "${CURRENT_BRANCH}" != "${ORFS_EXPECTED_BRANCH}" ]]; then
  echo "[Warn] current branch is ${CURRENT_BRANCH}, expected ${ORFS_EXPECTED_BRANCH}."
fi
echo "[ORFS-Research] HEAD=$(git rev-parse --short HEAD)"

if [[ "${CHECKOUT_OPENROAD}" == "1" ]]; then
  if [[ "${CLEAN_OPENROAD_DIR}" == "1" ]]; then
    rm -rf tools/OpenROAD
  fi
  echo "[OpenROAD-Research] cloning ${OPENROAD_RESEARCH_BRANCH} into tools/OpenROAD"
  git clone --branch "${OPENROAD_RESEARCH_BRANCH}" --recursive "${OPENROAD_RESEARCH_URL}" tools/OpenROAD
else
  echo "[OpenROAD-Research] skip checkout (CHECKOUT_OPENROAD=${CHECKOUT_OPENROAD})"
fi

if [[ ! -d "${PIN3D_DIR}" ]]; then
  echo "[Error] Pin3D directory not found: ${PIN3D_DIR}" >&2
  exit 1
fi

pushd "${PIN3D_DIR}" >/dev/null
echo "[Pin3D] PWD=${PWD}"
echo "[Pin3D] CMD=${PIN3D_CMD}"
eval "${PIN3D_CMD}"
popd >/dev/null

SUMMARY_PATH="${PIN3D_DIR}/${METRICS_SUMMARY}"
if [[ ! -f "${SUMMARY_PATH}" ]]; then
  echo "[Error] Metrics summary not found: ${SUMMARY_PATH}" >&2
  exit 1
fi

echo "======= Pin3D Local CI Metrics Summary ======="
if command -v column >/dev/null 2>&1; then
  column -t -s, "${SUMMARY_PATH}"
else
  cat "${SUMMARY_PATH}"
fi

GOLDEN_PATH="${PIN3D_DIR}/${METRICS_GOLDEN}"
COMPARE_SCRIPT="${PIN3D_DIR}/test/metrics_comparison.py"
if [[ ! -f "${GOLDEN_PATH}" ]]; then
  echo "[Compare] Golden not found: ${GOLDEN_PATH}. Skip comparison."
  exit 0
fi
if [[ ! -f "${COMPARE_SCRIPT}" ]]; then
  echo "[Error] Compare script not found: ${COMPARE_SCRIPT}" >&2
  exit 1
fi

set +e
(
  cd "${PIN3D_DIR}" && \
  python3 test/metrics_comparison.py \
    --summary "${METRICS_SUMMARY}" \
    --golden "${METRICS_GOLDEN}" \
    --keys "tech,case" \
    2>&1 | tee ci_metrics_compare.log
)
RC=$?
set -e

if [[ ${RC} -ne 0 ]]; then
  if [[ "${FAIL_ON_REGRESSION}" == "1" ]]; then
    echo "[Error] Metrics comparison failed (exit=${RC}). See ${PIN3D_DIR}/ci_metrics_compare.log" >&2
    exit ${RC}
  fi
  echo "[Warn] Metrics comparison failed (exit=${RC}) but FAIL_ON_REGRESSION=${FAIL_ON_REGRESSION}."
else
  echo "[Compare] Metrics comparison passed."
fi
