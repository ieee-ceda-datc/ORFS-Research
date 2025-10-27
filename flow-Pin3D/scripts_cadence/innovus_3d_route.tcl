# ===============================
# innovus_3d_route.tcl — route + postRoute opt (stable knobs)
# ===============================
source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl

set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR   [_get OBJECTS_DIR]

set DEF_IN   [file join $RESULTS_DIR "4_cts.def"]
set V_IN     [file join $RESULTS_DIR "4_cts.v"]
set sdc   [file join $RESULTS_DIR "4_cts.sdc"]

source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

setMultiCpuUsage -localCpu 16

# ---------- 初始化 ----------
set init_lef_file $lefs
set init_mmmc_file ""
set init_design_settop 1
set init_top_cell $DESIGN
set init_verilog $V_IN
set init_design_netlisttype "Verilog"

init_design -setup {WC_VIEW} -hold {BC_VIEW}
set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW
set_interactive_constraint_modes {CON}
setAnalysisMode -reset
setAnalysisMode -analysisType onChipVariation -cppr both

# 读入 DEF/SDC
defIn $DEF_IN

# 层限制（与 place 对齐）
if {[info exists ::env(MAX_ROUTING_LAYER)]} { setDesignMode -topRoutingLayer    $::env(MAX_ROUTING_LAYER) }
if {[info exists ::env(MIN_ROUTING_LAYER)]} { setDesignMode -bottomRoutingLayer $::env(MIN_ROUTING_LAYER) }

# ---------- 路由器设置（稳健） ----------
# GR：若计时太慢可以关 timing；开启先进工艺修复
setNanoRouteMode -grouteExpWithTimingDriven false
setNanoRouteMode -drouteEndIteration 5

# SI/时序驱动、自动 VIA、避免在 SC pin 内乱打 VIA
setNanoRouteMode -routeWithSiDriven true
setNanoRouteMode -routeWithTimingDriven true
setNanoRouteMode -routeUseAutoVia true
setNanoRouteMode -routeWithViaInPin "1:1"
setNanoRouteMode -routeWithViaOnlyForStandardCellPin "1:1"

# VIA1 仅 on-grid、先进工艺路由开关
setNanoRouteMode -drouteOnGridOnly "via 1:1"
setNanoRouteMode -drouteAutoStop false
setNanoRouteMode -drouteExpAdvancedMarFix true
setNanoRouteMode -routeExpAdvancedTechnology true

# ---------- 走线 + 后置优化 ----------
routeDesign
set all_insts [dbGet top.insts]
catch { setDontSize  $all_insts true }
catch { set_dont_size $all_insts true }
optDesign -postRoute

# ---------- 导出 ----------
set DEF_OUT  [file join $RESULTS_DIR "5_route.def"]
set V_OUT    [file join $RESULTS_DIR "5_route.v"]
set ENC_OUT  [file join $OBJECTS_DIR  "${DESIGN}_postRoute.enc"]
defOut -netlist -floorplan -routing $DEF_OUT
saveNetlist $V_OUT
saveDesign $ENC_OUT
fit
dumpToGIF $LOG_DIR/5_route.png
puts "INFO: Routing done. DEF: $DEF_OUT  V: $V_OUT  ENC: $ENC_OUT"
exit
