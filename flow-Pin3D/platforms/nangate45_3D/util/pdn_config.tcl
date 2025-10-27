#################################################################
# pdn_config.tcl — 对称工艺；M1..M10 镜像到 M20..M11
# 只在 M10 ↔ M11 做一次桥接；分段 sroute，避免整栈贯通
#################################################################

# ===== 基本网名 =====
set minCh 5

#           metal1  metal4  metal5  metal6  metal7  metal10 \
#           metal13 metal14 metal15 metal16 metal19
set layers  "metal1  metal4  metal5  metal6  metal7  metal10 \
             metal13 metal14 metal15 metal16 metal19"
set width   "0       0.84    0.84    0.84    2.4     3.20  \
             2.4     0.84    0.84    0.84    0"
set pitch   "0       20.16   10.08   10.08   40      32    \
             40      10.08   10.08   20.16   0"
set spacing "0       0.56    0.56    0.56    1.6     1.6   \
             1.6     0.56    0.56    0.56    0"
set ldir    "0       1       0       1       0       1     \
             0       1       0       1       0"
set isMacro "0       0       1       1       0       0     \
             0       1       1       0       0"
set isBM    "1       1       0       0       0       0     \
             0       0       0       1       1"
set isAM    "0       0       1       1       1       1     \
             1       1       1       0       0"
set isFP    "1       0       0       0       0       0     \
             0       0       0       0       1"
set soffset "0       2       2       2       2       2     \
             2       2       2       2       0"
set addch   "0       1       0       0       0       0     \
             0       0       0       1       0"