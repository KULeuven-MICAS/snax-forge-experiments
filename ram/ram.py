"""RAM1: SRAM bank area and energy from CACTI 7 at 45 nm (itrs-hp), one point per (depth, width).

    pixi run ram-build                       # clone and build CACTI into ram/cacti/ (once)
    pixi run ram point 512 64                # one point: config, run, parse, print
    pixi run ram point 512 64 --objective 0:0:0:100:0
    pixi run ram table -j 32                 # the lookup table -> results/ram/nangate45/ram_table.csv

Each point runs in its own folder, ram/runs/cacti/d<d>_w<w>[_<variant>]/, with tech_params/ linked
in: CACTI opens "tech_params/45nm.dat" relative to its working directory. A folder whose config
(and CACTI commit) is unchanged is not rerun. Dynamic energies are scaled from CACTI's itrs-hp
Vdd (1.0 V at 45 nm) to Nangate 45 nm's 1.10 V by (1.1 / 1.0)^2; area and timing are not scaled.
"""

import argparse
import csv
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CACTI_DIR = REPO / "ram" / "cacti"
CACTI_BIN = CACTI_DIR / "cacti"
RUNS = REPO / "ram" / "runs" / "cacti"
TABLE_OUT = REPO / "results" / "ram" / "nangate45" / "ram_table.csv"

TECH_U = 0.045
VDD_CACTI = 1.0      # itrs-hp at 45 nm (tech_params/45nm.dat, -Vdd hp column); checked against CACTI's printout
VDD_TARGET = 1.10    # Nangate 45 nm typical
E_SCALE = (VDD_TARGET / VDD_CACTI) ** 2
OBJECTIVE = "0:50:0:0:50"   # weights: delay, dynamic power, leakage power, cycle time, area
TIMEOUT_S = 3600

# The lookup table (X48): every depth 32..4096 in steps of 32 words, every width 8..256 in steps of 8 bits.
# Points CACTI rejects (under 64 bytes: only 32 x 8 here) are left out of the table.
TABLE_DEPTHS = range(32, 4096 + 1, 32)
TABLE_WIDTHS = range(8, 256 + 1, 8)
TABLE_COLUMNS = ["depth", "width", "area_um2", "e_rd_pj", "e_wr_pj", "t_access_ns", "t_cycle_ns", "leak_uw",
                 "ndwl", "ndbl", "nspd", "ndcm", "ndsam_l1", "ndsam_l2"]


def cacti_commit():
    try:
        return subprocess.run(["git", "-C", str(CACTI_DIR), "rev-parse", "--short=7", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return "unknown"


def cacti_width(w):
    """CACTI works in whole bytes: pad a width to a multiple of 8 (39 -> 40)."""
    return -(-w // 8) * 8


def set_line(lines, key, new):
    """Replace the one active (not //-commented) line of cache.cfg that starts with key."""
    hits = [i for i, l in enumerate(lines) if l.startswith(key)]
    if len(hits) != 1:
        raise ValueError(f"cache.cfg: {len(hits)} active lines start with {key!r}")
    lines[hits[0]] = new


def make_config(d, w, objective=OBJECTIVE, ecc=False):
    wc = cacti_width(w)
    lines = (CACTI_DIR / "cache.cfg").read_text().splitlines()
    set_line(lines, "-size (bytes)", f"-size (bytes) {d * wc // 8}")
    set_line(lines, "-block size (bytes)", f"-block size (bytes) {wc // 8}")
    set_line(lines, "-associativity", "-associativity 1")
    set_line(lines, "-read-write port", "-read-write port 1")
    set_line(lines, "-exclusive read port", "-exclusive read port 0")
    set_line(lines, "-exclusive write port", "-exclusive write port 0")
    set_line(lines, "-single ended read ports", "-single ended read ports 0")
    set_line(lines, "-UCA bank count", "-UCA bank count 1")
    set_line(lines, "-technology (u)", f"-technology (u) {TECH_U}")
    set_line(lines, "-Data array cell type", '-Data array cell type - "itrs-hp"')
    set_line(lines, "-Data array peripheral type", '-Data array peripheral type - "itrs-hp"')
    set_line(lines, "-output/input bus width", f"-output/input bus width {wc}")
    set_line(lines, "-operating temperature (K)", "-operating temperature (K) 300")
    set_line(lines, "-cache type", '-cache type "ram"')
    set_line(lines, "-design objective", "-design objective (weight delay, dynamic power, leakage power, cycle time, area) "
             + objective)
    # cache.cfg's ED^2 makes CACTI ignore the design objective and deviate (Ucache.cc find_optimal_uca)
    set_line(lines, "-Optimize ED or ED^2", '-Optimize ED or ED^2 (ED, ED^2, NONE): "NONE"')
    # cache.cfg adds one ECC bit per 8 data bits on the H-trees; a TCDM bank has no ECC
    set_line(lines, "-Add ECC", '-Add ECC - "{}"'.format("true" if ecc else "false"))
    set_line(lines, "-Print level", '-Print level (DETAILED, CONCISE) - "DETAILED"')
    set_line(lines, "-Print input parameters", '-Print input parameters - "true"')
    return "\n".join(lines) + "\n"


def run_dir(d, w, tag=""):
    return RUNS / (f"d{d}_w{w}" + (f"_{tag}" if tag else ""))


def run_point(d, w, objective=OBJECTIVE, ecc=False, tag=""):
    """Write the config, run CACTI unless the folder already ran this config, return the folder."""
    rd = run_dir(d, w, tag)
    rd.mkdir(parents=True, exist_ok=True)
    cfg = make_config(d, w, objective, ecc)
    key = {"cfg": cfg, "cacti_commit": cacti_commit()}
    keyf = rd / "key.json"
    if keyf.exists() and (rd / "rc").exists() and json.loads(keyf.read_text()) == key:
        return rd, True
    for name in ("tech_params", "contention.dat"):
        link = rd / name
        if not link.exists():
            link.symlink_to(CACTI_DIR / name)
    (rd / "cacti.cfg").write_text(cfg)
    t0 = time.time()
    try:
        with open(rd / "cacti.out", "w") as out, open(rd / "cacti.err", "w") as err:
            rc = subprocess.run([str(CACTI_BIN), "-infile", "cacti.cfg"], cwd=rd, stdout=out, stderr=err,
                                timeout=TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    (rd / "time_s").write_text(f"{time.time() - t0:.2f}\n")
    (rd / "rc").write_text(f"{rc}\n")
    keyf.write_text(json.dumps(key))
    return rd, False


FIELDS = {  # CACTI's printed label -> (key, unit factor to ours)
    "Access time (ns):": ("t_access_ns", 1.0),
    "Cycle time (ns):": ("t_cycle_ns", 1.0),
    "Total dynamic read energy per access (nJ):": ("e_rd_raw_pj", 1e3),
    "Total dynamic write energy per access (nJ):": ("e_wr_raw_pj", 1e3),
    "Total leakage power of a bank (mW):": ("leak_uw", 1e3),
    "Total gate leakage power of a bank (mW):": ("leak_gate_uw", 1e3),
    "Data array: Area (mm2):": ("data_area_um2", 1e6),
    "Best Ndwl :": ("ndwl", 1),
    "Best Ndbl :": ("ndbl", 1),
    "Best Nspd :": ("nspd", 1),
    "Best Ndcm :": ("ndcm", 1),
    "Best Ndsam L1 :": ("ndsam_l1", 1),
    "Best Ndsam L2 :": ("ndsam_l2", 1),
}
ORG = ("ndwl", "ndbl", "nspd", "ndcm", "ndsam_l1", "ndsam_l2")
COLUMNS = ["depth", "width", "width_cacti", "bits", "status", "area_um2", "data_area_um2", "height_um", "width_um",
           "e_rd_pj", "e_wr_pj", "e_rd_raw_pj", "e_wr_raw_pj", "e_rd_bit_fj", "e_wr_bit_fj", "leak_uw", "leak_gate_uw",
           "t_access_ns", "t_cycle_ns", "ndwl", "ndbl", "nspd", "ndcm", "ndsam_l1", "ndsam_l2", "area_eff_pct",
           "objective", "ecc", "cacti_commit", "run"]
ERROR_RE = re.compile(r"error|must|invalid|not supported|cannot|abort|fault|terminate", re.I)


def num(s):
    return float(s.strip().split()[0])


def sig(x, n=6):
    return x if isinstance(x, (int, str)) else float(f"{x:.{n}g}")


def parse(rd):
    """CACTI's output, by label. The first occurrence of each label is the summary block's."""
    out = (rd / "cacti.out").read_text(errors="replace")
    vals = {}
    for line in out.splitlines():
        s = line.strip()
        for label, (key, f) in FIELDS.items():
            if s.startswith(label) and key not in vals:
                v = num(s[len(label):])
                vals[key] = int(v) if key in ORG else v * f
        if s.startswith("Cache height x width (mm):") and "height_um" not in vals:
            h, w = s.split(":", 1)[1].split("x")
            vals["height_um"], vals["width_um"] = num(h) * 1e3, num(w) * 1e3
        m = re.search(r"Area efficiency \(Memory cell area/Total area\) - ([0-9.eE+-]+) %", s)
        if m and "area_eff_pct" not in vals:
            vals["area_eff_pct"] = float(m.group(1))
    return vals


def error_lines(rd, n=30):
    lines = []
    for name in ("cacti.err", "cacti.out"):
        p = rd / name
        if p.exists():
            lines += [l.rstrip() for l in p.read_text(errors="replace").splitlines() if ERROR_RE.search(l)]
    return lines[:n]


def row(d, w, objective=OBJECTIVE, ecc=False, tag=""):
    rd, cached = run_point(d, w, objective, ecc, tag)
    wc = cacti_width(w)
    r = {"depth": d, "width": w, "width_cacti": wc, "bits": d * w, "objective": objective, "ecc": int(ecc),
         "cacti_commit": json.loads((rd / "key.json").read_text())["cacti_commit"], "run": rd.name}
    rc = (rd / "rc").read_text().strip()
    vals = parse(rd)
    need = ("t_access_ns", "e_rd_raw_pj", "e_wr_raw_pj", "data_area_um2", "height_um")
    if rc != "0" or not all(k in vals for k in need):
        errs = error_lines(rd)
        r["status"] = f"failed: rc {rc}: " + (errs[0] if errs else "no results in cacti.out")
        return r, cached, errs
    r.update(vals)
    r["area_um2"] = vals["height_um"] * vals["width_um"]
    r["e_rd_pj"] = vals["e_rd_raw_pj"] * E_SCALE
    r["e_wr_pj"] = vals["e_wr_raw_pj"] * E_SCALE
    r["e_rd_bit_fj"] = r["e_rd_pj"] * 1e3 / wc
    r["e_wr_bit_fj"] = r["e_wr_pj"] * 1e3 / wc
    r["status"] = "ok" if wc == w else f"ok (width padded to {wc})"
    return {k: sig(v) for k, v in r.items()}, cached, []


def vdd_check():
    """Run 512 x 64 once with CACTI's debug print of the tech tables; every itrs-hp block (flavor 0) must be at
    VDD_CACTI. The data peripherals and the SRAM cell load flavor 0; flavor 1 (lstp, 1.1 V) is the sleep
    transistor (power gating off) and flavor 3 (lp-dram, 1.1 V) the DRAM wordline device."""
    rd = RUNS / "vdd_check"
    rd.mkdir(parents=True, exist_ok=True)
    cfg = make_config(512, 64) + '-print option - "debug detail"\n'
    key = {"cfg": cfg, "cacti_commit": cacti_commit()}
    if not ((rd / "key.json").exists() and json.loads((rd / "key.json").read_text()) == key):
        link = rd / "tech_params"
        if not link.exists():
            link.symlink_to(CACTI_DIR / "tech_params")
        (rd / "cacti.cfg").write_text(cfg)
        with open(rd / "cacti.out", "w") as out:
            subprocess.run([str(CACTI_BIN), "-infile", "cacti.cfg"], cwd=rd, stdout=out, stderr=subprocess.STDOUT,
                           timeout=TIMEOUT_S)
        (rd / "key.json").write_text(json.dumps(key))
    v0 = [float(m) for m in re.findall(r"^-Vdd\[0\]: ([0-9.eE+-]+) \(V\)", (rd / "cacti.out").read_text(), re.M)]
    if not v0 or any(abs(v - VDD_CACTI) > 1e-9 for v in v0):
        sys.exit(f"vdd check: CACTI's itrs-hp Vdd lines are {sorted(set(v0))}, not {VDD_CACTI}: stop ({rd})")
    return len(v0)


def run_table(j, csv_path):
    """Run (or reuse) every point of the lookup table and write it, one row per point CACTI models."""
    n = vdd_check()
    print(f"vdd check: {n} itrs-hp (-Vdd[0]) lines, all {VDD_CACTI} V; energies scaled by {E_SCALE:.4f}")
    jobs = [(d, w) for d in TABLE_DEPTHS for w in TABLE_WIDTHS]
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=j) as ex:
        results = list(ex.map(lambda a: row(*a), jobs))
    ran = sum(not c for _, c, _ in results)
    ok = [r for r, _, _ in results if r["status"] == "ok"]
    print(f"{len(results)} points ({ran} run, {len(results) - ran} cached) in {time.time() - t0:.0f} s; {len(ok)} ok")
    for r, _, errs in results:
        if r["status"] != "ok":
            print(f"  left out {r['run']}: {r['status']}")
    for r in ok:
        if r["cacti_commit"] != ok[0]["cacti_commit"] or r["objective"] != OBJECTIVE or r["ecc"]:
            sys.exit(f"{r['run']}: not run with this script's CACTI commit, objective and ECC off: stop")
    csv_path = Path(csv_path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with open(csv_path, "w", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=TABLE_COLUMNS, extrasaction="ignore", lineterminator="\n")
        wr.writeheader()
        for r in ok:
            wr.writerow(r)
    print(f"wrote {csv_path} ({len(ok)} rows, CACTI {ok[0]['cacti_commit']}, objective {OBJECTIVE}, "
          f"energies x {E_SCALE:.4f})")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("point", help="run one (depth, width) and print the parsed numbers")
    p.add_argument("depth", type=int)
    p.add_argument("width", type=int)
    p.add_argument("--objective", default=OBJECTIVE)
    p.add_argument("--ecc", action="store_true")
    p.add_argument("--tag", default="")
    a = sub.add_parser("table", help="the lookup table: every point of the dense grid, then the CSV")
    a.add_argument("-j", type=int, default=os.cpu_count())
    a.add_argument("--csv", default=str(TABLE_OUT))
    args = ap.parse_args()
    if not CACTI_BIN.exists():
        sys.exit(f"{CACTI_BIN} not found: pixi run ram-build")
    if args.cmd == "point":
        r, cached, errs = row(args.depth, args.width, args.objective, args.ecc, args.tag)
        print(f"{RUNS / r['run']}{' (cached)' if cached else ''}")
        for k in COLUMNS:
            if k in r:
                print(f"  {k}: {r[k]}")
        for e in errs:
            print("  " + e)
    else:
        run_table(args.j, args.csv)


if __name__ == "__main__":
    main()
