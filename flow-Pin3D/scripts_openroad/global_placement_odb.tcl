source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl

set DEF_IN       "$env(DESIGN_NAME)_3D.def"
set VERILOG_IN   "$env(DESIGN_NAME)_3D.v"

# 装载设计
load_design $DEF_IN 2_floorplan.sdc "Generate odb for global placement"
# read_def -floorplan_initialize $env(RESULTS_DIR)/$DEF_IN

write_db $env(RESULTS_DIR)/3_3_place_gp.odb

exit