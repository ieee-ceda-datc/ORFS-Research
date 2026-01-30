#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
COMMON_SCRIPT="${SCRIPT_DIR}/../../../_common/cds/run.sh"

: "${ENABLEMENT:=asap7_nangate45_3D}"
: "${DESIGN_NICKNAME:=jpeg}"

bash "${COMMON_SCRIPT}"
