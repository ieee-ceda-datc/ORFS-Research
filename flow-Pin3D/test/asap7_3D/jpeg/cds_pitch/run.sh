#!/bin/bash
source env.sh

export DESIGN_DIMENSION="3D"
export DESIGN_NICKNAME="gcd"
export USE_FLOW="cadence"
export FLOW_VARIANT="cadence_${hbPitch}"
# make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk clean_all
# make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config.mk clean_all
# make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-synth
# make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-preplace
# if [ $CDS_USE_OPENROADDOCKER -eq 1 ]; then
#     make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-docker-partition
# else
#     make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config2d.mk cds-tier-partition
# fi
mkdir -p results/asap7_3D/${DESIGN_NICKNAME}/${FLOW_VARIANT}
cp -r results/asap7/${DESIGN_NICKNAME}/${USE_FLOW} results/asap7_3D/${DESIGN_NICKNAME}/${FLOW_VARIANT} 
export TECH_LEF="platforms/asap7_3D/lef/cds_pitch_variant/asap7_tech_1x_9M8M.${hbPitch}.lef"
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config.mk ord-pre
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config.mk cds-3d-pdn
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-init
iteration=1
for ((i=1;i<=iteration;i++))
do
    echo "Iteration: $i"
    make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk cds-place-upper
    make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-place-bottom
done
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config.mk cds-place-finish
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-legalize-bottom
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config_bottom_cover.mk cds-legalize-upper
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config_upper_cover.mk cds-cts 
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config.mk cds-route 
make DESIGN_CONFIG=designs/asap7_3D/${DESIGN_NICKNAME}/config.mk cds-final 