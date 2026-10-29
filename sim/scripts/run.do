# sim/scripts/run.do - one gate-level power run in vsim -c (sim/pwr.py).
#
#   vsim -c <opt> +nospecify +notimingchecks <plusargs> -do <repo>/sim/scripts/run.do
#
# The TB does everything: $dumpvars on the DUT scopes, $dumpon / $dumpoff around the busy window
# (sim/tb/ap_ctrl_hs_seq.sv), $finish at the end. No log or power commands, so no waveform and no
# Questa SAIF are written (docs/DECISIONS.md X8, X18).
onbreak {resume}
onfinish stop
run -all
quit -f
