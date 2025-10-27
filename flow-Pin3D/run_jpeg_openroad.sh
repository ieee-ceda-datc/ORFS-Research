#!/bin/bash
source ./env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="jpeg_encoder"
export DESIGN_NICKNAME="jpeg" 
export DESIGN_NAME="jpeg_encoder" 

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk do-pin-3d-flow-2dpre
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-pin-3d-flow-pre
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_both_shrink.mk do-pin-3d-flow-place-init
iteration=1
for ((i=1;i<=iteration;i++))
do
    echo "Iteration: $i"
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_shrink.mk do-pin-3d-flow-place-upper
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_shrink.mk do-pin-3d-flow-place-bottom
done
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_shrink.mk do-autoflow 
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-cts
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-cts_eval 
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-route
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-finish
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk do-hotspot
