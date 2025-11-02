#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="aes"
export DESIGN_NICKNAME="aes"
export DESIGN_NAME="aes_cipher_top"
export FLOW_VARIANT="openroad"

make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk cds-final


