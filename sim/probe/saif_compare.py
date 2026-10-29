#!/usr/bin/env python3
"""sim/probe/saif_compare.py: Questa's SAIF against vcd2saif's SAIF of the same window, per net.

  pixi run python sim/probe/saif_compare.py <questa.saif> <vcd2saif.saif>

Both files come from one vsim run (sim/probe/run.do writes the Questa SAIF and the VCD;
vcd2saif -time cuts the same window from the VCD). Prints DURATION, how many nets have
T0 + T1 + TX = DURATION, T0 = T1 = 0, and how many differ in TC, with the TC sums and a
few examples.
"""
import re
import sys

REC = re.compile(r"\((\S+)\s+\(T0 (\d+)\)\s*\(T1 (\d+)\)\s*\(TX (\d+)\)\s*\(TC (\d+)\)\s*\(IG (\d+)\)", re.S)


def read(path):
    s = open(path).read()
    dur = int(re.search(r"\(DURATION (\d+)\)", s).group(1))
    nets = {m[0]: tuple(int(x) for x in m[1:]) for m in REC.findall(s)}
    return dur, nets


def main():
    (dq, q), (dv, v) = read(sys.argv[1]), read(sys.argv[2])
    common = sorted(set(q) & set(v))
    full_q = sum(1 for n in q.values() if n[0] + n[1] + n[2] == dq)
    full_q_win = sum(1 for n in q.values() if n[0] + n[1] + n[2] == dv)
    zero_q = sum(1 for n in q.values() if n[0] + n[1] + n[2] == 0)
    tc_diff = [k for k in common if q[k][3] != v[k][3]]
    print(f"Questa  {sys.argv[1]}: DURATION {dq}, {len(q)} nets, T0+T1+TX = DURATION on {full_q}, "
          f"= window ({dv}) on {full_q_win}, T0 = T1 = TX = 0 on {zero_q}, IG > 0 on "
          f"{sum(1 for n in q.values() if n[4] > 0)} (sum IG {sum(n[4] for n in q.values())})")
    print(f"vcd2saif {sys.argv[2]}: DURATION {dv}, {len(v)} nets, T0+T1+TX = DURATION on "
          f"{sum(1 for n in v.values() if n[0] + n[1] + n[2] == dv)}, IG > 0 on {sum(1 for n in v.values() if n[4] > 0)}")
    print(f"common nets {len(common)}: TC differs on {len(tc_diff)} "
          f"(Questa below vcd2saif on {sum(1 for k in tc_diff if q[k][3] < v[k][3])}); "
          f"sum TC Questa {sum(q[k][3] for k in common)}, vcd2saif {sum(v[k][3] for k in common)}")
    for k in sorted(tc_diff, key=lambda k: q[k][3] - v[k][3])[:5]:
        print(f"  {k}: Questa T0 {q[k][0]} T1 {q[k][1]} TC {q[k][3]} IG {q[k][4]} | vcd2saif T0 {v[k][0]} T1 {v[k][1]} TC {v[k][3]}")


if __name__ == "__main__":
    main()
