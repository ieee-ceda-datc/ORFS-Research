# io_even_sides.tcl
# 均分 I/O 并按 name 排序后成组约束到四边；避开 10um 角落区（10-90 为示例区间）

source $::env(OPENROAD_SCRIPTS_DIR)/load.tcl
load_design 2_1_floorplan.odb 1_synth.sdc "Pin placement by direction"

# 清理旧约束
clear_io_pin_constraints

# 用 OpenSTA 的集合命令拿到端口（不依赖 get_ports 的 -filter）
set in_pins  [lsort -dictionary [all_inputs]]
set out_pins [lsort -dictionary [all_outputs]]

# 简单均分函数
proc half_split {lst} {
  set n [llength $lst]
  if {$n <= 1} { return [list $lst {}] }
  set mid [expr {int(ceil($n/2.0))}]
  return [list [lrange $lst 0 [expr {$mid-1}]] [lrange $lst $mid end]]
}

lassign [half_split $in_pins]  in_bottom in_top
lassign [half_split $out_pins] out_left  out_right

set span "*"

# 方向/边界约束（-group -order 让同组按 x/y 递增连续布）
set_io_pin_constraint -pin_names $in_bottom  -region bottom:$span -group -order
set_io_pin_constraint -pin_names $in_top     -region top:$span    -group -order
set_io_pin_constraint -pin_names $out_left   -region left:$span   -group -order
set_io_pin_constraint -pin_names $out_right  -region right:$span  -group -order

# 执行 pin 放置（走 ioPlacer）
place_pins -hor_layers $::env(IO_PLACER_H) \
           -ver_layers $::env(IO_PLACER_V) \
           {*}$::env(PLACE_PINS_ARGS)

# 可选：保存检查点
if {![info exists save_checkpoint] || $save_checkpoint} {
  write_db  $::env(RESULTS_DIR)/2_2_floorplan_io.odb
  write_def $::env(RESULTS_DIR)/2_2_floorplan_io.def
  write_verilog $::env(RESULTS_DIR)/2_2_floorplan_io.v
}
exit
