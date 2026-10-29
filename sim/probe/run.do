# sim/probe/run.do: the SAIF windows of sim/probe/tb_vecadd_opt_w8.sv, in vsim -c.
#
#   vsim -c <opt> +nospecify +notimingchecks +STIM=<dir> \
#        -do "set saif_dir <dir>; set vcd_file <dir>/dut.vcd; do <repo>/sim/probe/run.do"
#
# Tcl variables, set before `do`:
#   saif_dir   where busy.saif and idle.saif go (default .)
#   add_form   the power add options (default none: the DUT's own nets, no recursion; the
#              netlist is flat)
#   dut        the DUT scope (default /tb_vecadd_opt_w8/dut)
#   vcd_file   if set, also dump the DUT's nets to this VCD (vcd add $dut/*)
#
# The TB calls $stop three times: 1 opens busy, 2 closes busy and opens idle, 3 closes idle.
# Each window: power reset, power on, run to the next $stop, power off, power report.
#
# What vsim 2022.4 writes is not usable as is (results/hls/runs/2026-10-29_pwr_step0.md):
# DURATION is the time since 0, not the window; nets with no event in the window get
# T0 = T1 = 0; and TC drops the zero-width glitches of a zero-delay simulation together
# with real toggles (TC below the VCD's toggle count on 493 of 2588 nets in busy). The VCD
# of the same run is the reference: PrimePower reads it with read_vcd -zero_delay -time,
# or vcd2saif -time cuts the windows into SAIF.
if {![info exists saif_dir]} { set saif_dir . }
if {![info exists add_form]} { set add_form "" }
if {![info exists dut]}      { set dut /tb_vecadd_opt_w8/dut }
onbreak {resume}
onfinish stop

eval power add $add_form [list $dut/*]
if {[info exists vcd_file]} {
    vcd file $vcd_file
    vcd add $dut/*
}

proc window {name} {
    global saif_dir
    power reset -all
    power on -all
    set t0 $::now
    run -continue
    power off -all
    set f [file join $saif_dir $name.saif]
    power report -all -bsaif $f
    echo "run.do: $name window $t0 .. $::now -> $f"
}

run -all
window busy
window idle
run -continue
quit -f
