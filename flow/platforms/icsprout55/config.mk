export PLATFORM                = icsprout55
export PROCESS                 = 55
export ASAP7_USE_VT           ?= RVT

export LIB_MODEL               = NLDM
export TECH_LEF                = $(PLATFORM_DIR)/prtech/techLEF/N551P6M_orfs_research.lef

export BC_TEMPERATURE          = 125C
export TC_TEMPERATURE          = 25C
export WC_TEMPERATURE          = -40C

export BC_VOLTAGE          = 1.32
export TC_VOLTAGE          = 1.20
export WC_VOLTAGE          = 1.08

# Dont use cells to ease congestion ?
# export DONT_USE_CELLS 

# Default to RVT if unset
export VT_LIST = $(if $(strip $(ASAP7_USE_VT)), $(ASAP7_USE_VT), RVT)

# # The first VT in the ASAP7_USE_VT list is the primary VT. The others get added to OTHER_VT
export PRIMARY_VT = $(word 1, $(VT_LIST))
# HVT->H7CH, LVT->H7CL, RVT->H7CR
export PRIMARY_VT_TAG = $(strip \
  $(if $(filter HVT,$(PRIMARY_VT)),H7CH, \
  $(if $(filter LVT,$(PRIMARY_VT)),H7CL, \
  $(if $(filter RVT,$(PRIMARY_VT)),H7CR, \
    $(error Unsupported VT: $(PRIMARY_VT). Supported VTs are HVT, LVT, RVT.)))))
export OTHER_VT = $(wordlist 2, $(words $(VT_LIST)), $(VT_LIST))
export PRIMARY_VT_TAG_SHORT = $(subst H7C,,$(PRIMARY_VT_TAG))

# Synthesis
export SYNTH_MINIMUM_KEEP_SIZE       ?= 1000
export ABC_LOAD_IN_FF            = 3.898
export MIN_BUF_CELL_AND_PORTS    = BUFX0P5H7$(PRIMARY_VT_TAG_SHORT) A Y
export ABC_DRIVER_CELL       = BUFX0P5H7$(PRIMARY_VT_TAG_SHORT)
export TIEHI_CELL_AND_PORT     ?= TIEHIH7$(PRIMARY_VT_TAG_SHORT) Z
export TIELO_CELL_AND_PORT     ?= TIELOH7$(PRIMARY_VT_TAG_SHORT) Z

#yosy mapping files?


# pdn
export PDN_TCL			   = $(PLATFORM_DIR)/pdn/icsprout55_pdn.tcl

# IO Placer pin layers
export IO_PLACER_H ?= MET3
export IO_PLACER_V ?= MET4

# place
export PLACE_SITE             = CoreSite
export MACRO_PLACE_HALO ?= 22.4 15.12
export PLACE_DENSITY ?= 0.60
export DONT_USE_CELLS = FILLER1H7$(PRIMARY_VT_TAG_SHORT)

# Endcap and Welltie cells
export TAPCELL_TCL ?= $(PLATFORM_DIR)/tap/tapcell.tcl
export TAP_CELL_NAME = FILLTAPH7$(PRIMARY_VT_TAG_SHORT)

#RC?
export SET_RC_TCL              = $(PLATFORM_DIR)/setRC.tcl
# OpenRCX extRules
export RCX_RULES               = $(PLATFORM_DIR)/N551P6M_orfs_research.rcx_patterns.rules
# Route options
export MIN_ROUTING_LAYER       ?= MET2
export MIN_CLK_ROUTING_LAYER   ?= MET4
export MAX_ROUTING_LAYER       ?= MET5

export MAKE_TRACKS             = $(PLATFORM_DIR)/make_tracks.tcl

# Define fastRoute tcl
export FASTROUTE_TCL ?= $(PLATFORM_DIR)/fastroute.tcl

# PLACEHOLDER gets replaced with the appropriate VT tag in the following templates
export BC_NLDM_LIB_FILES_T = $(PLATFORM_DIR)/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_PLACEHOLDER/liberty/ics55_LLSC_PLACEHOLDER_ff_cbest_1p32_125_nldm.lib.gz
export WC_NLDM_LIB_FILES_T = $(PLATFORM_DIR)/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_PLACEHOLDER/liberty/ics55_LLSC_PLACEHOLDER_ss_cworst_1p08_m40_nldm.lib.gz
export TC_NLDM_LIB_FILES_T = $(PLATFORM_DIR)/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_PLACEHOLDER/liberty/ics55_LLSC_PLACEHOLDER_typ_tt_1p2_25_nldm.lib.gz
export LEF_FILE_T = $(PLATFORM_DIR)/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_PLACEHOLDER/lef/ics55_LLSC_PLACEHOLDER_ieda.lef
export CDL_FILE_T = $(PLATFORM_DIR)/IP/STD_cell/ics55_LLSC_H7C_V1p10C100/ics55_LLSC_PLACEHOLDER/cdl/ics55_LLSC_PLACEHOLDER.cdl

export SC_LEF_                  ?= $(subst PLACEHOLDER,$(PRIMARY_VT_TAG),$(LEF_FILE_T))
export BC_NLDM_LIB_FILES    ?= $(subst PLACEHOLDER,$(PRIMARY_VT_TAG),$(BC_NLDM_LIB_FILES_T))
export TC_NLDM_LIB_FILES     ?= $(subst PLACEHOLDER,$(PRIMARY_VT_TAG),$(TC_NLDM_LIB_FILES_T))
export WC_NLDM_LIB_FILES     ?= $(subst PLACEHOLDER,$(PRIMARY_VT_TAG),$(WC_NLDM_LIB_FILES_T))
export CDL_FILE_            ?= $(subst PLACEHOLDER,$(PRIMARY_VT_TAG),$(CDL_FILE_T))

# Add other VTs to the library list
$(foreach vt_type, $(OTHER_VT), \
  $(eval vt_tag = $(strip \
    $(if $(filter HVT,$(vt_type)),H7CH, \
    $(if $(filter LVT,$(vt_type)),H7CL, \
    $(if $(filter RVT,$(vt_type)),H7CR, \
      $(error Unsupported VT: $(vt_type). Supported VTs are HVT, LVT, RVT.)))))) \
  $(eval BC_NLDM_LIB_FILES += $(subst PLACEHOLDER,$(vt_tag),$(BC_NLDM_LIB_FILES_T))) \
  $(eval TC_NLDM_LIB_FILES += $(subst PLACEHOLDER,$(vt_tag),$(TC_NLDM_LIB_FILES_T))) \
  $(eval WC_NLDM_LIB_FILES += $(subst PLACEHOLDER,$(vt_tag),$(WC_NLDM_LIB_FILES_T))) \
  $(eval SC_LEF_  += $(subst PLACEHOLDER,$(vt_tag),$(LEF_FILE_T))) \
  $(eval CDL_FILE_ += $(subst PLACEHOLDER,$(vt_tag),$(CDL_FILE_T))) \
)

export CORNER ?= BC
export SC_LEF                 += $(SC_LEF_)
export CDL_FILE              += $(CDL_FILE_)
export LIB_FILES              += $($(CORNER)_$(LIB_MODEL)_LIB_FILES)
export TEMPERATURE            = $($(CORNER)_TEMPERATURE)
export VOLTAGE                = $($(CORNER)_VOLTAGE)
echo "LIB_FILES: $(LIB_FILES)"

export PWR_NETS_VOLTAGES  ?= VDD 1.1
export GND_NETS_VOLTAGES  ?= VSS 0.0
export IR_DROP_LAYER ?= MET1