# ============== Final and extract metrics (restoreDesign → extract_report -postRoute) ==============

# ---- Common setup ----
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR   [_get OBJECTS_DIR]

# ---- Use ONLY 5_route.v / 5_route.sdc for init globals (no fallback) ----
set V_IN   [file join $RESULTS_DIR "5_route.v"]
set sdc  [file join $RESULTS_DIR "5_route.sdc"]
set DEF_IN [file join $RESULTS_DIR "5_route.def"]

if {![file exists $V_IN]}  { puts "ERROR: Missing netlist: $V_IN";  exit 1 }
if {![file exists $sdc]} { puts "ERROR: Missing SDC:     $sdc";  exit 1 }

# init_* globals required by some Innovus builds even for restoreDesign
if {![info exists lefs] || $lefs eq ""} {
  puts "WARN: 'lefs' was not exported by lib_setup.tcl; continue with netlist/SDC only."
}
set init_lef_file $lefs
set init_mmmc_file ""
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog   $V_IN
set init_design_netlisttype "Verilog"

if {[info exists lefs] && $lefs ne ""} { set init_lef_file $lefs }

# ---- Restore routed DB (no DEF fallback) ----
# set ENC_PRIMARY   [file join $OBJECTS_DIR "_postRoute.enc"]
set ENC_FILE [file join $OBJECTS_DIR "${DESIGN}_postRoute.enc.dat"]
if {[file exists $ENC_FILE]} {
  puts "INFO: restoreDesign $ENC_FILE $DESIGN"
  restoreDesign $ENC_FILE $DESIGN
} else {
  source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl
  puts "Missing routed ENC file: $ENC_FILE"
  init_design -setup {WC_VIEW} -hold {BC_VIEW}
  set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW
  setAnalysisMode -reset
}

# Analysis knobs
set_interactive_constraint_modes {CON}
setAnalysisMode -analysisType onChipVariation -cppr both
defIn $DEF_IN

setMultiCpuUsage -localCpu [_get NUM_CORES 16]
# Newer Voltus API hint (do not error if views absent)
catch { set_analysis_view -leakage WC_VIEW -dynamic WC_VIEW }

# Run unified extractor directly into LOG_DIR
file mkdir [file join $LOG_DIR timingReports]

set EXTRACT_TCL [file join $::env(CADENCE_SCRIPTS_DIR) extract_report.tcl]
if {![file exists $EXTRACT_TCL]} { puts "ERROR: Cannot find $EXTRACT_TCL"; exit 1 }
source $EXTRACT_TCL

set CSV_PATH [file join $LOG_DIR "final_metrics.csv"]
set SUMMARY  [file join $LOG_DIR "final_summary.txt"]

set csv_line [extract_report -postRoute \
                            -outdir $LOG_DIR \
                            -write_csv $CSV_PATH \
                            -write_summary $SUMMARY]

catch { file mkdir [file join $LOG_DIR final] }
catch { dumpPictures -dir [file join $LOG_DIR final] -prefix final }

puts "INFO: Final metrics CSV -> $CSV_PATH"
puts "INFO: Final summary     -> $SUMMARY"
puts "INFO: timingReports/, power_Final.rpt, drc.rpt, fep.rpt are under $LOG_DIR."

set [_get VISUALIZE_FINAL "0"] 
if {$VISUALIZE_FINAL eq "1"} {
  error "INTENTIONAL_ABORT: For Final Deisgn Visualize" 
}

exit
