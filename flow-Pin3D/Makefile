# settings.mk is not under source control. Put variables into this
# file to avoid having to adding the to the make command line.
-include settings.mk

DESIGN_CONFIG ?= ./designs/nangate45/gcd/config.mk

# Default TNS_END_PERCENT value
export TNS_END_PERCENT ?=5

# ==============================================================================
#  ____  _____ _____ _   _ ____
# / ___|| ____|_   _| | | |  _ \
# \___ \|  _|   | | | | | | |_) |
#  ___) | |___  | | | |_| |  __/
# |____/|_____| |_|  \___/|_|
#
# ==============================================================================

#-------------------------------------------------------------------------------
# Default target when invoking without specific target.
.DEFAULT_GOAL := finish

#-------------------------------------------------------------------------------
# Proper way to initiate SHELL for make
SHELL          := /usr/bin/env bash
.SHELLFLAGS    := -o pipefail -c

#-------------------------------------------------------------------------------
# Setup variables to point to root / head of the OpenROAD directory
# - the following settings allowed user to point OpenROAD binaries to different
#   location
# - default is current install / clone directory
export FLOW_HOME ?= $(shell pwd)

#-------------------------------------------------------------------------------
# Setup variables to point to other location for the following sub directory
# - designs - default is under current directory
# - platforms - default is under current directory
# - work home - default is current directory
# - utils, scripts, test - default is under current directory
export DESIGN_HOME   ?= $(FLOW_HOME)/designs
export PLATFORM_HOME ?= $(FLOW_HOME)/platforms
export WORK_HOME     ?= .

export UTILS_DIR     ?= $(FLOW_HOME)/util
export OPENROAD_SCRIPTS_DIR ?= $(FLOW_HOME)/scripts_openroad

#-------------------------------------------------------------------------------
# setup all commands used within this flow
TIME_CMD = /usr/bin/time -f 'Elapsed time: %E[h:]min:sec. CPU time: user %U sys %S (%P). Peak memory: %MKB.'
TIME_TEST = $(shell $(TIME_CMD) echo foo 2>/dev/null)
ifeq (, $(strip $(TIME_TEST)))
  TIME_CMD = /usr/bin/time
endif

# The following determine the executable location for each tool used by this flow.
# Priority is given to
#       1 user explicit set with variable in Makefile or command line, for instance setting OPENROAD_EXE
#       2 ORFS compiled tools: openroad, yosys
export OPENROAD_EXE      ?= $(shell which openroad)
export YOSYS_EXE               ?= $(shell which yosys)
export STA_EXE            := $(shell which sta)
OPENROAD_ARGS            = -no_init $(OR_ARGS)
OPENROAD_CMD             = $(OPENROAD_EXE) -exit $(OPENROAD_ARGS)
OPENROAD_NO_EXIT_CMD     = $(OPENROAD_EXE) $(OPENROAD_ARGS)
OPENROAD_GUI_CMD         = $(OPENROAD_EXE) -gui $(OR_ARGS)
YOSYS_FLAGS += -v 3

#-------------------------------------------------------------------------------
# Include design and platform configu	ration
include $(DESIGN_CONFIG)

PUBLIC=nangate45 nangate45_3D

ifneq ($(wildcard $(PLATFORM_HOME)/$(PLATFORM)),)
  export PLATFORM_DIR = $(PLATFORM_HOME)/$(PLATFORM)
else ifneq ($(findstring $(PLATFORM),$(PUBLIC)),)
  export PLATFORM_DIR = ./platforms/$(PLATFORM)
else ifneq ($(wildcard ../../$(PLATFORM)),)
  export PLATFORM_DIR = ../../$(PLATFORM)
else
  $(error [ERROR][FLOW] Platform '$(PLATFORM)' not found.)
endif

ifeq ($(MAKELEVEL),0)
$(info [INFO][FLOW] Using platform directory $(PLATFORM_DIR))
endif
include $(PLATFORM_DIR)/config.mk

# Setup working directories
export DESIGN_NICKNAME ?= $(DESIGN_NAME)
export FLOW_VARIANT ?= base
export DESIGN_DIR  = $(dir $(DESIGN_CONFIG))
export LOG_DIR     = $(WORK_HOME)/logs/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
export OBJECTS_DIR = $(WORK_HOME)/objects/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
export REPORTS_DIR = $(WORK_HOME)/reports/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
export RESULTS_DIR = $(WORK_HOME)/results/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)

#-------------------------------------------------------------------------------
ifeq (, $(strip $(NPROC)))
  # Linux (utility program)
  NPROC := $(shell nproc 2>/dev/null)

  ifeq (, $(strip $(NPROC)))
    # Linux (generic)
    NPROC := $(shell grep -c ^processor /proc/cpuinfo 2>/dev/null)
  endif
  ifeq (, $(strip $(NPROC)))
    # BSD (at least FreeBSD and Mac OSX)
    NPROC := $(shell sysctl -n hw.ncpu 2>/dev/null)
  endif
  ifeq (, $(strip $(NPROC)))
    # Fallback
    NPROC := 1
  endif
endif
export NUM_CORES := $(NPROC)

# Utility to print tool version information
#-------------------------------------------------------------------------------
.PHONY: versions.txt
versions.txt:
	@$(YOSYS_EXE) -V > $@
	@echo openroad `$(OPENROAD_EXE) -version` >> $@

# Pre-process libraries
# ==============================================================================
# Create temporary Liberty files which have the proper dont_use properties set
# For use with Yosys and ABC
#-------------------------------------------------------------------------------
export DONT_USE_LIBS   = $(patsubst %.lib.gz, %.lib, $(addprefix $(OBJECTS_DIR)/lib/, $(notdir $(LIB_FILES))))
export DONT_USE_SC_LIB ?= $(firstword $(DONT_USE_LIBS))

.SECONDEXPANSION:
$(DONT_USE_LIBS): $$(filter %$$(@F) %$$(@F).gz,$(LIB_FILES))
	@mkdir -p $(OBJECTS_DIR)/lib
	$(UTILS_DIR)/preprocessLib.py -i $^ -o $@

$(OBJECTS_DIR)/lib/merged.lib:
	$(UTILS_DIR)/mergeLib.pl $(PLATFORM)_merged $(DONT_USE_LIBS) > $@

# Design Flow Relative Settings
export GALLERY_REPORT ?= 0
# Enables hierarchical yosys
export SYNTH_HIERARCHICAL ?= 0
export SYNTH_STOP_MODULE_SCRIPT = $(OBJECTS_DIR)/mark_hier_stop_modules.tcl
ifeq ($(SYNTH_HIERARCHICAL), 1)
export HIER_REPORT_SCRIPT = $(OPENROAD_SCRIPTS_DIR)/synth_hier_report.tcl
export MAX_UNGROUP_SIZE ?= 0
endif
# Enables Re-synthesis for area reclaim
export RESYNTH_AREA_RECOVER ?= 0
export RESYNTH_TIMING_RECOVER ?= 0
export ABC_AREA ?= 0

# Global setting for Synthesis
export SYNTH_ARGS ?= -flatten

# Global setting for Floorplan
export PLACE_PINS_ARGS

export GPL_TIMING_DRIVEN ?= 1
export GPL_ROUTABILITY_DRIVEN ?= 1

export ENABLE_DPO ?= 1
export DPO_MAX_DISPLACEMENT ?= 5 1
# ==============================================================================
#  ______   ___   _ _____ _   _ _____ ____ ___ ____
# / ___\ \ / / \ | |_   _| | | | ____/ ___|_ _/ ___|
# \___ \\ V /|  \| | | | | |_| |  _| \___ \| |\___ \
#  ___) || | | |\  | | | |  _  | |___ ___) | | ___) |
# |____/ |_| |_| \_| |_| |_| |_|_____|____/___|____/
#
.PHONY: synth
synth: versions.txt \
       $(RESULTS_DIR)/1_synth.v \
       $(RESULTS_DIR)/1_synth.sdc

.PHONY: synth-report
synth-report: synth
	$(UNSET_AND_MAKE) do-synth-report

.PHONY: do-synth-report
do-synth-report:
	($(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/synth_metrics.tcl) 2>&1 | tee -a $(LOG_DIR)/1_1_yosys.log

# ==============================================================================


# Run Synthesis using yosys
#-------------------------------------------------------------------------------
SYNTH_SCRIPT ?= $(OPENROAD_SCRIPTS_DIR)/synth.tcl

$(SYNTH_STOP_MODULE_SCRIPT):
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	($(TIME_CMD) $(YOSYS_EXE) $(YOSYS_FLAGS) -c $(HIER_REPORT_SCRIPT)) 2>&1 | tee $(LOG_DIR)/1_1_yosys_hier_report.log

ifeq ($(SYNTH_HIERARCHICAL), 1)
$(RESULTS_DIR)/1_1_yosys.v: $(SYNTH_STOP_MODULE_SCRIPT)
endif

$(RESULTS_DIR)/1_1_yosys.v $(RESULTS_DIR)/1_synth.sdc &: $(DONT_USE_LIBS) $(WRAPPED_LIBS) $(DONT_USE_SC_LIB) $(DFF_LIB_FILE) $(VERILOG_FILES) $(CACHED_NETLIST) $(LATCH_MAP_FILE) $(ADDER_MAP_FILE) $(SDC_FILE)
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	($(TIME_CMD) $(YOSYS_EXE) $(YOSYS_FLAGS) -c $(SYNTH_SCRIPT)) 2>&1 | tee $(LOG_DIR)/1_1_yosys.log
	cp $(SDC_FILE) $(RESULTS_DIR)/1_synth.sdc

$(RESULTS_DIR)/1_synth.v: $(RESULTS_DIR)/1_1_yosys.v
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	cp $< $@

.PHONY: clean_synth
clean_synth:
	rm -f  $(RESULTS_DIR)/1_*.v $(RESULTS_DIR)/1_synth.sdc
	rm -f  $(REPORTS_DIR)/synth_*
	rm -f  $(LOG_DIR)/1_*
	rm -f  $(SYNTH_STOP_MODULE_SCRIPT)
	rm -rf _tmp_yosys-abc-*


# ==============================================================================
#  _____ _     ___   ___  ____  ____  _        _    _   _
# |  ___| |   / _ \ / _ \|  _ \|  _ \| |      / \  | \ | |
# | |_  | |  | | | | | | | |_) | |_) | |     / _ \ |  \| |
# |  _| | |__| |_| | |_| |  _ <|  __/| |___ / ___ \| |\  |
# |_|   |_____\___/ \___/|_| \_\_|   |_____/_/   \_\_| \_|
#
.PHONY: floorplan
floorplan: $(RESULTS_DIR)/2_floorplan.odb \
           $(RESULTS_DIR)/2_floorplan.sdc

# ==============================================================================

ifneq ($(FOOTPRINT),)
IS_CHIP = 1
else ifneq ($(FOOTPRINT_TCL),)
IS_CHIP = 1
endif

UNSET_AND_MAKE = @bash -c 'for var in $(UNSET_VARIABLES_NAMES); do unset $$var; done; $(MAKE) --no-print-directory DESIGN_CONFIG=$(DESIGN_CONFIG) $$@' --

define do-step
$(if $(5),$(5),$(RESULTS_DIR))/$(1)$(if $(4),$(4),.odb): $(2)
	$$(UNSET_AND_MAKE) do-$(1)

.PHONY: do-$(1)
do-$(1):
	($(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/$(3).tcl -metrics $(LOG_DIR)/$(1).json) 2>&1 | tee $(LOG_DIR)/$(1).tmp.log
	mv $(LOG_DIR)/$(1).tmp.log $(LOG_DIR)/$(1).log
endef

define do-copy
$(RESULTS_DIR)/$(1)$(if $(4),$(4),.odb): $(RESULTS_DIR)/$(2) $(3)
	$$(UNSET_AND_MAKE) do-$(1)$(if $(4),$(4),)

.PHONY: do-$(1)$(if $(4),$(4),)
do-$(1)$(if $(4),$(4),):
	cp $(RESULTS_DIR)/$(2) $(RESULTS_DIR)/$(1)$(if $(4),$(4),.odb)
endef


# STEP 1: Translate verilog to odb
#-------------------------------------------------------------------------------
$(eval $(call do-step,2_1_floorplan,$(RESULTS_DIR)/1_synth.v $(RESULTS_DIR)/1_synth.sdc $(TECH_LEF) $(SC_LEF) $(ADDITIONAL_LEFS) $(FOOTPRINT) $(SIG_MAP_FILE) $(FOOTPRINT_TCL),floorplan))

# STEP 2: IO Placement (random)
#-------------------------------------------------------------------------------
ifndef IS_CHIP
$(eval $(call do-step,2_2_floorplan_io,$(RESULTS_DIR)/2_1_floorplan.odb $(IO_CONSTRAINTS),io_placement_random))
else
$(eval $(call do-copy,2_2_floorplan_io,2_1_floorplan.odb,$(IO_CONSTRAINTS)))
endif

# STEP 3: Timing Driven Mixed Sized Placement
#-------------------------------------------------------------------------------
ifeq ($(MACRO_PLACEMENT)$(MACRO_PLACEMENT_TCL)$(RTLMP_FLOW),)
$(eval $(call do-step,2_3_floorplan_tdms,$(RESULTS_DIR)/2_2_floorplan_io.odb $(RESULTS_DIR)/1_synth.v $(RESULTS_DIR)/1_synth.sdc $(LIB_FILES),tdms_place))
else
$(eval $(call do-copy,2_3_floorplan_tdms,2_2_floorplan_io.odb,$(RESULTS_DIR)/1_synth.v $(RESULTS_DIR)/1_synth.sdc $(LIB_FILES)))
endif

.PHONY: do-pre_cts
do-pre_cts:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	cp $(RESULTS_DIR)/$(DESIGN_DIMENSION)_out.odb $(RESULTS_DIR)/2_5_floorplan_tapcell.odb
	$(UNSET_AND_MAKE) do-2_6_floorplan_pdn do-2_floorplan 
	cp $(RESULTS_DIR)/1_synth.sdc $(RESULTS_DIR)/2_floorplan.sdc
	cp $(RESULTS_DIR)/2_floorplan.odb $(RESULTS_DIR)/3_3_place_gp.odb
	$(UNSET_AND_MAKE) do-3_4_place_resized do-3_5_place_dp do-3_place do-3_place.sdc

.PHONY: do-autoflow
do-autoflow:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/init_odb.tcl
	$(UNSET_AND_MAKE) do-pre_cts

.PHONY: do-cts_eval
do-cts_eval:
	python3 $(OPENROAD_SCRIPTS_DIR)/save_map.py
	python3 $(OPENROAD_SCRIPTS_DIR)/modify_cts_def.py
	python3 $(OPENROAD_SCRIPTS_DIR)/split_cts_def.py
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/lg_bottom.tcl
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/lg_upper.tcl
	python3 $(OPENROAD_SCRIPTS_DIR)/read_def_store_coord.py
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/load_cts.tcl
	cp $(RESULTS_DIR)/my_cts.odb $(RESULTS_DIR)/4_cts.odb
	cp $(RESULTS_DIR)/1_synth.sdc $(RESULTS_DIR)/4_cts.sdc

# STEP 5: Tapcell and Welltie insertion
#-------------------------------------------------------------------------------
$(eval $(call do-step,2_5_floorplan_tapcell,$(RESULTS_DIR)/2_4_floorplan_macro.odb $(TAPCELL_TCL),tapcell))

# STEP 6: PDN generation
#-------------------------------------------------------------------------------
$(eval $(call do-step,2_6_floorplan_pdn,$(RESULTS_DIR)/2_5_floorplan_tapcell.odb $(PDN_TCL),pdn))

$(eval $(call do-copy,2_floorplan,2_6_floorplan_pdn.odb,))

$(RESULTS_DIR)/2_floorplan.sdc: $(RESULTS_DIR)/2_1_floorplan.odb

.PHONY: do-pin-3d-flow-tier-partition
do-pin-3d-flow-tier-partition:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/tier_partition.tcl

.PHONY: clean_floorplan
clean_floorplan:
	rm -f $(RESULTS_DIR)/2_*floorplan*.odb $(RESULTS_DIR)/2_floorplan.sdc $(RESULTS_DIR)/2_*.v $(RESULTS_DIR)/2_*.def
	rm -f $(REPORTS_DIR)/2_*
	rm -f $(LOG_DIR)/2_*

# ==============================================================================
#  ____  _        _    ____ _____
# |  _ \| |      / \  / ___| ____|
# | |_) | |     / _ \| |   |  _|
# |  __/| |___ / ___ \ |___| |___
# |_|   |_____/_/   \_\____|_____|
#
.PHONY: place
place: $(RESULTS_DIR)/3_place.odb \
       $(RESULTS_DIR)/3_place.sdc
# ==============================================================================
# STEP 1: Global placement without placed IOs, timing-driven, and routability-driven.
#-------------------------------------------------------------------------------
#$(eval $(call do-step,3_1_place_gp_skip_io,$(RESULTS_DIR)/2_floorplan.odb $(RESULTS_DIR)/2_floorplan.sdc $(LIB_FILES),global_place_skip_io))

$(eval $(call do-copy,3_1_place_gp_skip_io,2_floorplan.odb,))

# STEP 2: IO placement (non-random)
#-------------------------------------------------------------------------------
# ifndef IS_CHIP
# $(eval $(call do-step,3_2_place_iop,$(RESULTS_DIR)/3_1_place_gp_skip_io.odb $(IO_CONSTRAINTS),io_placement))
# else
$(eval $(call do-copy,3_2_place_iop,3_1_place_gp_skip_io.odb,$(IO_CONSTRAINTS)))
# endif

# STEP 3: Global placement with placed IOs, timing-driven, and routability-driven.
#-------------------------------------------------------------------------------
$(eval $(call do-step,3_3_place_gp,$(RESULTS_DIR)/3_2_place_iop.odb $(RESULTS_DIR)/2_floorplan.sdc $(LIB_FILES),global_place))

# STEP 4: Resizing & Buffering
#-------------------------------------------------------------------------------
$(eval $(call do-step,3_4_place_resized,$(RESULTS_DIR)/3_3_place_gp.odb $(RESULTS_DIR)/2_floorplan.sdc,resize))

.PHONY: clean_resize
clean_resize:
	rm -f $(RESULTS_DIR)/3_4_place_resized.odb

# STEP 5: Detail placement
#-------------------------------------------------------------------------------
$(eval $(call do-step,3_5_place_dp,$(RESULTS_DIR)/3_4_place_resized.odb,detail_place))

$(eval $(call do-copy,3_place,3_5_place_dp.odb,))

$(eval $(call do-copy,3_place,2_floorplan.sdc,,.sdc))

.PHONY: do-pin-3d-flow-place-init
do-pin-3d-flow-place-init:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/place_init.tcl

.PHONY: do-pin-3d-flow-place-upper
do-pin-3d-flow-place-upper:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _bottom --status FIXED
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/place_upper.tcl
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _bottom --status PLACED

.PHONY: do-pin-3d-flow-place-bottom
do-pin-3d-flow-place-bottom:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _upper --status FIXED
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/place_bottom.tcl
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _upper --status PLACED

.PHONY: do-pin-3d-flow-2dpre
do-pin-3d-flow-2dpre:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	mkdir -p $(WORK_HOME)/results/$(PLATFORM)_3D/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
	$(UNSET_AND_MAKE) synth do-2_1_floorplan do-2_2_floorplan_io do-pin-3d-flow-tier-partition
	cp -r $(WORK_HOME)/results/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)/* $(WORK_HOME)/results/$(PLATFORM)_3D/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)/

.PHONY: do-pin-3d-flow-pre
do-pin-3d-flow-pre:
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR)
	python3 $(OPENROAD_SCRIPTS_DIR)/generate_3d_def.py \
		--input $(RESULTS_DIR)/2_2_floorplan_io.def \
		--output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def \
		--partition $(RESULTS_DIR)/partition.txt
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/init_odb.tcl

# Clean Targets
#-------------------------------------------------------------------------------
.PHONY: clean_place
clean_place:
	rm -f $(RESULTS_DIR)/3_*place*.odb
	rm -f $(RESULTS_DIR)/3_place.sdc
	rm -f $(RESULTS_DIR)/3_*.def $(RESULTS_DIR)/3_*.v
	rm -f $(REPORTS_DIR)/3_*
	rm -f $(LOG_DIR)/3_*

# ==============================================================================
#   ____ _____ ____
#  / ___|_   _/ ___|
# | |     | | \___ \
# | |___  | |  ___) |
#  \____| |_| |____/
#
.PHONY: cts
cts: $(RESULTS_DIR)/4_cts.odb \
     $(RESULTS_DIR)/4_cts.sdc
# ==============================================================================

# Run TritonCTS
# ------------------------------------------------------------------------------
$(eval $(call do-step,4_1_cts,$(RESULTS_DIR)/3_place.odb $(RESULTS_DIR)/3_place.sdc,cts))

# Filler cell insertion
# ------------------------------------------------------------------------------
$(eval $(call do-step,4_2_cts_fillcell,$(RESULTS_DIR)/4_1_cts.odb,fillcell))

$(RESULTS_DIR)/4_cts.sdc: $(RESULTS_DIR)/4_cts.odb

$(eval $(call do-copy,4_cts,4_2_cts_fillcell.odb))

.PHONY: do-cts
do-cts:
	$(UNSET_AND_MAKE) do-4_1_cts do-4_2_cts_fillcell do-4_cts

.PHONY: clean_cts
clean_cts:
	rm -rf $(RESULTS_DIR)/4_*cts*.odb $(RESULTS_DIR)/4_cts.sdc $(RESULTS_DIR)/4_*.v $(RESULTS_DIR)/4_*.def
	rm -f  $(REPORTS_DIR)/4_*
	rm -f  $(LOG_DIR)/4_*

# ==============================================================================
#  ____   ___  _   _ _____ ___ _   _  ____
# |  _ \ / _ \| | | |_   _|_ _| \ | |/ ___|
# | |_) | | | | | | | | |  | ||  \| | |  _
# |  _ <| |_| | |_| | | |  | || |\  | |_| |
# |_| \_\\___/ \___/  |_| |___|_| \_|\____|
#
.PHONY: route
route: $(RESULTS_DIR)/5_route.odb \
       $(RESULTS_DIR)/5_route.sdc
# ==============================================================================

# STEP 1: Run global route
#-------------------------------------------------------------------------------
$(eval $(call do-step,5_1_grt,$(RESULTS_DIR)/4_cts.odb $(FASTROUTE_TCL) $(PRE_GLOBAL_ROUTE),global_route))

# STEP 2: Run detailed route
#-------------------------------------------------------------------------------
ifeq ($(USE_WXL),)
$(eval $(call do-step,5_2_route,$(RESULTS_DIR)/5_1_grt.odb,detail_route))
else
$(eval $(call do-step,5_2_route,$(RESULTS_DIR)/4_cts.odb,detail_route))
endif

$(eval $(call do-copy,5_route,5_2_route.odb))

$(eval $(call do-copy,5_route,4_cts.sdc,,.sdc))

.PHONY: do-route
do-route:
	$(UNSET_AND_MAKE) do-5_1_grt do-5_2_route do-5_route do-5_route.sdc

$(RESULTS_DIR)/5_route.v:
	@export OR_DB=5_route ;\
	$(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/write_verilog.tcl

.PHONY: clean_route
clean_route:
	rm -rf output*/ results*.out.dmp layer_*.mps
	rm -rf *.gdid *.log *.met *.sav *.res.dmp
	rm -rf $(RESULTS_DIR)/route.guide $(RESULTS_DIR)/output_guide.mod $(RESULTS_DIR)/updated_clks.sdc
	rm -rf $(RESULTS_DIR)/5_*.odb $(RESULTS_DIR)/5_route.sdc $(RESULTS_DIR)/5_*.def $(RESULTS_DIR)/5_*.v
	rm -f  $(REPORTS_DIR)/5_*
	rm -f  $(LOG_DIR)/5_*

# ==============================================================================
#  _____ ___ _   _ ___ ____  _   _ ___ _   _  ____
# |  ___|_ _| \ | |_ _/ ___|| | | |_ _| \ | |/ ___|
# | |_   | ||  \| || |\___ \| |_| || ||  \| | |  _
# |  _|  | || |\  || | ___) |  _  || || |\  | |_| |
# |_|   |___|_| \_|___|____/|_| |_|___|_| \_|\____|
#
GDS_FINAL_FILE = $(RESULTS_DIR)/6_final.gds
.PHONY: finish
finish: $(LOG_DIR)/6_report.log \
        $(RESULTS_DIR)/6_final.v \
        $(RESULTS_DIR)/6_final.sdc \
        $(GDS_FINAL_FILE)
	$(UNSET_AND_MAKE) elapsed

.PHONY: elapsed
elapsed:
	-@$(UTILS_DIR)/genElapsedTime.py -d $(BLOCK_LOG_FOLDERS) $(LOG_DIR)

# ==============================================================================

ifneq ($(USE_FILL),)
$(eval $(call do-step,6_1_fill,$(RESULTS_DIR)/5_route.odb $(RESULTS_DIR)/5_route.sdc $(FILL_CONFIG),density_fill))
else
$(eval $(call do-copy,6_1_fill,5_route.odb))
endif

$(eval $(call do-copy,6_1_fill,5_route.sdc,,.sdc))

$(eval $(call do-copy,6_final,5_route.sdc,,.sdc))

$(eval $(call do-step,6_report,$(RESULTS_DIR)/6_1_fill.odb $(RESULTS_DIR)/6_1_fill.sdc,final_report,.log,$(LOG_DIR)))

$(RESULTS_DIR)/6_final.def: $(LOG_DIR)/6_report.log
$(eval $(call do-step,6_figure,$(RESULTS_DIR)/6_1_fill.odb $(RESULTS_DIR)/6_1_fill.sdc,generate_fig,.log,$(LOG_DIR)))

# NOTE! No GDS file for now
.PHONY: do-finish
do-finish:
	$(UNSET_AND_MAKE) do-6_1_fill do-6_1_fill.sdc do-6_final.sdc do-6_report elapsed

$(RESULTS_DIR)/6_final.v: $(LOG_DIR)/6_report.log

$(GDS_FINAL_FILE): $(GDS_MERGED_FILE)
	cp $< $@

.PHONY: clean_finish
clean_finish:
	rm -rf $(RESULTS_DIR)/6_*.gds $(RESULTS_DIR)/6_*.oas $(RESULTS_DIR)/6_*.odb $(RESULTS_DIR)/6_*.v $(RESULTS_DIR)/6_*.def $(RESULTS_DIR)/6_*.sdc $(RESULTS_DIR)/6_*.spef
	rm -rf $(REPORTS_DIR)/6_*.rpt
	rm -f  $(LOG_DIR)/6_*

.PHONY: clean
clean:
	@echo
	@echo "Make clean disabled."
	@echo "Use make clean_all or clean individual steps:"
	@echo "  clean_synth clean_floorplan clean_place clean_cts clean_route clean_finish"
	@echo

.PHONY: clean_all
clean_all: clean_synth clean_floorplan clean_place clean_cts clean_route clean_finish clean_metadata clean_abstract
	rm -rf $(OBJECTS_DIR)

export FINAL_DEF ?= $(RESULTS_DIR)/6_final.def
export FINAL_V ?= $(RESULTS_DIR)/6_final.v
export FINAL_SDC ?= $(RESULTS_DIR)/6_1_fill.sdc
export FINAL_SPEF ?= $(RESULTS_DIR)/6_final.spef

# 3d hotspot flow
export HOTSPOT_SCRIPTS_DIR ?= $(FLOW_HOME)/HotSpot
export MAX_T_PY      := $(HOTSPOT_SCRIPTS_DIR)/scripts/max_t.py
export DIVIDE_GRID_PY      := $(HOTSPOT_SCRIPTS_DIR)/scripts/divide_grid.py
export DIVIDE_DEF_PY      := $(HOTSPOT_SCRIPTS_DIR)/scripts/divide_def.py
export REPORT_POWER_TCL   := $(HOTSPOT_SCRIPTS_DIR)/scripts/run_report_power.tcl
export MERGE_PTRACE_PY      := $(HOTSPOT_SCRIPTS_DIR)/scripts/merge_ptrace.py
export HOTSPOT_OUTPUT   := $(HOTSPOT_SCRIPTS_DIR)/scripts/output
.PHONY: do-hotspot
do-hotspot: 
	@echo "Starting HotSpot Thermal Analysis for design: $(DESIGN_NAME)"
	python3 $(DIVIDE_DEF_PY) -i $(FINAL_DEF) -o $(RESULTS_DIR)

	@echo "[1/8] Dividing upper DEF into grids..."
	python3 $(DIVIDE_GRID_PY) \
		-i "$(RESULTS_DIR)/6_final_upper.def" \
		-o "$(HOTSPOT_OUTPUT)" \
		-g 10 \
		--flp "floorplan1.flp" \
		--prefix "upper"
	
	@echo "[2/8] Running power analysis with STA for upper die..."
	$(STA_EXE) $(REPORT_POWER_TCL)

	@mv "$(HOTSPOT_OUTPUT)/gcc.ptrace" "$(HOTSPOT_OUTPUT)/upper.ptrace"

	@echo "[3/8] Dividing bottom DEF into grids..."
	python3 $(DIVIDE_GRID_PY) \
		-i "$(RESULTS_DIR)/6_final_bottom.def" \
		-o "$(HOTSPOT_OUTPUT)" \
		-g 10 \
		--flp "floorplan2.flp" \
		--prefix "bottom"

	@echo "[4/8] Running power analysis with STA for bottom die..."
	$(STA_EXE) $(REPORT_POWER_TCL)

	@mv "$(HOTSPOT_OUTPUT)/gcc.ptrace" "$(HOTSPOT_OUTPUT)/bottom.ptrace"

	python3 $(MERGE_PTRACE_PY) \
		-u "$(HOTSPOT_OUTPUT)/upper.ptrace" \
		-b "$(HOTSPOT_OUTPUT)/bottom.ptrace" \
		-o "$(HOTSPOT_OUTPUT)/test.ptrace"

	rm -f "$(HOTSPOT_OUTPUT)/upper.ptrace" "$(HOTSPOT_OUTPUT)/bottom.ptrace"
	
	@echo "[6/8] Creating version directory..."
	@mkdir -p "$(HOTSPOT_SCRIPTS_DIR)/examples/$(DESIGN_DIMENSION)_$(DESIGN_NAME)"
	@mkdir -p "$(HOTSPOT_SCRIPTS_DIR)/examples/thermal/"
	@chown -R $(USER):$(USER) "$(HOTSPOT_SCRIPTS_DIR)/examples/$(DESIGN_DIMENSION)_$(DESIGN_NAME)"
	
	@rsync -a --exclude='*/' \
		"$(HOTSPOT_SCRIPTS_DIR)/examples/thermal/" \
		"$(HOTSPOT_SCRIPTS_DIR)/examples/$(DESIGN_DIMENSION)_$(DESIGN_NAME)/"
	
	@cp -f "$(HOTSPOT_SCRIPTS_DIR)/scripts/output/"* \
		"$(HOTSPOT_SCRIPTS_DIR)/examples/$(DESIGN_DIMENSION)_$(DESIGN_NAME)/" 2>/dev/null || true
	
	@echo "Running HotSpot analysis..."
	@cd "$(HOTSPOT_SCRIPTS_DIR)/examples/$(DESIGN_DIMENSION)_$(DESIGN_NAME)/" && \
		chown -R $(USER):$(USER) ./ && \
		chmod +x run.sh && \
		./run.sh
	
	@mkdir -p "$(RESULTS_DIR)/hotspot_outputs"
	@rsync -a --delete \
		"$(HOTSPOT_SCRIPTS_DIR)/examples/$(DESIGN_DIMENSION)_$(DESIGN_NAME)/outputs/" \
		"$(RESULTS_DIR)/hotspot_outputs/" 2>/dev/null || true
	@chown -R $(USER):$(USER) "$(RESULTS_DIR)/hotspot_outputs"


	@rm -r "$(HOTSPOT_SCRIPTS_DIR)/examples/thermal/outputs" || true
	@mkdir -p "$(HOTSPOT_SCRIPTS_DIR)/examples/thermal/outputs"
	@chown -R $(USER):$(USER) "$(HOTSPOT_SCRIPTS_DIR)/examples/thermal/outputs"

	@echo "[8/8] Analysis completed. Results: $(RESULTS_DIR)/hotspot_outputs"