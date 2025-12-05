# placement_utils.tcl


# In placement phase
# ----------------------------------------------------------------------
# Mark instances as a given placement status by matching master name
# Usage:
#   mark_insts_by_master "*_bottom" FIRM
#   mark_insts_by_master "" FIRM
# ----------------------------------------------------------------------
proc mark_insts_by_master {{pattern ""} {status "FIRM"}} {
  # 1) Parse pattern
  if {$pattern eq ""} {
    return 0
  }

  # 2) Validate target status (common OpenROAD/ODB values)
  set valid_status {UNPLACED PLACED FIRM LOCKED FIXED}
  if {[lsearch -exact $valid_status $status] < 0} {
    puts "WARN: '$status' not in valid statuses: $valid_status ; fallback to FIRM"
    set status FIRM
  }

  # 3) Get DB/Block
  set db   [ord::get_db]
  set chip [$db getChip]
  if {$chip eq ""} {
    puts "WARN: No chip loaded."
    return 0
  }
  set block [$chip getBlock]
  if {$block eq ""} {
    puts "WARN: No block in chip."
    return 0
  }

  # 4) Iterate instances; match by master name and set status
  set cnt 0
  set examples {}
  foreach inst [$block getInsts] {
    set mname [[$inst getMaster] getName]
    if {[string match -nocase $pattern $mname]} {
      if {[catch {$inst setPlacementStatus $status} err]} {
        puts "WARN: fail to set $status for [$inst getName]($mname): $err"
      } else {
        incr cnt
        if {[llength $examples] < 5} {
          lappend examples "[$inst getName]($mname)"
        }
      }
    }
  }

  puts "INFO: Marked $cnt insts to '$status' by master pattern '$pattern'. Examples: [join $examples {, }]"
  return $cnt
}

# ---------- Helpers ----------
proc ::_as_int {v default} {
  if {![info exists v]} { return $default }
  if {![string is integer -strict $v]} { return $default }
  return $v
}

proc ::_env_or {name default} {
  if {[info exists ::env($name)]} { return $::env($name) }
  return $default
}

# ---------- Robust density calculator ----------
proc calculate_placement_density {} {
  set base_density [::_env_or PLACE_DENSITY 0.60]

  # 1) If no addon requested, just use base
  if {![info exists ::env(PLACE_DENSITY_LB_ADDON)]} {
  puts "INFO: PLACE_DENSITY_LB_ADDON not set, using PLACE_DENSITY=$base_density"
  return $base_density
  }

  # 2) DB preflight
  set db   [ord::get_db]
  if {$db eq ""} {
  puts "WARN: no DB; fallback density $base_density"
  return $base_density
  }
  set chip [$db getChip]
  if {$chip eq ""} {
  puts "WARN: no chip; fallback density $base_density"
  return $base_density
  }
  set block [$chip getBlock]
  if {$block eq ""} {
  puts "WARN: no block; fallback density $base_density"
  return $base_density
  }
  if {[llength [$block getRows]] == 0} {
  puts "WARN: no rows in block (DEF may lack ROWS); fallback density $base_density"
  return $base_density
  }

  # 3) Pad arguments must be integers; default to 0 if missing
  set pad_l [::_as_int $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) 0]
  set pad_r [::_as_int $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) 0]

  # 4) Compute LB with catch to absorb GPL-0301 on older builds / invalid states
  set lb 0.0
  set rc [catch {
  if {[info procs gpl::get_global_placement_uniform_density] ne ""} {
    set lb [gpl::get_global_placement_uniform_density -pad_left $pad_l -pad_right $pad_r]
  } elseif {[info procs gpl::get_global_placement_uniform_density_cmd] ne ""} {
    set lb [gpl::get_global_placement_uniform_density_cmd -pad_left $pad_l -pad_right $pad_r]
  } else {
    error "No GPL uniform-density helper in this build"
  }
  } err]

  if {$rc} {
  puts "WARN: failed to get density LB (GPL-0301/compat): $err ; fallback $base_density"
  return $base_density
  }

  # 5) Apply addon blend and a tiny nudge
  set addon $::env(PLACE_DENSITY_LB_ADDON)
  if {$addon < 0.0} { set addon 0.0 }
  if {$addon > 1.0} { set addon 1.0 }

  set density [expr {$lb + ((1.0 - $lb) * $addon) + 0.01}]
  if {$density <= 0.0} { set density 0.10 }
  if {$density >= 1.0} { set density 0.98 }

  puts "INFO: PLACE_DENSITY_LB=$lb, ADDON=$addon -> density=$density (padL=$pad_l padR=$pad_r)"
  return $density
}

# ==== Utility: delete instances by matching master name ====
# pattern default "*_bottom*"; dry_run=1 only prints; verbose controls logging
proc delete_insts_by_master {{pattern ""} {dry_run 0} {verbose 1}} {
  set db   [ord::get_db]
  set chip [$db getChip]
  if {$chip eq ""} { puts "WARN: no chip"; return 0 }
  set block [$chip getBlock]
  if {$block eq ""} { puts "WARN: no block"; return 0 }
  
  if {$pattern eq ""} {
  puts "WARN: empty pattern, skip."
  return 0
  }
  set del_names {}
  foreach inst [$block getInsts] {
  set mname [[$inst getMaster] getName]
  if {[string match -nocase $pattern $mname]} {
    lappend del_names [$inst getName]
  }
  }

  if {$verbose} {
  puts "INFO: matched [llength $del_names] insts by master '$pattern'"
  puts "INFO: examples: [join [lrange $del_names 0 9] {, }]"
  }

  if {$dry_run} { return [llength $del_names] }

  set ok 0
  foreach name $del_names {
  if {[catch {delete_instance $name} err]} {
    puts "WARN: delete_instance $name failed: $err"
  } else {
    incr ok
  }
  }
  if {$verbose} { puts "INFO: actually deleted $ok insts." }
  return $ok
}

# ===============================
# OpenROAD: dont_use & FastRoute
# ===============================

# Get environment variable as list (missing/empty => {})
proc _as_list {envname} {
  if {[info exists ::env($envname)] && $::env($envname) ne ""} {
  return $::env($envname)
  }
  return {}
}

# Expand wildcard patterns to real lib cell names; keep original if command unsupported
proc _expand_libcells {patterns} {
  set out {}
  foreach p $patterns {
  if {![catch {set hits [get_lib_cells $p]}]} {
    if {[llength $hits] > 0} {
    foreach h $hits { lappend out $h }
    continue
    }
  }
  lappend out $p
  }
  return [lsort -unique $out]
}

# set_dont_use prefers batch; if it fails, fall back to per-cell
proc _set_dont_use {cells} {
  if {![llength $cells]} { return }
  if {[catch {set_dont_use $cells}]} {
  foreach c $cells { catch { set_dont_use $c } }
  }
}

# ============= Tier strategy (similar approach to Cadence scripts) =============
# Environment variables (if already defined they take effect):
#   DNU_FOR_UPPER / DNU_FOR_BOTTOM  : disable pattern list for upper/bottom
#   DONT_USE_CELLS                  : overall dont-use list compatible with existing scripts (optional)
#   *_upper / *_bottom libraries can be matched by "*_upper" / "*_bottom" wildcards
proc apply_tier_policy {tier} {
  set tier [string tolower $tier]
  if {![string match "upper" $tier] && ![string match "bottom" $tier]} {
  error "apply_tier_policy: tier must be 'upper' or 'bottom'"
  }

  set dnu_up  [_as_list DNU_FOR_UPPER]
  set dnu_bot [_as_list DNU_FOR_BOTTOM]

  if {$tier eq "upper"} {
    if {[llength $dnu_up]} {
      _set_dont_use [_expand_libcells $dnu_up]
    } else {
      _set_dont_use [_expand_libcells "*_bottom"]
    }
    set ::env(TIEHI_CELL_AND_PORT) $::env(UPPER_TIEHI_CELL_AND_PORT)
    set ::env(TIELO_CELL_AND_PORT) $::env(UPPER_TIELO_CELL_AND_PORT)
    if {[info exists ::env(UPPER_SITE)]} {
      set ::env(PLACE_SITE) $::env(UPPER_SITE)
    }
    puts "INFO(OR): Tier policy applied for UPPER."
  } else {
    if {[llength $dnu_bot]} {
      _set_dont_use [_expand_libcells $dnu_bot]
    } else {
      _set_dont_use [_expand_libcells "*_upper"]
    }
    set ::env(TIEHI_CELL_AND_PORT) $::env(BOTTOM_TIEHI_CELL_AND_PORT)
    set ::env(TIELO_CELL_AND_PORT) $::env(BOTTOM_TIELO_CELL_AND_PORT)
    if {[info exists ::env(BOTTOM_SITE)]} {
      set ::env(PLACE_SITE) $::env(BOTTOM_SITE)
    }
    puts "INFO(OR): Tier policy applied for BOTTOM."
  }
  if {[info exists ::env(DONT_USE_CELLS)] && $::env(DONT_USE_CELLS) ne ""} {
    _set_dont_use [_expand_libcells $::env(DONT_USE_CELLS)]
    puts "INFO(OR): Applied DONT_USE_CELLS = '$::env(DONT_USE_CELLS)'."
  }
  or_rebuild_rows_for_site $::env(PLACE_SITE)
}

# ============= FastRoute fallback setup (can be overridden by external Tcl) =============
proc fastroute_setup {} {
  # Prefer user-provided external script
  if {[info exists ::env(FASTROUTE_TCL)] && $::env(FASTROUTE_TCL) ne ""} {
  puts "INFO(OR): Sourcing FASTROUTE_TCL = $::env(FASTROUTE_TCL)"
  catch { source $::env(FASTROUTE_TCL) }
  return
  }

  # Fallback: set signal layers and congestion adjustment from MIN/MAX_ROUTING_LAYER
  set minL [expr {[info exists ::env(MIN_ROUTING_LAYER)] ? $::env(MIN_ROUTING_LAYER) : "met1"}]
  set maxL [expr {[info exists ::env(MAX_ROUTING_LAYER)] ? $::env(MAX_ROUTING_LAYER) : "met5"}]

  catch { set_routing_layers -signal ${minL}-${maxL} }
  # Apply uniform layer adjustment (more conservative congestion); can be refined per-layer
  catch { set_global_routing_layer_adjustment ${minL}-${maxL} 0.5 }

  puts "INFO(OR): FastRoute default setup done: layers=${minL}-${maxL}, adjust=0.5"
}

proc or_rebuild_rows_for_site {new_site {out_def ""}} {
  if {![llength [info commands ord::get_die_area]]} {
    puts "ERROR: ord::get_die_area not available. Are you in OpenROAD?"
    return
  }

  set die_area [ord::get_die_area]
  set core_area [ord::get_core_area]

  puts "INFO: OR die_area  = $die_area"
  puts "INFO: OR core_area = $core_area"
  puts "INFO: OR rebuilding rows with site = $new_site"

  # 2) Rebuild the floorplan/rows with the same die/core area and the new site
  initialize_floorplan \
    -die_area  $die_area \
    -core_area $core_area \
    -site      $new_site

  if {$out_def ne ""} {
    write_def $out_def
    puts "INFO: wrote floorplan DEF with new rows: $out_def"
  }
}

# 递归打印某个 namespace 下的所有命令和子 namespace
proc or_list_ns_cmds {ns {indent ""}} {
  # 打印当前 namespace
  puts "${indent}Namespace: $ns"

  # 当前 namespace 下的命令（用 pattern 匹配）
  set pattern "${ns}::*"
  set cmds [lsort [info commands $pattern]]
  foreach c $cmds {
    puts "${indent}  [string range $c 0 end]"
  }

  # 递归进入子 namespace
  set children [lsort [namespace children $ns]]
  foreach child $children {
    or_list_ns_cmds $child "${indent}  "
  }
}


