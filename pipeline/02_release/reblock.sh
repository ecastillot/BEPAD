#!/bin/bash
# Rewrite an existing release in blocks (bepad.blocks): same rows and content, sorted by window_id,
# so one window can be read without reading the whole file. Needed once for releases built before
# blocks (v0.1); new builds already write blocks. Array of BUILD_TASKS=8 tasks over the networks, then
# finalize (checks every file and records the layout in manifest.json).
#
#   bash pipeline/02_release/reblock.sh <version> [<dependency>]
#
# Prints the finalize job id. Logs: results/<version>/logs/.
set -e
VERSION=${1:?usage: 02_release/reblock.sh <version> [<dependency>]}
source /groups/igonin/ecastillo/BEPAD/pipeline/config.sh >/dev/null
CFG=configs/$VERSION.yaml
L=$BEPAD_REPO/results/$VERSION/logs
mkdir -p "$L"
NETS=$L/reblock_networks.txt
ls data/releases/$VERSION/*/windows/ | grep -o 'network=[^.]*' | sed 's/network=//' | sort -u > "$NETS"
N=$(wc -l < "$NETS")
env="source $BEPAD_REPO/pipeline/config.sh"
K=$(( N < ${BUILD_TASKS:-8} ? N : ${BUILD_TASKS:-8} ))
b=$(sbatch --parsable ${2:+--dependency=$2} -p $CPU_PARTITION -N 1 --cpus-per-task=4 --mem=120G -t 1-00:00:00 \
    --array=1-$K -J bepad_${VERSION}_reblock -o "$L/%x_%A_%a.out" \
    --wrap "$env; for net in \$(awk -v k=\$SLURM_ARRAY_TASK_ID -v K=$K '(NR-k)%K==0' $NETS); do SECONDS=0; python -W ignore -c \"from bepad.blocks import reblock; reblock('data/releases/$VERSION', networks=['\$net'])\" || exit 1; echo network \$net elapsed \${SECONDS}s; done")
f=$(sbatch --parsable --dependency=afterok:$b -p $CPU_PARTITION -N 1 --cpus-per-task=8 --mem=200G -t 06:00:00 \
    -J bepad_${VERSION}_finalize -o "$L/%x_%j.out" \
    --wrap "$env; python -W ignore -m bepad finalize $CFG; du -sh data/releases/$VERSION")
echo "$VERSION reblock: $b ($N networks, $K tasks) -> finalize $f" >&2
echo $f
