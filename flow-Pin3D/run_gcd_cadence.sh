#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="gcd"
export DESIGN_NAME="gcd" 
export DESIGN_NICKNAME="gcd"
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cadence_synth
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cadence_preplace
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk do-pin-3d-flow-tier-partition
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk do-docker-partition
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-3d-pdn
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_both_shrink.mk do-pin-3d-flow-place-init
iteration=1
for ((i=1;i<=iteration;i++))
do
    echo "Iteration: $i"
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_shrink.mk do-pin-3d-flow-place-upper
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_shrink.mk do-pin-3d-flow-place-bottom
done
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-pin-3d-flow-place-finish
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-cts_eval 
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-route 
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-final
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-hotspot
