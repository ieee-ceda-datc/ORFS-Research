########################################################################
# 3D PDN for Innovus (aligning with OpenROAD 3D PDN logic, no renaming)
# - Part 0: helper procs (box flatten / row rebuild / tier inst query)
# - Part 1: BOT PG connect + M1 rails + M4/M7 mesh
# - Part 2: rebuild upper rows + TOP PG connect + M1_m/M2_m rails + M5_m/M6_m mesh
########################################################################

puts "INFO: Start 3D PDN (BOT then TOP)..."

########################################################################
# Utility: flatten box to "lx ly ux uy"
########################################################################
proc box_flat4 {box} {
  if {[llength $box] == 1} {
    set box [lindex $box 0]
  }
  if {[llength $box] == 2 && [llength [lindex $box 0]] == 2} {
    set ll [lindex $box 0]
    set ur [lindex $box 1]
    return [list [lindex $ll 0] [lindex $ll 1] [lindex $ur 0] [lindex $ur 1]]
  }
  return $box
}

########################################################################
# Utility: rebuild rows for a given site (upper tier)
########################################################################
proc rebuild_rows_for_site {site_name {out_def ""}} {
  if {$site_name eq ""} {
    puts "ERROR: rebuild_rows_for_site: empty site_name."
    return
  }

  set dieBoxF  [box_flat4 [dbGet top.fPlan.box]]
  set ioBoxF   [box_flat4 [dbGet top.fPlan.ioBox]]
  set coreBoxF [box_flat4 [dbGet top.fPlan.coreBox]]
  set bList [concat $dieBoxF $ioBoxF $coreBoxF]

  puts "INFO: dieBox  = $dieBoxF"
  puts "INFO: ioBox   = $ioBoxF"
  puts "INFO: coreBox = $coreBoxF"
  puts "INFO: Rebuilding rows with site $site_name"

  deleteRow -all
  floorPlan -b $bList -siteOnly $site_name

  if {$out_def ne ""} {
    defOut -floorplan $out_def
    puts "INFO: Wrote floorplan DEF with site $site_name : $out_def"
  }
}

########################################################################
# Utility: query bottom / upper tier instances by master name
#   - bottom tier: cell master name matches "*_bottom"
#   - upper  tier: cell master name matches "*_upper"
# NOTE: 使用 ABK 风格：dbGet <path> <pattern> -p2，再取 .name
########################################################################
proc get_bottom_tier_insts {} {
  # pointers to insts whose cell.name matches "*_bottom"
  set inst_ptrs [dbGet top.insts.cell.name "*_bottom" -p2]
  if {[llength $inst_ptrs] == 0} {
    return ""
  }
  # return instance names
  return [dbGet $inst_ptrs.name]
}

proc get_upper_tier_insts {} {
  # pointers to insts whose cell.name matches "*_upper"
  set inst_ptrs [dbGet top.insts.cell.name "*_upper" -p2]
  if {[llength $inst_ptrs] == 0} {
    return ""
  }
  return [dbGet $inst_ptrs.name]
}

########################################################################
# Part 0. NOTE: No rename — we keep original instance names
########################################################################

puts "INFO: Skip renaming instances; use master name (*_upper/*_bottom) to classify tiers."

########################################################################
# Part 1. BOT tier: BOT_VDD / BOT_VSS
########################################################################

puts "INFO: === Part 1: BOT tier PDN (BOT_VDD / BOT_VSS) ==="

set minCh 2

# 1) Unplace core cells and cut rows (same as ABK 2D)
dbset [dbget top.insts.cell.subClass core -p2 ].pStatus unplaced
finishFloorplan -fillPlaceBlockage hard $minCh
cutRow
finishFloorplan -fillPlaceBlockage hard $minCh

# Remove temporary place blockages
set fp_blk [dbGet top.fPlan.pBlkgs.name finishfp_place_blkg_* -p1]
if {[llength $fp_blk] > 0} {
  deselectAll
  select_obj $fp_blk
  deleteSelectedFromFPlan
  deselectAll
}

# 2) Global net connections for bottom tier only
set nets_bot [list BOT_VDD BOT_VSS]
clearGlobalNets

set bot_insts [get_bottom_tier_insts]
if {[llength $bot_insts] == 0} {
  puts "WARN: No *_bottom masters found. BOT PG connections will be empty."
} else {
  puts "INFO: BOT tier instance count [llength $bot_insts]"
  foreach inst $bot_insts {
    # inst 是实例名，逐个连 PG pin
    globalNetConnect BOT_VDD -type pgpin -pin VDD -inst $inst -override
    globalNetConnect BOT_VSS -type pgpin -pin VSS -inst $inst -override
  }
}

# Tie cells behavior (只 tie 到 BOT_VDD / BOT_VSS)
globalNetConnect BOT_VDD -type tiehi -all -override
globalNetConnect BOT_VSS -type tielo -all -override

puts "INFO: BOT globalNetConnect done."

# 3) Via generation (ABK style)
setGenerateViaMode -auto true
generateVias
editDelete -type Special -net $nets_bot
setViaGenMode -ignore_DRC false
setViaGenMode -optimize_cross_via true
setViaGenMode -allow_wire_shape_change false
setViaGenMode -extend_out_wire_end false
setViaGenMode -viarule_preference generated

# 4) Follow-pin rails for BOT on M1
sroute -nets {BOT_VDD BOT_VSS} \
       -connect {corePin} \
       -corePinLayer {M1} \
       -corePinTarget {firstAfterRowEnd}

# 5) BOT mesh on M4/M7
setAddStripeMode -orthogonal_only true -ignore_DRC false
setAddStripeMode -over_row_extension true
setAddStripeMode -extend_to_closest_target area_boundary
setAddStripeMode -inside_cell_only false
setAddStripeMode -route_over_rows_only false
setAddStripeMode -stacked_via_bottom_layer M1 -stacked_via_top_layer M7

addStripe -layer M4 \
          -direction vertical \
          -nets $nets_bot \
          -width 0.84 \
          -spacing 0.84 \
          -start_offset 0.0 \
          -set_to_set_distance 20.16

addStripe -layer M7 \
          -direction horizontal \
          -nets $nets_bot \
          -width 2.4 \
          -spacing 2.4 \
          -start_offset 2.0 \
          -set_to_set_distance 40.0

puts "INFO: BOT PDN (M1 rails + M4/M7 mesh) completed."

########################################################################
# Part 2. TOP tier: TOP_VDD / BOT_VSS
########################################################################

puts "INFO: === Part 2: TOP tier PDN (TOP_VDD / BOT_VSS) ==="

# 1) Rebuild rows for upper site (mirroring OpenROAD or_rebuild_rows_for_site)
if {[info exists ::env(UPPER_SITE)]} {
  puts "INFO: Rebuilding rows for upper tier site = $::env(UPPER_SITE)"
  rebuild_rows_for_site $::env(UPPER_SITE)
} else {
  puts "WARN: UPPER_SITE is not set; skip upper row rebuild."
}

# 2) Global net connections for *_upper instances
set nets_top [list TOP_VDD BOT_VSS]

# 保留 BOT 的 global nets; 不要 clearGlobalNets
set top_insts [get_upper_tier_insts]
if {[llength $top_insts] == 0} {
  puts "WARN: No *_upper masters found. TOP PG connections will be empty."
} else {
  puts "INFO: TOP tier instance count [llength $top_insts]"
  foreach inst $top_insts {
    globalNetConnect TOP_VDD -type pgpin -pin VDD -inst $inst -override
    globalNetConnect BOT_VSS -type pgpin -pin VSS -inst $inst -override
  }
}

# 如需，也可以给 TOP_VDD 单独 tiehi（可选）
globalNetConnect TOP_VDD -type tiehi -all -override

puts "INFO: TOP globalNetConnect done."

# 3a) Follow-pin rails for TOP on M1_m (where PG pins actually exist)
sroute -nets {TOP_VDD BOT_VSS} \
       -connect {corePin} \
       -corePinLayer {M1_m} \
       -corePinTarget {firstAfterRowEnd}

# 3b) Duplicate M1_m rails to M2_m to emulate multi-layer rails (like ORFS followpins on M2_m)
deselectAll
editSelect -layer M1_m -net $nets_top
# 如果 rails 是竖向，可以改为 -layer_vertical
editDuplicate -layer_horizontal M2_m
deselectAll

# 调整 M2_m rail 宽度（和 OpenROAD 一致，比如 0.018）
deselectAll
editSelect -layer M2_m -net $nets_top
editResize -to 0.018 -side high -direction y -keep_center_line 1
deselectAll

# 4) TOP mesh on M5_m / M6_m (no forced stacked-via to avoid IMPPP-537)
setAddStripeMode -orthogonal_only true -ignore_DRC false
setAddStripeMode -over_row_extension true
setAddStripeMode -extend_to_closest_target area_boundary
setAddStripeMode -inside_cell_only false
setAddStripeMode -route_over_rows_only false

addStripe -layer M5_m \
          -direction vertical \
          -nets $nets_top \
          -width 0.12 \
          -spacing 0.072 \
          -start_offset 0.300 \
          -set_to_set_distance 5.4

addStripe -layer M6_m \
          -direction vertical \
          -nets $nets_top \
          -width 0.288 \
          -spacing 0.096 \
          -start_offset 0.513 \
          -set_to_set_distance 5.4

puts "INFO: 3D PDN generation (BOT + TOP) finished."

# error "3D_PDN_SCRIPT_FINISHED"
