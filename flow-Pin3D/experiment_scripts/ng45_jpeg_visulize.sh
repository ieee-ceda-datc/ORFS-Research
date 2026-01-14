#!/bin/bash
source env.sh
export NUM_CORES=40
export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="cadence_2"
export USE_FLOW="cadence"

export VISUALIZE_FINAL=1
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-route 
