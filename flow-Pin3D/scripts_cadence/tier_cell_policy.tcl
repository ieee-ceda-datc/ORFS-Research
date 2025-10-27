# ==========================================
# tier_cell_policy.tcl — Upper/Bottom “do-not-use + filler/tap” policy
# 依赖环境变量（都可选，留空则尽量自动兜底）：
#   DONT_USE_CELLS_UPPER
#   DONT_USE_CELLS_BOTTOM
#   FILL_CELLS_UPPER
#   FILL_CELLS_BOTTOM
#   TAPCELL_UPPER   ;# 可选：若你想 addWellTap/by layer 时显式指定
#   TAPCELL_BOTTOM
# 用法：
#   source $::env(CADENCE_SCRIPTS_DIR)/tier_cell_policy.tcl
#   apply_tier_policy upper   ;# 或 bottom
# ==========================================

proc _as_list {envname} {
  if {[info exists ::env($envname)] && $::env($envname) ne ""} {
    return $::env($envname)
  }
  return {}
}

# 兼容性 set_dont_use（Innovus/Encounter/Genus 均可识别）
proc _set_dont_use {cells {flag true}} {
  foreach c $cells {
    catch { set_dont_use $c $flag }
    # 少数版本不接受 boolean 第二参，就退化成单参语法（置 true）
    if {$flag} { catch { set_dont_use $c } }
  }
}

# 将通配名展开成 lib cell 对象/名，尽量稳妥
proc _expand_libcells {patterns} {
  set out {}
  foreach p $patterns {
    # 优先 get_lib_cells；若不可用则直接用通配符名（让 set_dont_use 接受）
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

# 可选：限制优化可用的“允许名单”（比只禁止更强）
# 传入 allow 列表后，会对“全集-allow”做 dont_use；默认关闭。
proc _enforce_allowlist {allow_patterns} {
  if {![llength $allow_patterns]} { return }
  set allow  [_expand_libcells $allow_patterns]
  # 拿全集（所有 standard cell）
  set all ""
  catch { set all [get_lib_cells *] }
  if {$all eq ""} { return }
  # 求差集
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

  # 读取环境变量
  set DNU_UP   [_as_list DNU_FOR_UPPER]
  set DNU_BOT  [_as_list DNU_FOR_BOTTOM]
  set FILL_UP  [_as_list FILL_CELLS_UPPER]
  set FILL_BOT [_as_list FILL_CELLS_BOTTOM]
  set TAP_UP   [_as_list TAPCELL_UPPER]
  set TAP_BOT  [_as_list TAPCELL_BOTTOM]

  if {$tier eq "upper"} {
    # 1) 禁止使用 bottom 的 buffer/filler/tap
    if {[llength $DNU_UP]} {
      _set_dont_use [_expand_libcells $DNU_UP] true
    } else {
      # 兜底：禁掉 *_bottom
      _set_dont_use [_expand_libcells "*_bottom"] true
    }

    # 2) 明确 filler 列表只给 upper
    if {[llength $FILL_UP]} {
      setFillerMode -core $FILL_UP
    }

    # 3) 若跑 well tap/decap，请显式指定 upper tap/decap
    if {[llength $TAP_UP]} {
      # 例：addWellTap -cell [lindex $TAP_UP 0] -cellInterval 40 -prefix WT_U_
      # 仅示意，不强制调用（你的 flow 可能另处统一插）
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
      # 例：addWellTap -cell [lindex $TAP_BOT 0] -cellInterval 40 -prefix WT_B_
    }

    puts "INFO: Tier policy applied for BOTTOM: dont_use(upper), filler=BOTTOM list."
  }
  # 注：太强会让 hold 修复受限，默认不启用。
}
