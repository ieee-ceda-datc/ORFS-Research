# =========================================
# tech config.mk
# =========================================

# -------- Process --------
export PROCESS = 45

# -------- Tech / Libs --------
export TECH_LEF = $(PLATFORM_DIR)/lef/NangateOpenCellLibrary.tech.lef
export SC_LEF  ?= $(PLATFORM_DIR)/lef_bottom/NangateOpenCellLibrary.macro.mod.bottom.lef
export SC_LIB  ?= $(PLATFORM_DIR)/lib_bottom/NangateOpenCellLibrary_typical.bottom.lib

# 统一的 LEF/LIB 列表（以 Cadence 为准的顺序/命名）
export LEF_FILES = $(TECH_LEF) \
                   $(SC_LEF) \
                   $(ADDITIONAL_LEFS)
export LIB_FILES = $(SC_LIB) \
                   $(ADDITIONAL_LIBS)

# 目录/提取文件（Cadence）
export LIB_DIR ?= $(dir $(SC_LIB))
export LEF_DIR ?= $(dir $(TECH_LEF))
export QRC_FILE ?= $(PLATFORM_DIR)/qrc/NG45.tch

# 版图/GDS（OpenROAD 补充）
export GDS_FILES = $(sort $(wildcard $(PLATFORM_DIR)/gds/*.gds)) \
                   $(ADDITIONAL_GDS)

# -------- Synthesis / Mapping --------
# Cadence: RTL 搜索路径（便于 Genus）；OpenROAD: Yosys/ABC 相关开关
export RTL_SEARCH_DIRS ?= $(dir $(firstword $(VERILOG_FILES)))

# Yosys/ABC（OpenROAD 独有，保留方便混合流程）
export MAX_UNGROUP_SIZE ?= 10000
export TIEHI_CELL_AND_PORT = LOGIC1_X1_bottom Z
export TIELO_CELL_AND_PORT = LOGIC0_X1_bottom Z
export MIN_BUF_CELL_AND_PORTS = BUF_X1_bottom A Z
export LATCH_MAP_FILE    = $(PLATFORM_DIR)/cells_latch.v
export CLKGATE_MAP_FILE  = $(PLATFORM_DIR)/cells_clkgate.v
export ADDER_MAP_FILE   ?= $(PLATFORM_DIR)/cells_adders.v
export ABC_DRIVER_CELL   = BUF_X1_bottom
export ABC_LOAD_IN_FF    = 3.898

# -------- Floorplan --------
export PLACE_SITE   = FreePDK45_38x28_10R_NP_162NW_34O
export IO_PLACER_H ?= metal5
export IO_PLACER_V ?= metal6

# PDN / Endcap / Welltie（Cadence 为准）
export PDN_TCL      ?= $(PLATFORM_DIR)/grid_strategy-M1-M4-M7.tcl
export TAPCELL_TCL  ?= $(PLATFORM_DIR)/tapcell.tcl
export TAP_CELL_NAME = TAPCELL_X1_bottom

# -------- Placement --------
export CELL_PAD_IN_SITES_GLOBAL_PLACEMENT ?= 0
export CELL_PAD_IN_SITES_DETAIL_PLACEMENT ?= 0
export PLACE_DENSITY ?= 0.30

# 3D 分层相关（Cadence 结构化变量为准）
export FILL_CELLS_UPPER  ?= FILLCELL_X1_upper  FILLCELL_X2_upper  FILLCELL_X4_upper  \
                             FILLCELL_X8_upper  FILLCELL_X16_upper  FILLCELL_X32_upper
export FILL_CELLS_BOTTOM ?= FILLCELL_X1_bottom FILLCELL_X2_bottom FILLCELL_X4_bottom \
                             FILLCELL_X8_bottom FILLCELL_X16_bottom FILLCELL_X32_bottom
export DONT_USE_CELLS_UPPER  ?= TAPCELL_X1_upper  FILLCELL_X1_upper  AOI211_X1_upper  OAI211_X1_upper
export DONT_USE_CELLS_BOTTOM ?= TAPCELL_X1_bottom FILLCELL_X1_bottom AOI211_X1_bottom OAI211_X1_bottom
export DONT_USE_CELLS = $(DONT_USE_CELLS_UPPER) $(DONT_USE_CELLS_BOTTOM)

# 统一/派生给 Tcl 使用
export FILL_CELLS ?= $(FILL_CELLS_BOTTOM)     # 非分层/兜底用
export DNU_FOR_UPPER   := $(DONT_USE_CELLS_BOTTOM) *_bottom
export DNU_FOR_BOTTOM  := $(DONT_USE_CELLS_UPPER)  *_upper
export DNU_FOR_UNIFIED := *_upper *_bottom

# -------- CTS --------
export CTS_BUF_CELL ?= BUF_X4_bottom

# -------- Route --------
export MIN_ROUTING_LAYER = metal2
export MAX_ROUTING_LAYER = metal19

# OpenROAD 专用脚本（保留以便混合流程）
export FASTROUTE_TCL ?= $(PLATFORM_DIR)/fastroute.tcl

# 允许空 GDS cell（Cadence）
export GDS_ALLOW_EMPTY ?= fakeram.*

# -------- Signoff / RCX / IR --------
export CDL_FILE           = $(PLATFORM_DIR)/cdl/NangateOpenCellLibrary.cdl
export TEMPLATE_PGA_CFG  ?= $(PLATFORM_DIR)/template_pga.cfg
export RCX_RULES          = $(PLATFORM_DIR)/nangate45_3D.rules

# IR drop 设定（两侧一致）
export PWR_NETS_VOLTAGES ?= "VDD 1.1"
export GND_NETS_VOLTAGES ?= "VSS 0.0"
export IR_DROP_LAYER     ?= metal1
