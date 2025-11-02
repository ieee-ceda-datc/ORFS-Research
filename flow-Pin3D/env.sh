#!/usr/bin/env bash
function __setpaths() {
  DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
  echo "Setting FLOW_HOME to $DIR"
  export FLOW_HOME=$DIR
}
__setpaths
export OPENROAD_EXE=/scripts/ORFS-Research/tools/install/OpenROAD/bin/openroad
export YOSYS_EXE=/scripts/ORFS-Research/tools/install/yosys/bin/yosys
export STA_EXE=/scripts/ORFS-Research/tools/install/OpenROAD/bin/sta
# if you want to use docker to execute the openroad, you need to set the following variables
export CDS_USE_OPENROADDOCKER=0
export DOCKER=docker
export CONTAINER=orfs_zhiyu
export CONTAINER_USER=zhiyuzheng
export INNER_DIR=/scripts/ORFS-Research/flow-Pin3D
export OPENROAD_CMD_DOCKER="${OPENROAD_EXE} -exit"
export NUM_CORES=32
