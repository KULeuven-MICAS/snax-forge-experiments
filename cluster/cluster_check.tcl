################################
# cluster/cluster_check.tcl: the cluster run's gates (X67), sourced by dc_syn.tcl after the reports
# (SYN_POST_TCL). Writes reports/cluster_check.rpt, one fact per line, which syn/syn.py's read_run reads:
#   leaf_cells <n>                         every non-hierarchical cell of the design, constants included
#   constant <reference> <cells>           DC's pseudo-cells for a tied net (**logic_0**, **logic_1**): no
#                                          library cell, no area; left out of the lines below
#   ref <reference> <library> <cells> <bb> per leaf reference: the library its cell comes from ("-" when no
#                                          library holds it), its cell count, 1 if those cells are black boxes
#   unresolved <reference> <cells>         a leaf reference no library holds (an unresolved reference)
#   black_box <reference> <cells>          a black-box reference (the macros only, PITFALLS DC12)
#   library <library> <cells>              cells per library (Nangate's and the three macros', nothing else)
#   macro_area <um2>                       the black boxes' area (report_area's Macro/Black Box area)
# Unresolved references also show as LINK-5 lines in logs/dc_shell.log; syn.py counts those as well.
# No flop or combinational counting here.
################################

set cc_cells [get_cells -hierarchical -quiet -filter "is_hierarchical == false"]
# one attribute call over the collection, not one per cell (the cluster has hundreds of thousands)
set cc_refs [dict create]
foreach r [get_attribute -quiet $cc_cells ref_name] { dict incr cc_refs $r }
set cc_bb [dict create]
foreach r [get_attribute -quiet [filter_collection $cc_cells "is_black_box == true"] ref_name] { dict set cc_bb $r 1 }
set cc_libs [dict create]
set fh [open reports/cluster_check.rpt w]
puts $fh "# cluster/cluster_check.tcl on [get_object_name [current_design]]: leaf references, their library, black boxes"
puts $fh "leaf_cells [sizeof_collection $cc_cells]"
set cc_unres {}
set cc_bbs {}
foreach r [lsort [dict keys $cc_refs]] {
    set n [dict get $cc_refs $r]
    if {[regexp {^\*\*logic_[01]\*\*$} $r]} {
        puts $fh "constant $r $n"
        continue
    }
    set lc [get_lib_cells -quiet */$r]
    set lib "-"
    if {[sizeof_collection $lc] > 0} {
        set lib [lindex [split [get_object_name [index_collection $lc 0]] /] 0]
        dict incr cc_libs $lib $n
    } else {
        lappend cc_unres [list $r $n]
    }
    set bb [expr {[dict exists $cc_bb $r] ? 1 : 0}]
    if {$bb} { lappend cc_bbs [list $r $n] }
    puts $fh "ref $r $lib $n $bb"
}
foreach x $cc_unres { puts $fh "unresolved [lindex $x 0] [lindex $x 1]" }
foreach x $cc_bbs { puts $fh "black_box [lindex $x 0] [lindex $x 1]" }
dict for {l n} $cc_libs { puts $fh "library $l $n" }
redirect -variable cc_area { report_area -nosplit }
set cc_macro ""
regexp {Macro/Black Box area:\s*([0-9.]+)} $cc_area -> cc_macro
puts $fh "macro_area $cc_macro"
close $fh
puts "cluster_check.tcl: [sizeof_collection $cc_cells] leaf cells, [dict size $cc_refs] references, [llength $cc_unres] unresolved, [llength $cc_bbs] black-box references"
