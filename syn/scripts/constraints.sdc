################################
# syn/scripts/constraints.sdc
# Sourced by dc_syn.tcl after link. Every value is physical (ns, fF) and scaled
# to the library's units: $t_scale library time units per ns, $c_scale library
# capacitance units per fF. dc_syn.tcl also sets $clock_ns, $drive_cell,
# $out_load_ff and $max_trans_ns from the tech file (syn/tech/<tech>.json),
# and $clk_port and $rst_port from SYN_CLK_PORT and SYN_RST_PORT.
# Vitis's tops have one clock, ap_clk, and a synchronous active-low reset,
# ap_rst_n; snax-forge's have clk_i and an asynchronous active-low reset,
# rst_ni. Either reset is an ordinary input here, kept ideal.
################################

#-----------------------------
# Set design rules
#-----------------------------

# Setting as low as possible is nice for high speed
set_max_transition [expr {$max_trans_ns * $t_scale}] [current_design]

# Lower fanout means less delay on critical paths
set_max_fanout 32 [current_design]

#-----------------------------
# Declare clocks
#-----------------------------
create_clock -name clk -period [expr {$clock_ns * $t_scale}] [get_ports $clk_port]

#-----------------------------
# Setup and hold time uncertainties
#-----------------------------

# Set between 0.05 and 0.2 ns
set_clock_uncertainty [expr {0.1 * $t_scale}] -setup [get_clocks clk]

# Set between 0.05 and 0.1 ns
set_clock_uncertainty [expr {0.02 * $t_scale}] -hold [get_clocks clk]

#-----------------------------
# IO constraints (every input but the clock)
#-----------------------------
set data_inputs [remove_from_collection [all_inputs] [get_ports $clk_port]]

# The tech file's driving cell (INV_X4 on both Nangate libraries)
set_driving_cell -lib_cell $drive_cell $data_inputs

# The tech file's output load: four INV_X4 inputs
set_load [expr {$out_load_ff * $c_scale}] [all_outputs]

set_input_delay -max [expr {0.01 * $t_scale}] -clock clk $data_inputs

set_output_delay -max [expr {0.01 * $t_scale}] -clock clk [all_outputs]

#-----------------------------
# Reset
#-----------------------------
# The reset ($rst_port: ap_rst_n, synchronous; rst_ni, asynchronous) reaches
# nearly every flop. Keep it ideal here, so DC builds no buffer tree for it and
# does not report its fanout as max-cap violations; the reset tree belongs to
# place and route.
set_ideal_network [get_ports $rst_port]
