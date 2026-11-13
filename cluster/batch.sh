#!/usr/bin/env bash
# cluster/batch.sh POINT... [--from STEP]
#
# Runs the cluster flow on each point in order, in series: cluster rtl, cluster syn --cores 16, cluster gls,
# cluster pwr --cores 16, cluster-hwcost (PWR2). --from starts the first point at STEP (rtl|syn|gls|pwr|hwcost).
# ALLOW_BRANCH=1 adds --allow-branch to the four cluster steps (snax_cluster off origin/main).
#
# Before each point: quota -v against the global stop (QUOTA_MAX_FILES files, QUOTA_MAX_KB 1K blocks), and, when
# tmp/overnight-1/heads.txt lists "<repo dir> <sha>" lines, git fetch in each repo and its origin/main against <sha>.
# Each step's console goes to tmp/overnight-1/<point>_<step>.log; one line per step to tmp/overnight-1/status.txt
# (<iso time> <point> <step> START|PASS|FAIL <seconds>). The first failure writes FAIL and exits non-zero; the end
# writes ALL DONE. Run from the repo's root.
set -u

STEPS=(rtl syn gls pwr hwcost)
OUT=tmp/overnight-1
STATUS=$OUT/status.txt
QUOTA_MAX_FILES=${QUOTA_MAX_FILES:-1550000}
QUOTA_MAX_KB=${QUOTA_MAX_KB:-136718750}          # 140 GB
STEP_TIMEOUT=${STEP_TIMEOUT:-6h}                  # a guard only; the steps have their own timeouts

points=()
from=rtl
while [ $# -gt 0 ]; do
    case "$1" in
        --from) from=${2:?--from needs a step}; shift 2 ;;
        -*) echo "unknown option $1" >&2; exit 2 ;;
        *) points+=("$1"); shift ;;
    esac
done
[ ${#points[@]} -gt 0 ] || { echo "usage: cluster/batch.sh POINT... [--from STEP]" >&2; exit 2; }
case " ${STEPS[*]} " in *" $from "*) ;; *) echo "--from: one of ${STEPS[*]}" >&2; exit 2 ;; esac

mkdir -p "$OUT"
ab=()
[ "${ALLOW_BRANCH:-0}" = 1 ] && ab=(--allow-branch)

line() { echo "$(date -Iseconds) $1 $2 $3 $4" >> "$STATUS"; }

quota_ok() {   # the home quota line: blocks and files of the users/sli file system
    local q blocks files
    q=$(quota -v 2>&1 | awk '/homedirs\/users\/sli/ {if (NF == 1) getline; else $1 = ""; print; exit}')
    blocks=$(echo "$q" | awk '{print $1}' | tr -d '*'); files=$(echo "$q" | awk '{print $4}' | tr -d '*')
    echo "quota: $blocks KB, $files files (stop at $QUOTA_MAX_KB KB, $QUOTA_MAX_FILES files)"
    [ -n "$blocks" ] && [ -n "$files" ] && [ "$blocks" -le "$QUOTA_MAX_KB" ] && [ "$files" -le "$QUOTA_MAX_FILES" ]
}

mains_ok() {   # origin/main of each repo in heads.txt still at its start sha
    [ -f "$OUT/heads.txt" ] || return 0
    local dir sha now ok=0
    while read -r dir sha; do
        [ -n "$dir" ] || continue
        timeout 120 git -C "$dir" fetch -q origin main || { echo "fetch failed in $dir"; ok=1; continue; }
        now=$(git -C "$dir" rev-parse origin/main)
        [ "$now" = "$sha" ] || { echo "origin/main moved in $dir: $sha -> $now"; ok=1; }
    done < "$OUT/heads.txt"
    return $ok
}

run_step() {   # point step
    local p=$1 s=$2 t0 rc cmd
    case $s in
        rtl) cmd=(pixi run cluster rtl "$p" "${ab[@]}") ;;
        syn) cmd=(pixi run cluster syn "$p" --cores 16 "${ab[@]}") ;;
        gls) cmd=(pixi run cluster gls "$p" "${ab[@]}") ;;
        pwr) cmd=(pixi run cluster pwr "$p" --cores 16 "${ab[@]}") ;;
        hwcost) cmd=(pixi run cluster-hwcost "$p") ;;
    esac
    line "$p" "$s" START 0
    t0=$(date +%s)
    echo "+ ${cmd[*]}" > "$OUT/${p}_${s}.log"
    timeout "$STEP_TIMEOUT" "${cmd[@]}" < /dev/null >> "$OUT/${p}_${s}.log" 2>&1
    rc=$?
    if [ $rc -eq 0 ]; then line "$p" "$s" PASS $(( $(date +%s) - t0 )); return 0; fi
    echo "exit $rc" >> "$OUT/${p}_${s}.log"
    line "$p" "$s" FAIL $(( $(date +%s) - t0 ))
    return 1
}

first=1
for p in "${points[@]}"; do
    if ! quota_ok; then line "$p" quota FAIL 0; exit 3; fi
    if ! mains_ok; then line "$p" origin-main FAIL 0; exit 4; fi
    started=0
    for s in "${STEPS[@]}"; do
        if [ $first = 1 ] && [ $started = 0 ] && [ "$s" != "$from" ]; then continue; fi
        started=1
        run_step "$p" "$s" || exit 1
    done
    first=0
done
echo "$(date -Iseconds) ALL DONE" >> "$STATUS"
