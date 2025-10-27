# ===============================
# innovus_preplace.tcl
# Floorplan init + Pin placement (editPin)
# ===============================

source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
source $::env(CADENCE_SCRIPTS_DIR)/lib_setup.tcl
source $::env(CADENCE_SCRIPTS_DIR)/design_setup.tcl
# 目录与关键文件
set LOG_DIR       [_get LOG_DIR]
set RESULTS_DIR   [_get RESULTS_DIR]
set REPORTS_DIR   [_get REPORTS_DIR]
set OBJECTS_DIR  [_get OBJECTS_DIR]
set netlist     [file join $RESULTS_DIR "1_synth.v"]
set sdc        [file join $RESULTS_DIR "1_synth.sdc"]
source $::env(CADENCE_SCRIPTS_DIR)/mmmc_setup.tcl

setMultiCpuUsage -localCpu 16
set util [_get CORE_UTILIZATION 70]



# default settings
set init_pwr_net VDD
set init_gnd_net VSS
set init_verilog "$netlist"
set init_design_netlisttype "Verilog"
set init_design_settop 1
set init_top_cell "$DESIGN"
set init_lef_file "$lefs"

# MCMM setup
init_design -setup {WC_VIEW} -hold {BC_VIEW}
set_power_analysis_mode -leakage_power_view WC_VIEW -dynamic_power_view WC_VIEW

set_interactive_constraint_modes {CON}
setAnalysisMode -reset
setAnalysisMode -analysisType onChipVariation -cppr both

clearGlobalNets
globalNetConnect VDD -type pgpin -pin VDD -inst * -override
globalNetConnect VSS -type pgpin -pin VSS -inst * -override
globalNetConnect VDD -type tiehi -inst * -override
globalNetConnect VSS -type tielo -inst * -override


setOptMode -powerEffort low -leakageToDynamicRatio 0.5
setGenerateViaMode -auto true
generateVias

# basic path groups
# createBasicPathGroups -expanded

# Floorplan 参数
set CORE_UTIL     [_get CORE_UTILIZATION 80] 
set ASPECT_RATIO  [_get ASPECT_RATIO 1.0]      
set CORE_MARGIN   [_get CORE_MARGIN 0]       

# ===== Floorplan 初始化 =====
set util [expr {double($CORE_UTIL)/100.0}]
set mL $CORE_MARGIN; set mR $CORE_MARGIN; set mT $CORE_MARGIN; set mB $CORE_MARGIN
# floorPlan -r <aspect> <density> <l> <b> <r> <t>
floorPlan -r $ASPECT_RATIO $util $mL $mB $mR $mT

# ===== Pin 均匀摆放到四条边（带明确层设置）=====
# error "INTENTIONAL_ABORT: PDN stage completed; failing at user request"
source $::env(CADENCE_SCRIPTS_DIR)/place_pin.tcl 

place_design

# 6) 写出带 pin 的 DEF/数据库
set DEF_PINS      [file join $RESULTS_DIR "2_2_floorplan_io.def"]
set V_PINS       [file join $RESULTS_DIR "2_2_floorplan_io.v"]
defOut -floorplan $DEF_PINS
saveNetlist $V_PINS
set DB_PINS       [file join $OBJECTS_DIR "2_2_floorplan_io.enc"]
saveDesign $DB_PINS

puts "INFO: PrePlace pin placement finished."
puts "INFO:   pins DEF      : $DEF_PINS"
puts "INFO:   pins Verilog  : $V_PINS"
exit