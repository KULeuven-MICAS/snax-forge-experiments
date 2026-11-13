#-----------------------------
# syn/scripts/dc_syn.tcl
# Design Compiler synthesis of one bench point on one technology (syn/tech/<tech>.json).
#
# syn/syn.py runs it from the point's run folder, syn/runs/<source>/<tech>/<tier>/<kernel>/<point>/:
#   dc_shell -f <repo>/syn/scripts/dc_syn.tcl -output_log_file logs/dc_shell.log
# Everything this run writes stays in that folder (git ignores syn/runs/).
#
# Environment (syn.py sets all of it from the tech file):
#   SYN_FILELIST       rtl/<tier>/<kernel>/<point>/filelist.f: '# top: <module>', then the files
#                      (a forge point's is written into the run folder, with absolute paths)
#   SYN_LIB_DB         the standard-cell .db
#   SYN_LIB_NAME       the library name the .db must hold
#   SYN_TIME_UNIT      the library time unit the tech file expects (1ns, 1ps)
#   SYN_CAP_UNIT       the library capacitance unit the tech file expects (1ff)
#   SYN_T_SCALE        library time units per ns (1 or 1000)
#   SYN_C_SCALE        library capacitance units per fF
#   SYN_DRIVE_CELL     input driving cell (constraints.sdc)
#   SYN_OUT_LOAD_FF    load on every output, in fF (constraints.sdc)
#   SYN_MAX_TRANS_NS   max transition, in ns (constraints.sdc)
#   SYN_WIRE_LOAD      off (the library has wire-load models; keep them out) or none (it has none)
#   SYN_CLOCK_NS       clock period in ns
#   SYN_CORES          cores for DC
#   SYN_FORMAT         analyze's format: verilog (default; Vitis, Bambu, XLS) or sverilog (snax-forge,
#                      its blocks)
#   SYN_CLK_PORT       the clock port: ap_clk (default, Vitis), clock (Bambu; a snax-forge block),
#                      clk (XLS) or clk_i (snax-forge)
#   SYN_RAM_DBS        optional: SRAM macro .db files linked beside the library (X62, a Vitis RAM swapped)
#   SYN_RST_PORT       the reset port, kept ideal: ap_rst_n (default, Vitis, synchronous, active low),
#                      reset (Bambu, mostly synchronous, active low), rst (XLS, synchronous, active
#                      high), rst_ni (snax-forge, asynchronous, active low) or reset (a snax-forge
#                      block alone, CHAR1: asynchronous, active high)
#                      syn.py checks both ports are on the top before it starts DC (port guard)
#
# Optional hooks (CSYN1 Part B, the cluster source; unset, the run is as before):
#   SYN_FLIST_TCL      a Tcl file list in bender's synopsys form (snax_cluster's gen-syn syn_flist.tcl:
#                      analyze groups, each 'if {0 == [analyze ...]} {return 1}'), sourced in place of
#                      SYN_FILELIST; a failed group stops the run (exit 2). Needs SYN_TOP.
#   SYN_TOP            the module elaborated after SYN_FLIST_TCL
#   SYN_EXTRA_SDC      a file sourced right after constraints.sdc (it sees the same variables)
#   SYN_POST_TCL       a file sourced after the reports, before the outputs
#   SYN_WRITE_SDF      1: write the SDF beside the netlist (syn.py --sdf); otherwise none (X69)
#   SYN_IGNORE_LOAD    1: take SYN_CORES whatever the host's load (disable_multicore_resource_checks set before
#                      set_host_options); otherwise DC lowers the cores under load once, at the start (UIO-231)
#   SYN_CLK_GATE_ENABLE 1: CLK_GATE_ENABLE, clock gating (X79): clock_gating.tcl sourced before the compile,
#                      compile_ultra -no_autoungroup -gate_clock, and reports/clock_gating*.rpt; otherwise 0, none
#
# The constraints are physical (ns, fF) and scaled to the library's units here; the
# library's own name and units are checked against the tech file before any RTL is read.
#-----------------------------

set script_dir   [file dirname [file normalize [info script]]]
# Optional, the hls values by default (constraints.sdc reads $clk_port and $rst_port)
proc env_or {name default} {
    if {[info exists ::env($name)]} { return $::env($name) }
    return $default
}
set flist_tcl    [env_or SYN_FLIST_TCL ""]
if {$flist_tcl eq ""} { set filelist [file normalize $::env(SYN_FILELIST)] }
set lib_db       [file normalize $::env(SYN_LIB_DB)]
set lib_name     $::env(SYN_LIB_NAME)
set time_unit    $::env(SYN_TIME_UNIT)
set cap_unit     $::env(SYN_CAP_UNIT)
set t_scale      $::env(SYN_T_SCALE)
set c_scale      $::env(SYN_C_SCALE)
set drive_cell   $::env(SYN_DRIVE_CELL)
set out_load_ff  $::env(SYN_OUT_LOAD_FF)
set max_trans_ns $::env(SYN_MAX_TRANS_NS)
set wire_load    $::env(SYN_WIRE_LOAD)
set clock_ns     $::env(SYN_CLOCK_NS)
set hdl_format   [env_or SYN_FORMAT verilog]
set clk_port     [env_or SYN_CLK_PORT ap_clk]
set rst_port     [env_or SYN_RST_PORT ap_rst_n]
# X79: the clock-gating switch, off unless SYN_CLK_GATE_ENABLE is 1 (syn.py --clk-gate, a cluster point's syn.clk_gate)
set CLK_GATE_ENABLE [expr {[env_or SYN_CLK_GATE_ENABLE 0] eq "1" ? 1 : 0}]

#-----------------------------
# Setting up multiple cores
#-----------------------------

# SYN_IGNORE_LOAD=1 (the cluster source, X68): the load check is off before the cores are set, so DC keeps
# SYN_CORES; otherwise set_host_options cuts them by the load at this moment (UIO-231) for the whole run
if {[env_or SYN_IGNORE_LOAD 0] eq "1"} { set disable_multicore_resource_checks true }

# This sets the max number of cores to be used
set_host_options -max_cores $::env(SYN_CORES)

# Need to enable these variables
# To ensure that the cores run in parallel
set disable_multicore_resource_checks true
set dcnxt_adaptive_multithreading true

#-----------------------------
# The point: top module and Verilog files, from its filelist, or (SYN_FLIST_TCL) a Tcl list and SYN_TOP
#-----------------------------
if {$flist_tcl ne ""} {
    set flist_tcl [file normalize $flist_tcl]
    set target_design [env_or SYN_TOP ""]
    if {$target_design eq ""} {
        puts "dc_syn.tcl: SYN_FLIST_TCL is set but SYN_TOP is not"
        exit 2
    }
    puts "dc_syn.tcl: $target_design from $flist_tcl (sourced), clock $clock_ns ns on $clk_port, reset $rst_port"
} else {
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
    puts "dc_syn.tcl: $target_design from $filelist ([llength $rtl_files] files, $hdl_format), clock $clock_ns ns on $clk_port, reset $rst_port"
}

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
# Library check: name and units as the library states them, against the tech file.
# The constraints below are scaled with the tech file's units; a library in other
# units would take every number 1000x off without an error.
#-----------------------------
set read_names {}
foreach l [get_object_name [get_libs -quiet *]] {
    if {$l ni {gtech standard.sldb dw_foundation.sldb}} { lappend read_names $l }
}
set read_name [join $read_names " "]
set read_time ""
set read_cap  ""
set lib_report ""
if {[llength $read_names] == 1} {
    redirect -variable lib_report { report_lib $read_name }
    # "Time Unit : 1ns", "Capacitive Load Unit : 1.000000ff" -> 1ns, 1ff
    if {[regexp {Time Unit\s*:\s*([0-9.]+)\s*([A-Za-z]+)} $lib_report -> n u]} {
        set read_time "[format %g $n][string tolower $u]"
    }
    if {[regexp {Capacitive Load Unit\s*:\s*([0-9.]+)\s*([A-Za-z]+)} $lib_report -> n u]} {
        set read_cap "[format %g $n][string tolower $u]"
    }
}
if {$read_name ne $lib_name || $read_time ne [string tolower $time_unit] || $read_cap ne [string tolower $cap_unit]} {
    puts "dc_syn.tcl: library mismatch in $lib_db"
    puts "dc_syn.tcl:   tech file expects  name $lib_name, time unit $time_unit, cap unit $cap_unit"
    puts "dc_syn.tcl:   library reports    name $read_name, time unit $read_time, cap unit $read_cap"
    exit 2
}

# Operating condition (the library's first; both Nangate libraries hold only 'typical')
set oc_name ""; set oc_proc ""; set oc_temp ""; set oc_volt ""
regexp {Operating Condition Name\s*:\s*(\S+).*?Process\s*:\s*(\S+).*?Temperature\s*:\s*(\S+).*?Voltage\s*:\s*(\S+)} \
    $lib_report -> oc_name oc_proc oc_temp oc_volt
set default_wlm [get_attribute -quiet [get_libs $lib_name] default_wire_load]

set fh [open reports/lib_info.txt w]
puts $fh "library: $read_name"
puts $fh "db: $lib_db"
puts $fh "time_unit: $read_time"
puts $fh "cap_unit: $read_cap"
puts $fh "operating_condition: $oc_name"
puts $fh "process: $oc_proc"
puts $fh "voltage_v: $oc_volt"
puts $fh "temperature_c: $oc_temp"
puts $fh "default_wire_load: $default_wlm"
puts $fh "dc_version: $sh_product_version"
puts $fh "power_default_toggle_rate: $power_default_toggle_rate"
puts $fh "power_default_static_probability: $power_default_static_probability"
close $fh
puts "dc_syn.tcl: $read_name ($read_time, $read_cap), $oc_name $oc_volt V $oc_temp C"

#-----------------------------
# SRAM macros (X62): a Vitis RAM swapped for a generated macro; its .db is linked beside the library, after the
# library check above, which counts the libraries loaded so far (syn.py sets SYN_RAM_DBS, space separated)
#-----------------------------
set ram_dbs [env_or SYN_RAM_DBS ""]
if {$ram_dbs ne ""} {
    foreach db $ram_dbs { lappend link_library [file normalize $db] }
    puts "dc_syn.tcl: SRAM macros linked: $ram_dbs"
}

#-----------------------------
# Wire load. off: the library has wire-load models, none applies to this design.
# none: the library has none; check that.
#-----------------------------
set auto_wire_load_selection false
if {$wire_load eq "off"} {
    if {$default_wlm ne ""} { remove_attribute [get_libs $lib_name] default_wire_load }
} elseif {$wire_load eq "none"} {
    if {$default_wlm ne ""} {
        puts "dc_syn.tcl: wire_load is 'none' but $lib_name has default_wire_load $default_wlm"
        exit 2
    }
} else {
    puts "dc_syn.tcl: wire_load must be 'off' or 'none', not '$wire_load'"
    exit 2
}

#-----------------------------
# Read the design
#-----------------------------
if {$flist_tcl ne ""} {
    # bender's groups end in 'return 1' when an analyze fails, which source returns
    if {[catch {source $flist_tcl} r] || $r eq "1"} {
        puts "dc_syn.tcl: sourcing $flist_tcl failed: $r"
        exit 2
    }
} else {
    analyze -format $hdl_format $rtl_files
}
elaborate $target_design
current_design $target_design
link
if {$wire_load eq "off"} { remove_wire_load_model [current_design] }

check_design > logs/check_design.log

#-----------------------------
# Add constraints (reads $clock_ns, $t_scale, $c_scale and the tech values above)
#-----------------------------
source [file join $script_dir constraints.sdc]
set extra_sdc [env_or SYN_EXTRA_SDC ""]
if {$extra_sdc ne ""} {
    puts "dc_syn.tcl: extra constraints from $extra_sdc"
    source [file normalize $extra_sdc]
}

#-----------------------------
# Compile; with CLK_GATE_ENABLE (X79) the clock-gating style first, and -gate_clock
#-----------------------------
if {$CLK_GATE_ENABLE} {
    source [file join $script_dir clock_gating.tcl]
    compile_ultra -no_autoungroup -gate_clock
} else {
    compile_ultra -no_autoungroup
}

#-----------------------------
# Reports
#-----------------------------
report_qor -significant_digits 5 > reports/qor.rpt
report_area -nosplit > reports/area.rpt
report_area -hierarchy -nosplit > reports/area_hierarchy.rpt
report_reference -nosplit > reports/reference.rpt
report_timing -max_paths 5 -nosplit -significant_digits 5 > reports/timing.rpt
report_constraint -all_violators -nosplit -verbose -significant_digits 5 -max_delay > reports/constraint_setup.rpt
report_clock -nosplit > reports/clock.rpt
report_clock -skew -nosplit >> reports/clock.rpt
# The full port report runs to hundreds of kB on the wide AXI-stream tops; keep a sample of
# ports (clock, reset, first and last data input, first and last output) and tally every
# output's max pin load in design_rules.rpt.
set outputs [all_outputs]
set n_out [sizeof_collection $outputs]
set sample [get_ports [list $clk_port $rst_port]]
foreach c [list $data_inputs $outputs] {
    set n [sizeof_collection $c]
    set sample [add_to_collection -unique $sample [index_collection $c 0]]
    set sample [add_to_collection -unique $sample [index_collection $c [expr {$n - 1}]]]
}
report_port -verbose -nosplit $sample > reports/port.rpt
redirect -variable all_ports { report_port -nosplit }
set loads [dict create]
foreach ln [split $all_ports "\n"] {
    # 'Port  out  min_rise/fall  max_rise/fall  ...': the pin load columns
    if {[regexp {^\S+\s+out\s+\S+\s+(\S+)} $ln -> max_load]} { dict incr loads $max_load }
}
set fh [open reports/design_rules.rpt w]
puts $fh "Design rules on $target_design, in library units (time $read_time, cap $read_cap)"
puts $fh "max_transition: [get_attribute [current_design] max_transition]"
puts $fh "max_fanout: [get_attribute [current_design] max_fanout]"
puts $fh "outputs: $n_out"
dict for {l n} $loads { puts $fh "output max pin load rise/fall $l: $n ports" }
close $fh
# 6 digits in power.rpt; the hierarchical reports print 3 whatever -significant_digits says
report_power -significant_digits 6 > reports/power.rpt
report_power -hierarchy -nosplit -significant_digits 6 > reports/power_hierarchy.rpt
report_power -verbose -hierarchy -nosplit -significant_digits 6 > reports/power_verbose_hierarchy.rpt
# X79: what clock gating did: the summary, each ICG with the bits it gates, and every ungated register with why
if {$CLK_GATE_ENABLE} {
    report_clock_gating -nosplit > reports/clock_gating.rpt
    report_clock_gating -gating_elements -nosplit > reports/clock_gating_elements.rpt
    report_clock_gating -ungated -nosplit > reports/clock_gating_ungated.rpt
}

#-----------------------------
# Path classes (docs X40): the worst setup slack from inputs or registers to registers or
# outputs, measured after compile with get_timing_paths -from/-to only; nothing here
# changes the compile (no group_path). Inputs: every input but the clock and the reset;
# outputs: every output; registers: clock pins as start points, data pins as endpoints.
# One line per class, slack in library time units; 'none' where the class has no path.
#-----------------------------
set pc_in   [remove_from_collection [all_inputs] [get_ports -quiet [list $clk_port $rst_port]]]
set pc_out  [all_outputs]
set pc_rclk [all_registers -clock_pins]
set pc_rdat [all_registers -data_pins]
set fh [open reports/path_classes.rpt w]
puts $fh "# Worst setup slack per path class of $target_design at $clock_ns ns, in library time units ($read_time)"
puts $fh "# inputs [sizeof_collection $pc_in] (all but $clk_port and $rst_port), outputs [sizeof_collection $pc_out],\
 register clock pins [sizeof_collection $pc_rclk], register data pins [sizeof_collection $pc_rdat]"
puts $fh "# class slack startpoint endpoint"
foreach {cls from to} [list in2reg $pc_in $pc_rdat reg2reg $pc_rclk $pc_rdat \
                            reg2out $pc_rclk $pc_out in2out $pc_in $pc_out] {
    set slack none; set sp -; set ep -
    if {[sizeof_collection $from] > 0 && [sizeof_collection $to] > 0} {
        set path [get_timing_paths -delay_type max -max_paths 1 -from $from -to $to]
        if {[sizeof_collection $path] > 0} {
            set s [get_attribute -quiet $path slack]
            # an unconstrained path reports INFINITY: no path in the class
            if {[string is double -strict $s] && ![string match -nocase *inf* $s]} {
                set slack $s
                set sp [get_object_name [get_attribute $path startpoint]]
                set ep [get_object_name [get_attribute $path endpoint]]
            }
        }
    }
    puts $fh "$cls $slack $sp $ep"
}
close $fh

#-----------------------------
# A source's own checks and reports (SYN_POST_TCL), after the reports and before the outputs
#-----------------------------
set post_tcl [env_or SYN_POST_TCL ""]
if {$post_tcl ne ""} {
    puts "dc_syn.tcl: post script $post_tcl"
    source [file normalize $post_tcl]
}

#-----------------------------
# Outputs: the netlist; the SDF only with SYN_WRITE_SDF=1 (syn.py --sdf, X69): nothing reads it
#-----------------------------
write_file -format verilog -hierarchy -output out/${target_design}_mapped.v
if {[env_or SYN_WRITE_SDF 0] eq "1"} { write_sdf out/${target_design}_mapped.sdf }

exit
