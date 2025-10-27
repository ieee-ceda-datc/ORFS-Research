# ============== CTS on 3_placed.{def,v,sdc} ==============
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR   [_get OBJECTS_DIR]

set DEF_IN   [file join $RESULTS_DIR "3_placed.def"]
set V_IN     [file join $RESULTS_DIR "3_placed.v"]
set sdc   [file join $RESULTS_DIR "3_placed.sdc"]

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
set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW
set_interactive_constraint_modes {CON}
setAnalysisMode -reset
setAnalysisMode -analysisType onChipVariation -cppr both
defIn $DEF_IN

# --- CTS properties ---
set_ccopt_property post_conditioning_enable_routing_eco 1
set_ccopt_property -cts_def_lock_clock_sinks_after_routing true
setOptMode -unfixClkInstForOpt false

# --- run ccopt ---
create_ccopt_clock_tree_spec
ccopt_design

# --- 写出 DEF + Netlist（CTS 视图）---
defOut -floorplan -routing [file join $RESULTS_DIR "4_1_cts.def"]
saveNetlist [file join $RESULTS_DIR "4_1_cts.v"]
fit
dumpToGIF $LOG_DIR/4_1_cts.png
puts "INFO: CTS done. DEF -> [file join $RESULTS_DIR "4_1_cts.def"]  V -> [file join $RESULTS_DIR "4_1_cts.v"]"
exit
