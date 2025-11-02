export DESIGN_NAME = gcd
export PLATFORM    = nangate45

export VERILOG_FILES = $(DESIGN_HOME)/src/$(DESIGN_NAME)/gcd.v
export SDC_FILE      = $(DESIGN_HOME)/nangate45_3D/$(DESIGN_NAME)/constraint.sdc
export ABC_AREA      = 1

# Adders degrade GCD
export ADDER_MAP_FILE :=

export CORE_MARGIN = 1
export ASPECT_RATIO = 1.0
export CORE_UTILIZATION ?= 95
export PLACE_DENSITY_LB_ADDON = 0.10
export TNS_END_PERCENT        = 100
export REMOVE_CELLS_FOR_EQY   = TAPCELL*
export GEN_EFF medium
export MAP_EFF high

export OPEN_GUI ?= 1
export NUM_CORES   ?= 32
