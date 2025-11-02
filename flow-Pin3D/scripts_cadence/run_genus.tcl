# ==========================================
# run_genus.tcl — Genus synthesis (match Makefile)
# Outputs: $::env(RESULTS_DIR)/1_synth.v and 1_synth.sdc
# ==========================================

source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl
# Directories and key files
set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR  [_get OBJECTS_DIR]
foreach d [list $RESULTS_DIR $REPORTS_DIR $LOG_DIR] {
  if {$d ne "" && ![file exists $d]} { file mkdir $d }
}

set OUT_V   [file join $RESULTS_DIR "1_synth.v"]
set OUT_SDC [file join $RESULTS_DIR "1_synth.sdc"]

# Threads
set_db max_cpus_per_server [_get NUM_CORES 16] 
set_db super_thread_servers "localhost" 

set list_lib "$libworst"

# Target library
set link_library $list_lib
set target_library $list_lib

# Expand and deduplicate include directories (wildcards accepted)
set vi_all {}
foreach d $VERILOG_INCLUDE_DIRS {
  set hits [glob -nocomplain -- $d]
  if {[llength $hits]} {
    foreach x $hits { lappend vi_all $x }
  } elseif {[file isdirectory $d]} {
    lappend vi_all $d
  }
}
set vi_all [_uniq $vi_all]

# Key: Tell Genus to search for `include` files in these directories
if {[llength $vi_all]} {
  puts "init_hdl_search_path = $vi_all"
  set_db init_hdl_search_path $vi_all
}

# set path
set_db hdl_flatten_complex_port true
set_db hdl_record_naming_style  %s_%s

set_db library $list_lib

foreach rtl_file $rtl_all {
    read_hdl -sv $rtl_file
}

# Elaborate & Constraints & Initialization
elaborate $DESIGN
time_info Elaboration

read_sdc $sdc
init_design

# --- apply global dont-use from env (safe; no TAP/FILL/CLKBUF here) ---
# if {[info exists ::env(DONT_USE_CELLS)] && $::env(DONT_USE_CELLS) ne ""} {
#   foreach c $::env(DONT_USE_CELLS) { catch { set_dont_use $c true } }
# }

check_design -unresolved

check_timing_intent

# reports the physical layout estimation report from lef and QRC tech file
report_ple > ${REPORTS_DIR}/ple.rpt 

# keep hierarchy during synthesis

syn_generic
time_info GENERIC

write_reports -directory ${REPORTS_DIR} -tag generic
write_db  ${OBJECTS_DIR}/${DESIGN}_generic.db

syn_map
time_info MAPPED

# generate a summary for the current stage of synthesis
write_reports -directory ${REPORTS_DIR} -tag map
write_db  ${OBJECTS_DIR}/${DESIGN}_map.db

syn_opt
time_info OPT
write_db ${OBJECTS_DIR}/${DESIGN}_opt.db

# Flatten all modules except for macros/black boxes
ungroup -all -flatten 
##############################################################################
# Write reports
##############################################################################

# summarizes the information, warnings and errors
report_messages > ${REPORTS_DIR}/${DESIGN}_messages.rpt

# generate PPA reports
report_gates > ${REPORTS_DIR}/${DESIGN}_gates.rpt
report_power > ${REPORTS_DIR}/${DESIGN}_power.rpt
report_area > ${REPORTS_DIR}/${DESIGN}_power.rpt
write_reports -directory ${REPORTS_DIR} -tag final 

write_hdl > $OUT_V
write_sdc > $OUT_SDC

puts "INFO: Wrote $OUT_V"
puts "INFO: Wrote $OUT_SDC"
exit

