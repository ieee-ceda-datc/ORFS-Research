#!/usr/bin/env bash
# run_all_parallel_logs.sh - parallel version, write output to logs

echo "Starting all process variants in parallel..."

# Ensure work directory exists
mkdir -p work

# # Variant 1: asap7_nangate45_2A6M10M
# (
#   echo "[asap7_nangate45_2A6M10M] Starting"
#   export FLOW_VARIANT="asap7_nangate45_2A6M10M"
#   source env.sh && ./01_gen_patterns.sh > work/asap7_nangate45_2A6M10M/step1.log 2>&1
#   ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='asap7_nangate45_2A6M10M' && source env.sh && ./02_cds_extract.sh" > work/asap7_nangate45_2A6M10M/step2.log 2>&1
#   export FLOW_VARIANT="asap7_nangate45_2A6M10M"
#   source env.sh && ./03_gen_rules.sh > work/asap7_nangate45_2A6M10M/step3.log 2>&1
#   echo "[asap7_nangate45_2A6M10M] Done"
# ) &

# # Variant 2: asap7_tech_1x_2A6M7M
# (
#   echo "[asap7_tech_1x_2A6M7M] Starting"
#   export FLOW_VARIANT="asap7_tech_1x_2A6M7M"
#   source env.sh && ./01_gen_patterns.sh > work/asap7_tech_1x_2A6M7M/step1.log 2>&1
#   ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='asap7_tech_1x_2A6M7M' && source env.sh && ./02_cds_extract.sh" > work/asap7_tech_1x_2A6M7M/step2.log 2>&1
#   export FLOW_VARIANT="asap7_tech_1x_2A6M7M"
#   source env.sh && ./03_gen_rules.sh > work/asap7_tech_1x_2A6M7M/step3.log 2>&1
#   echo "[asap7_tech_1x_2A6M7M] Done"
# ) &

# # Variant 3: NangateOpenCellLibrary.tech
# (
#   echo "[NangateOpenCellLibrary.tech] Starting"
#   export FLOW_VARIANT="NangateOpenCellLibrary.tech"
#   source env.sh && ./01_gen_patterns.sh > work/NangateOpenCellLibrary.tech/step1.log 2>&1
#   ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='NangateOpenCellLibrary.tech' && source env.sh && ./02_cds_extract.sh" > work/NangateOpenCellLibrary.tech/step2.log 2>&1
#   export FLOW_VARIANT="NangateOpenCellLibrary.tech"
#   source env.sh && ./03_gen_rules.sh > work/NangateOpenCellLibrary.tech/step3.log 2>&1
#   echo "[NangateOpenCellLibrary.tech] Done"
# ) &

# # Variant 4: asap7_nangate45_6M10M
# (
#   echo "[asap7_nangate45_6M10M] Starting"
#   export FLOW_VARIANT="asap7_nangate45_6M10M"
#   source env.sh && ./01_gen_patterns.sh > work/asap7_nangate45_6M10M/step1.log 2>&1
#   ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='asap7_nangate45_6M10M' && source env.sh && ./02_cds_extract.sh" > work/asap7_nangate45_6M10M/step2.log 2>&1
#   export FLOW_VARIANT="asap7_nangate45_6M10M"
#   source env.sh && ./03_gen_rules.sh > work/asap7_nangate45_6M10M/step3.log 2>&1
#   echo "[asap7_nangate45_6M10M] Done"
# ) &

# # Variant 5: asap7_tech_1x_6M7M
# (
#   echo "[asap7_tech_1x_6M7M] Starting"
#   export FLOW_VARIANT="asap7_tech_1x_6M7M"
#   source env.sh && ./01_gen_patterns.sh > work/asap7_tech_1x_6M7M/step1.log 2>&1
#   ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='asap7_tech_1x_6M7M' && source env.sh && ./02_cds_extract.sh" > work/asap7_tech_1x_6M7M/step2.log 2>&1
#   export FLOW_VARIANT="asap7_tech_1x_6M7M"
#   source env.sh && ./03_gen_rules.sh > work/asap7_tech_1x_6M7M/step3.log 2>&1
#   echo "[asap7_tech_1x_6M7M] Done"
# ) &

# # Variant 6: NangateOpenCellLibrary.tech21
# (
#   echo "[NangateOpenCellLibrary.tech21] Starting"
#   export FLOW_VARIANT="NangateOpenCellLibrary.tech21"
#   source env.sh && ./01_gen_patterns.sh > work/NangateOpenCellLibrary.tech21/step1.log 2>&1
#   ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='NangateOpenCellLibrary.tech21' && source env.sh && ./02_cds_extract.sh" > work/NangateOpenCellLibrary.tech21/step2.log 2>&1
#   export FLOW_VARIANT="NangateOpenCellLibrary.tech21"
#   source env.sh && ./03_gen_rules.sh > work/NangateOpenCellLibrary.tech21/step3.log 2>&1
#   echo "[NangateOpenCellLibrary.tech21] Done"
# ) &

# Variant 6: N551P6M_ieda
echo "[N551P6M_ieda] Starting"
export FLOW_VARIANT="N551P6M_ieda"
source env.sh 
./01_gen_patterns.sh | tee work/N551P6M_ieda/step1.log 2>&1
ssh -T zhiyuzheng@hnode35 "cd /export/home/zhiyuzheng/Projects/3DIC/scripts/ORFS-Research/flow-Pin3D/platforms/rc_extract && export FLOW_VARIANT='N551P6M_ieda' && source env.sh && ./02_cds_extract.sh" | tee work/N551P6M_ieda/step2.log 2>&1
./03_gen_rules.sh | tee work/N551P6M_ieda/step3.log 2>&1
echo "[N551P6M_ieda] Done"

echo "All variants started and running in the background..."
echo "Use 'jobs' to check status"
echo "View logs: ls -la work/*/step*.log"