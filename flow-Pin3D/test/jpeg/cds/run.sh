#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="jpeg"
export DESIGN_NAME="jpeg_encoder" 
export DESIGN_NICKNAME="jpeg"
export FLOW_VARIANT="cadence"
# export OPEN_GUI=1
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk clean_all
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-synth
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-preplace
if [ $CDS_USE_OPENROADDOCKER -eq 1 ]; then
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-docker-partition
else
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk cds-tier-partition
fi
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-pre
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-3d-pdn
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-place-init
iteration=1
for ((i=1;i<=iteration;i++))
do
    echo "Iteration: $i"
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk cds-place-upper
    make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-bottom
done
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-place-finish
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-legalize-bottom
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk cds-legalize-upper
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-cts 
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-cts-eval 
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-route 
