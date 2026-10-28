#-----------------------------
# syn/scripts/dc_syn.tcl
# Design Compiler synthesis of one bench point on FreePDK45 (OSU gscl45nm).
#
# syn/syn.py runs it from the point's run folder, syn/runs/hls/<tier>/<kernel>/<point>/:
#   dc_shell -f <repo>/syn/scripts/dc_syn.tcl -output_log_file logs/dc_shell.log
# Everything this run writes stays in that folder (git ignores syn/runs/).
#
# Environment (syn.py sets all of it):
#   SYN_FILELIST  rtl/<tier>/<kernel>/<point>/filelist.f: '# top: <module>', then the files
#   SYN_LIB       the standard-cell .db (FreePDK45 next to this repo by default)
#   SYN_CLOCK_NS  clock period in ns (default 10)
#   SYN_CORES     cores for DC (default 16)
#-----------------------------

proc env_or {name default} {
    if {[info exists ::env($name)]} { return $::env($name) }
    return $default
}

set script_dir [file dirname [file normalize [info script]]]
set filelist   [file normalize $::env(SYN_FILELIST)]
set lib_db     [file normalize $::env(SYN_LIB)]
set clock_ns   [env_or SYN_CLOCK_NS 10]

#-----------------------------
# Setting up multiple cores
#-----------------------------

# This sets the max number of cores to be used
set_host_options -max_cores [env_or SYN_CORES 16]

# Need to enable these variables
# To ensure that the cores run in parallel
set disable_multicore_resource_checks true
set dcnxt_adaptive_multithreading true

#-----------------------------
# The point: top module and Verilog files, from its filelist
#-----------------------------
set rtl_dir [file dirname $filelist]
set target_design ""
set rtl_files {}
set fh [open $filelist r]
while {[gets $fh line] >= 0} {
    set line [string trim $line]
    if {[regexp {^#\s*top:\s*(\S+)} $line -> name]} { set target_design $name; continue }
    if {$line eq "" || [string index $line 0] eq "#"} { continue }
    lappend rtl_files [file join $rtl_dir $line]
}
close $fh
if {$target_design eq ""} {
    puts "dc_syn.tcl: no '# top:' line in $filelist"
    exit 2
}
puts "dc_syn.tcl: $target_design from $filelist ([llength $rtl_files] files), clock $clock_ns ns"

#-----------------------------
# Work, log, report and output folders, inside the run folder
#-----------------------------
file mkdir logs reports out WORK
define_design_lib WORK -path WORK

#-----------------------------
# Add logic library
#-----------------------------
set target_library $lib_db
# DesignWare, for compile_ultra's arithmetic (the 64-bit multipliers)
set synthetic_library dw_foundation.sldb
set link_library [list * $target_library $synthetic_library]

#-----------------------------
# Read the design
#-----------------------------
analyze -format verilog $rtl_files
elaborate $target_design
current_design $target_design
link

check_design > logs/check_design.log

#-----------------------------
# Library fix: gscl45nm.db sets max_capacitance = 0 on some output pins (AOI21X1,
# AOI22X1, NAND2X1, NAND3X1, NOR2X1, DFFSR, TBUFX1). Every net those pins drive is
# then a max-cap violation whatever its load, and compile spends effort and buffers
# on limits it can never meet. Drop the zero limits (or, if DC refuses to remove a
# library attribute, raise them out of the way); the other pins keep theirs.
#-----------------------------
set zero_cap_pins [get_lib_pins -quiet -filter "max_capacitance == 0" */*/*]
set n_zero_cap [sizeof_collection $zero_cap_pins]
if {$n_zero_cap > 0} {
    if {[catch {remove_attribute $zero_cap_pins max_capacitance} msg]} {
        puts "dc_syn.tcl: remove_attribute refused ($msg); setting max_capacitance = 10 instead"
        set_attribute $zero_cap_pins max_capacitance 10.0 -type float
    }
}
puts "dc_syn.tcl: lifted max_capacitance = 0 on $n_zero_cap library pins"

#-----------------------------
# Add constraints (reads $clock_ns)
#-----------------------------
source [file join $script_dir constraints.sdc]

#-----------------------------
# Compile
#-----------------------------
compile_ultra -no_autoungroup

#-----------------------------
# Reports
#-----------------------------
report_qor -significant_digits 5 > reports/qor.rpt
report_area -nosplit > reports/area.rpt
report_area -hierarchy -nosplit > reports/area_hierarchy.rpt
report_timing -max_paths 5 -nosplit -significant_digits 5 > reports/timing.rpt
report_constraint -all_violators -nosplit -verbose -significant_digits 5 -max_delay > reports/constraint_setup.rpt
report_power > reports/power.rpt
report_power -hierarchy > reports/power_hierarchy.rpt
report_power -verbose -hierarchy > reports/power_verbose_hierarchy.rpt

#-----------------------------
# Outputs
#-----------------------------
write_file -format verilog -hierarchy -output out/${target_design}_mapped.v
write_sdf out/${target_design}_mapped.sdf

exit
