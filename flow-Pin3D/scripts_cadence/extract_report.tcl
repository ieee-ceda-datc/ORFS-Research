# ============================================================
# extract_report.tcl — Unified reporting (postRoute, NO cd)
#   extract_report -postRoute -outdir <DIR> \
#                   [-write_csv <csvpath>] [-write_summary <txtpath>]
# All artifacts end up under -outdir:
#   <outdir>/timingReports/Final.summary(.gz), power_Final.rpt, drc.rpt, fep.rpt
# ============================================================

proc _open_any {path} {
  if {![file exists $path]} { return "" }
  set fp [open $path r]
  if {[string match *.gz $path]} { zlib push gunzip $fp }
  return $fp
}

proc _ensure_dir {d} { if {![file exists $d]} { file mkdir $d } }

# ---- Parsers ----
proc extract_from_timing_rpt {timing_rpt} {
  set wns ""; set tns ""; set hc ""; set vc ""; set flag 0
  set fp [_open_any $timing_rpt]
  if {$fp eq ""} {
    set fp [_open_any [file rootname $timing_rpt]]
    if {$fp eq ""} { return [list $wns $tns $hc $vc] }
  }
  while {[gets $fp line] >= 0} {
    if {$flag == 0} { set words [split $line "|"] } else { set words [split $line] }
    if {[llength $words] < 2} { continue }
    if {[string map {" " ""} [lindex $words 1]] eq "WNS(ns):"} {
      set wns [string map {" " ""} [lindex $words 2]]
    } elseif {[string map {" " ""} [lindex $words 1]] eq "TNS(ns):"} {
      set tns [string map {" " ""} [lindex $words 2]]
      set flag 1
    } elseif {[llength $words] == 7 && [lindex $words 0] eq "Routing"} {
      set hc [lindex $words 2]; set vc [lindex $words 5]; break
    }
  }
  close $fp
  return [list $wns $tns $hc $vc]
}

proc extract_from_power_rpt {power_rpt} {
  if {![file exists $power_rpt]} { return "" }
  set power ""
  set fp [open $power_rpt r]
  while {[gets $fp line] >= 0} {
    if {[llength $line] == 3 && [lindex $line 0] eq "Total"} {
      set power [lindex $line 2]; break
    }
  }
  close $fp
  return $power
}

proc extract_cell_area {} {
    set macro_area [expr  [join [dbget [dbget top.insts.cell.subClass block -p2 ].area ] +]]
    set std_cell_area [expr  [join [dbget [dbget top.insts.cell.subClass block -v -p2 ].area ] +]]
  return [list $macro_area $std_cell_area]
}

proc extract_wire_length {} {
  return [expr [join [dbget top.nets.wires.length] +]]
}

proc extract_fep {report_file_path} {
  timeDesign -postRoute
  set FEPs [report_timing -check_type setup -begin_end_pair -collection]
  set FEP_vios 0
  set FEP_TNS 0.0
  set FEP_WNS 1e9
  set uniq [dict create]
  foreach_in_collection p $FEPs {
    set slack [get_property $p slack]
    if {$slack < 0} {
      set ep [get_object_name [get_property $p capturing_point]]
      if {![dict exists $uniq $ep]} {
        dict set $uniq $ep 1
        incr FEP_vios
        set FEP_TNS [expr {$FEP_TNS + $slack}]
        set FEP_WNS [expr {min($FEP_WNS, $slack)}]
      }
    }
  }
  set fid [open $report_file_path w]
  puts $fid "Total FEP Violations: $FEP_vios"
  puts $fid "Total FEP TNS: $FEP_TNS"
  puts $fid "Total FEP WNS: $FEP_WNS"
  close $fid
  set v ""
  set fid [open $report_file_path r]
  while {[gets $fid line] >= 0} {
    if {[string match "*Total FEP Violations:*" $line]} {
      set parts [split $line ":"]
      set v [string trim [lindex $parts end]]
      break
    }
  }
  close $fid
  return $v
}

proc extract_drc {drc_rpt} {
  verify_drc -exclude_pg_net -limit 100000 -report $drc_rpt
  set v ""
  set fp [open $drc_rpt r]
  while {[gets $fp line] >= 0} {
    if {[string match "  Total Violations : * Viols." $line]} {
      regexp {Total Violations : (\d+) Viols.} $line _ v
      set v [string trim $v]
      break
    }
  }
  close $fp
  return $v
}

# ---- Internal worker (no cd): run timeDesign here, then COPY timingReports → outdir ----
proc _extract_postRoute {outdir} {
  set stage "Final"
  _ensure_dir $outdir
  _ensure_dir [file join $outdir timingReports]

  # 1) Run timing (writes ./timingReports/Final.* in CURRENT dir)
  timeDesign -postRoute -prefix ${stage}

  # 2) Power directly to outdir
  set power_rpt [file join $outdir power_${stage}.rpt]
  report_power > $power_rpt

  # 3) Copy timingReports/* to outdir/timingReports (if present)
  set tr_local "timingReports"
  set tr_out   [file join $outdir timingReports]
  if {[file exists $tr_local]} {
    foreach item [glob -nocomplain -directory $tr_local *] {
      file copy -force $item $tr_out
    }
  }

  # 4) Parse from OUTDIR timingReports (prefer .gz)
  set tpath_gz [file join $tr_out ${stage}.summary.gz]
  set tpath    [file join $tr_out ${stage}.summary]
  set timing_path [expr {[file exists $tpath_gz] ? $tpath_gz : $tpath}]
  set rpt1  [extract_from_timing_rpt $timing_path]
  set rpt2  [extract_from_power_rpt  $power_rpt]
  set rpt3  [extract_cell_area]
  set rpt4  [extract_wire_length]

  # 5) DRC & FEP directly under outdir
  set drc_v [extract_drc [file join $outdir drc.rpt]]
  set fep_v [extract_fep [file join $outdir fep.rpt]]

  # 6) Compose CSV line
  set core_area [dbget top.fplan.coreBox_area]
  set std_area  [lindex $rpt3 1]
  set mac_area  [lindex $rpt3 0]
  set wns       [lindex $rpt1 0]
  set tns       [lindex $rpt1 1]
  set hc        [lindex $rpt1 2]
  set vc        [lindex $rpt1 3]

  return "$stage,$core_area,$std_area,$mac_area,$rpt2,$rpt4,$wns,$tns,$hc,$vc,$drc_v,$fep_v"
}

# ---- Public entrypoint ----
proc extract_report {args} {
  set mode ""; set outdir "."; set write_csv ""; set write_sum ""
  set i 0
  while {$i < [llength $args]} {
    set a [lindex $args $i]
    switch -- $a {
      -postRoute      { set mode "postRoute" }
      -outdir         { incr i; set outdir    [lindex $args $i] }
      -write_csv      { incr i; set write_csv [lindex $args $i] }
      -write_summary  { incr i; set write_sum [lindex $args $i] }
      default         { error "extract_report: unknown option '$a'" }
    }
    incr i
  }
  if {$mode eq ""} { error "extract_report: specify -postRoute" }

  set csv_line ""
  if {$mode eq "postRoute"} {
    set csv_line [_extract_postRoute $outdir]
  }

  # Optional outputs
  if {$write_csv ne ""} {
    set fid [open $write_csv w]
    puts $fid "stage,core_area,std_cell_area,macro_area,total_power,wire_length,wns,tns,h_cong,v_cong,drc_violations,fep_violations"
    puts $fid $csv_line
    close $fid
  }
  if {$write_sum ne ""} {
    set fh [open $write_sum w]
    puts $fh "=== Cadence Pin3DFlow – Final Metrics (postRoute) ==="
    puts $fh "Out dir     : $outdir"
    if {$write_csv ne ""} { puts $fh "CSV         : $write_csv" }
    puts $fh ""
    set f [split $csv_line ","]
    puts $fh [format "%-18s %s" "Core Area"      [lindex $f 1]]
    puts $fh [format "%-18s %s" "StdCell Area"   [lindex $f 2]]
    puts $fh [format "%-18s %s" "Macro Area"     [lindex $f 3]]
    puts $fh [format "%-18s %s" "Total Power"    [lindex $f 4]]
    puts $fh [format "%-18s %s" "Wire Length"    [lindex $f 5]]
    puts $fh [format "%-18s %s" "WNS (ns)"       [lindex $f 6]]
    puts $fh [format "%-18s %s" "TNS (ns)"       [lindex $f 7]]
    puts $fh [format "%-18s %s" "H Congestion"   [lindex $f 8]]
    puts $fh [format "%-18s %s" "V Congestion"   [lindex $f 9]]
    puts $fh [format "%-18s %s" "DRC Violations" [lindex $f 10]]
    puts $fh [format "%-18s %s" "FEP Violations" [lindex $f 11]]
    close $fh
  }
  return $csv_line
}
