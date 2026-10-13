SHELL := /usr/bin/env bash

DRIVER_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
ORFS_ROOT := $(abspath $(DRIVER_DIR)/../../..)

SOURCE_DIR ?= $(abspath $(DRIVER_DIR)/..)
BUILD_DIR ?= $(ORFS_ROOT)/tools/build/d3d-partitioner
INSTALL_PREFIX ?= $(ORFS_ROOT)/tools/install/d3d-partitioner
ENV_PREFIX ?= $(CONDA_PREFIX)
SETUP_ENV_PREFIX ?= $(ORFS_ROOT)/.conda/taiwei-d3d-cpu
PYTHON_EXECUTABLE ?= $(if $(ENV_PREFIX),$(ENV_PREFIX)/bin/python,python3)
JOBS ?= $(shell nproc 2>/dev/null || echo 4)
ALLOW_DIRTY_SOURCE ?= 0
UPDATE_ENV ?= 0

.PHONY: help setup preflight install check

help:
	@echo "D3D partitioner CPU integration"
	@echo ""
	@echo "  make setup [SETUP_ENV_PREFIX=/path/to/conda/env] [JOBS=N]"
	@echo "             [UPDATE_ENV=1]"
	@echo "  make preflight ENV_PREFIX=/path/to/conda/env"
	@echo "  make install   ENV_PREFIX=/path/to/conda/env [JOBS=N]"
	@echo "  make check     ENV_PREFIX=/path/to/conda/env"
	@echo ""
	@echo "Source : $(SOURCE_DIR)"
	@echo "Build  : $(BUILD_DIR)"
	@echo "Install: $(INSTALL_PREFIX)"

setup:
	@D3D_ENV_PREFIX="$(SETUP_ENV_PREFIX)" \
	 D3D_CONDA_EXE="$(CONDA_EXE)" \
	 D3D_UPDATE_ENV="$(UPDATE_ENV)" \
	 JOBS="$(JOBS)" \
	 "$(DRIVER_DIR)/setup.sh"

preflight:
	@SOURCE_DIR="$(SOURCE_DIR)" \
	 BUILD_DIR="$(BUILD_DIR)" \
	 INSTALL_PREFIX="$(INSTALL_PREFIX)" \
	 ENV_PREFIX="$(ENV_PREFIX)" \
	 PYTHON_EXECUTABLE="$(PYTHON_EXECUTABLE)" \
	 CMAKE="$(CMAKE)" \
	 C_COMPILER="$(C_COMPILER)" \
	 CXX_COMPILER="$(CXX_COMPILER)" \
	 BISON_EXECUTABLE="$(BISON_EXECUTABLE)" \
	 FLEX_EXECUTABLE="$(FLEX_EXECUTABLE)" \
	 ALLOW_DIRTY_SOURCE="$(ALLOW_DIRTY_SOURCE)" \
	 "$(DRIVER_DIR)/install.sh" --preflight-only

install:
	@SOURCE_DIR="$(SOURCE_DIR)" \
	 BUILD_DIR="$(BUILD_DIR)" \
	 INSTALL_PREFIX="$(INSTALL_PREFIX)" \
	 ENV_PREFIX="$(ENV_PREFIX)" \
	 PYTHON_EXECUTABLE="$(PYTHON_EXECUTABLE)" \
	 JOBS="$(JOBS)" \
	 CMAKE="$(CMAKE)" \
	 C_COMPILER="$(C_COMPILER)" \
	 CXX_COMPILER="$(CXX_COMPILER)" \
	 BISON_EXECUTABLE="$(BISON_EXECUTABLE)" \
	 FLEX_EXECUTABLE="$(FLEX_EXECUTABLE)" \
	 ALLOW_DIRTY_SOURCE="$(ALLOW_DIRTY_SOURCE)" \
	 "$(DRIVER_DIR)/install.sh"

check:
	@env_prefix="$(ENV_PREFIX)"; \
	 library_path="$(INSTALL_PREFIX)/lib"; \
	 if [[ -n "$$env_prefix" ]]; then library_path="$$env_prefix/lib:$$library_path"; fi; \
	 LD_LIBRARY_PATH="$$library_path$${LD_LIBRARY_PATH:+:$$LD_LIBRARY_PATH}" \
	 PYTHONNOUSERSITE=1 \
	 "$(PYTHON_EXECUTABLE)" "$(DRIVER_DIR)/check_install.py" \
	   --prefix "$(INSTALL_PREFIX)" \
	   --require-manifest
