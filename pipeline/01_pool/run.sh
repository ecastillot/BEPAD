#!/bin/bash
# Step 1: data/pool/ from UTDQuake (CPU). QC of every UTDQuake network (array of POOL_TASKS=4 tasks), then the label model
# fitted on every network in the pool (and qc_report.csv, results/<version>/network_properties.csv).
#
#   bash pipeline/01_pool/run.sh <version> [<dependency>] [network ...]
#
# Without networks: every UTDQuake network. Prints the label job id. Logs: results/<version>/logs/.
# Settings: configs/pool.yaml (QC, split, labels) and config.sh (UTDQuake copy and commit).
set -e
VERSION=${1:?usage: 01_pool/run.sh <version> [<dependency>] [network ...]}
DEP=$2; shift $(( $# < 2 ? $# : 2 ))
source /groups/igonin/ecastillo/BEPAD/pipeline/config.sh >/dev/null
L=$BEPAD_REPO/results/$VERSION/logs
mkdir -p "$L"
NETS=$L/pool_networks.txt
if [ $# -gt 0 ]; then printf '%s\n' "$@" > "$NETS"
else python -W ignore -c "from bepad.build.utdquake import list_networks; print('\n'.join(list_networks()))" > "$NETS"; fi
N=$(wc -l < "$NETS")
env="source $BEPAD_REPO/pipeline/config.sh"
# K array tasks (cluster QOS: 100 queued jobs per user); task k QCs networks k, k+K, k+2K ... in turn
K=$(( N < ${POOL_TASKS:-4} ? N : ${POOL_TASKS:-4} ))
p=$(sbatch --parsable ${DEP:+--dependency=$DEP} -p $CPU_PARTITION -N 1 --cpus-per-task=4 --mem=120G -t 1-00:00:00 \
    --array=1-$K -J bepad_${VERSION}_pool -o "$L/%x_%A_%a.out" \
    --wrap "$env; for net in \$(awk -v k=\$SLURM_ARRAY_TASK_ID -v K=$K '(NR-k)%K==0' $NETS); do echo network \$net; python -W ignore -m bepad pool add \$net --force; done")
# afterany: a network whose QC failed is left out of the label model (see its log)
f=$(sbatch --parsable --dependency=afterany:$p -p $CPU_PARTITION -N 1 --cpus-per-task=8 --mem=128G -t 12:00:00 \
    -J bepad_${VERSION}_labels -o "$L/%x_%j.out" \
    --wrap "$env; python -W ignore pipeline/01_pool/report.py $NETS && python -W ignore -m bepad pool fit-labels && python -W ignore pipeline/01_pool/network_table.py results/$VERSION/network_properties.csv")
echo "$VERSION pool: QC $p ($N networks, $K tasks) -> labels $f" >&2
echo $f
