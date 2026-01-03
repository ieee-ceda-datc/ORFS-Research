# SPDX-License-Identifier: BSD-3-Clause
# Copyright (c) 2019-2025, The OpenROAD Authors
#
# ============================================================
# Iterative-PARALLEL TritonPart balance driver (<=N iters, <=8 procs/iter)
#
# Goal:
#   - Minimize CUT(nets) subject to an hb_layer density-derived cut budget
#   - Run at most PAR_MAX_ITERS iterations
#   - Each iteration spawns up to min(thread_count, PAR_MAX_WORKERS, 8) workers
#   - Each worker evaluates exactly ONE balance value (PAR_BAL_ONE)
#
# Master responsibilities (runs BEFORE load_design):
#   1) Print plan at top-level (what will be swept each iteration)
#   2) Clean per-iteration workspace before spawning
#   3) Spawn workers and collect their outputs (parallel_result.tcl)
#   4) Choose global best (min cut; tie-break by smaller balance)
#   5) Write:
#       - $RESULTS_DIR/partition.parallel_plan.txt
#       - $RESULTS_DIR/partition.parallel_history.tcl
#       - $RESULTS_DIR/partition.parallel_workers.tcl
#       - $RESULTS_DIR/partition.txt
#       - $RESULTS_DIR/partition.result.tcl
#
# Worker responsibilities:
#   - load_design + read floorplan DEF
#   - compute target_cut from hb-layer virtual via density model
#   - evaluate one balance (or a fallback grid if PAR_BAL_ONE is absent)
#   - write $RUN_DIR/parallel_result.tcl (a Tcl dict)
#
# Notes:
#   - Workers are forced to single-thread (OPENROAD_NUM_THREADS=1, OMP_NUM_THREADS=1)
#   - Timing-aware TritonPart is ALWAYS enabled (no dynamic toggle).
#   - This script does NOT mine tech; hb_layer knobs are manual.
# ============================================================

source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl
source $::env(OPENROAD_SCRIPTS_DIR)/util.tcl

# ----------------------------
# time helper
# ----------------------------
proc _ts {} {
  return [clock format [clock seconds] -format "%Y-%m-%d %H:%M:%S"]
}

# ============================================================
# Global knobs (defined early so MASTER can print them)
# ============================================================

# Parallel policy
set ::PAR_MAX_WORKERS 4
set ::PAR_MAX_ITERS   2
set ::PAR_FIXED_SEED  1

# Balance search range/snap defaults (override via env PAR_BAL_LO / PAR_BAL_HI / PAR_BAL_STEP)
# NOTE: step here is used for "snap-to-grid"/dedup, NOT for static chunking.
set ::PAR_BAL_LO_DEFAULT   1.0
set ::PAR_BAL_HI_DEFAULT   5.0
set ::PAR_BAL_STEP_DEFAULT 0.5

# hb_layer density-based cut budget knobs
set ::HB_CUT_LAYER         "hb_layer"
set ::HB_LAYER_WIDTH_UM    0.8
set ::HB_LAYER_SPACING_UM  0.8
set ::HB_LAYER_RES_OHM     0.02  ;# informational only
set ::HB_VIA_DENSITY       0.5
set ::CUTS_PER_NET         1
set ::CUT_TOL              0

# Cut counting options
set ::IGNORE_NET_NAMES {VDD VSS VPWR VGND TOP_VDD TOP_VSS BOT_VDD BOT_VSS}
set ::DUMP_CUT_NETS         false
set ::CUT_NETS_DUMP_FILE    "cut_nets.list"

# Master wait timeout (seconds) for each iteration (0 => wait forever)
set ::PAR_ITER_MAX_WAIT_SEC 0

# ============================================================
# Parallel master/worker dispatcher (runs BEFORE load_design)
# ============================================================

# ---------- role detection ----------
set ::IS_WORKER 0
if {[info exists ::env(PAR_WORKER)] && $::env(PAR_WORKER) ne ""} {
  set ::IS_WORKER 1
}

# ---------- stable work root under RESULTS_DIR ----------
set ::WORK_ROOT [file join $::env(RESULTS_DIR) WORK_DIR]
file mkdir $::WORK_ROOT

# ---------- per-run dir ----------
# - worker: env(PAR_RUN_DIR)
# - fallback single-run: WORK_DIR/single_run
set ::RUN_DIR [file join $::WORK_ROOT single_run]
if {$::IS_WORKER && [info exists ::env(PAR_RUN_DIR)] && $::env(PAR_RUN_DIR) ne ""} {
  set ::RUN_DIR $::env(PAR_RUN_DIR)
}
file mkdir $::RUN_DIR

# ---------- seed ----------
if {[info exists ::env(PAR_FIXED_SEED)] && $::env(PAR_FIXED_SEED) ne ""} {
  set ::PAR_FIXED_SEED [expr {int($::env(PAR_FIXED_SEED))}]
}
set ::PAR_SEED $::PAR_FIXED_SEED
if {$::IS_WORKER && [info exists ::env(PAR_SEED)] && $::env(PAR_SEED) ne ""} {
  set ::PAR_SEED [expr {int($::env(PAR_SEED))}]
}

# ---------- openroad binary ----------
set ::OPENROAD_BIN [info nameofexecutable]
if {[info exists ::env(OPENROAD_EXE)] && $::env(OPENROAD_EXE) ne ""} {
  set ::OPENROAD_BIN $::env(OPENROAD_EXE)
}

# ---------- optional overrides ----------
if {[info exists ::env(PAR_MAX_WORKERS)] && $::env(PAR_MAX_WORKERS) ne ""} {
  set ::PAR_MAX_WORKERS [expr {int($::env(PAR_MAX_WORKERS))}]
}
if {$::PAR_MAX_WORKERS < 1} { set ::PAR_MAX_WORKERS 1 }

if {[info exists ::env(PAR_MAX_ITERS)] && $::env(PAR_MAX_ITERS) ne ""} {
  set ::PAR_MAX_ITERS [expr {int($::env(PAR_MAX_ITERS))}]
}
if {$::PAR_MAX_ITERS < 1} { set ::PAR_MAX_ITERS 1 }

if {[info exists ::env(PAR_ITER_MAX_WAIT_SEC)] && $::env(PAR_ITER_MAX_WAIT_SEC) ne ""} {
  set ::PAR_ITER_MAX_WAIT_SEC [expr {int($::env(PAR_ITER_MAX_WAIT_SEC))}]
  if {$::PAR_ITER_MAX_WAIT_SEC < 0} { set ::PAR_ITER_MAX_WAIT_SEC 0 }
}

# ============================================================
# IO helpers / safe clean
# ============================================================
proc write_text_file {outfile text} {
  set fh [open $outfile w]
  puts $fh $text
  close $fh
}

proc write_kv_file {outfile kv_dict} {
  set fh [open $outfile w]
  puts $fh $kv_dict
  close $fh
}

proc read_kv_file {outfile} {
  set fh [open $outfile r]
  set s [read $fh]
  close $fh
  return [string trim $s]
}

proc safe_clean_dir {dir root} {
  # Safety: only delete inside root (normalized).
  set nd [file normalize $dir]
  set nr [file normalize $root]
  if {$nd eq $nr} {
    utl::error PAR 970 "Refuse to delete root itself: $nd"
  }
  if {![string match "${nr}/*" $nd]} {
    utl::error PAR 971 "Refuse to delete outside WORK_ROOT: dir=$nd root=$nr"
  }
  if {[file exists $nd]} {
    file delete -force $nd
  }
  file mkdir $nd
}

# ============================================================
# Sampling utilities (iterative search)
# ============================================================

proc _clamp {x lo hi} {
  if {$x < $lo} { return $lo }
  if {$x > $hi} { return $hi }
  return $x
}

# snap to step-grid; return 3-decimal string for stable dedup/printing
proc snap_balance {x lo hi step} {
  set v [_clamp $x $lo $hi]
  if {$step > 0} {
    set k [expr {round((double($v) - double($lo))/double($step))}]
    set v [expr {double($lo) + double($k)*double($step)}]
    set v [_clamp $v $lo $hi]
  }
  return [format "%.3f" $v]
}

proc unique_balances {lst} {
  set seen [dict create]
  set out {}
  foreach b $lst {
    if {![dict exists $seen $b]} {
      dict set seen $b 1
      lappend out $b
    }
  }
  return $out
}

proc get_seen_balances_from_hist {hist} {
  set out {}
  foreach r $hist {
    if {[dict exists $r balance]} {
      lappend out [format "%.3f" [dict get $r balance]]
    }
  }
  return [lsort -real -unique $out]
}

# best by: min cut; tie-break: smaller balance
proc get_best_from_hist_min_cut {hist} {
  set best ""
  foreach r $hist {
    if {$r eq ""} { continue }
    if {$best eq ""} { set best $r; continue }
    set cut  [dict get $r cut]
    set bcut [dict get $best cut]
    if {$cut < $bcut} { set best $r; continue }
    if {$cut == $bcut} {
      set bal  [dict get $r balance]
      set bbal [dict get $best balance]
      if {$bal < $bbal} { set best $r; continue }
    }
  }
  return $best
}

# maximum-gap midpoint exploration (deterministic)
proc propose_gap_midpoint {lo hi step seen_list} {
  set pts [list [format "%.3f" $lo] [format "%.3f" $hi]]
  foreach b $seen_list { lappend pts [format "%.3f" $b] }
  set pts [lsort -real -unique $pts]

  set best_gap -1.0
  set best_mid ""
  for {set i 0} {$i < [expr {[llength $pts]-1}]} {incr i} {
    set a [expr {double([lindex $pts $i])}]
    set c [expr {double([lindex $pts [expr {$i+1}]])}]
    set gap [expr {$c - $a}]
    if {$gap > $best_gap} {
      set mid [expr {($a + $c)/2.0}]
      set mid_s [snap_balance $mid $lo $hi $step]
      if {$mid_s ne [format "%.3f" $a] && $mid_s ne [format "%.3f" $c]} {
        set best_gap $gap
        set best_mid $mid_s
      }
    }
  }
  return $best_mid
}

# propose <=batch_size balances for iteration iter (1..N)
proc propose_batch_balances {iter batch_size lo hi step hist} {
  set seen [get_seen_balances_from_hist $hist]
  set cand {}

  if {$iter == 1 || [llength $hist] == 0} {
    # Iter-1: space-filling (mid-quantiles)
    for {set i 0} {$i < $batch_size} {incr i} {
      set x [expr {double($lo) + (double($i)+0.5)*(double($hi)-double($lo))/double($batch_size)}]
      lappend cand [snap_balance $x $lo $hi $step]
    }
  } else {
    # Iter>=2: local contraction around global best + exploration midpoints
    set best [get_best_from_hist_min_cut $hist]
    set b0   [expr {double([dict get $best balance])}]

    set span [expr {double($hi) - double($lo)}]
    set r    [expr {$span / pow(2.0, double($iter))}]
    if {$r < $step} { set r $step }

    # Local points (including center)
    set offsets [list -1.0 -0.5 -0.25 0.0 0.25 0.5 1.0]
    foreach k $offsets {
      set x [expr {$b0 + double($k)*$r}]
      lappend cand [snap_balance $x $lo $hi $step]
    }

    # Exploration points from max gaps
    set g1 [propose_gap_midpoint $lo $hi $step $seen]
    if {$g1 ne ""} { lappend cand $g1 }
    if {$g1 ne ""} {
      set seen2 [concat $seen [list $g1]]
      set g2 [propose_gap_midpoint $lo $hi $step $seen2]
      if {$g2 ne ""} { lappend cand $g2 }
    }
  }

  set cand [unique_balances $cand]

  # filter out already-seen
  set out {}
  foreach b $cand {
    if {[lsearch -exact $seen $b] < 0} {
      lappend out $b
    }
    if {[llength $out] >= $batch_size} { break }
  }

  # if still short, keep adding max-gap midpoints
  while {[llength $out] < $batch_size} {
    set cur_seen [lsort -real -unique [concat $seen $out]]
    set g [propose_gap_midpoint $lo $hi $step $cur_seen]
    if {$g eq ""} { break }
    if {[lsearch -exact $cur_seen $g] < 0} {
      lappend out $g
    } else {
      break
    }
  }

  return $out
}

# ============================================================
# MASTER: iterative dispatcher
# ============================================================
proc run_parallel_master_iterative {} {
  # Determine batch size = min(thread_count, PAR_MAX_WORKERS, 8)
  set n_workers 1
  if {[info commands ::ord::thread_count] ne ""} {
    set n_workers [::ord::thread_count]
  }
  if {$n_workers < 1} { set n_workers 1 }
  if {$n_workers > $::PAR_MAX_WORKERS} { set n_workers $::PAR_MAX_WORKERS }
  if {$n_workers > 8} { set n_workers 8 }

  if {$n_workers <= 1} {
    puts [format {INFO %s: PARALLEL disabled (n_workers=%d). Fallback to single-run.} [_ts] $n_workers]
    flush stdout
    return
  }

  # Script path
  set script_path [info script]
  if {$script_path eq ""} {
    utl::error PAR 960 "Cannot locate current script path via [info script]."
  }

  # Shared floorplan DEF
  set floorplan_def [file join $::env(RESULTS_DIR) 2_2_floorplan_io.def]
  if {![file exists $floorplan_def]} {
    utl::error PAR 961 "Floorplan DEF not found: $floorplan_def"
  }

  # Balance search range + snap step
  set lo   $::PAR_BAL_LO_DEFAULT
  set hi   $::PAR_BAL_HI_DEFAULT
  set step $::PAR_BAL_STEP_DEFAULT
  if {[info exists ::env(PAR_BAL_LO)]   && $::env(PAR_BAL_LO) ne ""}   { set lo   [expr {double($::env(PAR_BAL_LO))}] }
  if {[info exists ::env(PAR_BAL_HI)]   && $::env(PAR_BAL_HI) ne ""}   { set hi   [expr {double($::env(PAR_BAL_HI))}] }
  if {[info exists ::env(PAR_BAL_STEP)] && $::env(PAR_BAL_STEP) ne ""} { set step [expr {double($::env(PAR_BAL_STEP))}] }

  # Plan file (top-level visible)
  set plan_file [file join $::env(RESULTS_DIR) partition.parallel_plan.txt]
  set plan_lines ""
  append plan_lines "PARALLEL ITERATIVE PLAN @ [_ts]\n"
  append plan_lines "OPENROAD_BIN=$::OPENROAD_BIN\n"
  append plan_lines "RESULTS_DIR=$::env(RESULTS_DIR)\n"
  append plan_lines "WORK_ROOT=$::WORK_ROOT\n"
  append plan_lines "FIXED_SEED=$::PAR_FIXED_SEED\n"
  append plan_lines "MAX_ITERS=$::PAR_MAX_ITERS\n"
  append plan_lines "BATCH_WORKERS=$n_workers\n"
  append plan_lines [format "BAL_RANGE_LO=%.3f BAL_RANGE_HI=%.3f SNAP_STEP=%.3f\n" $lo $hi $step]
  append plan_lines [format "HB_LAYER=%s WIDTH_UM=%.3f SPACING_UM=%.3f DENSITY=%.3f CUTS_PER_NET=%d CUT_TOL=%d\n" \
    $::HB_CUT_LAYER $::HB_LAYER_WIDTH_UM $::HB_LAYER_SPACING_UM $::HB_VIA_DENSITY $::CUTS_PER_NET $::CUT_TOL]
  append plan_lines "TIMING_AWARE_ALWAYS=true\n\n"

  puts [format {INFO %s: cap parallel workers: thread_count=%d -> n_workers=%d (cap=%d)} \
    [_ts] [::ord::thread_count] $n_workers $::PAR_MAX_WORKERS]
  puts [format {INFO %s: PARALLEL ITERATIVE SEARCH BEGIN} [_ts]]
  puts [format {INFO %s:   openroad_bin=%s} [_ts] $::OPENROAD_BIN]
  puts [format {INFO %s:   results_dir=%s} [_ts] $::env(RESULTS_DIR)]
  puts [format {INFO %s:   work_root=%s} [_ts] $::WORK_ROOT]
  puts [format {INFO %s:   fixed_seed=%d} [_ts] $::PAR_FIXED_SEED]
  puts [format {INFO %s:   iters=%d batch<=%d balance_range=[%.3f,%.3f] snap_step=%.3f} \
    [_ts] $::PAR_MAX_ITERS $n_workers $lo $hi $step]
  puts [format {INFO %s:   hb_knobs: layer=%s width=%.3fum spacing=%.3fum density=%.3f cuts_per_net=%d tol=%d} \
    [_ts] $::HB_CUT_LAYER $::HB_LAYER_WIDTH_UM $::HB_LAYER_SPACING_UM $::HB_VIA_DENSITY $::CUTS_PER_NET $::CUT_TOL]
  puts [format {INFO %s:   timing_aware=true (fixed)} [_ts]]
  flush stdout

  # Iteration history (list of dict)
  set hist {}

  # For per-iteration worker summaries
  set workers_summary {}

  for {set iter 1} {$iter <= $::PAR_MAX_ITERS} {incr iter} {
    set batch [propose_batch_balances $iter $n_workers $lo $hi $step $hist]
    if {[llength $batch] == 0} {
      puts [format {INFO %s: iter=%d: no new balances to evaluate; stop.} [_ts] $iter]
      flush stdout
      break
    }

    puts [format {INFO %s: ITER %d/%d PLAN: balances(%d) = %s} \
      [_ts] $iter $::PAR_MAX_ITERS [llength $batch] [join $batch ","]]
    flush stdout

    append plan_lines [format {ITER[%d]_BALANCES_COUNT=%d\n} $iter [llength $batch]]
    append plan_lines [format {ITER[%d]_BALANCES=%s\n\n} $iter [join $batch ","]]

    # Clean iteration root ONCE per iter
    set iter_root [file join $::WORK_ROOT [format {iter%d} $iter]]
    safe_clean_dir $iter_root $::WORK_ROOT

    # Spawn jobs
    set result_files {}
    set job 0
    foreach b $batch {
      incr job
      set run_dir [file join $iter_root [format {job%d_b%s} $job $b]]
      file mkdir $run_dir

      # Inject worker env
      set ::env(PAR_WORKER) 1
      set ::env(PAR_ITER) $iter
      set ::env(PAR_JOB)  $job
      set ::env(PAR_WORKER_ID) $job
      set ::env(PAR_SEED) $::PAR_FIXED_SEED
      set ::env(PAR_RUN_DIR) $run_dir
      set ::env(PAR_FLOORPLAN_DEF) $floorplan_def
      set ::env(PAR_BAL_ONE) $b

      # Force each worker to be single-threaded
      set ::env(OPENROAD_NUM_THREADS) 1
      set ::env(OMP_NUM_THREADS) 1

      set log_file [file join $run_dir openroad_partition.log]
      set res_file [file join $run_dir parallel_result.tcl]
      lappend result_files $res_file

      puts [format {INFO %s: spawn iter=%d job=%d balance=%s run_dir=%s} [_ts] $iter $job $b $run_dir]
      flush stdout

      set cmd [list $::OPENROAD_BIN -no_init -exit -threads 1 $script_path]
      set pids [exec {*}$cmd > $log_file &]
      puts [format {INFO %s: spawned iter=%d job=%d balance=%s pid=%s log=%s} \
        [_ts] $iter $job $b $pids $log_file]
      flush stdout
    }

    puts [format {INFO %s: ITER %d: waiting for %d jobs...} [_ts] $iter [llength $result_files]]
    flush stdout

    set t0 [clock seconds]
    while {1} {
      set all_done 1
      set missing {}
      foreach rf $result_files {
        if {![file exists $rf]} {
          set all_done 0
          lappend missing $rf
        }
      }
      if {$all_done} { break }

      if {$::PAR_ITER_MAX_WAIT_SEC > 0} {
        set dt [expr {[clock seconds] - $t0}]
        if {$dt >= $::PAR_ITER_MAX_WAIT_SEC} {
          puts [format {ERROR %s: iter=%d timeout waiting jobs (missing=%d)} [_ts] $iter [llength $missing]]
          foreach m $missing { puts "ERROR missing_result: $m" }
          flush stdout
          exit 2
        }
      }
      after 200
    }

    # Read results
    set round_results {}
    foreach rf $result_files {
      set txt [read_kv_file $rf]
      if {$txt eq ""} {
        puts [format {WARN %s: empty worker result file: %s} [_ts] $rf]
        flush stdout
        continue
      }
      if {[catch {dict size $txt} _]} {
        puts [format {WARN %s: invalid dict in %s} [_ts] $rf]
        puts "WARN raw: $txt"
        flush stdout
        continue
      }

      lappend round_results $txt
      lappend hist $txt

      set wid    [dict get $txt worker_id]
      set seed   [dict get $txt seed]
      set bal    [dict get $txt balance]
      set cut    [dict get $txt cut]
      set feas   [dict get $txt feasible]
      set diff   [dict get $txt abs_diff]
      set target [dict get $txt target]
      set tol    [dict get $txt tol]
      set sol    [dict get $txt solution_file]
      lappend workers_summary [dict create \
        iter $iter worker_id $wid seed $seed balance $bal cut $cut feasible $feas \
        abs_diff $diff target $target tol $tol solution_file $sol]
    }

    set round_best  [get_best_from_hist_min_cut $round_results]
    set global_best [get_best_from_hist_min_cut $hist]

    puts [format {INFO %s: ITER %d DONE: round_best balance=%.4f cut=%d} \
      [_ts] $iter [dict get $round_best balance] [dict get $round_best cut]]
    puts [format {INFO %s: GLOBAL BEST: balance=%.4f cut=%d} \
      [_ts] [dict get $global_best balance] [dict get $global_best cut]]
    flush stdout

    if {[dict get $global_best cut] == 0} {
      puts [format {INFO %s: cut=0 reached; stop early at iter=%d} [_ts] $iter]
      flush stdout
      break
    }
  }

  # Write plan
  write_text_file $plan_file $plan_lines
  puts [format {INFO %s: PARALLEL PLAN written: %s} [_ts] $plan_file]
  flush stdout

  # Write worker summary + history
  set workers_file [file join $::env(RESULTS_DIR) partition.parallel_workers.tcl]
  write_kv_file $workers_file $workers_summary

  set hist_file [file join $::env(RESULTS_DIR) partition.parallel_history.tcl]
  write_kv_file $hist_file $hist

  puts [format {INFO %s: wrote workers summary: %s} [_ts] $workers_file]
  puts [format {INFO %s: wrote history: %s} [_ts] $hist_file]
  flush stdout

  # Pick final best and materialize final outputs
  set best [get_best_from_hist_min_cut $hist]
  if {$best eq ""} {
    utl::error PAR 962 "Iterative runs produced no valid result."
  }

  set best_sol [dict get $best solution_file]
  set dst_sol  [file join $::env(RESULTS_DIR) partition.txt]
  file copy -force $best_sol $dst_sol

  set dst_sum [file join $::env(RESULTS_DIR) partition.result.tcl]
  write_kv_file $dst_sum $best

  puts [format {INFO %s: PARALLEL FINAL BEST: balance=%.4f cut=%d worker_id=%s} \
    [_ts] [dict get $best balance] [dict get $best cut] [dict get $best worker_id]]
  puts [format {INFO %s: final_solution=%s} [_ts] $dst_sol]
  puts [format {INFO %s: summary=%s} [_ts] $dst_sum]
  flush stdout

  exit
}

# Master executes BEFORE load_design
if {!$::IS_WORKER} {
  run_parallel_master_iterative
}

# ============================================================
# Worker / single-run flow starts here
# ============================================================

load_design 2_2_floorplan_io.v 1_synth.sdc "Start Triton Partitioning"

# Stable DEF input (workers share same read-only DEF)
set fp_def [file join $::env(RESULTS_DIR) 2_2_floorplan_io.def]
if {[info exists ::env(PAR_FLOORPLAN_DEF)] && $::env(PAR_FLOORPLAN_DEF) ne ""} {
  set fp_def $::env(PAR_FLOORPLAN_DEF)
}
read_def -floorplan_initialize $fp_def

# ============================================================
# ODB helpers / die / budget
# ============================================================
proc _get_dbu {} {
  set db [ord::get_db]
  if {$db eq "NULL"} { utl::error PAR 910 "No db." }
  set tech [odb::dbDatabase_getTech $db]
  if {$tech eq "NULL"} { utl::error PAR 911 "No tech." }
  return [odb::dbTech_getDbUnitsPerMicron $tech]
}

proc _poly_bbox_area_dbu2 {coords} {
  # coords: {x1 y1 x2 y2 ...} in DBU
  set n [llength $coords]
  if {$n < 6 || ($n % 2) != 0} {
    utl::error PAR 912 "Invalid polygon die coords (need even count >= 6): $coords"
  }

  set minx 1e99
  set miny 1e99
  set maxx -1e99
  set maxy -1e99

  # shoelace (area2 = 2*area) in DBU^2
  set area2 0.0

  set x0 [expr {double([lindex $coords 0])}]
  set y0 [expr {double([lindex $coords 1])}]
  set x_prev $x0
  set y_prev $y0

  set minx $x0; set maxx $x0
  set miny $y0; set maxy $y0

  for {set i 2} {$i < $n} {incr i 2} {
    set x [expr {double([lindex $coords $i])}]
    set y [expr {double([lindex $coords [expr {$i+1}]])}]

    if {$x < $minx} { set minx $x }
    if {$x > $maxx} { set maxx $x }
    if {$y < $miny} { set miny $y }
    if {$y > $maxy} { set maxy $y }

    set area2 [expr {$area2 + ($x_prev*$y - $x*$y_prev)}]
    set x_prev $x
    set y_prev $y
  }

  set area2 [expr {$area2 + ($x_prev*$y0 - $x0*$y_prev)}]
  set area2 [expr {abs($area2)}]

  return [list [expr {int($minx)}] [expr {int($miny)}] [expr {int($maxx)}] [expr {int($maxy)}] $area2]
}

proc _get_die_rect_coords_dbu {die_obj} {
  # Case A: list
  if {[llength $die_obj] >= 4} {
    # A1: {lx ly ux uy}
    if {[llength $die_obj] == 4} {
      set lx [lindex $die_obj 0]
      set ly [lindex $die_obj 1]
      set ux [lindex $die_obj 2]
      set uy [lindex $die_obj 3]
      if {[string is integer -strict $lx] && [string is integer -strict $ly] &&
          [string is integer -strict $ux] && [string is integer -strict $uy]} {
        set w [expr {$ux - $lx}]
        set h [expr {$uy - $ly}]
        set area2 [expr {2.0 * double($w) * double($h)}]
        return [list $lx $ly $ux $uy $area2]
      }
    }

    # A2: polygon list {x1 y1 x2 y2 ...}
    set n [llength $die_obj]
    if {$n >= 6 && ($n % 2) == 0} {
      return [_poly_bbox_area_dbu2 $die_obj]
    }
  }

  # Case B: odb::Rect
  if {![catch {odb::Rect_xMin $die_obj} lx] &&
      ![catch {odb::Rect_yMin $die_obj} ly] &&
      ![catch {odb::Rect_xMax $die_obj} ux] &&
      ![catch {odb::Rect_yMax $die_obj} uy]} {
    set w [expr {$ux - $lx}]
    set h [expr {$uy - $ly}]
    set area2 [expr {2.0 * double($w) * double($h)}]
    return [list $lx $ly $ux $uy $area2]
  }

  # Case C: odb::dbBox
  if {![catch {odb::dbBox_xMin $die_obj} lx] &&
      ![catch {odb::dbBox_yMin $die_obj} ly] &&
      ![catch {odb::dbBox_xMax $die_obj} ux] &&
      ![catch {odb::dbBox_yMax $die_obj} uy]} {
    set w [expr {$ux - $lx}]
    set h [expr {$uy - $ly}]
    set area2 [expr {2.0 * double($w) * double($h)}]
    return [list $lx $ly $ux $uy $area2]
  }

  # Case D: fallback to block bbox if available
  set block [ord::get_db_block]
  if {$block ne "NULL"} {
    if {![catch {odb::dbBlock_getBBox $block} bb] && $bb ne "NULL"} {
      if {![catch {odb::dbBox_xMin $bb} lx] &&
          ![catch {odb::dbBox_yMin $bb} ly] &&
          ![catch {odb::dbBox_xMax $bb} ux] &&
          ![catch {odb::dbBox_yMax $bb} uy]} {
        set w [expr {$ux - $lx}]
        set h [expr {$uy - $ly}]
        set area2 [expr {2.0 * double($w) * double($h)}]
        return [list $lx $ly $ux $uy $area2]
      }
    }
  }

  utl::error PAR 912 "Unsupported die area object type from dbBlock_getDieArea."
}

proc get_die_wh_area_um2 {} {
  set block [ord::get_db_block]
  if {$block eq "NULL"} { utl::error PAR 900 "No db block." }

  set dbu [_get_dbu]
  set die_obj [odb::dbBlock_getDieArea $block]

  # returns {lx ly ux uy area2_dbu2}
  lassign [_get_die_rect_coords_dbu $die_obj] lx ly ux uy area2_dbu2

  set dx_dbu [expr {$ux - $lx}]
  set dy_dbu [expr {$uy - $ly}]

  set w_um  [expr {double($dx_dbu) / double($dbu)}]
  set h_um  [expr {double($dy_dbu) / double($dbu)}]

  # polygon-aware area: area_um2 = (area2/2)/dbu^2
  set a_um2 [expr {(double($area2_dbu2) * 0.5) / double($dbu*$dbu)}]

  return [list $w_um $h_um $a_um2]
}

proc estimate_max_hb_cuts_from_pitch {die_w_um die_h_um die_area_um2 pitch_x pitch_y density} {
  if {$pitch_x <= 0.0 || $pitch_y <= 0.0} {
    utl::error PAR 902 "Invalid pitch (<=0)."
  }
  if {$density < 0.0 || $density > 1.0} {
    utl::error PAR 904 "HB_VIA_DENSITY must be within [0, 1]."
  }

  # bbox-based counts (for reporting only)
  set nx [expr {int(floor(double($die_w_um) / double($pitch_x)))}]
  set ny [expr {int(floor(double($die_h_um) / double($pitch_y)))}]
  if {$nx < 0} { set nx 0 }
  if {$ny < 0} { set ny 0 }

  # polygon/area-based grid (recommended)
  set pitch_a [expr {double($pitch_x) * double($pitch_y)}]
  set grid_area [expr {int(floor(double($die_area_um2) / $pitch_a))}]
  if {$grid_area < 0} { set grid_area 0 }

  set nmax [expr {int(floor(double($density) * double($grid_area)))}]
  return [list $nx $ny $grid_area $nmax]
}

# ============================================================
# solution file parsing (instance_name -> partition_id)
# ============================================================
proc read_solution_part_map_kv {solution_file} {
  if {![file exists $solution_file]} {
    utl::error PAR 930 "Solution file not found: $solution_file"
  }
  set fh [open $solution_file r]
  set kv {}
  set lines 0
  set kept  0
  while {[gets $fh line] >= 0} {
    incr lines
    set s [string trim $line]
    if {$s eq ""} { continue }
    if {[string match "#*" $s]}  { continue }
    if {[string match "//*" $s]} { continue }

    set toks [split $s]
    if {[llength $toks] < 2} { continue }

    set name [lindex $toks 0]
    set pid  [lindex $toks end]
    if {![string is integer -strict $pid]} { continue }
    if {$pid != 0 && $pid != 1} { continue }

    lappend kv $name $pid
    incr kept
  }
  close $fh
  puts [format {INFO %s: parsed solution_file=%s lines=%d mapped_vertices=%d} \
    [_ts] $solution_file $lines $kept]
  flush stdout
  return $kv
}

# ============================================================
# Worker: compute target_cut (density budget)
# ============================================================
puts [format {INFO %s: Using manual CUT-layer params for %s (no tech mining)} [_ts] $::HB_CUT_LAYER]
puts [format {INFO %s: %s WIDTH=%.3fum SPACING=%.3fum RES=%.4fohm} \
  [_ts] $::HB_CUT_LAYER $::HB_LAYER_WIDTH_UM $::HB_LAYER_SPACING_UM $::HB_LAYER_RES_OHM]
flush stdout

set xcut    $::HB_LAYER_WIDTH_UM
set ycut    $::HB_LAYER_WIDTH_UM
set pitch_x [expr {$::HB_LAYER_WIDTH_UM + $::HB_LAYER_SPACING_UM}]
set pitch_y [expr {$::HB_LAYER_WIDTH_UM + $::HB_LAYER_SPACING_UM}]
set pitch_a [expr {$pitch_x * $pitch_y}]
set cut_a   [expr {$xcut * $ycut}]

puts [format {INFO %s: Virtual HB via: cut=%.3fx%.3f pitch=%.3fx%.3f pitchA=%.6f cutA=%.6f} \
  [_ts] $xcut $ycut $pitch_x $pitch_y $pitch_a $cut_a]
flush stdout

lassign [get_die_wh_area_um2] die_w die_h die_area
puts [format {INFO %s: DIE w=%.3fum h=%.3fum area=%.3fum^2} [_ts] $die_w $die_h $die_area]
flush stdout

lassign [estimate_max_hb_cuts_from_pitch $die_w $die_h $die_area $pitch_x $pitch_y $::HB_VIA_DENSITY] nx ny grid nmax
set max_cut_nets [expr {int(floor(double($nmax) / double($::CUTS_PER_NET)))}]

puts [format {STAT %s: HB_VIA_DENSITY=%.2f grid=%dx%d=%d max_hb_cuts=%d CUTS_PER_NET=%d => CUT_NET_BUDGET=%d} \
  [_ts] $::HB_VIA_DENSITY $nx $ny $grid $nmax $::CUTS_PER_NET $max_cut_nets]
flush stdout

# ============================================================
# Partitioning + Cut counting
# ============================================================
proc run_triton_part {solution_file balance seed} {
  # Always enable timing-aware partitioning.
  puts [format {INFO %s: run triton_part_design balance=%.4f seed=%d timing_aware=true -> %s} \
    [_ts] $balance $seed $solution_file]
  flush stdout

  triton_part_design \
    -num_parts 2 \
    -balance_constraint $balance \
    -seed $seed \
    -solution_file $solution_file \
    -timing_aware_flag true

  puts [format {INFO %s: triton_part_design finished} [_ts]]
  flush stdout
}

proc calc_cut_nets_from_solution {solution_file {ignore_net_names {}}} {
  puts [format {INFO %s: >>> enter calc_cut_nets_from_solution sol=%s} [_ts] $solution_file]
  flush stdout

  set block [ord::get_db_block]
  if {$block eq "NULL"} { utl::error PAR 940 "No db block." }

  array set part {}
  array set part [read_solution_part_map_kv $solution_file]

  set cut_nets 0
  set nets [odb::dbBlock_getNets $block]
  puts [format {INFO %s: nets_total=%d} [_ts] [llength $nets]]
  flush stdout

  set miss_inst 0
  set seen_inst 0
  set cut_net_names {}

  foreach net $nets {
    set nname [odb::dbNet_getName $net]
    if {[llength $ignore_net_names] > 0 && [lsearch -exact $ignore_net_names $nname] >= 0} {
      continue
    }

    set seen0 0
    set seen1 0
    foreach iterm [odb::dbNet_getITerms $net] {
      set inst  [odb::dbITerm_getInst $iterm]
      set iname [odb::dbInst_getName $inst]
      incr seen_inst

      if {![info exists part($iname)]} {
        incr miss_inst
        continue
      }
      set pid $part($iname)

      if {$pid == 0} { set seen0 1 }
      if {$pid == 1} { set seen1 1 }
      if {$seen0 && $seen1} { break }
    }

    if {$seen0 && $seen1} {
      incr cut_nets
      if {$::DUMP_CUT_NETS} { lappend cut_net_names $nname }
    }
  }

  if {$::DUMP_CUT_NETS} {
    set out [file join $::RUN_DIR $::CUT_NETS_DUMP_FILE]
    set fh [open $out w]
    foreach n $cut_net_names { puts $fh $n }
    close $fh
    puts [format {INFO %s: dumped cut net names to %s (count=%d)} [_ts] $out [llength $cut_net_names]]
    flush stdout
  }

  puts [format {INFO %s: <<< exit calc_cut_nets_from_solution cut_nets=%d iterms_seen=%d inst_missing_in_solution=%d} \
    [_ts] $cut_nets $seen_inst $miss_inst]
  flush stdout
  return $cut_nets
}

proc calc_upper_bottom_size {} {
  set block [ord::get_db_block]
  if {$block eq "NULL"} { utl::error PAR 901 "No db block." }

  set dbu [_get_dbu]
  if {![info exists ::_MASTER_AREA_UM2]} { array set ::_MASTER_AREA_UM2 {} }

  set bottom_area 0.0
  set upper_area  0.0
  set bottom_cnt  0
  set upper_cnt   0

  foreach inst [odb::dbBlock_getInsts $block] {
    set prop [odb::dbIntProperty_find $inst "partition_id"]
    if {$prop eq "NULL"} { continue }
    set pid [odb::dbIntProperty_getValue $prop]
    if {$pid != 0 && $pid != 1} { continue }

    set master [odb::dbInst_getMaster $inst]
    set mname  [odb::dbMaster_getName $master]

    if {[info exists ::_MASTER_AREA_UM2($mname)]} {
      set area_um2 $::_MASTER_AREA_UM2($mname)
    } else {
      set w [odb::dbMaster_getWidth  $master]
      set h [odb::dbMaster_getHeight $master]
      set area_um2 [expr {double($w)*double($h)/double($dbu*$dbu)}]
      set ::_MASTER_AREA_UM2($mname) $area_um2
    }

    if {$pid == 1} {
      set bottom_area [expr {$bottom_area + $area_um2}]
      incr bottom_cnt
    } else {
      set upper_area [expr {$upper_area + $area_um2}]
      incr upper_cnt
    }
  }

  return [list $bottom_area $bottom_cnt $upper_area $upper_cnt]
}

proc report_upper_bottom_and_cut {balance cut} {
  lassign [calc_upper_bottom_size] b_area b_cnt u_area u_cnt
  set tot_area [expr {$b_area + $u_area}]
  if {$tot_area > 0} {
    set b_pct [expr {100.0*$b_area/$tot_area}]
    set u_pct [expr {100.0*$u_area/$tot_area}]
  } else {
    set b_pct 0.0
    set u_pct 0.0
  }

  puts [format {INFO %s: STAT balance=%.4f CUT(nets)=%d bottom: area=%.3f um^2 (%.2f%%) inst=%d upper: area=%.3f um^2 (%.2f%%) inst=%d} \
    [_ts] $balance $cut $b_area $b_pct $b_cnt $u_area $u_pct $u_cnt]
  flush stdout
}

# ============================================================
# Balance evaluation
# ============================================================
proc eval_balance_grid {out_dir target_cut seed balances} {
  puts [format {INFO %s: >>> enter eval_balance_grid out_dir=%s target=%d seed=%d balances=%d} \
    [_ts] $out_dir $target_cut $seed [llength $balances]]
  flush stdout
  file mkdir $out_dir

  set best_balance ""
  set best_cut 1e99
  set best_sol ""

  foreach b $balances {
    set bal [expr {double($b)}]
    set sol [file join $out_dir [format {part.ub%.3f.seed%d.txt} $bal $seed]]

    run_triton_part $sol $bal $seed
    set cut [calc_cut_nets_from_solution $sol $::IGNORE_NET_NAMES]
    report_upper_bottom_and_cut $bal $cut

    # Local "best" for this worker: minimize abs_diff; tie-break by smaller cut
    set diff [expr {abs($cut - $target_cut)}]
    set best_diff [expr {abs($best_cut - $target_cut)}]
    if {$diff < $best_diff || ($diff == $best_diff && $cut < $best_cut)} {
      set best_cut $cut
      set best_balance $bal
      set best_sol $sol
      puts [format {INFO %s: update best -> balance=%.4f cut=%d sol=%s} [_ts] $best_balance $best_cut $best_sol]
      flush stdout
    }

    # Early exit if feasible
    if {$cut <= ($target_cut + $::CUT_TOL)} {
      puts [format {INFO %s: feasible met at balance=%.4f cut=%d target=%d tol=%d => stop} \
        [_ts] $bal $cut $target_cut $::CUT_TOL]
      flush stdout
      break
    }
  }

  puts [format {INFO %s: <<< exit eval_balance_grid best_balance=%.4f best_cut=%d best_sol=%s} \
    [_ts] $best_balance $best_cut $best_sol]
  flush stdout
  return [list $best_balance $best_cut $best_sol]
}

# ============================================================
# Worker Driver (single balance per worker)
# ============================================================
puts [format {INFO %s: starting worker balance evaluation...} [_ts]]
flush stdout

set target_cut $max_cut_nets
set out_dir $::RUN_DIR
set seed $::PAR_SEED

# Determine balances:
#   - Worker: PAR_BAL_ONE is a single point assigned by master
#   - Fallback: if PAR_BAL_ONE is absent, evaluate a local grid (debug)
set balances {}
if {[info exists ::env(PAR_BAL_ONE)] && $::env(PAR_BAL_ONE) ne ""} {
  set balances [list $::env(PAR_BAL_ONE)]
} else {
  set bal_lo   $::PAR_BAL_LO_DEFAULT
  set bal_hi   $::PAR_BAL_HI_DEFAULT
  set bal_step $::PAR_BAL_STEP_DEFAULT
  if {[info exists ::env(PAR_BAL_LO)]   && $::env(PAR_BAL_LO) ne ""}   { set bal_lo   [expr {double($::env(PAR_BAL_LO))}] }
  if {[info exists ::env(PAR_BAL_HI)]   && $::env(PAR_BAL_HI) ne ""}   { set bal_hi   [expr {double($::env(PAR_BAL_HI))}] }
  if {[info exists ::env(PAR_BAL_STEP)] && $::env(PAR_BAL_STEP) ne ""} { set bal_step [expr {double($::env(PAR_BAL_STEP))}] }
  set balances {}
  set x $bal_lo
  while {$x <= ($bal_hi + 1.0e-9)} {
    lappend balances [format "%.3f" $x]
    set x [expr {$x + $bal_step}]
  }
}

set result [eval_balance_grid $out_dir $target_cut $seed $balances]
puts [format {INFO %s: worker grid result = %s} [_ts] $result]
flush stdout

lassign $result best_balance best_cut best_sol

# Worker writes compact result for master aggregation
if {$::IS_WORKER} {
  set feasible [expr {$best_cut <= ($target_cut + $::CUT_TOL)}]
  set abs_diff [expr {abs($best_cut - $target_cut)}]

  set wid "NA"
  if {[info exists ::env(PAR_WORKER_ID)] && $::env(PAR_WORKER_ID) ne ""} { set wid $::env(PAR_WORKER_ID) }

  set iter "NA"
  if {[info exists ::env(PAR_ITER)] && $::env(PAR_ITER) ne ""} { set iter $::env(PAR_ITER) }

  set job "NA"
  if {[info exists ::env(PAR_JOB)] && $::env(PAR_JOB) ne ""} { set job $::env(PAR_JOB) }

  set res_dict [dict create \
    iter $iter \
    job  $job \
    worker_id $wid \
    seed $seed \
    target $target_cut \
    tol $::CUT_TOL \
    feasible $feasible \
    abs_diff $abs_diff \
    balance $best_balance \
    cut $best_cut \
    solution_file $best_sol \
    run_dir $::RUN_DIR]

  set res_file [file join $::RUN_DIR parallel_result.tcl]
  write_kv_file $res_file $res_dict
  puts [format {INFO %s: worker done iter=%s job=%s wid=%s seed=%d wrote %s} [_ts] $iter $job $wid $seed $res_file]
  flush stdout
  exit
}

# Single-run fallback: materialize final outputs
set final_sol [file join $::env(RESULTS_DIR) partition.txt]
file copy -force $best_sol $final_sol

set final_sum [file join $::env(RESULTS_DIR) partition.result.tcl]
set feasible [expr {$best_cut <= ($target_cut + $::CUT_TOL)}]
set abs_diff [expr {abs($best_cut - $target_cut)}]
set sum_dict [dict create \
  worker_id "single" \
  seed $seed \
  target $target_cut \
  tol $::CUT_TOL \
  feasible $feasible \
  abs_diff $abs_diff \
  balance $best_balance \
  cut $best_cut \
  solution_file $best_sol \
  run_dir $::RUN_DIR]
write_kv_file $final_sum $sum_dict

puts [format {INFO %s: final_solution=%s} [_ts] $final_sol]
puts [format {INFO %s: summary=%s} [_ts] $final_sum]
flush stdout

exit
