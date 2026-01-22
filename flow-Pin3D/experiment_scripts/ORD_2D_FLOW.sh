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
export NUM_CORES=16

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-2d_flow

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="aes" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-2d_flow

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="ibex" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-2d_flow

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk ord-2d_flow

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="aes" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk ord-2d_flow

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="ibex" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk ord-2d_flow

ssh -Y zhiyuzheng@hnode27 /bin/bash << 'EOF'
cd ~/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D
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
export NUM_CORES=16

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-final & 

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="aes" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-final & 

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="ibex" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-final & 

export PROCESS=7
export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"
export TECH_LEF=../flow/platforms/asap7/lef/asap7_tech_1x_201209.lef
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-final  &

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="aes" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"
export TECH_LEF=../flow/platforms/asap7/lef/asap7_tech_1x_201209.lef
export VISUALIZE_FINAL=1
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-final 

export DESIGN_DIMENSION="2D"
export DESIGN_NICKNAME="ibex" 
export FLOW_VARIANT="orfs"
export USE_FLOW="openroad"
export TECH_LEF=../flow/platforms/asap7/lef/asap7_tech_1x_201209.lef
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-final & 

wait
EOF
