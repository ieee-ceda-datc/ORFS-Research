#!/bin/bash
source env.sh
export NUM_CORES=40
export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="cadence_2"
export USE_FLOW="cadence"

# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-3d-pdn
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-init
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk cds-place-upper
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-bottom
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-place-finish
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-legalize-bottom
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk cds-legalize-upper
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-cts 
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-route 
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final 