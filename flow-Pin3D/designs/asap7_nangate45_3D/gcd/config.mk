export DESIGN_NAME = gcd
export PLATFORM    = asap7_nangate45_3D

export PLACE_DENSITY_LB_ADDON = 0.10
export TNS_END_PERCENT        = 100
export SKIP_GATE_CLONING   = 1

export GLOBAL_ROUTE_ARGS = -verbose -congestion_iterations 30

export CORE_UTILIZATION ?= 30
export OPEN_GUI ?= 1
export NUM_CORES   ?= 32
