# ==========================================
# tier_cell_policy.tcl — Upper/Bottom “do-not-use + filler/tap” policy
# Depends on environment variables (all optional, will try to auto-fallback if empty):
#   DONT_USE_CELLS_UPPER
#   DONT_USE_CELLS_BOTTOM
#   FILL_CELLS_UPPER
#   FILL_CELLS_BOTTOM
#   TAPCELL_UPPER   ;# Optional: if you want to explicitly specify for addWellTap/by layer
#   TAPCELL_BOTTOM
# Usage:
#   source $::env(CADENCE_SCRIPTS_DIR)/tier_cell_policy.tcl
#   apply_tier_policy upper   ;# or bottom
# ==========================================

proc _as_list {envname} {
  if {[info exists ::env($envname)] && $::env($envname) ne ""} {
    return $::env($envname)
  }
  return {}
}

# Compatible set_dont_use (recognized by Innovus/Encounter/Genus)
proc _set_dont_use {cells {flag true}} {
  foreach c $cells {
    catch { set_dont_use $c $flag }
    # Some versions don't accept the boolean second argument, so fallback to single-argument syntax (sets to true)
    if {$flag} { catch { set_dont_use $c } }
  }
}

# Expand wildcard names into lib cell objects/names, as robustly as possible
proc _expand_libcells {patterns} {
  set out {}
  foreach p $patterns {
    # Prefer get_lib_cells; if unavailable, use the wildcard name directly (for set_dont_use to accept)
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

# Optional: Restrict optimization to an "allowlist" (stronger than just don't_use)
# After passing an allow list, it will apply dont_use to "all_cells - allow_list"; disabled by default.
proc _enforce_allowlist {allow_patterns} {
  if {![llength $allow_patterns]} { return }
  set allow  [_expand_libcells $allow_patterns]
  # Get the full set (all standard cells)
  set all ""
  catch { set all [get_lib_cells *] }
  if {$all eq ""} { return }
  # Calculate the difference
  array set mark {}
  foreach a $allow { set mark($a) 1 }
  set ban {}
  foreach a $all { if {![info exists mark($a)]} { lappend ban $a } }
  _set_dont_use $ban true
}

proc apply_tier_policy {tier} {
  set tier [string tolower $tier]
  if {![string match "upper" $tier] && ![string match "bottom" $tier]} {
    error "apply_tier_policy: tier must be 'upper' or 'bottom'"
  }

  # Read environment variables
  set DNU_UP   [_as_list DNU_FOR_UPPER]
  set DNU_BOT  [_as_list DNU_FOR_BOTTOM]
  set FILL_UP  [_as_list FILL_CELLS_UPPER]
  set FILL_BOT [_as_list FILL_CELLS_BOTTOM]
  set TAP_UP   [_as_list TAPCELL_UPPER]
  set TAP_BOT  [_as_list TAPCELL_BOTTOM]

  if {$tier eq "upper"} {
    # 1) Set dont_use for bottom's buffer/filler/tap cells
    if {[llength $DNU_UP]} {
      _set_dont_use [_expand_libcells $DNU_UP] true
    } else {
      # Fallback: disable *_bottom
      _set_dont_use [_expand_libcells "*_bottom"] true
    }

    # 2) Explicitly set the filler list for the upper tier
    if {[llength $FILL_UP]} {
      setFillerMode -core $FILL_UP
    }

    # 3) If running well tap/decap, please explicitly specify upper tap/decap cells
    if {[llength $TAP_UP]} {
      # Example: addWellTap -cell [lindex $TAP_UP 0] -cellInterval 40 -prefix WT_U_
      # This is just an example, not enforced (your flow might insert them elsewhere)
    }

    puts "INFO: Tier policy applied for UPPER: dont_use(bottom), filler=UPPER list."
  } else {
    # bottom
    if {[llength $DNU_BOT]} {
      _set_dont_use [_expand_libcells $DNU_BOT] true
    } else {
      _set_dont_use [_expand_libcells "*_upper"] true
    }

    if {[llength $FILL_BOT]} {
      setFillerMode -core $FILL_BOT
    }

    if {[llength $TAP_BOT]} {
      # Example: addWellTap -cell [lindex $TAP_BOT 0] -cellInterval 40 -prefix WT_B_
    }

    puts "INFO: Tier policy applied for BOTTOM: dont_use(upper), filler=BOTTOM list."
  }
  # Note: This can be too restrictive for hold fixing, so it's not enabled by default.
}
