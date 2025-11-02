source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl

set DEF_IN       "4_cts.def"
set VERILOG_IN   "4_2_cts.v"

load_design $DEF_IN 3_place.sdc "Generate CTS ODB"
# read_def -floorplan_initialize $env(RESULTS_DIR)/$DEF_IN

write_db $env(RESULTS_DIR)/4_cts.odb

exit