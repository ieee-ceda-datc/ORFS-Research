# ===============================
# innovus_place3D_bottom.tcl — fix upper, place bottom
# ===============================
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/place_common.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]

set GPDEF     [file join $RESULTS_DIR "${DESIGN}_3D.tmp.def"]
set GPVERILOG [file join $RESULTS_DIR "${DESIGN}_3D.tmp.v"]
set sdc       [file join $RESULTS_DIR "1_synth.sdc"]

source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

set init_lef_file $lefs
set init_mmmc_file ""
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog $GPVERILOG
set init_design_netlisttype "Verilog"

init_design -setup {WC_VIEW} -hold {BC_VIEW}
set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW
defIn $GPDEF

# Fix upper tier, place bottom tier
set _upper_match  "*_upper"
set _bottom_match "*_bottom"
set upper_insts_names  [dbGet [dbGet -p2 top.insts.cell.name $_upper_match].name]
set bottom_insts_names [dbGet [dbGet -p2 top.insts.cell.name $_bottom_match].name]

if {[llength $upper_insts_names]} {
  dbSet [dbGet -p2 top.insts.cell.name $_upper_match].pStatus fixed
  puts "INFO: upper tier fixed."
}
if {[llength $bottom_insts_names]} {
  dbSet [dbGet -p2 top.insts.cell.name $_bottom_match].pStatus placed
}

# Tier strategy: allow cells + fillers on bottom, disable upper tier cells
source $::env(CADENCE_SCRIPTS_DIR)/tier_cell_policy.tcl
apply_tier_policy bottom

pc::setup_basic
pc::run_place

# Unfix upper tier
if {[llength $upper_insts_names]} {
  dbSet [dbGet -p2 top.insts.cell.name $_upper_match].pStatus placed
}

# Export
saveDesign [file join $::env(OBJECTS_DIR) "${DESIGN}_3d_after_bottom.enc"]
defOut -floorplan $GPDEF
saveNetlist [file join $RESULTS_DIR "${DESIGN}_3D.tmp.v"]
fit
dumpToGIF $LOG_DIR/bottom_place.png
puts "INFO: 3D bottom placement done."
exit

