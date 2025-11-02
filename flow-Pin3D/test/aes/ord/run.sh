#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DEF_VERSION="aes"
export DESIGN_NICKNAME="aes"
export DESIGN_NAME="aes_cipher_top"
export FLOW_VARIANT="openroad"
# export OPEN_GUI=0
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk clean_all
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-synth
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-preplace
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config2d.mk ord-tier-partition
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-pre
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-3d-pdn
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-place-init
iteration=1
for ((i=1;i<=iteration;i++)); do
  echo "Iteration: $i"
  make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-place-upper
  make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk  ord-place-bottom
done
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-pre-opt
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk ord-legalize-bottom
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk ord-legalize-upper
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config_upper_cover.mk ord-cts
# make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-cts-eval
make DESIGN_CONFIG=designs/nangate45_3D/${DESIGN_NICKNAME}/config.mk ord-route
