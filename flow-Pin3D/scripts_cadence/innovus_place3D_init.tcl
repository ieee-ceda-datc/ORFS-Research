# ===============================
# innovus_place3D_init.tcl — 3D place init with stable modes
# ===============================
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/place_common.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]

set FPDEF      [file join $RESULTS_DIR "2_floorplan.def"]
set FPVERILOG  [file join $RESULTS_DIR "2_floorplan.v"]
set sdc        [file join $RESULTS_DIR "1_synth.sdc"]

source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

set init_lef_file $lefs
set init_mmmc_file ""
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog $FPVERILOG
set init_design_netlisttype "Verilog"

init_design -setup {WC_VIEW} -hold {BC_VIEW}
set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW
defIn $FPDEF
generateTracks

pc::setup_basic
place_design

set GPDEFOUT [file join $RESULTS_DIR "${DESIGN}_3D.tmp.def"]
set GPVOUT   [file join $RESULTS_DIR "${DESIGN}_3D.tmp.v"]
defOut -floorplan $GPDEFOUT
saveNetlist $GPVOUT
fit
dumpToGIF $LOG_DIR/init_place.png
puts "INFO: 3D place init done. DEF: $GPDEFOUT  V: $GPVOUT"
exit
