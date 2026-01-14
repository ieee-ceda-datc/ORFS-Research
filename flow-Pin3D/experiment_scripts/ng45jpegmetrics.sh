#!/bin/bash
source env.sh
export NUM_CORES=40
export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="jpeg" 
export FLOW_VARIANT="openroad"
export USE_FLOW="openroad"


make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-final
