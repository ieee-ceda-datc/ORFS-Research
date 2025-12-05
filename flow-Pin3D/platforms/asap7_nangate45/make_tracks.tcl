make_tracks M1 -x_offset 0.095 -x_pitch 0.19 -y_offset 0.07 -y_pitch 0.14
make_tracks M2 -x_offset 0.095 -x_pitch 0.19 -y_offset 0.07 -y_pitch  0.14
make_tracks M3 -x_offset 0.095 -x_pitch 0.19 -y_offset 0.07 -y_pitch  0.14
make_tracks M4 -x_offset 0.095 -x_pitch 0.28 -y_offset 0.07 -y_pitch  0.28
make_tracks M5 -x_offset 0.095 -x_pitch 0.28 -y_offset 0.07 -y_pitch  0.28
make_tracks M6 -x_offset 0.095 -x_pitch 0.28 -y_offset 0.07 -y_pitch  0.28
make_tracks M7 -x_offset 0.095 -x_pitch 0.8 -y_offset 0.07 -y_pitch  0.8
make_tracks M8 -x_offset 0.095 -x_pitch 0.8 -y_offset 0.07 -y_pitch  0.8
make_tracks M9 -x_offset 0.095 -x_pitch 1.6 -y_offset 0.07 -y_pitch  1.6
make_tracks M10 -x_offset 0.095 -x_pitch 1.6 -y_offset 0.07 -y_pitch 1.6

# ==========================================
# make_tracks.tcl — Core-aligned routing tracks
# 关键：offset 使用 “core 对齐修正”
# offset_abs = (core_min_um % pitch) + local_offset
# 这样不同芯片原点/不同 coreLL 下轨道都能与行/引脚对齐
# ==========================================

# proc um_per_dbu {} {
#   # OpenROAD 内部单位：DBU；换算为微米
#   set dbu [[odb::get_block] getDbUnitsPerMicron]
#   return [expr {1.0 / double($dbu)}]
# }

# proc get_core_ll_um {} {
#   # 返回 {xmin_um ymin_um}
#   set area [ord::get_core_area] ;# {xmin ymin xmax ymax} in DBU
#   set s [um_per_dbu]
#   set xmin_um [expr {[lindex $area 0] * $s}]
#   set ymin_um [expr {[lindex $area 1] * $s}]
#   return [list $xmin_um $ymin_um]
# }

# # 给定 “局部偏移(local_offset)” 和 “节距(pitch)”，
# # 计算相对 coreLL 对齐后的 “绝对偏移(absolute offset)”
# proc core_aligned_offset {core_min_um pitch local_offset} {
#   if {$pitch <= 0} {
#     error "Pitch must be > 0"
#   }
#   # fmod for Tcl
#   set frac [expr {$core_min_um - floor($core_min_um / $pitch) * $pitch}]
#   set off  [expr {$frac + $local_offset}]
#   # 归一到 [0, pitch) 区间，避免越界
#   set off  [expr {$off - floor($off / $pitch) * $pitch}]
#   return $off
# }

# # 按“层名 → {x_pitch y_pitch x_loc_off y_loc_off}”配置
# # 这些数值全部是“你原来脚本里的”，只是交由 core 对齐去修正 offset
# array set LAYER_CFG {
#   M1   {0.19 0.14 0.095 0.07}
#   M2   {0.19 0.14 0.095 0.07}
#   M3   {0.19 0.14 0.095 0.07}
#   M4   {0.28 0.28 0.095 0.07}
#   M5   {0.28 0.28 0.095 0.07}
#   M6   {0.28 0.28 0.095 0.07}
#   M7   {0.80 0.80 0.095 0.07}
#   M8   {0.80 0.80 0.095 0.07}
#   M9   {1.60 1.60 0.095 0.07}
#   M10  {1.60 1.60 0.095 0.07}
# }

# # 如果你的 LEF 层名是 metal1/metal2...，可以在这里做别名映射（两者都建一遍更保险）
# array set LAYER_ALIAS {
#   metal1  M1
#   metal2  M2
#   metal3  M3
#   metal4  M4
#   metal5  M5
#   metal6  M6
#   metal7  M7
#   metal8  M8
#   metal9  M9
#   metal10 M10
# }

# proc build_tracks_for_layer {layer} {
#   variable LAYER_CFG
#   if {![info exists LAYER_CFG($layer)]} {
#     puts "[format {Skip %s (no config)} $layer]"
#     return
#   }
#   lassign $LAYER_CFG($layer) x_pitch y_pitch x_loc y_loc
#   lassign [get_core_ll_um] core_x core_y
#   set x_off [core_aligned_offset $core_x $x_pitch $x_loc]
#   set y_off [core_aligned_offset $core_y $y_pitch $y_loc]

#   puts "[format {Tracks %s: x_off=%.6f x_pitch=%.6f | y_off=%.6f y_pitch=%.6f} \
#     $layer $x_off $x_pitch $y_off $y_pitch]"

#   # 实际建轨
#   make_tracks $layer \
#     -x_offset $x_off -x_pitch $x_pitch \
#     -y_offset $y_off -y_pitch $y_pitch
# }

# # 主流程：先用 M-系列建轨，再（如存在）用 metalN 做一遍别名轨道
# foreach L {M1 M2 M3 M4 M5 M6 M7 M8 M9 M10} {
#   build_tracks_for_layer $L
# }
