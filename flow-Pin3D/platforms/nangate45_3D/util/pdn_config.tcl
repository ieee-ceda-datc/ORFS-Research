#################################################################
# pdn_3d_mirror_1_20.tcl
# 3D symmetric PDN script (homogeneous process)
#   - M1..M10 are mirrored to M20..M11
#   - We only use:
#       * Bottom die : M1 (rails), M4 / M7 (mesh)
#       * Top die    : M20 (rails), M17 / M14 (mesh)
#   - Other layers in the config are ignored by this script.
#
#   PG nets:
#     Bottom : BOT_VDD / BOT_VSS
#     Top    : TOP_VDD / TOP_VSS   (independent; change TOP_VSS->BOT_VSS
#                                   below if you want shared ground)
#################################################################

puts "INFO: \[pdn_3d_mirror_1_20\] Start symmetric 3D PDN (M1<->M20, M4<->M17, M7<->M14)..."

# ===== Basic floorplan channel size =====
set minCh 5

# ===== Layer / geometry configuration =====
#           M1  M4  M5  M6  M7  M10 \
#           M14 M15 M16 M17 M20
set layers  "M1  M4  M5  M6  M7  M10 \
             M14 M15 M16 M17 M20"
set width   "0       0.84    0.84    0.84    2.4     3.20  \
             2.4     0.84    0.84    0.84    0"
set pitch   "0       20.16   10.08   10.08   40      32    \
             40      10.08   10.08   20.16   0"
set spacing "0       0.56    0.56    0.56    1.6     1.6   \
             1.6     0.56    0.56    0.56    0"
set ldir    "0       1       0       1       0       1     \
             0       1       0       1       0"
set isMacro "0       0       1       1       0       0     \
             0       1       1       0       0"
set isBM    "1       1       0       0       0       0     \
             0       0       0       1       1"
set isAM    "0       0       1       1       1       1     \
             1       1       1       0       0"
set isFP    "1       0       0       0       0       0     \
             0       0       0       0       1"
set soffset "0       2       2       2       2       2     \
             2       2       2       2       0"
set addch   "0       1       0       0       0       0     \
             0       0       0       1       0"

#################################################################
# Helper: query bottom / upper tier instances by master name
#################################################################
proc get_bottom_tier_insts {} {
  set inst_ptrs [dbGet top.insts.cell.name "*_bottom" -p2]
  if {[llength $inst_ptrs] == 0} {
    return ""
  }
  return [dbGet $inst_ptrs.name]
}

proc get_upper_tier_insts {} {
  set inst_ptrs [dbGet top.insts.cell.name "*_upper" -p2]
  if {[llength $inst_ptrs] == 0} {
    return ""
  }
  return [dbGet $inst_ptrs.name]
}

#################################################################
# Helper: get a per-layer parameter from the config lists
#################################################################
proc get_layer_param {layer layers values} {
  set idx [lsearch -exact $layers $layer]
  if {$idx < 0} {
    return ""
  }
  return [lindex $values $idx]
}

#################################################################
# Helper: build PDN for one die (tier)
#   tier_name : "BOT" / "TOP"
#   inst_list : list of inst names belonging to this tier
#   vdd_net   : PG VDD net name (BOT_VDD / TOP_VDD)
#   vss_net   : PG VSS net name (BOT_VSS / TOP_VSS)
#   rail_layer: lower follow-pin rail layer (M1 / M20)
#   mesh_l1   : first mesh layer (M4 / M17)
#   mesh_l2   : second mesh layer (M7 / M14)
#################################################################
proc build_pdn_symmetric_tier {tier_name inst_list vdd_net vss_net \
                               rail_layer mesh_l1 mesh_l2} {

  global layers width pitch spacing soffset

  puts "INFO: \[pdn_3d_mirror_1_20\] === \[$tier_name\] PDN: rails on $rail_layer, mesh on $mesh_l1 / $mesh_l2 ==="

  if {[llength $inst_list] == 0} {
    puts "WARN: \[pdn_3d_mirror_1_20\] \[$tier_name\] No tier instances found. Skip PDN."
    return
  }

  puts "INFO: \[pdn_3d_mirror_1_20\] \[$tier_name\] instance count = [llength $inst_list]"

  # 1) Global net connect for all tier instances
  foreach inst $inst_list {
    globalNetConnect $vdd_net -type pgpin -pin VDD -inst $inst -override
    globalNetConnect $vss_net -type pgpin -pin VSS -inst $inst -override
  }

  # Tie cells (optional but recommended)
  globalNetConnect $vdd_net -type tiehi -all -override
  globalNetConnect $vss_net -type tielo -all -override

  puts "INFO: \[pdn_3d_mirror_1_20\] \[$tier_name\] globalNetConnect done for $vdd_net / $vss_net."

  # 2) Follow-pin rails on rail_layer
  sroute -nets [list $vdd_net $vss_net] \
         -connect {corePin} \
         -corePinLayer [list $rail_layer] \
         -corePinTarget {firstAfterRowEnd}

  puts "INFO: \[pdn_3d_mirror_1_20\] \[$tier_name\] follow-pin rails created on $rail_layer."

  # 3) Mesh stripes on mesh_l1 / mesh_l2

  # mesh_l1 parameters (e.g., M4 / M17)
  set w1 [get_layer_param $mesh_l1 $layers $width]
  set p1 [get_layer_param $mesh_l1 $layers $pitch]
  set s1 [get_layer_param $mesh_l1 $layers $spacing]
  set o1 [get_layer_param $mesh_l1 $layers $soffset]

  # mesh_l2 parameters (e.g., M7 / M14)
  set w2 [get_layer_param $mesh_l2 $layers $width]
  set p2 [get_layer_param $mesh_l2 $layers $pitch]
  set s2 [get_layer_param $mesh_l2 $layers $spacing]
  set o2 [get_layer_param $mesh_l2 $layers $soffset]

  if {$w1 eq "" || $w2 eq ""} {
    puts "ERROR: \[pdn_3d_mirror_1_20\] \[$tier_name\] Missing PDN parameters for $mesh_l1 / $mesh_l2."
    return
  }

  # Directions: M4/M17 vertical, M7/M14 horizontal
  set dir1 "vertical"
  set dir2 "horizontal"

  addStripe -layer $mesh_l1 \
            -direction $dir1 \
            -nets [list $vdd_net $vss_net] \
            -width $w1 \
            -spacing $s1 \
            -start_offset $o1 \
            -set_to_set_distance $p1

  addStripe -layer $mesh_l2 \
            -direction $dir2 \
            -nets [list $vdd_net $vss_net] \
            -width $w2 \
            -spacing $s2 \
            -start_offset $o2 \
            -set_to_set_distance $p2

  puts "INFO: \[pdn_3d_mirror_1_20\] \[$tier_name\] mesh stripes added on $mesh_l1 (vertical) / $mesh_l2 (horizontal)."
}

#################################################################
# Top-level PDN flow
#################################################################

# 1) Create channels between rows
dbset [dbget top.insts.cell.subClass core -p2].pStatus unplaced
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

# 2) Query bottom / top tier instances
set bot_insts [get_bottom_tier_insts]
set top_insts [get_upper_tier_insts]

puts "INFO: \[pdn_3d_mirror_1_20\] BOT tier inst count = [llength $bot_insts]"
puts "INFO: \[pdn_3d_mirror_1_20\] TOP tier inst count = [llength $top_insts]"

# 3) Common stripe mode
setAddStripeMode -orthogonal_only true
setAddStripeMode -ignore_DRC false
setAddStripeMode -over_row_extension true
setAddStripeMode -extend_to_closest_target area_boundary
setAddStripeMode -inside_cell_only false
setAddStripeMode -route_over_rows_only false

# Own PG mapping in this script
clearGlobalNets

# 4) Build BOT tier PDN
#    - rail layer : M1
#    - mesh layers: M4 (vertical) / M7 (horizontal)
build_pdn_symmetric_tier "BOT" $bot_insts \
                         BOT_VDD BOT_VSS \
                         M1 M4 M7

# 5) Build TOP tier PDN
#    - rail layer : M20 (mirror of M1)
#    - mesh layers: M17 (mirror of M4) / M14 (mirror of M7)
#
#    NOTE:
#      If you want shared ground, replace TOP_VSS with BOT_VSS here:
#        build_pdn_symmetric_tier "TOP" ... TOP_VDD BOT_VSS ...
build_pdn_symmetric_tier "TOP" $top_insts \
                         TOP_VDD TOP_VSS \
                         M20 M17 M14

puts "INFO: \[pdn_3d_mirror_1_20\] Symmetric 3D PDN (Bottom + Top) finished."
