# Cluster settings of the pipeline, sourced by every run script (edit this file for another cluster).
#
#   source /groups/igonin/ecastillo/BEPAD/pipeline/config.sh

BEPAD_REPO=/groups/igonin/ecastillo/BEPAD
CONDA_SH=/groups/igonin/ecastillo/anaconda3/etc/profile.d/conda.sh
CONDA_ENV=bepad          # has pyocto (baselines); torch is only needed for bepad.torch

# SLURM partition of every job (all CPU)
CPU_PARTITION=normal

# UTDQuake 1.0, local copy of the Hugging Face dataset (main = commit 8524c6f0: v1 + v2 networks, one schema,
# JAPAN renamed JMA)
export UTDQUAKE_ROOT=${UTDQUAKE_ROOT:-/groups/igonin/ecastillo/UTDQuake}
export UTDQUAKE_DAS_ROOT=${UTDQUAKE_DAS_ROOT:-/groups/igonin/ecastillo/UTDQuake_DAS}
export UTDQUAKE_REVISION=${UTDQUAKE_REVISION:-8524c6f0c7cea7405670dab99967aa73b6a30775}

source "$CONDA_SH"
conda activate "$CONDA_ENV"
# this repository's code first (the environment may have other versions of BEPAD and UTDQuake
# installed), and UTDQuake >= 1.0.1 (reads the 1.0 layout)
UTDQUAKE_CODE=/groups/igonin/ecastillo/utdquake
export PYTHONPATH=$BEPAD_REPO:$UTDQUAKE_CODE${PYTHONPATH:+:$PYTHONPATH}
export PYTHONUNBUFFERED=1 OMP_NUM_THREADS=${OMP_NUM_THREADS:-8}
cd "$BEPAD_REPO"
