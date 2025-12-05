source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl
load_design $env(DESIGN_NAME)_3D.fp.def 1_synth.sdc "Starting PDN generation"
# read_def -floorplan_initialize $env(RESULTS_DIR)/2_5_floorplan_tapcell.def

source $::env(OPENROAD_SCRIPTS_DIR)/placement_utils.tcl

if {[info exists ::env(MAKE_TRACKS)]} {
  source $::env(MAKE_TRACKS)
}

source $::env(PDN_TCL)
if { [info exists ::env(UPPER_SITE)] && [info exists ::env(BOTTOM_SITE)] } {
  puts "PDN sites: UPPER_SITE=$::env(UPPER_SITE), BOTTOM_SITE=$::env(BOTTOM_SITE)"
} else {
  if {[catch {
    pdngen
  } errorMessage]} {
      puts "ErrorPDN: $errorMessage"
  }
}

if { [info exists ::env(POST_PDN_TCL)] && [file exists $::env(POST_PDN_TCL)] } {
  source $::env(POST_PDN_TCL)
}

# Check all supply nets
set block [ord::get_db_block]
foreach net [$block getNets] {
    set type [$net getSigType]
    if {$type == "POWER" || $type == "GROUND"} {
# Temporarily disable due to CI issues
#        puts "Check supply: [$net getName]"
#        check_power_grid -net [$net getName]
    }
}

write_def $env(RESULTS_DIR)/2_6_floorplan_pdn.def
write_verilog $env(RESULTS_DIR)/2_6_floorplan_pdn.v

exit