# placement_utils.tcl


# In placement phase
# ----------------------------------------------------------------------
# Mark instances as a given placement status by matching master name
# Usage:
#   mark_insts_by_master "*_bottom" FIRM
#   mark_insts_by_master "" FIRM
# ----------------------------------------------------------------------
proc mark_insts_by_master {{pattern ""} {status "FIRM"}} {
    # 1) 解析匹配模式
    if {$pattern eq ""} {
        return 0
    }

    # 2) 校验目标状态（OpenROAD/ODB 常见可用值）
    set valid_status {UNPLACED PLACED FIRM LOCKED FIXED}
    if {[lsearch -exact $valid_status $status] < 0} {
        puts "WARN: '$status' not in valid statuses: $valid_status ; fallback to FIRM"
        set status FIRM
    }

    # 3) 取 DB/Block
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

    # 4) 遍历实例，按 master 名匹配，设置状态
    set cnt 0
    set examples {}
    foreach inst [$block getInsts] {
        # master 名
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
  # puts "DEBUG: Entering calculate_placement_density"
  # 0) Base density default
  set base_density [::_env_or PLACE_DENSITY 0.60]
  # puts "DEBUG: base_density = $base_density"

  # 1) If no addon requested, just use base
  if {![info exists ::env(PLACE_DENSITY_LB_ADDON)]} {
    puts "INFO: PLACE_DENSITY_LB_ADDON not set, using PLACE_DENSITY=$base_density"
    return $base_density
  }
  # puts "DEBUG: PLACE_DENSITY_LB_ADDON is set, proceeding."

  # 2) DB preflight
  # puts "DEBUG: Starting DB preflight checks."
  set db   [ord::get_db]
  if {$db eq ""} {
    puts "WARN: no DB; fallback density $base_density"
    return $base_density
  }
  # puts "DEBUG: Got DB object."
  set chip [$db getChip]
  if {$chip eq ""} {
    puts "WARN: no chip; fallback density $base_density"
    return $base_density
  }
  # puts "DEBUG: Got chip object."
  set block [$chip getBlock]
  if {$block eq ""} {
    puts "WARN: no block; fallback density $base_density"
    return $base_density
  }
  # puts "DEBUG: Got block object."
  # Rows are required for LB computation
  if {[llength [$block getRows]] == 0} {
    puts "WARN: no rows in block (DEF may lack ROWS); fallback density $base_density"
    return $base_density
  }
  # puts "DEBUG: Block has rows. DB preflight passed."

  # 3) Pad arguments must be integers; default to 0 if missing
  # puts "DEBUG: Reading padding arguments."
  set pad_l [::_as_int $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) 0]
  set pad_r [::_as_int $::env(CELL_PAD_IN_SITES_GLOBAL_PLACEMENT) 0]
  # puts "DEBUG: pad_l=$pad_l, pad_r=$pad_r"

  # 4) Compute LB with catch to absorb GPL-0301 on older builds / invalid states
  # puts "DEBUG: Preparing to compute LB."
  set lb 0.0
  set rc [catch {
    # puts "DEBUG: Inside catch block, attempting to call GPL helper."
    # Some builds expose gpl::get_global_placement_uniform_density,
    # others the *_cmd symbol; try both.
    if {[info procs gpl::get_global_placement_uniform_density] ne ""} {
      # puts "DEBUG: Calling gpl::get_global_placement_uniform_density..."
      set lb [gpl::get_global_placement_uniform_density -pad_left $pad_l -pad_right $pad_r]
    } elseif {[info procs gpl::get_global_placement_uniform_density_cmd] ne ""} {
      # puts "DEBUG: Calling gpl::get_global_placement_uniform_density_cmd..."
      set lb [gpl::get_global_placement_uniform_density_cmd -pad_left $pad_l -pad_right $pad_r]
    } else {
      error "No GPL uniform-density helper in this build"
    }
    # puts "DEBUG: GPL helper call finished."
  } err]

  if {$rc} {
    puts "WARN: failed to get density LB (GPL-0301/compat): $err ; fallback $base_density"
    return $base_density
  }
  # puts "DEBUG: Successfully computed LB = $lb"

  # 5) Apply addon blend and a tiny nudge
  # puts "DEBUG: Applying addon and calculating final density."
  set addon $::env(PLACE_DENSITY_LB_ADDON)
  # clamp addon into [0,1] just in case
  if {$addon < 0.0} { set addon 0.0 }
  if {$addon > 1.0} { set addon 1.0 }

  set density [expr {$lb + ((1.0 - $lb) * $addon) + 0.01}]
  # puts "DEBUG: Calculated density before clamping: $density"
  # clamp to (0,1)
  if {$density <= 0.0} { set density 0.10 }
  if {$density >= 1.0} { set density 0.98 }
  # puts "DEBUG: Final density after clamping: $density"

  puts "INFO: PLACE_DENSITY_LB=$lb, ADDON=$addon -> density=$density (padL=$pad_l padR=$pad_r)"
  return $density
}

# ==== 工具函数：按 master 名匹配，删除实例 ====
# pattern 默认 "*_bottom*"；dry_run=1 时只打印不删；verbose 控制日志
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
    # delete_instance 只能吃名字；做保护性调用
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

# 取环境变量为 list（不存在/空串 => {}）
proc _as_list {envname} {
  if {[info exists ::env($envname)] && $::env($envname) ne ""} {
    return $::env($envname)
  }
  return {}
}

# 将通配名展开为真实 lib cell 名；若命令不可用则保留通配符原样
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

# OpenROAD 的 set_dont_use 主要接受“单/批量 cell 列表”单参写法
# 这里做兼容：优先批量调用，失败则逐个调用
proc _set_dont_use {cells} {
  if {![llength $cells]} { return }
  if {[catch {set_dont_use $cells}]} {
    foreach c $cells { catch { set_dont_use $c } }
  }
}

# ============= Tier 策略（与 Cadence 脚本等价思路） =============
# 约定环境变量（若你已有同名即直接生效）：
#   DNU_FOR_UPPER / DNU_FOR_BOTTOM  : 针对 upper/bottom 的禁用 patterns 列表
#   DONT_USE_CELLS                  : 与你现有脚本兼容的总禁用列表（可选）
#   *_upper / *_bottom 后缀库名可用“*_upper”“*_bottom”作兜底通配
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
    puts "INFO(OR): Tier policy applied for UPPER."
  } else {
    if {[llength $dnu_bot]} {
      _set_dont_use [_expand_libcells $dnu_bot]
    } else {
      _set_dont_use [_expand_libcells "*_upper"]
    }
    set ::env(TIEHI_CELL_AND_PORT) $::env(BOTTOM_TIEHI_CELL_AND_PORT)
    set ::env(TIELO_CELL_AND_PORT) $::env(BOTTOM_TIELO_CELL_AND_PORT)
    puts "INFO(OR): Tier policy applied for BOTTOM."
  }
}

# 与你原来的接口兼容：可传 tier，也可只吃全局 DONT_USE_CELLS
proc tier_dont_use_strategy {{tier ""}} {
  if {$tier ne ""} {
    apply_tier_policy $tier
  }
  if {[info exists ::env(DONT_USE_CELLS)] && $::env(DONT_USE_CELLS) ne ""} {
    _set_dont_use [_expand_libcells $::env(DONT_USE_CELLS)]
    puts "INFO(OR): Applied DONT_USE_CELLS = '$::env(DONT_USE_CELLS)'."
  }
}

# ============= FastRoute 兜底设置（可被外部 Tcl 覆盖） =============
proc fastroute_setup {} {
  # 优先走你提供的外部脚本
  if {[info exists ::env(FASTROUTE_TCL)] && $::env(FASTROUTE_TCL) ne ""} {
    puts "INFO(OR): Sourcing FASTROUTE_TCL = $::env(FASTROUTE_TCL)"
    catch { source $::env(FASTROUTE_TCL) }
    return
  }

  # 兜底：根据 MIN/MAX_ROUTING_LAYER 设置信号层与拥塞调整
  set minL [expr {[info exists ::env(MIN_ROUTING_LAYER)] ? $::env(MIN_ROUTING_LAYER) : "met1"}]
  set maxL [expr {[info exists ::env(MAX_ROUTING_LAYER)] ? $::env(MAX_ROUTING_LAYER) : "met5"}]

  catch { set_routing_layers -signal ${minL}-${maxL} }
  # 对整段层做统一负载调整（拥塞更保守）；你也可替换为分层细化
  catch { set_global_routing_layer_adjustment ${minL}-${maxL} 0.5 }

  if {[info exists ::env(MACRO_EXTENSION)] && $::env(MACRO_EXTENSION) ne ""} {
    catch { set_macro_extension $::env(MACRO_EXTENSION) }
  }

  # 可选：指定线程数（若你的镜像支持）
  if {[info exists ::env(GRT_THREADS)] && $::env(GRT_THREADS) ne ""} {
    catch { set_thread_count $::env(GRT_THREADS) }
  }

  puts "INFO(OR): FastRoute default setup done: layers=${minL}-${maxL}, adjust=0.5"
}

# ============= 建议的调用顺序（示例） =============
# 1) 在 global_placement / repair_timing 之前：
#    tier_dont_use_strategy upper|bottom
#    tier_dont_use_strategy         ;# 若想再叠加全局 DONT_USE_CELLS
# 2) 在 global_route / route_eco 之前：
#    fastroute_setup
#
# 例：
#   tier_dont_use_strategy upper
#   fastroute_setup
#   global_placement -routability_driven
#   fastroute_setup
#   global_route
