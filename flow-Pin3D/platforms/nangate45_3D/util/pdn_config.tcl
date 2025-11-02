#################################################################
# pdn_config.tcl — Symmetrical process; M1..M10 are mirrored to M20..M11.
# Only bridge once between M10 and M11; use segmented sroute
# to avoid full-stack through-vias.
#################################################################

# ===== Basic Net Names =====
set minCh 5

#           M1  M4  M5  M6  M7  M10 \
#           M14 M15 M16 M17 M20
set layers  "M1  M4  M5  M6  M7  M10 \
             M14 M15 M16 M17 M20"
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