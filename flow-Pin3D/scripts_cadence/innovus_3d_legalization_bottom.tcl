# ============== Legalize ONLY BOTTOM tier ==============
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl


set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR   [_get OBJECTS_DIR]

set DEF_IN   [file join $RESULTS_DIR "4_1_cts.def"]
set V_IN     [file join $RESULTS_DIR "4_1_cts.v"]
set SDC_IN   [file join $RESULTS_DIR "3_placed.sdc"]
set sdc $SDC_IN

source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

setMultiCpuUsage -localCpu 16

# --- init design ---
set init_lef_file $lefs
set init_mmmc_file ""
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog $V_IN
set init_design_netlisttype "Verilog"
init_design -setup {WC_VIEW} -hold {BC_VIEW}
defIn $DEF_IN

# --- delete UPPER instances, keep BOTTOM only ---
set _upper_match  "*_upper"
set _bottom_match "*_bottom"
set upper_insts_names [dbGet [dbGet -p2 top.insts.cell.name $_upper_match].name]
if {[llength $upper_insts_names]} {
  deleteInst $upper_insts_names
  puts "INFO: Deleted [llength $upper_insts_names] upper instances; bottom only remains."
}

# --- incremental legalization on remaining (bottom) ---
checkPlace
setPlaceMode -place_detail_legalization_inst_gap 1
setFillerMode -fitGap true
source $::env(CADENCE_SCRIPTS_DIR)/tier_cell_policy.tcl
apply_tier_policy bottom
catch { place_opt_design -out_dir $REPORTS_DIR -prefix legalize_bottom }
checkPlace
fit
dumpToGIF $LOG_DIR/4_2_lg_bottom.png
# --- write out only-bottom DEF ---
set DEF_OUT  [file join $RESULTS_DIR "4_2_bottom.def"]
set V_OUT [file join $RESULTS_DIR "4_2_bottom.v"]
defOut -floorplan $DEF_OUT
saveNetlist $V_OUT 
puts "INFO: Bottom-only legalized DEF -> $DEF_OUT"
puts "INFO: Bottom-only legalized Verilog -> $V_OUT"
exit
