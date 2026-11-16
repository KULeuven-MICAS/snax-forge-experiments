# forge

snax-forge's accelerators as points of this repository, named as hls-exercises names its points (`<tier>/<kernel>/<case>_w<W>`, e.g. `done/dot/forge3_w4`), so a forge row joins the HLS rows of the same kernel and W. `points.json` lists them: recipe, W, the point's own `sets` and `dtypes`. The commands are in [`docs/TOOL.md`](../docs/TOOL.md#2-make-the-rtl-of-a-source); synthesis and power in [`syn/README.md`](../syn/README.md#the-forge-source) and [`docs/power.md`](../docs/power.md) (X21, X22, X23 · X58, X57).

## The bundles (`bundles.py`, `pixi run forge-rtl`)

Per point, in the snax-forge checkout (SNAX_FORGE, default ../snax-forge from the repo root), each through `pixi run --manifest-path $SNAX_FORGE/pixi.toml`:

1. sandbox recipes/<folder>/<r>.json --set W=<w> [--set K=V ...] --out out/sandbox/syn1/<r>_w<w>[_<K><V>...]
2. design <the last .snaxdfg of that folder> --platform platforms/snax_forge.json --out out/design/syn1/<r>_w<w>[_<K><V>...]
3. bundle out/design/syn1/<...>/design_point.json --out <DIR>/<point>/

DIR is rtl/forge/ in this repo (git ignores rtl/: a bundle is rebuilt from its commit). A point's folder is emptied first. bundle.json names the commit and whether snax-forge's work tree was dirty; a dirty bundle is refused (its folder emptied but for the log) unless --allow-dirty. A bundle that is kept gets point.json: point, recipe, W, snax_forge_commit, dirty, date. Each point's task output is in forge-rtl.log. When the point is done, its folder is packed into <DIR>/<point>.zip, test-read and deleted: syn/syn.py and sim/pwr.py read the zip, a failed or refused point's zip holds the log only.

The tasks run inside this repo's `pixi run`, whose PIXI_* and CONDA_* variables and .pixi/ PATH entries would make the inner pixi take this repo's environment; they are removed, and before any point the driver checks that the inner CONDA_PREFIX is under $SNAX_FORGE/.pixi/envs/.

The first point runs alone when hw/chisel's Emit classpath (hw/chisel/target/emit-classpath.txt) is not there yet: the first Emit exports it through sbt, and parallel first calls would race. A point's own `sets` (points.json, e.g. ["M=16", "N=128"]) and then the global --set values (e.g. --set N=2048) go to the sandbox step after W, and tag the sandbox and design folder names in that order; point.json records them as `sets`.

A recipe is found by its name in any folder under $SNAX_FORGE/recipes/ but recipes/custom/ (the editor's), as snax-forge keeps them by category (recipes/reduce/rowsum_2.json); a name found in no folder or in several is refused (find_recipe, also used by forge/query.py).

A point's `dtypes` (points.json, e.g. {"A": "int64", "B": "int64"}) are the recipe's `dtypes` field (snax-forge's recipe.py, D113): the driver writes the recipe it found with that field set into tmp/forge_recipes/<work name>.json, gives the sandbox that file, and deletes it when the point ends. snax-forge's relu, matadd and axpy kernels are int32, the HLS points int64; the dtypes make forge's points int64 too. The work name ends _<dtype> then, and point.json records `dtypes` and `recipe_file` (the recipe in snax-forge it was made from).

## What the power flow asks snax-forge (`query.py`)

Runs inside snax-forge's pixi environment, with snax-forge as the working directory (sim/sources/forge.py calls it as forge/bundles.py calls snax-forge's tasks: `pixi run --manifest-path $SNAX_FORGE/pixi.toml`, PIXI_* and CONDA_* removed). It prints one JSON object on stdout.

snax-forge is not changed: only its modules are imported.

- **`point BUNDLE_DIR`:** kernel: the recipe's kernel (point.json's recipe, found under recipes/**/ by forge/bundles.py's find_recipe) ports:  per outer port of accelerator.json (inputs, then outputs, in its order) the container the design point's graph binds it to, as snax-forge's gen/rtl.py `vectors` finds it baked:  {container: value} of the recipe's bake_scalar steps with a number (axpy_baked's alpha = 3) dtypes: {container: dtype} of the design point's graph (not transients) and its type parameters (ACC): the dtypes the bundle was made at, after the recipe's `dtypes` and a `--set types=` preset
- **`program BUNDLE_DIR`:** what snax-forge's LOWER writes for the design point's own size (lower/derive.py's task_list, the C backend's job_writes and scalar slots, lower/c.py), for its one accelerator task: symbols   the graph's bound symbols (the size the design point was made at: the point's sets) n         the task's firings; writes [[unit, CSR, value], ...] JOBS then each JOB_BEATS, as job_writes scalars   [{unit, slot, container, dtype, csrs}] each slot read from a scalar container (axpy's k1 from alpha): its R/W CSRs (K1, or K1_LO and K1_HI at 64 bits, low word first, gen/accelerator.py's scalar_csrs), written with the container's value before START streams   per streamer task {end, component, dir, container, shape, beats, lanes, num_ch, num_slc, d_out, dtype, order, identity}: order the container's flat (row-major) element index of each element slot the streamer moves, beat by beat, channel 0 first and in a channel's word its num_slc slices little-endian (lower/derive.py's addresses over the task's bounds and strides in words, design/streamers.py's word_bounds, mapped back through the container's L1 layout), -1 for a packed output's slice past its last result (D174: 0); lanes = num_ch x num_slc slots a beat; identity when it is 0, 1, 2, ...
- **`cycles BUNDLE_DIR JOBS BEATS_JSON`:** the group's busy cycles E - s of one run: gen/rtl.py's `group_counter` (snax-gvsoc's group rule, estimate/cycles.py's `group_cycles`, every input valid and the output ready), with JOBS and each unit's T its JOB_BEATS (BEATS_JSON: {unit: value}) or its fixed T, as the program writes them
- **`ctrl_bits ACCELERATOR_JSON`:** per control unit <tag>_<group>_ctrl of the accelerator.json (a file, or a bundle folder holding one), the registers firtool keeps and their bits, from snax-forge's estimate/bits.py (`accelerator_registers`, as hw/chisel's CtrlRegistersSpec reads them): {module: {"registers": [[name, bits], ...], "bits": n}}
- **`ref KERNEL IN_NPZ OUT_NPZ [SYMBOLS_JSON [DTYPES_JSON]]`:** the kernel's NumPy body (kernels/<...>/<KERNEL>.py, SPEC.func) on the arrays in IN_NPZ (a scalar container, axpy's alpha, as a 0-d array cast to its descriptor's dtype); the kernel's inout arrays not given (its outputs, zero-filled at the size the SPEC's descriptors give for SYMBOLS_JSON, else every symbol = N, the length of the first input) written to OUT_NPZ; an inout array given (axpy's y) is updated in place and written too. DTYPES_JSON ({container: dtype}, the point's) replaces the descriptors' dtypes, as the recipe's dtypes do in the bundle (relu, matadd and axpy are int32 kernels); a name in it that is the kernel's type parameter (`ACC` in axpy's and matadd's `x.astype(ACC)`, snax-forge's PACK1a) rebinds that global (`KernelSpec.with_types`), so an int64 point at `ACC` int32 would wrap in the reference as in the bundle.

## Files

| File | What it is |
|---|---|
| `points.json` | the forge points |
| `bundles.py` | `pixi run forge-rtl`, and `find_recipe` |
| `query.py` | the questions `sim/sources/forge.py` asks snax-forge, run in snax-forge's environment |
| `sv_diff.py` | two bundles' SV compared with the tag and block names masked (PITFALLS E5) |
