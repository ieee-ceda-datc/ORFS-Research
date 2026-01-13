#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="jpeg" 
export USE_FLOW="openroad"
export FLOW_VARIANT="openroad"

make DESIGN_CONFIG=designs/asap7_nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final
