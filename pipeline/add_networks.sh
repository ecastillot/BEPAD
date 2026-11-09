#!/bin/bash
# Add networks to a release without changing the networks already in it (CPU, SLURM chain):
#   1. pool the new networks (QC, split)
#   2. label model: add only their travel-time curves (q(M, r), sigma(r) and the other networks' curves are kept)
#   3. build only their windows, then finalize (stations, metadata, manifest, figures of the whole release)
#
#   bash pipeline/add_networks.sh <version> NET1 [NET2 ...]
#
# The windows of the other networks are not rebuilt: their files stay as they are. A new network's windows
# use the release's seed_namespace, like every network. Logs: results/<version>/logs/ (chain.txt: job ids).
set -e
VERSION=${1:?usage: add_networks.sh <version> NET1 [NET2 ...]}; shift
[ $# -gt 0 ] || { echo "give the networks to add" >&2; exit 1; }
source /groups/igonin/ecastillo/BEPAD/pipeline/config.sh >/dev/null
L=$BEPAD_REPO/results/$VERSION/logs
mkdir -p "$L"
env="source $BEPAD_REPO/pipeline/config.sh"
{
p=$(sbatch --parsable -p $CPU_PARTITION -N 1 --cpus-per-task=4 --mem=120G -t 1-00:00:00 \
    -J bepad_${VERSION}_add_pool -o "$L/%x_%j.out" \
    --wrap "$env; for net in $*; do echo network \$net; python -W ignore -m bepad pool add \$net --force || exit 1; done; python -W ignore -m bepad pool fit-labels --networks $* --keep-global")
echo "$VERSION add $*: pool + labels $p" >&2
NETWORKS="$*" bash pipeline/02_release/run.sh $VERSION afterok:$p >/dev/null
} 2>&1 | tee -a $L/chain.txt
