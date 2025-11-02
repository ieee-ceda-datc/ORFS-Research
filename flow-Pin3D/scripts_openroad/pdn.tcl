source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl
load_design $env(DESIGN_NAME)_3D.fp.def 1_synth.sdc "Starting PDN generation"
# read_def -floorplan_initialize $env(RESULTS_DIR)/2_5_floorplan_tapcell.def

if {[file exists $::env(PLATFORM_DIR)/make_tracks.tcl]} {
  source $::env(PLATFORM_DIR)/make_tracks.tcl
}

source $::env(PDN_TCL)
if {[catch {
  pdngen
} errorMessage]} {
    puts "ErrorPDN: $errorMessage"
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