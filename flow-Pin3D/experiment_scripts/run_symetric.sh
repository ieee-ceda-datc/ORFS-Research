export DISPLAY=:1
ssh -Y zhiyuzheng@hnode35 "
    cd ~/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D || exit
    source env.sh
    export NUM_CORES=20
    export DESIGN_DIMENSION="3D"
    export DESIGN_NICKNAME="aes" 
    export FLOW_VARIANT="cadence_hbPitch_V6_track"
    export USE_FLOW="cadence"
    export TECH_LEF=platforms/asap7_3D/lef/cds_pitch_variant/asap7_tech_1x_6M7M.hbPitch_V6.lef
    make DESIGN_CONFIG=designs/asap7_3D/\${DESIGN_NICKNAME}/config.mk cds-route 
    make DESIGN_CONFIG=designs/asap7_3D/\${DESIGN_NICKNAME}/config.mk cds-final 
"