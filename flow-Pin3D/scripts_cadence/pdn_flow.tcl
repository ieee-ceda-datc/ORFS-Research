#################################################################
# pdn_flow.tcl — 下半构建 → 上半镜像 → 分段连通 → 只桥接 M10↔M11
# 用法：
#   source pdn_config.tcl
#   source pdn_flow.tcl
#################################################################

# ====== 小工具（修正：不用命名空间 upvar，统一全局数组访问） ======

# 必要键检查（标量）
proc _need {v} {
  if {![info exists ::PDN($v)]} {
    error "Missing PDN($v). Please: source pdn_config.tcl first."
  }
}

# 取全局数组的元素：_aget <全局数组名> <layer>
proc _aget {arrName layer} {
  upvar #0 $arrName A
  if {![info exists A($layer)]} {
    error "Missing $arrName($layer) — check pdn_config.tcl"
  }
  return $A($layer)
}

# 方向转字符串
proc _dirStr {d} { expr {$d ? "vertical" : "horizontal"} }

# 安全 GNC（最小覆盖）
proc _safeGNC_from_map {} {
  foreach entry $::PDN(gnc_map) {
    set net  [lindex $entry 0]
    set pins [lindex $entry 1]
    foreach p $pins {
      catch { globalNetConnect $net -type pgpin -pin $p -inst * -override }
    }
  }
  catch { globalNetConnect VDD -type tiehi -all -override }
  catch { globalNetConnect VSS -type tielo -all -override }
}

# 在指定层画条带（只画“线”，via 稍后由分段 sroute 决定）
proc _stripe_on {L nets} {
  addStripe -layer $L \
    -direction [_dirStr [_aget PDN_ldir $L]] \
    -nets $nets \
    -width   [_aget PDN_width   $L] \
    -spacing [_aget PDN_spacing $L] \
    -start_offset 5 \
    -set_to_set_distance [_aget PDN_pitch $L] \
    -extend_to design_boundary \
    -narrow_channel 1 \
    -snap_wire_center_to_grid Grid
}


# 只复制“线”到目标层（不复制 via），并可选按目标层宽度重设
proc _dup_layer_wires {src dst {dst_width ""}} {
  # catch { deselectAll; editDelete -type Special -layer $dst -net $::PDN(nets) }

  deselectAll
  editSelect -type Special -layer $src -net $::PDN(nets)
  catch { editDeselect -object_type Via }

  set d [_aget PDN_ldir $dst]
  if {$d} {
    catch { editDuplicate -layer_vertical   $dst }
  } else {
    catch { editDuplicate -layer_horizontal $dst }
  }

  if {$dst_width ne ""} {
    deselectAll
    editSelect -type Special -layer $dst -net $::PDN(nets)
    catch { editResize -to $dst_width -side high -direction y -keep_center_line 1 }
    deselectAll
  }
}

# 清掉所有 PG via（只保留“线”），避免 addStripe 自动贯通
proc _zap_pg_vias {} {
  deselectAll
  editSelect -type Special -object_type Via -net $::PDN(nets)
  catch { editDelete }
  deselectAll
}

# 在给定层窗口内做 sroute（via 仅允许在窗口里出现）
proc _sroute_windows {win_list connect_kinds} {
  foreach rng $win_list {
    if {[llength $rng] != 2} { continue }
    set L0 [lindex $rng 0]
    set L1 [lindex $rng 1]
    sroute -connect $connect_kinds \
      -layerChangeRange         [list $L0 $L1] \
      -targetViaLayerRange      [list $L0 $L1] \
      -crossoverViaLayerRange   [list $L0 $L1] \
      -allowJogging 1 -allowLayerChange 1 \
      -nets $::PDN(nets)
  }
}

# ====== 前置检查 ======
_need nets; _need top_routing_layer; _need isFP; _need fp_layer
_need stripe_layers_lower; _need mirror_pairs
_need windows_lower; _need windows_upper; _need window_bridge
_need minCh

# ====== 基础准备（一次就够）======
finishFloorplan -fillPlaceBlockage hard $PDN(minCh)
cutRow
finishFloorplan -fillPlaceBlockage hard $PDN(minCh)

catch { setDesignMode -topRoutingLayer $PDN(top_routing_layer) }

clearGlobalNets
_safeGNC_from_map

# 清旧特布
deselectAll
catch { editDelete -type Special -net $PDN(nets) }

# 关闭自动 via：via 只允许在我们指定的窗口由 sroute 打
catch { setGenerateViaMode -auto false }

# ====== 1) Follow-pin（通常固定在 M1）======
if {$PDN(isFP)} {
  set fpL $PDN(fp_layer)
  set fpC [expr {[info exists PDN(fp_connect)] ? $PDN(fp_connect) : {corePin}}]
  sroute -connect $fpC \
    -layerChangeRange       [list $fpL $fpL] \
    -targetViaLayerRange    [list $fpL $fpL] \
    -crossoverViaLayerRange [list $fpL $fpL] \
    -allowJogging 1 -allowLayerChange 0 \
    -nets $PDN(nets)
}

# ====== 2) 下半：addStripe（仅造“线”）======
foreach L $PDN(stripe_layers_lower) { _stripe_on $L $PDN(nets) }
# 清掉 addStripe 自动 via
_zap_pg_vias

# ====== 3) 下半分段连通（止于 M10）======
set _lower_connect  {corePin floatingStripe}
if {[info exists PDN(connect_block_pins)] && $PDN(connect_block_pins)} { lappend _lower_connect blockPin }
if {[info exists PDN(connect_pad_pins)]   && $PDN(connect_pad_pins)}   { lappend _lower_connect padPin padRing }
_sroute_windows $PDN(windows_lower) $_lower_connect

# ====== 4) 镜像：把“线”复制到上半（不复制 via）======
foreach pair $PDN(mirror_pairs) {
  set SRC [lindex $pair 0]
  set DST [lindex $pair 1]
  set W ""
  if {[info exists ::PDN_width($DST)]} { set W $::PDN_width($DST) }
  _dup_layer_wires $SRC $DST $W
}

# ====== 5) 上半分段连通（止于 M11）======
set _upper_connect {floatingStripe}
if {[info exists PDN(connect_block_pins)] && $PDN(connect_block_pins)} { lappend _upper_connect blockPin }
if {[info exists PDN(connect_pad_pins)]   && $PDN(connect_pad_pins)}   { lappend _upper_connect padPin padRing }
_sroute_windows $PDN(windows_upper) $_upper_connect

# ====== 6) 唯一桥接：M10 ↔ M11（只连条带↔条带）======
_sroute_windows [list $PDN(window_bridge)] {floatingStripe}

# ====== 7) 同层合并（可选，让条带更整洁）======
set _merge_layers {}
foreach L $PDN(stripe_layers_lower) { lappend _merge_layers $L }
foreach pair $PDN(mirror_pairs)     { lappend _merge_layers [lindex $pair 1] }
set _merge_layers [lsort -unique $_merge_layers]
foreach L $_merge_layers {
  deselectAll
  editSelect -layer $L -net $PDN(nets)
  catch { editMerge }
}
deselectAll

puts "INFO: PDN OK — lower(M1..M10) built → mirrored to (M20..M11) → segmented sroute → single bridge M10↔M11."
