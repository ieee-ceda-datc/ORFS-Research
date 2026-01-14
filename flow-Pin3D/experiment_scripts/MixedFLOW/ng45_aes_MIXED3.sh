#!/bin/bash
source env.sh
export NUM_CORES=40
export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="aes" 
export FLOW_VARIANT="mixed3"
export USE_FLOW="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-3d-pdn

ssh zhiyuzheng@hnode35 "
    cd ~/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D || exit
    source env.sh
    export NUM_CORES=40
    export DESIGN_DIMENSION="3D"
    export DESIGN_NICKNAME="aes" 
    export FLOW_VARIANT="mixed3"
    export USE_FLOW="openroad"
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-init
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config_bottom_cover.mk cds-place-upper
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-bottom
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config.mk cds-place-finish
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config_upper_cover.mk cds-legalize-bottom
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config_bottom_cover.mk cds-legalize-upper
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config_upper_cover.mk cds-cts 
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config.mk cds-route 
    make DESIGN_CONFIG=designs/nangate45_3D/\${DESIGN_NICKNAME}/config.mk cds-final 
"