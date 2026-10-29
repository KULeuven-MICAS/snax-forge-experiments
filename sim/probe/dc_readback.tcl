#-----------------------------
# sim/probe/dc_readback.tcl
# Design Compiler reads one mapped netlist back from syn/runs/ (no compile) and reports power
# as dc_syn.tcl did, for comparisons with sim/probe/pt_power.tcl. Nothing under syn/runs/ is
# written: run it from a folder of its own.
#
#   dc_shell -f <repo>/sim/probe/dc_readback.tcl -output_log_file dc_shell.log < /dev/null
#
# Environment:
#   PWR_RUN    the syn run folder: syn/runs/hls/<tech>/<tier>/<kernel>/<point>
#   PWR_MODE   p0       DC's defaults, propagated (reproduces the run's reports/power.rpt)
#              uniform  power_default_toggle_rate and power_default_static_probability
#                       annotated on every net but the clock's (pt_power.tcl's uniform)
#-----------------------------
set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize [file join $script_dir .. ..]]
set run        [file normalize $::env(PWR_RUN)]
set mode       $::env(PWR_MODE)
set fh [open [file join $run tech.json] r]; set tj [read $fh]; close $fh
foreach {var key} {lib_db lib_db lib_name lib_name wire_load wire_load t_scale t_scale c_scale c_scale clock_ns clock_ns drive_cell drive_cell} {
    regexp "\"$key\":\\s*\"(\[^\"\]*)\"" $tj -> $var
}
regexp {"out_load_ff":\s*([0-9.eE+-]+)} $tj -> out_load_ff
regexp {"max_transition_ns":\s*([0-9.eE+-]+)} $tj -> max_trans_ns

set target_library $lib_db
set link_library [list * $lib_db]
set auto_wire_load_selection false
if {$wire_load eq "off"} { remove_attribute [get_libs $lib_name] default_wire_load }
read_verilog [glob [file join $run out *_mapped.v]]
set top [regsub {_mapped$} [file rootname [file tail [glob [file join $run out *_mapped.v]]]] {}]
current_design $top
link
if {$wire_load eq "off"} { remove_wire_load_model [current_design] }
source [file join $repo syn scripts constraints.sdc]
if {$mode eq "uniform"} {
    set nets [remove_from_collection [get_nets -hierarchical *] [get_nets -of_objects [get_ports ap_clk]]]
    set_switching_activity -toggle_rate $power_default_toggle_rate -base_clock clk \
        -static_probability $power_default_static_probability $nets
}
file mkdir reports
report_power -significant_digits 6 > reports/power.rpt
report_power -net -nosplit -significant_digits 6 > reports/power_net.rpt
exit
