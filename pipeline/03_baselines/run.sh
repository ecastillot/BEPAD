#!/bin/bash
# Step 3: the reference associators on the test split of a release (CPU), as leaderboard entries:
# results/<version>/baselines/<associator>/ (predictions, report, submission.json).
#
#   bash pipeline/03_baselines/run.sh <version> [<dependency>] [associator ...]
#
# Default associators: every folder of associators/. NETWORKS=core runs only BEPAD-10 (default: every
# network). Prints the job ids. Logs: results/<version>/logs/.
set -e
VERSION=${1:?usage: 03_baselines/run.sh <version> [<dependency>] [associator ...]}
DEP=$2; shift $(( $# < 2 ? $# : 2 ))
source /groups/igonin/ecastillo/BEPAD/pipeline/config.sh >/dev/null
L=$BEPAD_REPO/results/$VERSION/logs
mkdir -p "$L"
ASSOC=${@:-$(ls associators)}
W=16
env="source $BEPAD_REPO/pipeline/config.sh"
ids=""
for a in $ASSOC; do
  out=results/$VERSION/baselines/$a
  j=$(sbatch --parsable ${DEP:+--dependency=$DEP} -p $CPU_PARTITION -N 1 --cpus-per-task=$W --mem=96G -t 2-00:00:00 \
      -J bepad_${VERSION}_$a -o "$L/%x_%j.out" \
      --wrap "$env; SECONDS=0; python -W ignore -m bepad run associators/$a --split test ${NETWORKS:+--networks $NETWORKS} --release-dir data/releases/$VERSION --workers $W --out $out && python -W ignore -m bepad submit $out --code associators/$a --release-dir data/releases/$VERSION --dry-run; echo elapsed \${SECONDS}s")
  echo "$VERSION baseline $a: $j" >&2
  ids="$ids:$j"
done
echo ${ids#:}
