#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="jpeg"
export DESIGN_NICKNAME="jpeg" 
export DESIGN_NAME="jpeg_encoder" 
export FLOW_VARIANT="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final
