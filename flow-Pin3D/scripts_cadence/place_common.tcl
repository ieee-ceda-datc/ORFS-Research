# ==========================================
# place_common.tcl — Stable pre-GR/pre-legal setup for Innovus placement
# 依赖：已 source utils.tcl / lib_setup.tcl / design_setup.tcl / mmmc_setup.tcl
# 环境变量（可选）：
#   PAD_REGEX  : 需要加 padding 的 cell 基元名正则（如 "BUF.*|INV.*"）
#   PAD_LEFT   : 左侧留白 sites（默认 0）
#   PAD_RIGHT  : 右侧留白 sites（默认 0）
#   DISABLE_SCAN_REORDER : 1 则关闭扫描重排（默认 1，更稳）
#   NON_TIMING_PLACE     : 1 则关闭时序驱动（默认 0）
#   USE_PLACE_OPT        : 1 则使用 place_opt_design（默认 1）
#   USE_CONCURRENT_MACRO : 1 则并行宏+单元放（默认 0；需有可移动宏）
#   HONOR_INST_PAD       : 1 则将实例 padding 设为硬规则
#   MAX_ROUTING_LAYER / MIN_ROUTING_LAYER : 限制布线层
# ==========================================

# 确保命名空间存在
if {![namespace exists pc]} {
  namespace eval pc {
    namespace export setup_basic run_place
  }
}

proc pc::_env_or {name default} {
  if {[info exists ::env($name)]} { return $::env($name) }
  return $default
}

proc pc::setup_basic {} {
  # --- 线程与分析 ---
  catch { setMultiCpuUsage -localCpu 16 }
  catch { set_interactive_constraint_modes {CON} }  ;# 有的版本没有该命令
  catch { setAnalysisMode -reset }
  catch { setAnalysisMode -analysisType onChipVariation -cppr both }

  # --- 布线层限制（如设置） ---
  if {[info exists ::env(MAX_ROUTING_LAYER)]} { catch { setDesignMode -topRoutingLayer    $::env(MAX_ROUTING_LAYER) } }
  if {[info exists ::env(MIN_ROUTING_LAYER)]} { catch { setDesignMode -bottomRoutingLayer $::env(MIN_ROUTING_LAYER) } }

  # --- 合法化与回填 ---
  catch { setPlaceMode -place_detail_legalization_inst_gap 1 }
  catch { setFillerMode -fitGap true }

  # --- 扫描链（默认先关，规划成熟后再开） ---
  set disable_scan [pc::_env_or DISABLE_SCAN_REORDER 1]
  catch { setPlaceMode -place_global_reorder_scan [expr {$disable_scan ? "false" : "true"}] }

  # --- 时序驱动（原型阶段可关闭） ---
  set non_timing [pc::_env_or NON_TIMING_PLACE 0]
  if {$non_timing} { catch { setPlaceMode -place_global_timing_effort false } }

  # --- 严格遵守实例 padding（可选） ---
  if {[pc::_env_or HONOR_INST_PAD 0]} {
    catch { setPlaceMode -place_detail_honor_inst_pad true }
  }

  # --- 按需添加实例级 padding ---
  set pad_l   [pc::_env_or PAD_LEFT  0]
  set pad_r   [pc::_env_or PAD_RIGHT 0]
  set pad_rxp [pc::_env_or PAD_REGEX ""]
  if {($pad_l>0 || $pad_r>0) && $pad_rxp ne ""} {
    puts "INFO\[pc\]: Applying inst padding L=$pad_l R=$pad_r on regex: $pad_rxp"
    # 使用 get_db 过滤；不同版本属性名可能不同，做兜底
    set sel {}
    # 优先：基元名（base cell）
    catch { set sel [get_db insts -if {.[baseCell].name =~ $pad_rxp}] }
    # 回退：libcell 名称路径（旧版）
    if {[llength $sel] == 0} {
      catch { set sel [get_db insts -if {.[cell].name =~ $pad_rxp}] }
    }
    if {[llength $sel] > 0} {
      catch { setInstPad $sel -left $pad_l -right $pad_r }
    } else {
      puts "WARN\[pc\]: No insts matched PAD_REGEX='$pad_rxp' — padding skipped."
    }
  }
}

# 一步式：place_opt_design（推荐）
proc pc::run_place {} {
  set use_pod           [pc::_env_or USE_PLACE_OPT 1]
  set do_concurrent_mac [pc::_env_or USE_CONCURRENT_MACRO 0]

  if {$do_concurrent_mac} {
    puts "INFO\[pc\]: place_design -concurrent_macros"
    catch { place_design -concurrent_macros } msg
    if {[info exists msg] && $msg ne ""} { puts "INFO\[pc\]: $msg" }
  } else {
    puts "INFO\[pc\]: Skip concurrent_macros (disabled or no movable macros)."
  }

  if {$use_pod} {
    puts "INFO\[pc\]: place_opt_design (integrated preCTS opt)"
    # 报表目录/前缀可能在你的设计脚本中已定义；做兼容兜底
    set reports_dir [expr {[info exists ::REPORTS_DIR] ? $::REPORTS_DIR : "./reports"}]
    file mkdir $reports_dir
    catch { place_opt_design -out_dir $reports_dir -prefix prects } msg
    if {[info exists msg] && $msg ne ""} { puts "INFO\[pc\]: $msg" }
  } else {
    puts "INFO\[pc\]: classic flow: place_design + optDesign -preCTS"
    catch { place_design }
    catch { optDesign -preCTS }
  }

  catch { checkPlace }
}
