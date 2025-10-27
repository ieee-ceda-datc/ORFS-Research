set all_lefs [concat $env(LEF_FILES)]
foreach lef_file $all_lefs {
    read_lef $lef_file
}
set all_libs [concat $env(LIB_FILES)]
foreach lib_file $all_libs {
    read_liberty $lib_file
}
set VERILOGFILE $::env(RESULTS_DIR)/2_2_floorplan_io.v
set DEFFILE $::env(RESULTS_DIR)/2_2_floorplan_io.def
set sdc $::env(RESULTS_DIR)/1_synth.sdc
read_verilog $VERILOGFILE
link_design $::env(DESIGN_NAME)
read_sdc $sdc
read_def -floorplan_initialize $DEFFILE
puts "Starting tier partitioning..."
triton_part_design -solution_file $::env(RESULTS_DIR)/partition.txt

