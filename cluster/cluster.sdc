################################
# cluster/cluster.sdc: the cluster's constraints on top of syn/scripts/constraints.sdc (X68)
# Sourced by dc_syn.tcl right after constraints.sdc (SYN_EXTRA_SDC), with the same variables: $clock_ns,
# $t_scale, $clk_port, $rst_port. constraints.sdc has given every input but the clock INV_X4 drive and
# 0.01 ns input delay, every output four INV_X4 loads and 0.01 ns output delay, and kept the reset ideal.
# This file adds:
#   - rst_ni asynchronous: set_false_path from it;
#   - the static and asynchronous ports the wrapper marks (* false_path *) (meip_i, mtip_i, msip_i,
#     hart_base_id_i, cluster_base_addr_i, boot_addr_i, obs_o) and sram_cfgs_i: set_false_path from or to them;
#   - the narrow and wide AXI ports: input and output delay of 30 % of the clock;
#   - the CSR ports to BINGO (csr_*, unused here): 10 % of the clock.
# Every other port keeps constraints.sdc's values. reports/cluster_ports.rpt: each group's port count and
# every port in no group.
################################

set axi_delay [expr {0.3 * $clock_ns * $t_scale}]
set csr_delay [expr {0.1 * $clock_ns * $t_scale}]

# The reset: asynchronous, ideal (constraints.sdc), no timing from it
set g_rst [get_ports -quiet $rst_port]
set_false_path -from $g_rst

# Static and asynchronous ports
set g_false [get_ports -quiet {meip_i* mtip_i* msip_i* hart_base_id_i* cluster_base_addr_i* boot_addr_i* obs_o* sram_cfgs_i*}]
set g_false_in  [filter_collection $g_false "direction == in"]
set g_false_out [filter_collection $g_false "direction == out"]
if {[sizeof_collection $g_false_in] > 0}  { set_false_path -from $g_false_in }
if {[sizeof_collection $g_false_out] > 0} { set_false_path -to $g_false_out }

# The narrow and wide AXI ports: 30 % of the clock
set g_axi [get_ports -quiet {narrow_* wide_*}]
set g_axi_in  [filter_collection $g_axi "direction == in"]
set g_axi_out [filter_collection $g_axi "direction == out"]
if {[sizeof_collection $g_axi_in] > 0}  { set_input_delay  -max $axi_delay -clock clk $g_axi_in }
if {[sizeof_collection $g_axi_out] > 0} { set_output_delay -max $axi_delay -clock clk $g_axi_out }

# The CSR ports to BINGO: 10 % of the clock
set g_csr [get_ports -quiet {csr_*}]
set g_csr_in  [filter_collection $g_csr "direction == in"]
set g_csr_out [filter_collection $g_csr "direction == out"]
if {[sizeof_collection $g_csr_in] > 0}  { set_input_delay  -max $csr_delay -clock clk $g_csr_in }
if {[sizeof_collection $g_csr_out] > 0} { set_output_delay -max $csr_delay -clock clk $g_csr_out }

# The report: each group's count, then every port in no group (constraints.sdc's values)
set g_clk [get_ports -quiet $clk_port]
set grouped [add_to_collection -unique $g_clk $g_rst]
foreach g [list $g_false $g_axi $g_csr] { set grouped [add_to_collection -unique $grouped $g] }
set rest [remove_from_collection [get_ports *] $grouped]
set fh [open reports/cluster_ports.rpt w]
puts $fh "# cluster/cluster.sdc on [get_object_name [current_design]] at $clock_ns ns (X68): ports per group"
puts $fh "ports [sizeof_collection [get_ports *]]"
puts $fh "clock $clk_port [sizeof_collection $g_clk]"
puts $fh "reset_false_path $rst_port [sizeof_collection $g_rst]"
puts $fh "false_path in [sizeof_collection $g_false_in] out [sizeof_collection $g_false_out]"
puts $fh "axi_30pct in [sizeof_collection $g_axi_in] out [sizeof_collection $g_axi_out] delay [expr {$axi_delay / $t_scale}] ns"
puts $fh "csr_10pct in [sizeof_collection $g_csr_in] out [sizeof_collection $g_csr_out] delay [expr {$csr_delay / $t_scale}] ns"
puts $fh "ungrouped [sizeof_collection $rest]"
puts $fh "# false_path ports by name prefix"
set counts [dict create]
foreach_in_collection p $g_false { regexp {^([^\[]+)} [get_object_name $p] -> base; dict incr counts $base }
dict for {b n} $counts { puts $fh "false_path_port $b $n" }
puts $fh "# ports in no group (constraints.sdc's 0.01 ns delay, INV_X4 drive or four INV_X4 loads)"
foreach_in_collection p $rest { puts $fh "ungrouped_port [get_object_name $p] [get_attribute $p direction]" }
close $fh
puts "cluster.sdc: [sizeof_collection $g_false] false-path ports, [sizeof_collection $g_axi] AXI ports at $axi_delay, [sizeof_collection $g_csr] CSR ports at $csr_delay, [sizeof_collection $rest] in no group"
