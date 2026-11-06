"""RAM1: SRAM bank area and energy from CACTI 7 at 45 nm (itrs-hp), one point per (depth, width).

    pixi run ram-build                       # clone and build CACTI into ram/cacti/ (once)
    pixi run ram point 512 64                # one point: config, run, parse, print
    pixi run ram point 512 64 --objective 0:0:0:100:0
    pixi run ram table -j 32                 # the lookup table -> results/ram/nangate45/ram_table.csv
    pixi run ram lib 512 64 --mask 8         # one SRAM macro (.lib, .db, .v) -> ram/runs/lib/sram_d512_w64_m8.zip
    pixi run ram libs ram/macros.json -j 4   # the macros in a list

Each point runs in a temporary folder under tmp/ with tech_params/ linked in: CACTI opens
"tech_params/45nm.dat" relative to its working directory. What is kept of it, key.json, rc,
cacti.out and cacti.err, goes into one zip, ram/runs/cacti.zip, as d<d>_w<w>[_<variant>]/... (X51;
the vdd check as vdd_check/...); the main thread rewrites the zip once at the end of a command when
points were added or changed. A point whose config (and CACTI commit) is unchanged in the zip is not
rerun. Dynamic energies are scaled from CACTI's itrs-hp Vdd (1.0 V at 45 nm) to Nangate 45 nm's
1.10 V by (1.1 / 1.0)^2; area and timing are not scaled.
"""

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "arc"))
import arc  # noqa: E402  arc/arc.py: outputs zipped (X51)

CACTI_DIR = REPO / "ram" / "cacti"
CACTI_BIN = CACTI_DIR / "cacti"
RUNS = REPO / "ram" / "runs" / "cacti"          # the folders before X51 (pixi run arc migrate packs them)
CACTI_ZIP = REPO / "ram" / "runs" / "cacti.zip"
CACTI_KEEP = ("key.json", "rc", "cacti.out", "cacti.err")   # per point; the rest of its run folder is scratch
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


class Cache:
    """ram/runs/cacti.zip in memory, {point: {file: bytes}}: loaded once, new or changed points added by the workers,
    written back whole by the main thread (save) when something changed."""

    def __init__(self, path):
        self.path, self.points, self.changed = path, None, False
        self.lock = threading.Lock()

    def _load(self):
        with self.lock:
            if self.points is None:
                self.points = {}
                for m, b in arc.read_all(self.path).items():
                    pt, f = m.split("/", 1)
                    self.points.setdefault(pt, {})[f] = b

    def get(self, name):
        self._load()
        return self.points.get(name)

    def put(self, name, files):
        self._load()
        with self.lock:
            self.points[name] = dict(files)
            self.changed = True

    def save(self):
        """Rewrite the zip (not appended), test-read, when points were added or changed; returns the point count."""
        if self.points is None or not self.changed:
            return 0
        with self.lock:
            arc.write(self.path, {f"{pt}/{f}": b for pt, fs in self.points.items() for f, b in fs.items()})
            self.changed = False
            return len(self.points)


CACHE = Cache(CACTI_ZIP)


def point_name(d, w, tag=""):
    return f"d{d}_w{w}" + (f"_{tag}" if tag else "")


def run_cacti(name, cfg, key, split_err=True):
    """CACTI on one config in a temporary folder under tmp/ (tech_params linked in, PITFALLS C1); returns the files
    kept (CACTI_KEEP). The folder is deleted, the files go into CACHE."""
    with arc.workdir(f"cacti_{name}") as rd:
        for link in ("tech_params", "contention.dat"):
            (rd / link).symlink_to(CACTI_DIR / link)
        (rd / "cacti.cfg").write_text(cfg)
        try:
            with open(rd / "cacti.out", "w") as out, open(rd / "cacti.err", "w") as err:
                rc = subprocess.run([str(CACTI_BIN), "-infile", "cacti.cfg"], cwd=rd, stdout=out,
                                    stderr=err if split_err else subprocess.STDOUT, timeout=TIMEOUT_S).returncode
        except subprocess.TimeoutExpired:
            rc = "timeout"
        files = {"key.json": json.dumps(key).encode(), "cacti.out": (rd / "cacti.out").read_bytes()}
        if split_err:
            files.update({"rc": f"{rc}\n".encode(), "cacti.err": (rd / "cacti.err").read_bytes()})
    CACHE.put(name, files)
    return files


def run_point(d, w, objective=OBJECTIVE, ecc=False, tag=""):
    """Run CACTI on the point unless cacti.zip already holds this config; returns (name, files, cached)."""
    name = point_name(d, w, tag)
    cfg = make_config(d, w, objective, ecc)
    key = {"cfg": cfg, "cacti_commit": cacti_commit()}
    got = CACHE.get(name)
    if got and "rc" in got and "key.json" in got and json.loads(got["key.json"]) == key:
        return name, got, True
    return name, run_cacti(name, cfg, key), False


def migrate_cacti(inventory=None):
    """The run folders of ram/runs/cacti/ into cacti.zip (CACTI_KEEP), folders deleted after the zip's test read;
    a folder without key.json is kept; inventory(kind, folder, files, inodes, zip) per point. Returns (points,
    [(folder, why)])."""
    if not RUNS.is_dir():
        return 0, []
    done, failed = [], []
    for rd in sorted(p for p in RUNS.iterdir() if p.is_dir() and not p.is_symlink()):
        if not (rd / "key.json").is_file():
            failed.append((str(rd.relative_to(REPO)), "no key.json"))
            continue
        CACHE.put(rd.name, {f: (rd / f).read_bytes() for f in CACTI_KEEP if (rd / f).is_file()})
        done.append(rd)
    CACHE.save()
    for rd in done:
        if inventory:
            inventory("ram/runs/cacti", str(rd.relative_to(REPO)), sum(1 for _ in rd.iterdir()),
                      arc.inodes(rd), CACTI_ZIP, len(CACHE.get(rd.name)))
        shutil.rmtree(rd)
    if not any(RUNS.iterdir()):
        RUNS.rmdir()
    return len(done), failed


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


def parse(files):
    """CACTI's output, by label. The first occurrence of each label is the summary block's."""
    out = files["cacti.out"].decode(errors="replace")
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


def error_lines(files, n=30):
    lines = []
    for name in ("cacti.err", "cacti.out"):
        if name in files:
            lines += [l.rstrip() for l in files[name].decode(errors="replace").splitlines() if ERROR_RE.search(l)]
    return lines[:n]


def row(d, w, objective=OBJECTIVE, ecc=False, tag=""):
    name, files, cached = run_point(d, w, objective, ecc, tag)
    wc = cacti_width(w)
    r = {"depth": d, "width": w, "width_cacti": wc, "bits": d * w, "objective": objective, "ecc": int(ecc),
         "cacti_commit": json.loads(files["key.json"])["cacti_commit"], "run": name}
    rc = files["rc"].decode().strip()
    vals = parse(files)
    need = ("t_access_ns", "e_rd_raw_pj", "e_wr_raw_pj", "data_area_um2", "height_um")
    if rc != "0" or not all(k in vals for k in need):
        errs = error_lines(files)
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
    cfg = make_config(512, 64) + '-print option - "debug detail"\n'
    key = {"cfg": cfg, "cacti_commit": cacti_commit()}
    files = CACHE.get("vdd_check")
    if not (files and "key.json" in files and json.loads(files["key.json"]) == key):
        files = run_cacti("vdd_check", cfg, key, split_err=False)
    v0 = [float(m) for m in re.findall(r"^-Vdd\[0\]: ([0-9.eE+-]+) \(V\)", files["cacti.out"].decode(), re.M)]
    if not v0 or any(abs(v - VDD_CACTI) > 1e-9 for v in v0):
        sys.exit(f"vdd check: CACTI's itrs-hp Vdd lines are {sorted(set(v0))}, not {VDD_CACTI}: stop "
                 f"({CACTI_ZIP.relative_to(REPO)}, vdd_check/)")
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


# ---------------------------------------------------------------------------------------------------------------
# Macros (R3): a Liberty model (.lib -> .db) and a behavioural Verilog model per (depth, width[, mask]), from the
# cached CACTI point and Nangate 45 nm's units and pin values (ram/nangate45_pins.json). Never committed.

GEN_VERSION = 1
PINS = REPO / "ram" / "nangate45_pins.json"
LIB_RUNS = REPO / "ram" / "runs" / "lib"
LC_SHELL = os.environ.get("LC_SHELL", "/esat/micas-data/software/Synopsys/lc/Y-2026.03-SP2/bin/lc_shell")
LMUTIL = os.environ.get("LMUTIL", "/esat/micas-data/software/Mentor/questasim_2022.4/linux_x86_64/lmutil")
SNPS_LICENSE = "1709@licserv"
LC_TIMEOUT_S = 600
LC_MSG_RE = re.compile(r"^(Error|Warning|Information)\b.*", re.M)


def macro_name(d, w, mask=None):
    return f"sram_d{d}_w{w}" + (f"_m{mask}" if mask else "")


def addr_bits(d):
    return max(1, (d - 1).bit_length())   # $clog2(depth), at least 1 as tc_sram


def pins_values():
    raw = PINS.read_bytes()
    p = json.loads(raw)
    v = lambda *ks: _dig(p, ks)["value"]
    return {
        "md5": hashlib.md5(raw).hexdigest(),
        "units": {k: v("units", k) for k in p["units"]},
        "nom": {k: v(k) for k in ("nom_process", "nom_voltage", "nom_temperature")},
        "oc": {k: v("operating_conditions", k) for k in ("name", "process", "voltage", "temperature", "tree_type")},
        "thresholds": {k: v("thresholds", k) for k in p["thresholds"]},
        "defaults": {k: v("defaults", k) for k in p["defaults"]},
        "ipu": v("internal_power_unit"),
        "cap_ck": v("DFF_X1", "CK", "capacitance"),
        "cap_d": v("DFF_X1", "D", "capacitance"),
        "setup": {e: v("DFF_X1", "setup_rising_D_CK", f"{e}_constraint") for e in ("rise", "fall")},
        "hold": {e: v("DFF_X1", "hold_rising_D_CK", f"{e}_constraint") for e in ("rise", "fall")},
        "max_cap": v("BUF_X4", "Z", "max_capacitance"),
        "tr": {e: v("BUF_X4", "Z", f"{e}_transition") for e in ("rise", "fall")},
    }


def _dig(d, ks):
    for k in ks:
        d = d[k]
    return d


def unit_scale(s, base):
    """'1nW' -> factor of base (W, J): 1e-9."""
    m = re.fullmatch(r"([0-9.]+)\s*([munpf]?)" + base, s.strip())
    if not m:
        raise ValueError(f"unit {s!r} is not a multiple of {base}")
    return float(m.group(1)) * {"": 1, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15}[m.group(2)]


def lib_values(r, pv):
    """The numbers the .lib holds, in the library's units, from a CACTI row (pJ, uW, ns, um2)."""
    e_unit = unit_scale(pv["ipu"], "J")
    leak_unit = unit_scale(pv["units"]["leakage_power_unit"], "W")
    if pv["units"]["time_unit"] != "1ns":
        raise ValueError("the generator writes times in ns: the library's time unit must be 1ns")
    return {"area": r["area_um2"], "e_rd": r["e_rd_pj"] * 1e-12 / e_unit, "e_wr": r["e_wr_pj"] * 1e-12 / e_unit,
            "leak": r["leak_uw"] * 1e-6 / leak_unit, "t_access": r["t_access_ns"], "t_cycle": r["t_cycle_ns"]}


def f6(x):
    return f"{x:.6g}"


def scalar(kind, x):
    return f'{kind} (scalar) {{ values ("{f6(x)}"); }}'


def gen_lib(name, d, w, mask, r, pv):
    lv = lib_values(r, pv)
    a = addr_bits(d)
    u, nom, oc, th = pv["units"], pv["nom"], pv["oc"], pv["thresholds"]
    buses = [("addr_i", a), ("data", w)] + ([("be_i", w // mask)] if mask else [])
    L = []
    o = L.append
    o("/*")
    o(f" * {name}: {d} words x {w} bits, one read-write port" + (f", byte enables every {mask} bits" if mask else "")
      + ", read data one cycle after the read (rising edge), as tc_sram at NumPorts 1, Latency 1.")
    o(f" * Generated by snax-forge-experiments ram/ram.py (lib, generator version {GEN_VERSION}); never committed.")
    o(f" * Numbers: CACTI 7 commit {r['cacti_commit']}, 45 nm itrs-hp, objective {r['objective']}, ECC off, point "
      f"{r['run']} of ram/runs/cacti.zip ({d} x {r['width_cacti']}" + (", ports keep the real width " + str(w) if w != r["width_cacti"] else "") + ").")
    o(f" * Energies are CACTI's at 1.0 V scaled to 1.1 V by {E_SCALE:.4f} (as results/ram/nangate45/ram_table.csv, X48):")
    o(f" *   read {r['e_rd_pj']} pJ, write {r['e_wr_pj']} pJ per access, written below in the library's internal-power "
      f"unit ({pv['ipu']}).")
    o(" * Energy is charged once per access, on clk_i's rising edge, when req_i is high; nothing when req_i is low.")
    if mask:
        o(" * A byte-masked write is charged as a full write: CACTI gives one write energy per access.")
    o(f" * Area {r['area_um2']} um2 (CACTI height x width), access {r['t_access_ns']} ns, cycle {r['t_cycle_ns']} ns, "
      f"leakage {r['leak_uw']} uW (not used by the cost model).")
    o(f" * Units, nom_* and operating conditions are Nangate 45 nm's, pin capacitances and setup/hold DFF_X1's, the "
      f"read data's drive BUF_X4's (ram/nangate45_pins.json, md5 {pv['md5']}).")
    o(" */")
    o(f"library ({name}) {{")
    o("  technology (cmos);")
    o("  delay_model : table_lookup;")
    for k in ("time_unit", "voltage_unit", "current_unit", "leakage_power_unit", "pulling_resistance_unit"):
        o(f'  {k} : "{u[k]}";')
    o(f"  capacitive_load_unit ({u['capacitive_load_unit']});")
    for k in ("nom_process", "nom_temperature", "nom_voltage"):
        o(f"  {k} : {nom[k]:.2f};")
    o(f"  operating_conditions ({oc['name']}) {{")
    for k in ("process", "voltage", "temperature"):
        o(f"    {k} : {oc[k]:.2f};")
    o(f"    tree_type : {oc['tree_type']};")
    o("  }")
    o(f"  default_operating_conditions : {oc['name']};")
    for k, x in th.items():
        o(f"  {k} : {x:.2f};")
    for k, x in pv["defaults"].items():   # Nangate's; without them lc_shell warns LBDB-172 and uses the same values
        o(f"  {k} : {f6(x)};")
    # The clk_i energy is the macro's own; rdata_o's load is switching power that DC and PT add (LBDB-366 without)
    o("  char_config () {")
    o("    internal_power_calculation : exclude_switching_on_rise_and_fall;")
    o("  }")
    for b, n in buses:
        o(f"  type (bus{n}) {{ base_type : array; data_type : bit; bit_width : {n}; bit_from : {n - 1}; bit_to : 0; "
          f"downto : true; }}")
    o(f"  cell ({name}) {{")
    o(f"    area : {f6(lv['area'])};")
    o("    dont_use : true;")
    o("    dont_touch : true;")
    o(f"    cell_leakage_power : {f6(lv['leak'])};")
    o("    pin (clk_i) {")
    o("      direction : input;")
    o("      clock : true;")
    o(f"      capacitance : {f6(pv['cap_ck'])};")
    o(f"      min_period : {f6(lv['t_cycle'])};")
    o(f"      min_pulse_width_high : {f6(lv['t_cycle'] / 2)};")
    o(f"      min_pulse_width_low : {f6(lv['t_cycle'] / 2)};")
    for when, e in (("req_i & !we_i", lv["e_rd"]), ("req_i & we_i", lv["e_wr"]), ("!req_i", 0.0)):
        o("      internal_power () {")
        o(f'        when : "{when}";')
        o(f"        {scalar('rise_power', e)}")
        o(f"        {scalar('fall_power', 0.0)}")
        o("      }")
    o("    }")

    def constraints(ind):
        for tt, val in (("setup_rising", pv["setup"]), ("hold_rising", pv["hold"])):
            o(f"{ind}timing () {{")
            o(f'{ind}  related_pin : "clk_i";')
            o(f"{ind}  timing_type : {tt};")
            o(f"{ind}  {scalar('rise_constraint', val['rise'])}")
            o(f"{ind}  {scalar('fall_constraint', val['fall'])}")
            o(f"{ind}}}")

    for p in ("req_i", "we_i"):
        o(f"    pin ({p}) {{")
        o("      direction : input;")
        o(f"      capacitance : {f6(pv['cap_d'])};")
        constraints("      ")
        o("    }")
    for p, n in [("addr_i", a), ("wdata_i", w)] + ([("be_i", w // mask)] if mask else []):
        o(f"    bus ({p}) {{")
        o(f"      bus_type : bus{n};")
        o("      direction : input;")
        o(f"      capacitance : {f6(pv['cap_d'])};")
        constraints("      ")
        o("    }")
    o("    bus (rdata_o) {")
    o(f"      bus_type : bus{w};")
    o("      direction : output;")
    o(f"      max_capacitance : {f6(pv['max_cap'])};")
    o("      timing () {")
    o('        related_pin : "clk_i";')
    o("        timing_type : rising_edge;")
    o("        timing_sense : non_unate;")
    o(f"        {scalar('cell_rise', lv['t_access'])}")
    o(f"        {scalar('cell_fall', lv['t_access'])}")
    o(f"        {scalar('rise_transition', pv['tr']['rise'])}")
    o(f"        {scalar('fall_transition', pv['tr']['fall'])}")
    o("      }")
    o("    }")
    o("  }")
    o("}")
    # bus types: one per distinct width (addr and data may share none, be may equal addr's width)
    seen, out = set(), []
    for line in L:
        m = re.match(r"  type \((bus\d+)\)", line)
        if m:
            if m.group(1) in seen:
                continue
            seen.add(m.group(1))
        out.append(line)
    return "\n".join(out) + "\n"


def gen_v(name, d, w, mask):
    a = addr_bits(d)
    nb = w // mask if mask else 0
    be_port = f"\n  input  logic [{nb - 1}:0] be_i," if mask else ""
    if mask:
        write = (f"        for (int b = 0; b < {nb}; b++)\n"
                 f"          if (be_i[b]) mem[addr_i][b*{mask} +: {mask}] <= wdata_i[b*{mask} +: {mask}];")
    else:
        write = "        mem[addr_i] <= wdata_i;"
    return f"""// {name}: behavioural model of the generated macro ({d} x {w}{f', byte enables every {mask} bits' if mask else ''}).
// Generated by snax-forge-experiments ram/ram.py (lib, generator version {GEN_VERSION}); never committed.
// Behaves as tech_cells_generic's tc_sram at NumPorts 1, Latency 1 (v0.2.14): rdata_o is loaded on every rising
// edge, with mem[addr_i] on a read and with mem[last read address] (its value before the edge) otherwise, so it
// holds the last read word and follows a write to that word one cycle later. No reset: tc_sram resets only the
// read address, and with X contents that shows the same X until the first read. Contents start X, or zero (and
// the read address zero, as tc_sram after reset with SimInit "zeros") with +define+SRAM_INIT_ZERO.
`timescale 1ns/1ps
module {name} (
  input  logic clk_i,
  input  logic req_i,
  input  logic we_i,
  input  logic [{a - 1}:0] addr_i,
  input  logic [{w - 1}:0] wdata_i,{be_port}
  output logic [{w - 1}:0] rdata_o
);
`ifdef SRAM_INIT_ZERO
  logic [{w - 1}:0] mem [0:{d - 1}] = '{{default: '0}};
  logic [{a - 1}:0] r_addr_q = '0;
  logic [{w - 1}:0] rdata_q = '0;
`else
  logic [{w - 1}:0] mem [0:{d - 1}];
  logic [{a - 1}:0] r_addr_q;
  logic [{w - 1}:0] rdata_q;
`endif
  assign rdata_o = rdata_q;

  always_ff @(posedge clk_i) begin
    rdata_q <= (req_i && !we_i) ? mem[addr_i] : mem[r_addr_q];
    if (req_i) begin
      if (we_i) begin
{write}
      end else begin
        r_addr_q <= addr_i;
      end
    end
  end

`ifndef SYNTHESIS
  // Access counts, sampled at the rising edge as the .lib charges energy: reads req_i & !we_i, writes req_i & we_i
  // (a byte-masked write is a write).
  bit [63:0] n_rd = 0, n_wr = 0;
  always @(posedge clk_i) begin
    if (req_i === 1'b1 && we_i === 1'b0) n_rd <= n_rd + 1;
    if (req_i === 1'b1 && we_i === 1'b1) n_wr <= n_wr + 1;
  end
  final $display("RAMCOUNT %m {name} reads %0d writes %0d", n_rd, n_wr);
`endif
endmodule
"""


def lc_free():
    """Free Library-Compiler licences on the Synopsys server, or None if lmutil cannot tell."""
    try:
        out = subprocess.run([LMUTIL, "lmstat", "-c", SNPS_LICENSE, "-f", "Library-Compiler"], capture_output=True,
                             text=True, timeout=60).stdout
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = re.search(r"Users of Library-Compiler:.*Total of (\d+) licenses? issued;\s*Total of (\d+) licenses? in use", out)
    return int(m.group(1)) - int(m.group(2)) if m else None


def macro_keep(name):
    """What ram/runs/lib/<name>.zip keeps (X51): the .lib, .db and .v, lc_shell's log, key.json and result.json (the
    cache check reads both); lc.tcl and lc_shell's command log and output are scratch."""
    return (f"{name}.lib", f"{name}.db", f"{name}.v", "lc.log", "key.json", "result.json")


def macro_zip(name):
    return LIB_RUNS / f"{name}.zip"


def pack_macro(od):
    """A macro's folder to ram/runs/lib/<name>.zip (macro_keep), test-read; then the folder goes."""
    z = macro_zip(od.name)
    arc.pack(od, z, macro_keep(od.name))
    shutil.rmtree(od)
    return z


def make_macro(d, w, mask=None):
    """Write the .lib and .v, compile the .db with lc_shell in a folder under tmp/, keep them in
    ram/runs/lib/<name>.zip; reuse the zip if its key is unchanged."""
    if mask and w % mask:
        raise ValueError(f"width {w} is not a multiple of the mask {mask}")
    name = macro_name(d, w, mask)
    z = macro_zip(name)
    r, _, errs = row(d, cacti_width(w))
    if not r["status"].startswith("ok"):
        return {"name": name, "status": r["status"], "errors": errs}
    pv = pins_values()
    lib_text, v_text = gen_lib(name, d, w, mask, r, pv), gen_v(name, d, w, mask)
    md5 = lambda t: hashlib.md5(t.encode()).hexdigest()
    key = {"row": r, "pins_md5": pv["md5"], "generator": GEN_VERSION, "width": w, "mask": mask, "lc_shell": LC_SHELL,
           "lib_md5": md5(lib_text), "v_md5": md5(v_text)}   # the texts too: a generator edit regenerates
    if arc.has(z, "key.json") and arc.has(z, "result.json") and json.loads(arc.read(z, "key.json")) == key:
        res = json.loads(arc.read(z, "result.json"))
        if res["status"] == "ok":
            return {**res, "cached": True}
    with arc.workdir(name) as od:
        res = _build_macro(od, name, d, w, mask, r, pv, key, lib_text, v_text)
        arc.pack(od, z, macro_keep(name))
    return {**res, "cached": False}


def _build_macro(od, name, d, w, mask, r, pv, key, lib_text, v_text):
    (od / f"{name}.lib").write_text(lib_text)
    (od / f"{name}.v").write_text(v_text)
    (od / "lc.tcl").write_text(f"read_lib {name}.lib\nwrite_lib {name} -format db -output {name}.db\nexit\n")
    t0 = time.time()
    try:
        with open(od / "lc.log", "w") as log:
            rc = subprocess.run([LC_SHELL, "-f", "lc.tcl"], cwd=od, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, timeout=LC_TIMEOUT_S).returncode
    except subprocess.TimeoutExpired:
        rc = "timeout"
    except OSError as e:
        rc = f"cannot run {LC_SHELL}: {e}"
    text = (od / "lc.log").read_text(errors="replace")
    msgs = [m.group(0).strip() for m in LC_MSG_RE.finditer(text)]
    errors = [m for m in msgs if m.startswith("Error")]
    status = "ok"
    if rc != 0 or errors or not (od / f"{name}.db").exists():
        status = f"failed: lc_shell rc {rc}" + (f": {errors[0]}" if errors else "") + \
                 ("" if (od / f"{name}.db").exists() else "; no .db")
    lv = lib_values(r, pv)
    res = {"name": name, "status": status, "depth": d, "width": w, "mask": mask, "width_cacti": r["width_cacti"],
           "area_um2": r["area_um2"], "e_rd_pj": r["e_rd_pj"], "e_wr_pj": r["e_wr_pj"],
           "t_access_ns": r["t_access_ns"], "t_cycle_ns": r["t_cycle_ns"], "leak_uw": r["leak_uw"],
           "lib_values": {k: float(f6(x)) for k, x in lv.items()}, "lc_s": round(time.time() - t0, 1),
           "warnings": [m for m in msgs if m.startswith("Warning")],
           "information": [m for m in msgs if m.startswith("Information")], "errors": errors[:30]}
    (od / "result.json").write_text(json.dumps(res, indent=2) + "\n")
    (od / "key.json").write_text(json.dumps(key, indent=2) + "\n")
    return res


def print_macro(res):
    print(f"{macro_zip(res['name'])}{' (cached)' if res.get('cached') else ''}: {res['status']}")
    if "area_um2" in res:
        print(f"  {res['depth']} x {res['width']}" + (f" (CACTI {res['width_cacti']})" if res['width_cacti'] != res['width'] else "")
              + (f", mask {res['mask']}" if res['mask'] else "") +
              f": area {res['area_um2']} um2, read {res['e_rd_pj']} pJ, write {res['e_wr_pj']} pJ, "
              f"access {res['t_access_ns']} ns, cycle {res['t_cycle_ns']} ns, leakage {res['leak_uw']} uW"
              f"{'' if res.get('cached') else ', lc_shell ' + str(res['lc_s']) + ' s'}")
    for k in ("errors", "warnings", "information"):
        for m in res.get(k, []):
            print(f"  {m}")


def make_macros(spec, j):
    macros = json.loads(Path(spec).read_text())["macros"]
    free = lc_free()
    jj = max(1, min(j, len(macros), free if free is not None else j))
    print(f"{len(macros)} macros, {jj} at a time (asked {j}, Library-Compiler free: "
          f"{free if free is not None else 'unknown'})")
    with ThreadPoolExecutor(max_workers=jj) as ex:
        results = list(ex.map(lambda m: make_macro(m["depth"], m["width"], m.get("mask")), macros))
    for res in results:
        print_macro(res)
    bad = [r["name"] for r in results if r["status"] != "ok"]
    if bad:
        sys.exit(f"failed: {', '.join(bad)}")



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
    m = sub.add_parser("lib", help="one SRAM macro: .lib, .db (lc_shell) and .v in ram/runs/lib/<name>.zip")
    m.add_argument("depth", type=int)
    m.add_argument("width", type=int)
    m.add_argument("--mask", type=int, default=None, help="byte-enable granularity in bits (be_i[width/mask-1:0])")
    ms = sub.add_parser("libs", help="the macros listed in a JSON file (ram/macros.json)")
    ms.add_argument("spec")
    ms.add_argument("-j", type=int, default=4)
    args = ap.parse_args()
    if not CACTI_BIN.exists():
        sys.exit(f"{CACTI_BIN} not found: pixi run ram-build")
    try:
        run_cmd(args)
    finally:                    # the main thread writes cacti.zip once, also when a command stops (X51)
        n = CACHE.save()
        if n:
            print(f"wrote {CACTI_ZIP.relative_to(REPO)} ({n} points)")


def run_cmd(args):
    if args.cmd == "point":
        r, cached, errs = row(args.depth, args.width, args.objective, args.ecc, args.tag)
        print(f"{CACTI_ZIP}: {r['run']}/{' (cached)' if cached else ''}")
        for k in COLUMNS:
            if k in r:
                print(f"  {k}: {r[k]}")
        for e in errs:
            print("  " + e)
    elif args.cmd == "lib":
        res = make_macro(args.depth, args.width, args.mask)
        print_macro(res)
        if res["status"] != "ok":
            sys.exit(1)
    elif args.cmd == "libs":
        make_macros(args.spec, args.j)
    else:
        run_table(args.j, args.csv)


if __name__ == "__main__":
    main()
