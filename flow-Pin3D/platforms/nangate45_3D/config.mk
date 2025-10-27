# Process node
export PROCESS = 45

#-----------------------------------------------------
# Tech/Libs
# ----------------------------------------------------
export TECH_LEF = $(PLATFORM_DIR)/lef/NangateOpenCellLibrary.tech.lef
export SC_LEF ?= $(PLATFORM_DIR)/lef_bottom/NangateOpenCellLibrary.macro.mod.bottom.lef
export SC_LIB ?= $(PLATFORM_DIR)/lib_bottom/NangateOpenCellLibrary_typical.bottom.lib
export LIB_FILES = $(SC_LIB) \
                $(ADDITIONAL_LIBS)
export LEF_FILES = $(TECH_LEF) $(SC_LEF) \
                   $(ADDITIONAL_LEFS)

export GDS_FILES = $(sort $(wildcard $(PLATFORM_DIR)/gds/*.gds)) \
                     $(ADDITIONAL_GDS)
# Dont use cells to ease congestion
# Specify at least one filler cell if none
export DONT_USE_CELLS = TAPCELL_X1_upper FILLCELL_X1_upper AOI211_X1_upper OAI211_X1_upper TAPCELL_X1_bottom FILLCELL_X1_bottom AOI211_X1_bottom OAI211_X1_bottom 
# BUF_X32_upper BUF_X16_upper BUF_X8_upper BUF_X4_upper BUF_X2_upper BUF_X1_upper CLKBUF_X1_upper CLKBUF_X2_upper CLKBUF_X3_upper

# Fill cells used in fill cell insertion
export FILL_CELLS ?= FILLCELL_X1_bottom FILLCELL_X2_bottom FILLCELL_X4_bottom FILLCELL_X8_bottom FILLCELL_X16_bottom FILLCELL_X32_bottom

# -----------------------------------------------------
#  Yosys
#  ----------------------------------------------------
# Ungroup size for hierarchical synthesis
export MAX_UNGROUP_SIZE ?= 10000
# Set the TIEHI/TIELO cells
# These are used in yosys synthesis to avoid logical 1/0's in the netlist
export TIEHI_CELL_AND_PORT = LOGIC1_X1_bottom Z
export TIELO_CELL_AND_PORT = LOGIC0_X1_bottom Z

# Used in synthesis
export MIN_BUF_CELL_AND_PORTS = BUF_X1_bottom A Z


# Yosys mapping files
export LATCH_MAP_FILE = $(PLATFORM_DIR)/cells_latch.v
export CLKGATE_MAP_FILE = $(PLATFORM_DIR)/cells_clkgate.v
export ADDER_MAP_FILE ?= $(PLATFORM_DIR)/cells_adders.v
#
export ABC_DRIVER_CELL = BUF_X1_bottom
# BUF_X1, pin (A) = 0.974659. Arbitrarily multiply by 4
export ABC_LOAD_IN_FF = 3.898

#--------------------------------------------------------
# Floorplan
# -------------------------------------------------------

# Placement site for core cells
# This can be found in the technology lef
export PLACE_SITE = FreePDK45_38x28_10R_NP_162NW_34O

# IO Placer pin layers
export IO_PLACER_H = metal5
export IO_PLACER_V = metal6

# Define default PDN config
export PDN_TCL ?= $(PLATFORM_DIR)/grid_strategy-M1-M4-M7.tcl

# Endcap and Welltie cells
export TAPCELL_TCL ?= $(PLATFORM_DIR)/tapcell.tcl
export TAP_CELL_NAME = TAPCELL_X1_bottom

#---------------------------------------------------------
# Place
# --------------------------------------------------------
# Cell padding in SITE widths to ease rout-ability.  Applied to both sides
export CELL_PAD_IN_SITES_GLOBAL_PLACEMENT ?= 0
export CELL_PAD_IN_SITES_DETAIL_PLACEMENT ?= 0
#

export PLACE_DENSITY ?= 0.30

# --------------------------------------------------------
#  CTS
#  -------------------------------------------------------
# TritonCTS options
export CTS_BUF_CELL   ?= BUF_X4_bottom

# ---------------------------------------------------------
#  Route
# ---------------------------------------------------------
# FastRoute options
export MIN_ROUTING_LAYER = metal2
export MAX_ROUTING_LAYER = metal19

# Define fastRoute tcl
export FASTROUTE_TCL ?= $(PLATFORM_DIR)/fastroute.tcl

export CDL_FILE = $(PLATFORM_DIR)/cdl/NangateOpenCellLibrary.cdl

# Template definition for power grid analysis
export TEMPLATE_PGA_CFG ?= $(PLATFORM_DIR)/template_pga.cfg

# OpenRCX extRules
export RCX_RULES               = $(PLATFORM_DIR)/nangate45_3D.rules
# ---------------------------------------------------------
#  IR Drop
# ---------------------------------------------------------

# IR drop estimation supply net name to be analyzed and supply voltage variable
# For multiple nets: PWR_NETS_VOLTAGES  = "VDD1 1.8 VDD2 1.2"
export PWR_NETS_VOLTAGES  ?= "VDD 1.1"
export GND_NETS_VOLTAGES  ?= "VSS 0.0"
export IR_DROP_LAYER ?= metal1
