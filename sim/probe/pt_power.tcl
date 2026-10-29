#-----------------------------
# sim/probe/pt_power.tcl
# PrimePower (pt_shell, averaged mode) on one mapped netlist from syn/runs/, with the same
# library, constraints and wire-load setting as syn/scripts/dc_syn.tcl. Nothing is
# resynthesized and nothing under syn/runs/ is written: run it from a folder of its own.
#
#   pt_shell -no_init -f <repo>/sim/probe/pt_power.tcl -output_log_file pt_shell.log < /dev/null
#
# Environment:
#   PWR_RUN     the syn run folder: syn/runs/hls/<tech>/<tier>/<kernel>/<point>
#   PWR_MODE    p0    no activity file: DC's power_default_toggle_rate and
#                     power_default_static_probability (the run's reports/lib_info.txt)
#               uniform  the same two values annotated on every net but the clock's, so
#                     nothing is propagated (with sim/probe/dc_readback.tcl: the check that
#                     PT and DC compute the same power from the same activity)
#               saif  read_saif PWR_ACT -strip_path PWR_STRIP
#               vcd   read_vcd -zero_delay PWR_ACT -strip_path PWR_STRIP -time PWR_TIME
#   PWR_ACT     the SAIF or VCD file (saif, vcd)
#   PWR_STRIP   the DUT instance in the TB, e.g. tb_vecadd_opt_w8/dut (saif, vcd)
#   PWR_TIME    the VCD window in ns, "t0 t1" (vcd)
#   PWR_OUT     where the reports go (default reports)
#   PWR_NETS    1: also write net_activity.txt, every net's toggle rate (per ns) and static
#               probability after update_power, for comparisons with DC
#-----------------------------

set script_dir [file dirname [file normalize [info script]]]
set repo       [file normalize [file join $script_dir .. ..]]
set run        [file normalize $::env(PWR_RUN)]
set mode       $::env(PWR_MODE)
set out        [expr {[info exists ::env(PWR_OUT)] ? $::env(PWR_OUT) : "reports"}]
file mkdir $out

#-----------------------------
# The run's tech.json: the same values dc_syn.tcl had (syn.py passed them as SYN_*)
#-----------------------------
set fh [open [file join $run tech.json] r]; set tj [read $fh]; close $fh
proc tj_str {key} {
    global tj
    if {![regexp "\"$key\":\\s*\"(\[^\"\]*)\"" $tj -> v]} { error "tech.json: no string $key" }
    return $v
}
proc tj_num {key} {
    global tj
    if {![regexp "\"$key\":\\s*(\[0-9.eE+-\]+)" $tj -> v]} { error "tech.json: no number $key" }
    return $v
}
set lib_db       [tj_str lib_db]
set lib_md5      [tj_str lib_md5]
set lib_name     [tj_str lib_name]
set wire_load    [tj_str wire_load]
set t_scale      [tj_str t_scale]
set c_scale      [tj_str c_scale]
set clock_ns     [tj_str clock_ns]
set drive_cell   [tj_str drive_cell]
set out_load_ff  [tj_num out_load_ff]
set max_trans_ns [tj_num max_transition_ns]

set md5 [lindex [exec md5sum $lib_db] 0]
if {$md5 ne $lib_md5} {
    puts "pt_power.tcl: $lib_db has md5 $md5, the run's tech.json says $lib_md5"
    exit 2
}
puts "pt_power.tcl: $run, mode $mode, library $lib_name ($lib_db, md5 $md5 as in tech.json)"

#-----------------------------
# Library and netlist
#-----------------------------
set power_enable_analysis true
set power_analysis_mode averaged
set search_path [list . [file dirname $lib_db]]
set link_library [list * $lib_db]
set netlist [glob [file join $run out *_mapped.v]]
read_verilog $netlist
set top [file rootname [file tail $netlist]]
regsub {_mapped$} $top {} top
current_design $top
link_design

#-----------------------------
# Wire load: none, as in dc_syn.tcl. PT applies the library's default_wire_load
# (5K_hvratio_1_1 on nangate45, 'library default' in report_wire_load) whatever
# auto_wire_load_selection and remove_wire_load_model say, and report_design still shows
# wire_load_model '--'. So every net gets wire capacitance 0 and resistance 0 annotated,
# which overrides the model: total capacitance is the pin and port capacitances, as in
# DC. (set_load -wire_load 0 is rejected on nets; set_load 0 on nets is the wire cap.)
#-----------------------------
set auto_wire_load_selection false
if {$wire_load eq "off"} { remove_wire_load_model }
set_load 0 [get_nets -hierarchical *]
set_resistance 0 [get_nets -hierarchical *]
redirect [file join $out wire_load.rpt] {
    puts "auto_wire_load_selection: $auto_wire_load_selection"
    puts "library default_wire_load (PT): '[get_attribute -quiet [get_libs $lib_name] default_wire_load]'"
    report_design
    report_wire_load
    set nw 0; set wsum 0.0; set nr 0
    foreach_in_collection n [get_nets -hierarchical *] {
        set w [get_attribute -quiet $n wire_capacitance_max]
        if {$w ne "" && $w > 0} { incr nw; set wsum [expr {$wsum + $w}] }
        set r [get_attribute -quiet $n net_resistance_max]
        if {$r ne "" && $r > 0} { incr nr }
    }
    puts "nets: [sizeof_collection [get_nets -hierarchical *]], with wire_capacitance_max > 0: $nw (sum $wsum), with net_resistance_max > 0: $nr"
}

#-----------------------------
# Constraints: syn/scripts/constraints.sdc unchanged, with dc_syn.tcl's variables
#-----------------------------
source [file join $repo syn scripts constraints.sdc]

#-----------------------------
# Activity
#-----------------------------
if {$mode eq "p0"} {
    set fh [open [file join $run reports lib_info.txt] r]; set li [read $fh]; close $fh
    regexp {power_default_toggle_rate:\s*(\S+)} $li -> tr
    regexp {power_default_static_probability:\s*(\S+)} $li -> sp
    set power_default_toggle_rate $tr
    set power_default_static_probability $sp
    puts "pt_power.tcl: P0, power_default_toggle_rate $tr, power_default_static_probability $sp (DC's)"
} elseif {$mode eq "uniform"} {
    set fh [open [file join $run reports lib_info.txt] r]; set li [read $fh]; close $fh
    regexp {power_default_toggle_rate:\s*(\S+)} $li -> tr
    regexp {power_default_static_probability:\s*(\S+)} $li -> sp
    set nets [remove_from_collection [get_nets -hierarchical *] [get_nets -of_objects [get_ports ap_clk]]]
    set_switching_activity -toggle_rate $tr -base_clock clk -static_probability $sp $nets
    puts "pt_power.tcl: uniform, toggle rate $tr per clk cycle and static probability $sp on [sizeof_collection $nets] nets"
} elseif {$mode eq "saif"} {
    read_saif -strip_path $::env(PWR_STRIP) $::env(PWR_ACT)
} elseif {$mode eq "vcd"} {
    read_vcd -zero_delay -strip_path $::env(PWR_STRIP) -time $::env(PWR_TIME) $::env(PWR_ACT)
} else {
    puts "pt_power.tcl: PWR_MODE must be p0, saif or vcd, not '$mode'"
    exit 2
}

update_power

#-----------------------------
# Reports
#-----------------------------
report_switching_activity > [file join $out switching_activity.rpt]
if {$mode ne "p0"} {
    report_switching_activity -list_not_annotated > [file join $out not_annotated.rpt]
}
redirect [file join $out units.rpt] { report_units }
report_power -nosplit -significant_digits 6 > [file join $out power.rpt]
report_power -hierarchy -nosplit -significant_digits 6 > [file join $out power_hierarchy.rpt]
redirect [file join $out licenses.rpt] { list_licenses }
if {[info exists ::env(PWR_NETS)] && $::env(PWR_NETS)} {
    set fh [open [file join $out net_activity.txt] w]
    foreach_in_collection n [get_nets -hierarchical *] {
        puts $fh "[get_object_name $n] [get_attribute -quiet $n toggle_rate] [get_attribute -quiet $n static_probability]"
    }
    close $fh
}
exit
