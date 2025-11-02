# ============== Legalize ONLY UPPER tier ==============
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR   [_get OBJECTS_DIR]

set DEF_IN   [file join $RESULTS_DIR "4_1_cts.def"]
set V_IN     [file join $RESULTS_DIR "4_1_cts.v"]
set SDC_IN   [file join $RESULTS_DIR "3_place.sdc"]
set sdc $SDC_IN

source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

setMultiCpuUsage -localCpu [_get NUM_CORES 16]

# --- init design ---
set init_lef_file $lefs
set init_mmmc_file ""
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog $V_IN
set init_design_netlisttype "Verilog"
init_design -setup {WC_VIEW} -hold {BC_VIEW}
defIn $DEF_IN

# --- delete BOTTOM instances, keep UPPER only ---
set to_del_insts [dbGet -u -e -regexp -p2 top.insts.cell.name {.*bottom.*}]
puts "INFO: candidates(inst ptr) = [llength $to_del_insts]"
puts [join [dbGet $to_del_insts.name] " "]
if {[llength $to_del_insts]} {
  foreach inst [dbGet $to_del_insts.name] {
    deleteInst $inst
  }
  puts "INFO: deleted [llength $to_del_insts] bottom insts."
} else {
  puts "INFO: nothing to delete."
}

# --- incremental legalization on remaining (upper) ---
checkPlace
setPlaceMode -place_detail_legalization_inst_gap 1
setFillerMode -fitGap true
source $::env(CADENCE_SCRIPTS_DIR)/tier_cell_policy.tcl
apply_tier_policy upper
catch { place_opt_design -out_dir $REPORTS_DIR -prefix legalize_upper }
checkPlace
fit
dumpToGIF $LOG_DIR/4_2_lg_upper.png
# --- write out only-upper DEF ---
set DEF_OUT  [file join $RESULTS_DIR "4_2_upper.def"]
set V_OUT [file join $RESULTS_DIR "4_2_upper.v"]
defOut -floorplan $DEF_OUT
saveNetlist $V_OUT
puts "INFO: Upper-only legalized DEF -> $DEF_OUT"
puts "INFO: Upper-only legalized Verilog -> $V_OUT"
exit