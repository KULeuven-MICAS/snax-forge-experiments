################################
# syn/scripts/constraints.sdc
# Sourced by dc_syn.tcl after link, which sets $clock_ns.
# Vitis's tops have one clock, ap_clk, and a synchronous active-low reset,
# ap_rst_n, which is treated as an ordinary input here.
################################

#-----------------------------
# Set design rules
#-----------------------------

# Setting as low as possible is nice for high speed
set_max_transition 0.25 [current_design]

# Lower fanout means less delay on critical paths
set_max_fanout 32 [current_design]

#-----------------------------
# Declare clocks
#-----------------------------
set clk_port ap_clk
create_clock -name clk -period $clock_ns [get_ports $clk_port]

#-----------------------------
# Setup and hold time uncertainties
#-----------------------------

# Set between 0.05 and 0.2
set_clock_uncertainty 0.1 -setup [get_clocks clk]

# Set between 0.05 and 0.1
set_clock_uncertainty 0.02 -hold [get_clocks clk]

#-----------------------------
# IO constraints (every input but the clock)
#-----------------------------
set data_inputs [remove_from_collection [all_inputs] [get_ports $clk_port]]

# Get from the FreePDK45nm
set_driving_cell -lib_cell INVX4 $data_inputs

# Set some generic.
set_load 0.03 [all_outputs]

set_input_delay -max 0.01 -clock clk $data_inputs

set_output_delay -max 0.01 -clock clk [all_outputs]

#-----------------------------
# Reset
#-----------------------------
# ap_rst_n is synchronous and reaches nearly every flop. Keep it ideal here, so
# DC builds no buffer tree for it and does not report its fanout as max-cap
# violations; the reset tree belongs to place and route.
set_ideal_network [get_ports ap_rst_n]
