# lg_upper.tcl
source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl

set DEF_IN       "4_2_cts.def"
set VERILOG_IN   "4_2_cts.v"
set DEF_OUT      "4_2_upper.def"
set VERILOG_OUT  "4_2_upper.v"

# 装载设计
load_design $DEF_IN 3_place.sdc "Starting upper leagalization"
# read_def -floorplan_initialize $env(RESULTS_DIR)/$DEF_IN

source $::env(OPENROAD_SCRIPTS_DIR)/placement_utils.tcl
# ==== 在 upper 合法化前删除 bottom 实例 ====

delete_insts_by_master "*_bottom*" 0

detailed_placement -max_displacement 300

write_def    $env(RESULTS_DIR)/$DEF_OUT
write_verilog $env(RESULTS_DIR)/$VERILOG_OUT

save_image -resolution 0.1 $::env(LOG_DIR)/4_2_upper_legalized.webp

exit