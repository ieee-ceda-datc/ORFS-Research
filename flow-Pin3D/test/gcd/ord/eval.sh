#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="gcd"
export DESIGN_NICKNAME="gcd" 
export DESIGN_NAME="gcd" 
export FLOW_VARIANT="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final


