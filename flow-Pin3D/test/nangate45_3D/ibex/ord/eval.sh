#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="ibex"
export USE_FLOW="openroad"
export FLOW_VARIANT="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final
