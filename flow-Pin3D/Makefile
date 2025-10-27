# =========================================
# Unified Pin3D Flow Makefile (ord-* for OpenROAD, cds-* for Cadence)
# =========================================
# - No legacy target names preserved (only ord-* / cds-*).
# - OpenROAD scripts: scripts_openroad/
# - Cadence  scripts: scripts_cadence/
# - Flow behavior matches your original sequences.

-include settings.mk

# ---------------- Common paths ----------------
export FLOW_HOME     ?= $(shell pwd)
export DESIGN_HOME   ?= $(FLOW_HOME)/designs
export PLATFORM_HOME ?= $(FLOW_HOME)/platforms
export WORK_HOME     ?= .

# Scripts (OpenROAD & Cadence)
export OPENROAD_SCRIPTS_DIR ?= $(FLOW_HOME)/scripts_openroad
export CADENCE_SCRIPTS_DIR  ?= $(FLOW_HOME)/scripts_cadence    # Cadence 专用脚本目录

# ---------------- Design config ----------------
# 默认指向 3D gcd 配置；可在命令行覆盖
DESIGN_CONFIG ?= ./designs/nangate45_3D/gcd/config.mk
include $(DESIGN_CONFIG)

# ---------------- Platform resolve ----------------
PUBLIC_PLATFORMS = nangate45 nangate45_3D
ifneq ($(wildcard $(PLATFORM_HOME)/$(PLATFORM)),)
  export PLATFORM_DIR = $(PLATFORM_HOME)/$(PLATFORM)
else ifneq ($(findstring $(PLATFORM),$(PUBLIC_PLATFORMS)),)
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

# ---------------- Work dirs ----------------
export DESIGN_NICKNAME ?= $(DESIGN_NAME)
export FLOW_VARIANT    ?= base
export LOG_DIR         ?= $(WORK_HOME)/logs/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
export OBJECTS_DIR     ?= $(WORK_HOME)/objects/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
export REPORTS_DIR     ?= $(WORK_HOME)/reports/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
export RESULTS_DIR     ?= $(WORK_HOME)/results/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)

# ---------------- Shell / time ----------------
SHELL       := /usr/bin/env bash
.SHELLFLAGS := -o pipefail -c
TIME_CMD    = /usr/bin/time -f 'Elapsed: %E  CPU: user %U sys %S (%P)  Peak: %M KB'
TIME_TEST   = $(shell $(TIME_CMD) echo foo 2>/dev/null); ifeq (, $(strip $(TIME_TEST))) ; TIME_CMD=/usr/bin/time ; endif

# ---------------- Tools (OpenROAD side) ----------------
export OPENROAD_EXE ?= $(shell which openroad)
export YOSYS_EXE    ?= $(shell which yosys)
export STA_EXE      ?= $(shell which sta)
OPENROAD_ARGS        = -no_init $(OR_ARGS)
OPENROAD_CMD         = $(OPENROAD_EXE) -exit $(OPENROAD_ARGS)
OPENROAD_GUI_CMD     = $(OPENROAD_EXE) -gui $(OR_ARGS)
YOSYS_FLAGS         += -v 3

# ---------------- Tools (Cadence side) ----------------
export GENUS_EXE   ?= $(shell which genus)
export INNOVUS_EXE ?= $(shell which innovus)
GENUS_CMD   = $(GENUS_EXE)
INNOVUS_CMD = $(INNOVUS_EXE)
export OPEN_GUI ?= 0
OPEN_GUI_CMD = $(if $(filter 1,$(OPEN_GUI)), , -no_gui)

# ---------------- Helpers ----------------
define _mkstdirs
	mkdir -p $(RESULTS_DIR) $(LOG_DIR) $(REPORTS_DIR) $(OBJECTS_DIR)
endef

# A small "sub-make" helper that clears env-vars side effects when chaining steps
UNSET_AND_MAKE = @bash -lc '$(MAKE) --no-print-directory DESIGN_CONFIG=$(DESIGN_CONFIG) $$@'

# ===============================
# ===== OpenROAD (ord-*) ========
# ===============================
# Keep functional parity with your original OpenROAD Makefile, but expose only ord-* targets.
# Files generated follow your original naming.

# Versions info (optional)
.PHONY: ord-versions
ord-versions:
	@$(call _mkstdirs)
	@{ \
		$(YOSYS_EXE) -V ; \
		echo openroad $$($(OPENROAD_EXE) -version) ; \
	} > $(LOG_DIR)/versions.txt 2>&1 || true

# ---------------- Synthesis (Yosys) ----------------
export DONT_USE_LIBS   = $(patsubst %.lib.gz, %.lib, $(addprefix $(OBJECTS_DIR)/lib/, $(notdir $(LIB_FILES))))
export DONT_USE_SC_LIB ?= $(firstword $(DONT_USE_LIBS))
export SYNTH_SCRIPT    ?= $(OPENROAD_SCRIPTS_DIR)/synth.tcl

$(OBJECTS_DIR)/lib/%.lib: $(LIB_DIR)/%.lib
	@mkdir -p $(OBJECTS_DIR)/lib
	@cp $< $@

$(OBJECTS_DIR)/lib/%.lib: $(LIB_DIR)/%.lib.gz
	@mkdir -p $(OBJECTS_DIR)/lib
	@gunzip -c $< > $@

# 主产物
ORD_SYN_V   := $(RESULTS_DIR)/1_synth.v
ORD_SYN_SDC := $(RESULTS_DIR)/1_synth.sdc

.PHONY: ord-synth
ord-synth: $(ORD_SYN_V) $(ORD_SYN_SDC)

$(RESULTS_DIR)/1_1_yosys.v $(ORD_SYN_SDC): $(DONT_USE_LIBS) $(VERILOG_FILES) $(SDC_FILE)
	@$(call _mkstdirs)
	( $(TIME_CMD) $(YOSYS_EXE) $(YOSYS_FLAGS) -c $(SYNTH_SCRIPT) ) 2>&1 | tee $(LOG_DIR)/1_1_yosys.log
	@cp $(SDC_FILE) $(ORD_SYN_SDC)

$(ORD_SYN_V): $(RESULTS_DIR)/1_1_yosys.v
	@$(call _mkstdirs)
	@cp $< $@

# ---------------- Generic step helpers used by OR flow ----------------
define do-step
$(RESULTS_DIR)/$(1)$(if $(4),$(4),.odb): $(2)
	$(UNSET_AND_MAKE) __do-$(1)

.PHONY: __do-$(1)
__do-$(1):
	( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/$(3).tcl -metrics $(LOG_DIR)/$(1).json ) 2>&1 | tee $(LOG_DIR)/$(1).log
endef

define do-copy
$(RESULTS_DIR)/$(1)$(if $(4),$(4),.odb): $(RESULTS_DIR)/$(2) $(3)
	$(UNSET_AND_MAKE) __do-$(1)$(if $(4),$(4),)

.PHONY: __do-$(1)$(if $(4),$(4),)
__do-$(1)$(if $(4),$(4),):
	cp $(RESULTS_DIR)/$(2) $(RESULTS_DIR)/$(1)$(if $(4),$(4),.odb)
endef

# Floorplan steps needed by ord-2dpre / ord-pre
$(eval $(call do-step,2_1_floorplan,$(ORD_SYN_V) $(ORD_SYN_SDC) $(TECH_LEF) $(SC_LEF) $(ADDITIONAL_LEFS) $(FOOTPRINT) $(SIG_MAP_FILE) $(FOOTPRINT_TCL),floorplan))
ifndef FOOTPRINT
  ifndef FOOTPRINT_TCL
    $(eval $(call do-step,2_2_floorplan_io,$(RESULTS_DIR)/2_1_floorplan.odb $(IO_CONSTRAINTS),io_placement_random))
  else
    $(eval $(call do-copy,2_2_floorplan_io,2_1_floorplan.odb,$(IO_CONSTRAINTS)))
  endif
else
  $(eval $(call do-copy,2_2_floorplan_io,2_1_floorplan.odb,$(IO_CONSTRAINTS)))
endif

# Some additional convenience copies
$(eval $(call do-step,2_5_floorplan_tapcell,$(RESULTS_DIR)/2_4_floorplan_macro.odb $(TAPCELL_TCL),tapcell))
$(eval $(call do-step,2_6_floorplan_pdn,$(RESULTS_DIR)/2_5_floorplan_tapcell.odb $(PDN_TCL),pdn))
$(eval $(call do-copy,2_floorplan,2_6_floorplan_pdn.odb,))
$(RESULTS_DIR)/2_floorplan.sdc: $(RESULTS_DIR)/2_1_floorplan.odb
	@cp $(ORD_SYN_SDC) $@

# ---------------- ord-2dpre（= synth + 2D fp + 2D IO + tier partition + copy to *_3D） ----------------
.PHONY: ord-2dpre
ord-2dpre: ord-synth $(RESULTS_DIR)/2_1_floorplan.odb $(RESULTS_DIR)/2_2_floorplan_io.odb
	@$(call _mkstdirs)
	# Tier partition（OpenROAD脚本）
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/tier_partition.tcl
	# 将2D阶段产物复制到 *_3D 路径，保持你原来的目录风格
	mkdir -p $(WORK_HOME)/results/$(PLATFORM)_3D/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)
	cp -r $(WORK_HOME)/results/$(PLATFORM)/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)/* \
	      $(WORK_HOME)/results/$(PLATFORM)_3D/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)/

# ---------------- ord-pre（= 生成3D初始 DEF + init_odb） ----------------
.PHONY: ord-pre
ord-pre:
	@$(call _mkstdirs)
	python3 $(OPENROAD_SCRIPTS_DIR)/generate_3d_def.py \
		--input  $(RESULTS_DIR)/2_2_floorplan_io.def \
		--output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def \
		--partition $(RESULTS_DIR)/partition.txt
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/init_odb.tcl

# ---------------- ord-place-*（upper/bottom/init） ----------------
.PHONY: ord-place-init
ord-place-init:
	@$(call _mkstdirs)
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/place_init.tcl

.PHONY: ord-place-upper
ord-place-upper:
	@$(call _mkstdirs)
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _bottom --status FIXED
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/place_upper.tcl
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _bottom --status PLACED

.PHONY: ord-place-bottom
ord-place-bottom:
	@$(call _mkstdirs)
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _upper --status FIXED
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/place_bottom.tcl
	python3 $(OPENROAD_SCRIPTS_DIR)/mark_cell.py --input $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --output $(RESULTS_DIR)/$(DESIGN_NAME)_3D.gp.def --backfix _upper --status PLACED

# ---------------- ord-autoflow（预CTS初始化，一次性跑若干置换） ----------------
.PHONY: ord-autoflow
ord-autoflow:
	@$(call _mkstdirs)
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/init_odb.tcl
	# 复用你之前的预CTS拼接逻辑
	cp $(RESULTS_DIR)/$(DESIGN_DIMENSION)_out.odb $(RESULTS_DIR)/2_5_floorplan_tapcell.odb || true
	$(UNSET_AND_MAKE) __do-2_6_floorplan_pdn __do-2_floorplan
	cp $(RESULTS_DIR)/1_synth.sdc $(RESULTS_DIR)/2_floorplan.sdc
	cp $(RESULTS_DIR)/2_floorplan.odb $(RESULTS_DIR)/3_3_place_gp.odb
	$(UNSET_AND_MAKE) __do-3_4_place_resized __do-3_5_place_dp
	cp $(RESULTS_DIR)/3_5_place_dp.odb $(RESULTS_DIR)/3_place.odb
	cp $(RESULTS_DIR)/2_floorplan.sdc $(RESULTS_DIR)/3_place.sdc

# ---------------- ord-cts / ord-cts-eval ----------------
.PHONY: ord-cts
ord-cts:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/cts.tcl ) 2>&1 | tee $(LOG_DIR)/4_1_cts.log
	( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/fillcell.tcl ) 2>&1 | tee $(LOG_DIR)/4_2_cts_fillcell.log
	cp $(RESULTS_DIR)/4_2_cts_fillcell.odb $(RESULTS_DIR)/4_cts.odb
	cp $(RESULTS_DIR)/3_place.sdc $(RESULTS_DIR)/4_cts.sdc

.PHONY: ord-cts-eval
ord-cts-eval:
	@$(call _mkstdirs)
	python3 $(OPENROAD_SCRIPTS_DIR)/save_map.py
	python3 $(OPENROAD_SCRIPTS_DIR)/modify_cts_def.py
	python3 $(OPENROAD_SCRIPTS_DIR)/split_cts_def.py
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/lg_bottom.tcl
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/lg_upper.tcl
	python3 $(OPENROAD_SCRIPTS_DIR)/read_def_store_coord.py
	$(OPENROAD_EXE) -exit $(OPENROAD_SCRIPTS_DIR)/load_cts.tcl
	cp $(RESULTS_DIR)/my_cts.odb $(RESULTS_DIR)/4_cts.odb
	cp $(RESULTS_DIR)/1_synth.sdc $(RESULTS_DIR)/4_cts.sdc

# ---------------- ord-route ----------------
.PHONY: ord-route
ord-route:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/global_route.tcl ) 2>&1 | tee $(LOG_DIR)/5_1_grt.log
	( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/detail_route.tcl ) 2>&1 | tee $(LOG_DIR)/5_2_route.log
	cp $(RESULTS_DIR)/5_2_route.odb $(RESULTS_DIR)/5_route.odb
	cp $(RESULTS_DIR)/4_cts.sdc   $(RESULTS_DIR)/5_route.sdc

# ---------------- ord-finish ----------------
export FINAL_DEF  ?= $(RESULTS_DIR)/6_final.def
export FINAL_V    ?= $(RESULTS_DIR)/6_final.v
export FINAL_SDC  ?= $(RESULTS_DIR)/6_1_fill.sdc
.PHONY: ord-finish
ord-finish:
	@$(call _mkstdirs)
	# density fill（如未配置则直接拷贝）
	if [ -n "$(USE_FILL)" ]; then \
	  ( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/density_fill.tcl ) 2>&1 | tee $(LOG_DIR)/6_1_fill.log ; \
	else \
	  cp $(RESULTS_DIR)/5_route.odb $(RESULTS_DIR)/6_1_fill.odb ; \
	  cp $(RESULTS_DIR)/5_route.sdc $(RESULTS_DIR)/6_1_fill.sdc ; \
	fi
	( $(TIME_CMD) $(OPENROAD_CMD) $(OPENROAD_SCRIPTS_DIR)/final_report.tcl ) 2>&1 | tee $(LOG_DIR)/6_report.log

# ---------------- ord-hotspot ----------------
export HOTSPOT_SCRIPTS_DIR ?= $(FLOW_HOME)/HotSpot
export MAX_T_PY        := $(HOTSPOT_SCRIPTS_DIR)/scripts/max_t.py
export DIVIDE_GRID_PY  := $(HOTSPOT_SCRIPTS_DIR)/scripts/divide_grid.py
export DIVIDE_DEF_PY   := $(HOTSPOT_SCRIPTS_DIR)/scripts/divide_def.py
export REPORT_POWER_TCL:= $(HOTSPOT_SCRIPTS_DIR)/scripts/run_report_power.tcl
export MERGE_PTRACE_PY := $(HOTSPOT_SCRIPTS_DIR)/scripts/merge_ptrace.py
export HOTSPOT_OUTPUT  := $(HOTSPOT_SCRIPTS_DIR)/scripts/output

.PHONY: ord-hotspot
ord-hotspot:
	@echo "Starting HotSpot Thermal Analysis for design: $(DESIGN_NAME)"
	python3 $(DIVIDE_DEF_PY) -i $(FINAL_DEF) -o $(RESULTS_DIR)
	python3 $(DIVIDE_GRID_PY) -i "$(RESULTS_DIR)/6_final_upper.def" -o "$(HOTSPOT_OUTPUT)" -g 10 --flp "floorplan1.flp" --prefix "upper"
	$(STA_EXE) $(REPORT_POWER_TCL)
	@mv "$(HOTSPOT_OUTPUT)/gcc.ptrace" "$(HOTSPOT_OUTPUT)/upper.ptrace"
	python3 $(DIVIDE_GRID_PY) -i "$(RESULTS_DIR)/6_final_bottom.def" -o "$(HOTSPOT_OUTPUT)" -g 10 --flp "floorplan2.flp" --prefix "bottom"
	$(STA_EXE) $(REPORT_POWER_TCL)
	@mv "$(HOTSPOT_OUTPUT)/gcc.ptrace" "$(HOTSPOT_OUTPUT)/bottom.ptrace"
	python3 $(MERGE_PTRACE_PY) -u "$(HOTSPOT_OUTPUT)/upper.ptrace" -b "$(HOTSPOT_OUTPUT)/bottom.ptrace" -o "$(HOTSPOT_OUTPUT)/test.ptrace"
	@mkdir -p "$(RESULTS_DIR)/hotspot_outputs" || true

# ===============================
# ===== Cadence (cds-*) =========
# ===============================
# 使用 scripts_cadence/ 目录中的 Tcl；流程对齐你的 bash

# 关键输出
CDS_SYN_V   := $(RESULTS_DIR)/1_synth.v
CDS_SYN_SDC := $(RESULTS_DIR)/1_synth.sdc

# -------- 综合（Genus） --------
.PHONY: cds-synth
cds-synth: $(CDS_SYN_V) $(CDS_SYN_SDC)

$(CDS_SYN_V) $(CDS_SYN_SDC): $(VERILOG_FILES) $(SDC_FILE) $(LIB_FILES)
	@$(call _mkstdirs)
	( $(TIME_CMD) $(GENUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	    -log $(LOG_DIR)/cadence_1_genus.log \
	    -f $(CADENCE_SCRIPTS_DIR)/run_genus.tcl ) 2>&1 | tee -a $(LOG_DIR)/1_genus.log

# -------- 2D 预放置（Innovus） --------
.PHONY: cds-preplace
cds-preplace: cds-synth
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	    -log $(LOG_DIR)/cadence_2_innovus_preplace.log \
	    -files $(CADENCE_SCRIPTS_DIR)/innovus_preplace.tcl ) 2>&1 | tee -a $(LOG_DIR)/2_innovus_preplace.log

# -------- （可选）Tier Partition 两种实现：OpenROAD 内/容器内 --------
.PHONY: cds-tier-partition
cds-tier-partition:
	@set -ex; \
	NEW_RESULTS_DIR="$(WORK_HOME)/results/$(PLATFORM)_3D/$(DESIGN_NICKNAME)/$(FLOW_VARIANT)"; \
	mkdir -p "$$NEW_RESULTS_DIR"; \
	cp -r "$(RESULTS_DIR)"/* "$$NEW_RESULTS_DIR"; \
	export RESULTS_DIR="$$NEW_RESULTS_DIR"; \
	( $(TIME_CMD) $(OPENROAD_CMD) $(CADENCE_SCRIPTS_DIR)/tritonpart_tier_partition.tcl ) 2>&1 | tee -a $(LOG_DIR)/2_tritonpart.log; \
	python3 "$(CADENCE_SCRIPTS_DIR)/generate_3d_views.py" \
	  --def-in "$$RESULTS_DIR/2_2_floorplan_io.def" \
	  --v-in   "$$RESULTS_DIR/2_2_floorplan_io.v" \
	  --def-out "$$RESULTS_DIR/$(DESIGN_NAME)_3D.fp.def" \
	  --v-out   "$$RESULTS_DIR/$(DESIGN_NAME)_3D.fp.v" \
	  --partition "$$RESULTS_DIR/partition.txt"

.PHONY: cds-docker-partition
DOCKER        ?= docker
CONTAINER     ?= orfs_zhiyu
CONTAINER_USER?= $(shell id -un)
INNER_DIR     ?= /scripts/OpenROAD-3D-flowdir/flow-Cadence
cds-docker-partition:
	@set -e; \
	cname="$(CONTAINER)"; \
	if [ -z "$$($(DOCKER) ps -q -f name=^$${cname}$$)" ]; then \
	  echo "[ERR] container '$$cname' is not running."; exit 1; fi; \
	if $(DOCKER) exec "$$cname" id -u "$(CONTAINER_USER)" >/dev/null 2>&1; then \
	  user_arg="-u $(CONTAINER_USER)"; else user_arg="-u $(shell id -u):$(shell id -g)"; fi; \
	$(DOCKER) exec $$user_arg -e DESIGN_CONFIG="$(DESIGN_CONFIG)" -w / "$$cname" \
	  /bin/bash -lc "cd ~ && [ -f ~/.bashrc ] && source ~/.bashrc || true; cd '$(INNER_DIR)' && make DESIGN_CONFIG='$(DESIGN_CONFIG)' cds-tier-partition"

# -------- 3D PDN --------
.PHONY: cds-3d-pdn
cds-3d-pdn:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_3d_pdn.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_3d_pdn.tcl ) 2>&1 | tee -a $(LOG_DIR)/2_pdn.log
	@cp "$(RESULTS_DIR)/1_synth.sdc"  "$(RESULTS_DIR)/2_floorplan.sdc"

# -------- 3D 放置（init / upper / bottom / finish） --------
.PHONY: cds-place-init
cds-place-init:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_place_init.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_place3D_init.tcl ) 2>&1 | tee -a $(LOG_DIR)/3_place_init.log

.PHONY: cds-place-upper
cds-place-upper:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_place_upper.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_place3D_upper.tcl ) 2>&1 | tee -a $(LOG_DIR)/3_place_upper.log

.PHONY: cds-place-bottom
cds-place-bottom:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_place_bottom.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_place3D_bottom.tcl ) 2>&1 | tee -a $(LOG_DIR)/3_place_bottom.log

.PHONY: cds-place-finish
cds-place-finish:
	cp -r results/${PLATFORM}/${DESIGN_NICKNAME}/cadence/${DESIGN_NAME}_3D.tmp.def results/${PLATFORM}/${DESIGN_NICKNAME}/cadence/3_placed.def
	cp -r results/${PLATFORM}/${DESIGN_NICKNAME}/cadence/${DESIGN_NAME}_3D.tmp.v   results/${PLATFORM}/${DESIGN_NICKNAME}/cadence/3_placed.v
	cp $(RESULTS_DIR)/2_floorplan.sdc $(RESULTS_DIR)/3_placed.sdc

# -------- CTS 评估 & 合并 --------
.PHONY: cds-cts-eval
cds-cts-eval:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_3d_cts.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_3d_cts.tcl ) 2>&1 | tee -a $(LOG_DIR)/4_1_cts.log
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_3d_legalization_upper.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_3d_legalization_upper.tcl ) 2>&1 | tee -a $(LOG_DIR)/4_2_upper.log
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_3d_legalization_bottom.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_3d_legalization_bottom.tcl ) 2>&1 | tee -a $(LOG_DIR)/4_2_bottom.log
	python3 $(CADENCE_SCRIPTS_DIR)/merge_def.py \
	  --base $(RESULTS_DIR)/4_1_cts.def \
	  --upper $(RESULTS_DIR)/4_2_upper.def \
	  --bottom $(RESULTS_DIR)/4_2_bottom.def \
	  --out $(RESULTS_DIR)/4_cts.def
	cp $(RESULTS_DIR)/4_1_cts.v $(RESULTS_DIR)/4_cts.v
	cp $(RESULTS_DIR)/3_placed.sdc $(RESULTS_DIR)/4_cts.sdc

# -------- 3D Route --------
.PHONY: cds-route
cds-route:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_3d_route.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_3d_route.tcl ) 2>&1 | tee -a $(LOG_DIR)/5_route.log
	cp $(RESULTS_DIR)/4_cts.sdc $(RESULTS_DIR)/5_route.sdc

# -------- Final --------
.PHONY: cds-final
cds-final:
	@$(call _mkstdirs)
	( $(TIME_CMD) $(INNOVUS_CMD) $(OPEN_GUI_CMD) -overwrite \
	  -log $(LOG_DIR)/cadence_innovus_3d_final.log \
	  -files $(CADENCE_SCRIPTS_DIR)/innovus_3d_final.tcl ) 2>&1 | tee -a $(LOG_DIR)/6_final.log

# -------- HotSpot（可选，与 OpenROAD 复用变量） --------
.PHONY: cds-hotspot
cds-hotspot: ord-hotspot

# ===============================
# Convenience pipelines (optional)
# ===============================
# 这些流水线只是方便批量跑，与 bash 行为一致，仍使用新命名目标。
export DESIGN_DIR           := $(dir $(DESIGN_CONFIG))
export DCFG_2D              ?= $(DESIGN_DIR)/config2d.mk
export DCFG                 ?= $(DESIGN_DIR)/config.mk
export DCFG_BOTH_SHRINK     ?= $(DESIGN_DIR)/config_both_shrink.mk
export DCFG_BOTTOM_SHRINK   ?= $(DESIGN_DIR)/config_bottom_shrink.mk
export DCFG_UPPER_SHRINK    ?= $(DESIGN_DIR)/config_upper_shrink.mk
export iteration            ?= 1

.PHONY: ord-run
ord-run:
	@echo "[OpenROAD] clean dirs"; rm -rf objects/ results/ reports/ logs/ || true
	$(MAKE) DESIGN_CONFIG=$(DCFG_2D)            ord-2dpre
	$(MAKE) DESIGN_CONFIG=$(DCFG)               ord-pre
	$(MAKE) DESIGN_CONFIG=$(DCFG_BOTH_SHRINK)   ord-place-init
	@i=1; while [ $$i -le $(iteration) ]; do \
	  echo "Iteration: $$i"; \
	  $(MAKE) DESIGN_CONFIG=$(DCFG_BOTTOM_SHRINK) ord-place-upper; \
	  $(MAKE) DESIGN_CONFIG=$(DCFG_UPPER_SHRINK)  ord-place-bottom; \
	  i=$$((i+1)); \
	done
	$(MAKE) DESIGN_CONFIG=$(DCFG_UPPER_SHRINK)  ord-autoflow
	$(MAKE) DESIGN_CONFIG=$(DCFG)               ord-cts
	$(MAKE) DESIGN_CONFIG=$(DCFG)               ord-cts-eval
	$(MAKE) DESIGN_CONFIG=$(DCFG)               ord-route
	$(MAKE) DESIGN_CONFIG=$(DCFG)               ord-finish
	$(MAKE) DESIGN_CONFIG=$(DCFG)               ord-hotspot

.PHONY: cds-run
cds-run:
	@echo "[Cadence] clean dirs"; rm -rf objects/ results/ reports/ logs/ || true
	$(MAKE) DESIGN_CONFIG=$(DCFG_2D) cds-synth
	$(MAKE) DESIGN_CONFIG=$(DCFG_2D) cds-preplace
	# 二选一：容器外 or 容器内分层
	# $(MAKE) DESIGN_CONFIG=$(DCFG_2D) cds-tier-partition
	$(MAKE) DESIGN_CONFIG=$(DCFG_2D) cds-docker-partition
	$(MAKE) DESIGN_CONFIG=$(DCFG)    cds-3d-pdn
	$(MAKE) DESIGN_CONFIG=$(DCFG_BOTH_SHRINK) cds-place-init
	@i=1; while [ $$i -le $(iteration) ]; do \
	  echo "Iteration: $$i"; \
	  $(MAKE) DESIGN_CONFIG=$(DCFG_BOTTOM_SHRINK) cds-place-upper; \
	  $(MAKE) DESIGN_CONFIG=$(DCFG_UPPER_SHRINK)  cds-place-bottom; \
	  i=$$((i+1)); \
	done
	$(MAKE) DESIGN_CONFIG=$(DCFG) cds-place-finish
	$(MAKE) DESIGN_CONFIG=$(DCFG) cds-cts-eval
	$(MAKE) DESIGN_CONFIG=$(DCFG) cds-route
	$(MAKE) DESIGN_CONFIG=$(DCFG) cds-final
	# $(MAKE) DESIGN_CONFIG=$(DCFG) cds-hotspot

# 默认不跑任何东西，防止误触；你可以自行选择 ord-run / cds-run
.DEFAULT_GOAL := ord-versions
