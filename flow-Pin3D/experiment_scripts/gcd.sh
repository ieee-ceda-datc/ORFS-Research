#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLOW_ROOT="${SCRIPT_DIR}"
while [[ "${FLOW_ROOT}" != "/" && ! -f "${FLOW_ROOT}/env.sh" ]]; do
  FLOW_ROOT="$(dirname "${FLOW_ROOT}")"
done
if [[ ! -f "${FLOW_ROOT}/env.sh" ]]; then
  echo "ERROR: env.sh not found for ${SCRIPT_DIR}" >&2
  exit 1
fi
source "${FLOW_ROOT}/env.sh"

export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="gcd"
export FLOW_VARIANT="openroad"
export USE_FLOW="openroad"
export VISUALIZE_FINAL=1
export ENABLEMENTS=nangate45_3D
make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config.mk ord-synth
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config.mk ord-3d-pdn
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config.mk ord-place-init
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-place-upper
# cp -r results/${ENABLEMENTS}/gcd/openroad/gcd_3D.tmp.v results/${ENABLEMENTS}/gcd/openroad/gcd_3D.tmp.upper.v
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config_upper_cover.mk  ord-place-bottom
# cp -r results/${ENABLEMENTS}/gcd/openroad/gcd_3D.tmp.v results/${ENABLEMENTS}/gcd/openroad/gcd_3D.tmp.bottom.v
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config.mk ord-pre-opt
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config_upper_cover.mk ord-legalize-bottom
# cp -r results/${ENABLEMENTS}/gcd/openroad/gcd_3D.tmp.v results/${ENABLEMENTS}/gcd/openroad/gcd_3D.lg.bottom.v
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-legalize-upper
# cp -r results/${ENABLEMENTS}/gcd/openroad/gcd_3D.tmp.v results/${ENABLEMENTS}/gcd/openroad/gcd_3D.lg.upper.v
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-cts
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config.mk ord-route
# make DESIGN_CONFIG=designs/${ENABLEMENTS}/${DESIGN_NICKNAME}/config.mk cds-final