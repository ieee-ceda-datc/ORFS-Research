#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="aes"
export USE_FLOW="cadence"
export FLOW_VARIANT="cadence"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final
