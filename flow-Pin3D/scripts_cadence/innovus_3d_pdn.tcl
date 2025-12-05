# ==========================================
# innovus_3d_pdn.tcl - 3D PDN design flow script
# Goal:
# General Interface for different technologys PDN design
# ==========================================

source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl
# Directories and key files
set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR  [_get OBJECTS_DIR]
set DEF_IO    $RESULTS_DIR/${DESIGN}_3D.fp.def
set VERILOG_IO $RESULTS_DIR/${DESIGN}_3D.fp.v
set sdc        [file join $RESULTS_DIR "1_synth.sdc"]
source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

setMultiCpuUsage -localCpu [_get NUM_CORES 16]
set util [_get CORE_UTILIZATION 70]

# === 3D place init: import gp DEF, create groups, initial fixing ===
set init_lef_file          $lefs
set init_mmmc_file         ""
set init_design_settop     1
set init_top_cell          $DESIGN
set init_verilog           $VERILOG_IO
set init_design_netlisttype "Verilog"

# 如果上下两层的 site 都存在，视为 3D F2F flow，显式指定电源网络
if {[info exists ::env(UPPER_SITE)] && [info exists ::env(BOTTOM_SITE)]} {
    # 3D 模式：上下层各一条 VDD，地网共用 BOT_VSS
    set init_pwr_net  {BOT_VDD TOP_VDD}
    set init_gnd_net  {BOT_VSS}
} else {
    # 非 3D 情况：如果没在别处设置过，就退回普通 VDD/VSS
    if {![info exists init_pwr_net]} {
        set init_pwr_net {VDD}
    }
    if {![info exists init_gnd_net]} {
        set init_gnd_net {VSS}
    }
}

init_design -setup {WC_VIEW} -hold {BC_VIEW}
set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW

set_interactive_constraint_modes {CON}
setAnalysisMode -reset
setAnalysisMode -analysisType onChipVariation -cppr both

setOptMode -powerEffort low -leakageToDynamicRatio 0.5

defIn $DEF_IO

generateTracks

source $::env(PLATFORM_DIR)/util/pdn_config.tcl

fit
dumpToGIF $LOG_DIR/2_pdn.png
defOut -floorplan $RESULTS_DIR/2_floorplan.def
saveNetlist $RESULTS_DIR/2_floorplan.v

# error "INTENTIONAL_ABORT: PDN stage completed; failing at user request"

exit