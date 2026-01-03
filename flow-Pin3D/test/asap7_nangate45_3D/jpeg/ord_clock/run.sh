#!/bin/bash
source env.sh


export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="jpeg"
export USE_FLOW="openroad"
export FLOW_VARIANT="openroad_clock_${CLK_PERIOD}"
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config2d.mk clean_all
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config.mk clean_all
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-synth
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-preplace
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-tier-partition
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-pre
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-3d-pdn
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk ord-place-init
iteration=1
for ((i=1;i<=iteration;i++)); do
  echo "Iteration: $i"
  make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-place-upper
  make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk  ord-place-bottom
done
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-pre-opt
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk ord-legalize-bottom
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-legalize-upper
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk ord-cts
make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-route
ssh zhiyuzheng@hnode35 "
    cd ~/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D || exit
    source env.sh
    export DESIGN_DIMENSION=\"${DESIGN_DIMENSION}\"
    export DESIGN_NICKNAME=\"${DESIGN_NICKNAME}\"
    export USE_FLOW=\"${USE_FLOW}\"
    export FLOW_VARIANT=\"${FLOW_VARIANT}\"
    export CLK_PERIOD=\"${CLK_PERIOD}\"
    make DESIGN_CONFIG=designs/asap7_nangate45_3D/\${DESIGN_NICKNAME}/config.mk cds-final 
"
