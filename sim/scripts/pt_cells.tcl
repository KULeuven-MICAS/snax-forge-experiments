#-----------------------------
# sim/scripts/pt_cells.tcl
# pt_power.tcl unchanged (the same library, netlist, wire-load setting, constraints and SAIF), then
# every leaf cell's power and area into <PWR_OUT>/cells.tsv: SYN1's control/datapath split
# (report/flop_split.py). Nothing under syn/runs/ or sim/runs/ is written; PWR_OUT is a folder of its own.
#
#   pt_shell -no_init -f <repo>/sim/scripts/pt_cells.tcl -output_log_file pt_shell.log < /dev/null
#
# Environment: as pt_power.tcl (PWR_RUN, PWR_MODE saif, PWR_ACT, PWR_STRIP, PWR_OUT, PWR_THREADS), and
#   SPLIT_DATA_PORTS  the data input ports, as get_ports patterns (Vitis: *_TDATA; forge: stream2acc_*_data_i)
# cells.tsv: cell (full name), ref (library cell), seq (is_sequential), area (library units),
# internal_w, switching_w, leakage_w (W; switching is the power of the cell's output nets), data (1 when the
# cell is in the forward cone of a data input port: all_fanout through logic, and through every flop it
# reaches, until nothing new is reached).
#-----------------------------

set fh [open [file join [file dirname [file normalize [info script]]] pt_power.tcl] r]
set pt_power_src [read $fh]
close $fh
if {![regsub {\nexit\s*$} $pt_power_src "\n" pt_power_src]} {
    puts "pt_cells.tcl: pt_power.tcl no longer ends with exit"
    exit 2
}
eval $pt_power_src

#-----------------------------
# The data cone: the cells reached from the data input ports, through logic and through flops
#-----------------------------
set dports [get_ports -quiet $::env(SPLIT_DATA_PORTS) -filter "direction == in"]
if {[sizeof_collection $dports] == 0} {
    puts "pt_cells.tcl: no input port matches '$::env(SPLIT_DATA_PORTS)'"
    exit 2
}
set cone [all_fanout -from $dports -flat -only_cells -trace_arcs all]
set done_flops {}
set rounds 0
while {1} {
    set flops [filter_collection $cone "is_sequential == true"]
    set new [remove_from_collection $flops $done_flops]
    if {[sizeof_collection $new] == 0} { break }
    set done_flops [add_to_collection $done_flops $new]
    set qs [get_pins -quiet -of_objects $new -filter "direction == out"]
    if {[sizeof_collection $qs]} {
        set cone [add_to_collection -unique $cone [all_fanout -from $qs -flat -only_cells -trace_arcs all]]
    }
    incr rounds
}
foreach_in_collection c $cone { set in_cone([get_object_name $c]) 1 }
puts "pt_cells.tcl: data cone from [sizeof_collection $dports] ports: [sizeof_collection $cone] cells, [sizeof_collection $done_flops] flops, $rounds rounds"

set fh [open [file join $out cells.tsv] w]
puts $fh "cell\tref\tseq\tarea\tinternal_w\tswitching_w\tleakage_w\tdata"
foreach_in_collection c [get_cells -hierarchical -filter "is_hierarchical == false"] {
    set name [get_object_name $c]
    puts $fh [join [list $name [get_attribute $c ref_name] [get_attribute -quiet $c is_sequential] \
        [get_attribute -quiet $c area] [get_attribute -quiet $c internal_power] \
        [get_attribute -quiet $c switching_power] [get_attribute -quiet $c leakage_power] \
        [expr {[info exists in_cone($name)] ? 1 : 0}]] "\t"]
}
close $fh
puts "pt_cells.tcl: [file join $out cells.tsv]"
exit
