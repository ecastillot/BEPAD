#!/bin/bash
# The whole recipe of a version as one SLURM chain: 1 pool (+ label model) -> 2 release windows
# (+ finalize, figures) -> 3 baselines on the test split. Logs: results/<version>/logs/ (chain.txt: the job ids).
#
#   bash pipeline/run_version.sh <version> [network ...]      # configs/<version>.yaml; networks: pool only those
#   BASELINES=0 bash pipeline/run_version.sh <version>        # without step 3
set -e
VERSION=${1:?usage: run_version.sh <version> [network ...]}; shift
cd /groups/igonin/ecastillo/BEPAD
mkdir -p results/$VERSION/logs
{
p=$(bash pipeline/01_pool/run.sh $VERSION "" "$@")
r=$(bash pipeline/02_release/run.sh $VERSION afterok:$p)
[ "${BASELINES:-1}" = 0 ] || bash pipeline/03_baselines/run.sh $VERSION afterok:$r >/dev/null
} 2>&1 | tee -a results/$VERSION/logs/chain.txt
