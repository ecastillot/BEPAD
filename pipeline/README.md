# Pipeline: the recipe of a BEPAD release

Everything needed to make a release of BEPAD, from the UTDQuake data to the windows on Hugging Face.
Each step is a folder with a `run.sh` (SLURM). Run every command from the repository root; cluster
settings (environment, partition, UTDQuake copy and commit) are in [`config.sh`](config.sh), and the
release settings in `configs/<version>.yaml` and `configs/pool.yaml`.

```bash
bash pipeline/run_version.sh v0.1                 # every UTDQuake network
bash pipeline/run_version.sh dev tx CM R08        # a quick check: pool only these networks, configs/dev.yaml
```

| Step | Command | Makes |
|---|---|---|
| 1. Pool | `bash pipeline/01_pool/run.sh <version> [<dep>] [network ...]` | `data/pool/`: QC'd events, picks, stations per network; `qc_report.csv`; `label_model.json` |
| 2. Release | `bash pipeline/02_release/run.sh <version> [<dep>]` | `data/releases/<version>/`: windows of every split and scenario, manifest, metadata, figures |
| 2b. Blocks (once, old releases) | `bash pipeline/02_release/reblock.sh <version> [<dep>]` | rewrites a release built before blocks (v0.1) in blocks; same content (new builds already write blocks) |
| 3. Baselines | `bash pipeline/03_baselines/run.sh <version> [<dep>] [associator ...]` | `results/<version>/baselines/<associator>/`: test-split predictions, scores, `submission.json` (checked with `bepad submit --dry-run`) |
| 4. Publish | see `docs/source/reference/building.rst` | the release and the baselines' leaderboard entries on Hugging Face |

Logs of every job go to `results/<version>/logs/` (`chain.txt`: the job ids). `data/` and `results/`
are not in git.

## UTDQuake

BEPAD v0.1 reads UTDQuake 1.0 from the local copy `$UTDQUAKE_ROOT` at Hugging Face commit
`$UTDQUAKE_REVISION` (`8524c6f0`: the v1 and v2 networks in one schema), with the UTDQuake code
>= 1.0.1. Both are recorded in every pool `manifest.json` and in the release manifest. In BEPAD,
`network` is the UTDQuake network (`utdq_net`) and a station is `NET.STA`; the one place that
reads UTDQuake is `bepad/build/utdquake.py`.

## Cluster limits

The juno QOS allows 4 running and 100 queued jobs per user, shared with every other project (e.g.
HypoGT's evaluation submits its own jobs). So the steps do not run one job per network: the pool is
an array of `POOL_TASKS` (4) tasks and the release of `BUILD_TASKS` (8), each task processing every
K-th network of the list in turn. A full chain queues about 16 jobs.
