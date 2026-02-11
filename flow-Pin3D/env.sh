#!/usr/bin/env bash
###
 # @Author: Zhiyu Zheng zyzheng24@m.fudan.edu.cn 
 # @Date: 2026-01-17 18:31:45
 # @LastEditors: Zhiyu Zheng zyzheng24@m.fudan.edu.cn
 # @LastEditTime: 2026-01-18 00:33:57
 # @FilePath: env.sh
 # @Description: 3D Evaluation Environment Setup
### 

# ------------------------------------------------------------------------------
# Toolchain paths (override in your shell if needed)
# ------------------------------------------------------------------------------
export FLOW_HOME=$(pwd)
export NUM_CORES="${NUM_CORES:-16}"

# OpenROAD toolchain (prefer from PATH via which)
export OPENROAD_EXE="$(which openroad 2>/dev/null)"
export YOSYS_EXE="$(which yosys 2>/dev/null)"
export STA_EXE="$(which sta 2>/dev/null)"

# Fallback to ORFS install if not found in PATH
export ORFS_DIR="${ORFS_DIR:-..}"
if [[ -z "${OPENROAD_EXE}" || ! -x "${OPENROAD_EXE}" ]]; then
  export OPENROAD_EXE="${ORFS_DIR}/tools/install/OpenROAD/bin/openroad"
fi
if [[ -z "${YOSYS_EXE}" || ! -x "${YOSYS_EXE}" ]]; then
  export YOSYS_EXE="${ORFS_DIR}/tools/install/yosys/bin/yosys"
fi
if [[ -z "${STA_EXE}" || ! -x "${STA_EXE}" ]]; then
  export STA_EXE="${ORFS_DIR}/tools/install/OpenROAD/bin/sta"
fi

# Cadence toolchain
export GENUS_EXE="${GENUS_EXE:-$(which genus)}"
export INNOVUS_EXE="${INNOVUS_EXE:-$(which innovus)}"
GENUS_CMD="${GENUS_EXE} -64 -abort_on_error"
INNOVUS_CMD="${INNOVUS_EXE} -64 -abort_on_error"