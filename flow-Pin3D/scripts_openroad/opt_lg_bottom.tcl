# opt_lg_bottom.tcl
source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl

set DEF_IN       "$::env(DESIGN_NAME)_3D.lg.def"
set VERILOG_IN   "$::env(DESIGN_NAME)_3D.lg.v"
set DEF_OUT      "$::env(DESIGN_NAME)_3D.lg.def"
set VERILOG_OUT  "$::env(DESIGN_NAME)_3D.lg.v"

# 装载设计
load_design $DEF_IN 2_floorplan.sdc "Starting bottom optimization and legalization"

# 引入工具函数
source $::env(OPENROAD_SCRIPTS_DIR)/placement_utils.tcl

# ==== 在 bottom opt & lg 前 set 好 dont_use_cell ====
tier_dont_use_strategy bottom

source $::env(OPENROAD_SCRIPTS_DIR)/opt_lg_design.tcl

write_def    $env(RESULTS_DIR)/$DEF_OUT
write_verilog $env(RESULTS_DIR)/$VERILOG_OUT

save_image -resolution 0.1 $::env(LOG_DIR)/3_4_opt_lg_bottom_legalized.webp

exit