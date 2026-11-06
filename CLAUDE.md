# snax-forge-experiments

Synthesis, power, memory and cost flows shared by snax-forge and the HLS comparison, with their results committed. Read `docs/README.md` first (folders, sibling repos, environment), then the decisions (`docs/DECISIONS.md`, X-numbers) and pitfalls (`docs/PITFALLS.md`) the task touches. A choice that contradicts an X-number gets a new X-number, never a silent change.

## Files are zipped, one zip per point (X51)

Ryan's home has a file-count quota (1,600,000 soft, folders count too), shared by every repo, environment and cache on it. Bulky outputs are therefore never left as loose files. Check it with `quota -v` before a large batch.

1. **What is zipped.** Every point's outputs live as one zip: DC runs (`syn/runs/`), power runs (`sim/runs/`), the CACTI cache (`ram/runs/cacti.zip`), the generated macros (`ram/runs/lib/`), the bundles (`rtl/`), and the committed reports (`results/*/<tech>/reports/` and `power_reports/`). CSVs, the RAM lookup table, run notes, docs and code stay plain text.
2. **Reading.** Read a single file straight from the zip (`arc.read`). Unpack (`arc.unpacked`) only for a tool that needs real files on disk (DC reading a bundle, PT reading a netlist, `lc_shell` reading a `.lib`), into a temporary folder that is deleted when the step ends, also when it fails.
3. **Processing.** Unpack what the step needs, process, pack the results into the point's zip (`arc.pack`), check the zip with a test read, then delete everything unpacked. Delete originals only after that check passes.
4. **One point at a time.** A job unpacks one point, finishes it and cleans up before the next; a batch never unpacks everything first. With N parallel jobs, at most N points are unpacked at once.
5. **Scratch is deleted, not zipped.** DC's `WORK/`, `alib-*/`, `.sdf`, `.svf` and the reports not kept; Questa's `work/`, transcripts, logs and generated `tb.sv`; CACTI's per-point run folder.
6. **Deterministic zips.** Entries sorted, fixed timestamps, so a rerun with the same contents gives the same bytes and a committed zip changes only when its contents do.
7. **Nothing left behind.** `pixi run arc check` lists unpacked run folders, stray temporary folders and the file count per top-level folder. It must report nothing left over at the end of every round; say so in the run note. Never commit an unpacked report folder.

`arc/arc.py` holds the helpers (`pack`, `read`, `names`, `unpacked`, `check`); every script imports it rather than calling `zipfile` itself.

## Working rules

- Python through the repo's pixi workspace (`pixi run ...`, Python 3.11; docs X15); scripts in files, not `pixi run python -c` (PITFALLS E1).
- Start a round with `git pull` in this repo and every sibling repo the round reads (`docs/README.md`, Sibling repos).
- A clean never deletes `syn/runs/` or `sim/runs/` (X6); they hold the netlists the power flow reads.
- DC, Questa and PT parallelism from free licences (`lmutil lmstat`, PITFALLS L2, L3); CACTI and Python steps with `-j$(nproc)`.
- Report after every step what changed and what was found. A failure stays as a row with its status and at most 30 error lines from its log.
- A round ends with a run note (`results/<source>/runs/<date>_<task>_<round>.md`), new X-numbers and PITFALLS entries where the round found them.
- Commits: one short line, no Co-Authored-By trailer. Push to the task's branch (`ry/<task>`); Ryan opens or merges PRs.
- Markdown prose is one line per paragraph, list item and table row, never hard-wrapped.
