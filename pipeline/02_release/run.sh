#!/bin/bash
# Step 2: data/releases/<version>/ from the pool (CPU). The windows of every network, split and scenario
# (array of BUILD_TASKS=8 tasks), then finalize (stations, metadata, manifest) and the release figures.
#
#   bash pipeline/02_release/run.sh <version> [<dependency>]
#   NETWORKS="NET1 NET2" bash pipeline/02_release/run.sh <version>   # build only these (the others are kept)
#
# Config: configs/<version>.yaml. Prints the finalize job id. Logs: results/<version>/logs/.
set -e
VERSION=${1:?usage: 02_release/run.sh <version> [<dependency>]}
source /groups/igonin/ecastillo/BEPAD/pipeline/config.sh >/dev/null
CFG=configs/$VERSION.yaml
L=$BEPAD_REPO/results/$VERSION/logs
mkdir -p "$L"
NETS=$L/release_networks.txt
POOL_NETS=$L/pool_networks.txt
if [ -n "$NETWORKS" ]; then printf '%s\n' $NETWORKS > "$NETS"
else python -W ignore pipeline/02_release/networks.py $CFG $( [ -f $POOL_NETS ] && echo $POOL_NETS ) > "$NETS"; fi
N=$(wc -l < "$NETS")
W=32
env="source $BEPAD_REPO/pipeline/config.sh"
# K array tasks (cluster QOS: 100 queued jobs per user); task k builds networks k, k+K, k+2K ... in turn
K=$(( N < ${BUILD_TASKS:-8} ? N : ${BUILD_TASKS:-8} ))
b=$(sbatch --parsable ${2:+--dependency=$2} -p $CPU_PARTITION -N 1 --cpus-per-task=$W --mem=120G -t 2-00:00:00 \
    --array=1-$K -J bepad_${VERSION}_build -o "$L/%x_%A_%a.out" \
    --wrap "$env; for net in \$(awk -v k=\$SLURM_ARRAY_TASK_ID -v K=$K '(NR-k)%K==0' $NETS); do echo network \$net; SECONDS=0; python -W ignore -m bepad build $CFG --networks \$net --workers $W --no-finalize; echo network \$net elapsed \${SECONDS}s exit \$?; done")
# afterany: a network whose build failed is left out (finalize lists the built ones)
f=$(sbatch --parsable --dependency=afterany:$b -p $CPU_PARTITION -N 1 --cpus-per-task=8 --mem=200G -t 06:00:00 \
    -J bepad_${VERSION}_finalize -o "$L/%x_%j.out" \
    --wrap "$env; echo networks in the release: \$(ls data/releases/$VERSION/_parts | wc -l), built in this run: $N; python -W ignore -m bepad finalize $CFG && python -W ignore -m bepad figures $CFG; du -sh data/releases/$VERSION data/releases/$VERSION/*")
echo "$VERSION release: build $b ($N networks, $K tasks) -> finalize $f" >&2
echo $f
