# start opt_lg_design.tcl
puts "Starting opt_lg_design.tcl..."

estimate_parasitics -placement

if {![info exists ::env(FOOTPRINT)]} {
  puts "Perform port buffering..."
  buffer_ports
}

puts "Perform buffer insertion..."
set additional_args ""
if { [info exists ::env(CAP_MARGIN)] && $::env(CAP_MARGIN) > 0.0} {
  puts "Cap margin $::env(CAP_MARGIN)"
  append additional_args " -cap_margin $::env(CAP_MARGIN)"
}
if { [info exists ::env(SLEW_MARGIN)] && $::env(SLEW_MARGIN) > 0.0} {
  puts "Slew margin $::env(SLEW_MARGIN)"
  append additional_args " -slew_margin $::env(SLEW_MARGIN)"
}

repair_design {*}$additional_args

if { [info exists env(TIE_SEPARATION)] } {
  set tie_separation $env(TIE_SEPARATION)
} else {
  set tie_separation 0
}

# Repair tie lo fanout
puts "Repair tie lo fanout..."
set tielo_cell_name [lindex $env(TIELO_CELL_AND_PORT) 0]
set tielo_lib_name [get_name [get_property [lindex [get_lib_cell $tielo_cell_name] 0] library]]
set tielo_pin $tielo_lib_name/$tielo_cell_name/[lindex $env(TIELO_CELL_AND_PORT) 1]
repair_tie_fanout -separation $tie_separation $tielo_pin

# Repair tie hi fanout
puts "Repair tie hi fanout..."
set tiehi_cell_name [lindex $env(TIEHI_CELL_AND_PORT) 0]
set tiehi_lib_name [get_name [get_property [lindex [get_lib_cell $tiehi_cell_name] 0] library]]
set tiehi_pin $tiehi_lib_name/$tiehi_cell_name/[lindex $env(TIEHI_CELL_AND_PORT) 1]
repair_tie_fanout -separation $tie_separation $tiehi_pin

set_placement_padding -global \
    -left $::env(CELL_PAD_IN_SITES_DETAIL_PLACEMENT) \
    -right $::env(CELL_PAD_IN_SITES_DETAIL_PLACEMENT)

set max_displacement 300

detailed_placement -max_displacement $max_displacement

if {[info exists ::env(ENABLE_DPO)] && $::env(ENABLE_DPO)} {
  if {[info exist ::env(DPO_MAX_DISPLACEMENT)]} {
    improve_placement -max_displacement $::env(DPO_MAX_DISPLACEMENT)
  } else {
    improve_placement
  }
}
puts "optimize_mirroring"
optimize_mirroring
