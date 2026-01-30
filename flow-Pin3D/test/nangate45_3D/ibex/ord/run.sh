#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SCRIPT="${SCRIPT_DIR}/../../../_common/ord/run.sh"

: "${ENABLEMENT:=nangate45_3D}"
: "${DESIGN_NICKNAME:=ibex}"

bash "${COMMON_SCRIPT}"
