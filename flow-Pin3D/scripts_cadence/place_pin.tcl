# =========================================
# place_pin.tcl — Put all IOs on IO_PLACER_H / IO_PLACER_V
#   IN     -> LEFT/RIGHT on IO_PLACER_H
#   OUT/IO -> BOTTOM/TOP on IO_PLACER_V
# =========================================
# =========================================
# place_io_by_flags.tcl
# IN (isInput==1)       -> LEFT/RIGHT on layerH
# OUT (isOutput==1) and INOUT (inOutDir==INOUT) -> TOP/BOTTOM on layerV
# No heuristics. Uses only explicit attributes: isInput, isOutput, inOutDir.
# =========================================

proc __place_side {pins side layer} {
  if {[llength $pins] == 0} { return }
  puts [format ">> %-6s : %4d pins on %s (sample: %s)" \
        $side [llength $pins] $layer [lindex $pins 0]]
  editPin -layer $layer -pin $pins -side $side -spreadType SIDE \
          -snap TRACK -fixOverlap 1 -fixedPin
}

proc place_io_by_flags {layerH layerV} {
  # Read and align attribute lists in parallel
  set names    [dbGet top.terms.name]
  set isInL    {}
  set isOutL   {}
  set iodirL   {}

  if {[catch {dbGet top.terms.isInput}  isInL]}  { set isInL  {} }
  if {[catch {dbGet top.terms.isOutput} isOutL]} { set isOutL {} }
  if {[catch {dbGet top.terms.inOutDir} iodirL]} { set iodirL {} }

  set N [llength $names]
  if {$N == 0} { error "No top.terms found." }

  set IN   {}
  set OUT  {}
  set IO   {}

  for {set i 0} {$i < $N} {incr i} {
    set n    [lindex $names  $i]
    set isIn  [expr {[llength $isInL]  == $N ? [lindex $isInL  $i] : 0}]
    set isOut [expr {[llength $isOutL] == $N ? [lindex $isOutL $i] : 0}]
    set iod   [expr {[llength $iodirL] == $N ? [lindex $iodirL $i] : ""}]

    # First, identify INOUT (based on inOutDir)
    if {[string equal -nocase $iod "INOUT"]} {
      lappend IO $n
      continue
    }
    # Then, identify IN/OUT (based on isInput/isOutput)
    if {$isIn  == 1} { lappend IN  $n; continue }
    if {$isOut == 1} { lappend OUT $n; continue }

    # Other values: ignore (zero heuristics, no guessing)
  }

  puts [format "Collected: IN=%d, OUT=%d, INOUT=%d, total=%d" \
        [llength $IN] [llength $OUT] [llength $IO] $N]
  if {[llength $IN]==0 && [llength $OUT]==0 && [llength $IO]==0} {
    error "No pins matched (isInput/isOutput/inOutDir are absent or all zero)."
  }
  puts [format "Layers: H=%s (LEFT/RIGHT), V=%s (TOP/BOTTOM)" $layerH $layerV]

  # Evenly distribute: IN -> LEFT/RIGHT
  set nI   [llength $IN]
  set midI [expr {int(ceil($nI/2.0))}]
  set IN_L [lrange $IN 0 [expr {$midI-1}]]
  set IN_R [lrange $IN $midI end]

  # OUT+INOUT -> BOTTOM/TOP
  set OUTX  [concat $OUT $IO]
  set nO    [llength $OUTX]
  set midO  [expr {int(ceil($nO/2.0))}]
  set OUT_B [lrange $OUTX 0 [expr {$midO-1}]]
  set OUT_T [lrange $OUTX $midO end]

  # Debugging samples
  if {$nI>0}  { puts "IN sample:   [lrange $IN 0 [expr {min($nI-1,4)}]]" }
  if {$nO>0}  { puts "OUTX sample: [lrange $OUTX 0 [expr {min($nO-1,4)}]]" }

  # Placement
  __place_side $IN_L  LEFT   $layerH
  __place_side $IN_R  RIGHT  $layerH
  __place_side $OUT_B BOTTOM $layerV
  __place_side $OUT_T TOP    $layerV

  legalizePin
}

# ---------- Example ----------
set IO_PLACER_H [_get IO_PLACER_H]  
set IO_PLACER_V [_get IO_PLACER_V]  

place_io_by_flags $IO_PLACER_H $IO_PLACER_V
