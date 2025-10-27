# ==========================================
# design_setup.tcl  — common DESIGN/RTL/SDC setup
# ==========================================

source $::env(CADENCE_SCRIPTS_DIR)/utils.tcl
puts "--- DESIGN/RTL/SDC setup ---"

set DESIGN               [_get DESIGN_NAME]
set sdc                  [_get SDC_FILE]
set VERILOG_FILES        [_get VERILOG_FILES]
set RTL_SEARCH_DIRS      [_get RTL_SEARCH_DIRS]
set VERILOG_INCLUDE_DIRS [_get VERILOG_INCLUDE_DIRS]   ;# 新增：读取 include 目录

# 规范化列表
set rtldir [_uniq $RTL_SEARCH_DIRS]

# 展开 VERILOG_FILES 的通配
set rtl_all {}
foreach g $VERILOG_FILES {
  set m [glob -nocomplain -- $g]
  if {[llength $m]} {
    foreach f $m { lappend rtl_all $f }
  } elseif {[file exists $g]} {
    lappend rtl_all $g
  }
}

set GEN_EFF [_get GEN_EFF "medium"]
set MAP_EFF [_get MAP_EFF "high"]
set SITE [_get PLACE_SITE]
set HALO_WIDTH [_get HALO_WIDTH "5"]
set TOP_ROUTING_LAYER [_get MAX_ROUTING_LAYER]
