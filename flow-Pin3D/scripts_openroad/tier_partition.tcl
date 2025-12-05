source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl
source $::env(OPENROAD_SCRIPTS_DIR)/util.tcl
load_design 2_2_floorplan_io.v 1_synth.sdc "Start Triton Partitioning"
read_def -floorplan_initialize $::env(RESULTS_DIR)/2_2_floorplan_io.def

triton_part_design -solution_file $env(RESULTS_DIR)/partition.txt

exit