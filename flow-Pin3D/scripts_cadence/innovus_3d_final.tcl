# ============== Final and extract metrics (restoreDesign → extract_report -postRoute) ==============

# ---- Common setup ----
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set OBJECTS_DIR   [_get OBJECTS_DIR]

# ---- Use ONLY 5_route.v / 5_route.sdc for init globals (no fallback) ----
set NL_5R   [file join $RESULTS_DIR "5_route.v"]
set SDC_5R  [file join $RESULTS_DIR "5_route.sdc"]

if {![file exists $NL_5R]}  { puts "ERROR: Missing netlist: $NL_5R";  exit 1 }
if {![file exists $SDC_5R]} { puts "ERROR: Missing SDC:     $SDC_5R";  exit 1 }

# init_* globals required by some Innovus builds even for restoreDesign
if {![info exists lefs] || $lefs eq ""} {
  puts "WARN: 'lefs' was not exported by lib_setup.tcl; continue with netlist/SDC only."
}
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog   $NL_5R
set init_mmmc_file $SDC_5R
if {[info exists lefs] && $lefs ne ""} { set init_lef_file $lefs }

# ---- Restore routed DB (no DEF fallback) ----
# set ENC_PRIMARY   [file join $OBJECTS_DIR "_postRoute.enc"]
set ENC_FILE [file join $OBJECTS_DIR "${DESIGN}_postRoute.enc.dat"]

puts "INFO: restoreDesign $ENC_FILE $DESIGN"
restoreDesign $ENC_FILE $DESIGN

set DEF_5R [file join $RESULTS_DIR "5_route.def"]
defIn $DEF_5R


# Analysis knobs
set_interactive_constraint_modes {CON}
setAnalysisMode -analysisType onChipVariation -cppr both
setMultiCpuUsage -localCpu 16
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
exit
