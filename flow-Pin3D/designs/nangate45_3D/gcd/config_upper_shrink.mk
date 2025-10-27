export DESIGN_NAME = gcd
export PLATFORM    = nangate45_3D
export FLOW_VARIANT = openroad

export SC_LEF ?= $(PLATFORM_DIR)/lef_bottom/NangateOpenCellLibrary.macro.mod.bottom.lef
export ADDITIONAL_LEFS = $(PLATFORM_DIR)/lef_upper_shrink/NangateOpenCellLibrary.macro.mod.upper.lef 

export SC_LIB ?= $(PLATFORM_DIR)/lib_bottom/NangateOpenCellLibrary_typical.bottom.lib 
export ADDITIONAL_LIBS = $(PLATFORM_DIR)/lib_upper/NangateOpenCellLibrary_typical.upper.lib

export PLACE_DENSITY_LB_ADDON = 0.10
export TNS_END_PERCENT        = 100
export SKIP_GATE_CLONING   = 1

export DETAILED_ROUTE_ARGS = -droute_end_iter 5
export GLOBAL_ROUTE_ARGS = -allow_congestion -verbose -congestion_iterations 2
