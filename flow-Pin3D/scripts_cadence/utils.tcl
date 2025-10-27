# ==========================================
# util.tcl  — common helpers for Tcl scripts
# ==========================================

proc _get {name {def ""}} {
  if {[info exists ::env($name)] && $::env($name) ne ""} { return $::env($name) }
  return $def
}

# de-dup list utility
proc _uniq {lst} {
  array set seen {}
  set out {}
  foreach x $lst { if {![info exists seen($x)]} { set seen($x) 1; lappend out $x } }
  return $out
}
