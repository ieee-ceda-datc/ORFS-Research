export DESIGN_NICKNAME = jpeg
export DESIGN_NAME = jpeg_encoder
export PLATFORM    = nangate45

export VERILOG_FILES = $(sort $(wildcard $(DESIGN_HOME)/src/$(DESIGN_NICKNAME)/*.v))
export VERILOG_INCLUDE_DIRS = $(DESIGN_HOME)/src/$(DESIGN_NICKNAME)/include
export SDC_FILE = $(DESIGN_HOME)/nangate45_3D/$(DESIGN_NICKNAME)/constraint.sdc

export ABC_AREA = 1
export CORE_MARGIN = 1
export CORE_ASPECT_RATIO = 1.0
export CORE_UTILIZATION ?= 95
export PLACE_DENSITY_LB_ADDON = 0.10
export TNS_END_PERCENT        = 100
# Effort level during optimization in syn_generic -physical (or called generic) stage
export GEN_EFF medium
# Effort level during optimization in syn_map -physical (or called mapping) stage
export MAP_EFF high

export OPEN_GUI ?= 1
export NUM_CORES   ?= 32
