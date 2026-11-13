#-----------------------------
# syn/scripts/clock_gating.tcl
# Clock gating for one DC run (X79): sourced by dc_syn.tcl right before compile_ultra when CLK_GATE_ENABLE is 1,
# which then compiles with -gate_clock. Off (the default), dc_syn.tcl never sources it and the run is as before.
#
# The library's integrated clock gates are found by DC itself: on nangate45 CLKGATE_X1-X8 carry
# clock_gating_integrated_cell latch_posedge (CLKGATETST_X1-X8 latch_posedge_precontrol, used only with a test
# control point, which is not set here). A library with no latch_posedge cell stops the run (exit 2) rather than
# having the attribute set here: it would not be the library we take it for.
#
# Not set, on purpose: -control_point and a test_mode port (DC would add a port to the top; no scan here),
# -negative_edge_logic (no negedge ICG in Nangate; every flop of these designs is posedge), operand isolation
# (it changes the datapath's logic, a different effect), power_cg_designware (obsolete in DC Y-2026.03, which
# ignores it with INFO-100; CG1 R2).
#-----------------------------

set cg_cells [get_lib_cells -quiet */* -filter "clock_gating_integrated_cell == latch_posedge"]
if {[sizeof_collection $cg_cells] == 0} {
    puts "clock_gating.tcl: no library cell with clock_gating_integrated_cell latch_posedge; stopping (X79)"
    exit 2
}
puts "clock_gating.tcl: integrated clock gates [lsort [get_object_name $cg_cells]]"

set power_cg_derive_related_clock true
set power_remove_redundant_clock_gates true
set power_cg_reconfig_stages true
set compile_clock_gating_through_hierarchy true

# One ICG (latch, then AND) per bank of at least two flops that share an enable; the bank's muxes go
set_clock_gating_style -sequential_cell latch -positive_edge_logic {integrated} -minimum_bitwidth 2
