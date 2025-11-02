utl::set_metrics_stage "cts__{}"
source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl
load_design 4_1_cts.odb 3_place.sdc "Starting fill cell"

set_propagated_clock [all_clocks]

# filler_placement $::env(FILL_CELLS)
# check_placement

if {![info exists save_checkpoint] || $save_checkpoint} {
  write_db $::env(RESULTS_DIR)/4_cts.odb
  write_def $::env(RESULTS_DIR)/4_cts.def
  write_verilog $::env(RESULTS_DIR)/4_cts.v
}

exit