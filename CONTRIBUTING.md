# Contributing to BEPAD

The main way to contribute is **your associator**: add it to the leaderboard so others can compare
with it and reproduce it. You only add your own folder; nothing else in BEPAD changes.

```bash
pip install bepad                                              # or: pip install -e . from a clone
bepad new my-method                                            # associators/my-method/ from the template
# fill in associate() in associators/my-method/associator.py, parameters in config.yaml
bepad run associators/my-method --split val                    # tune on val
bepad run associators/my-method --split test --out results/my-method
bepad submit results/my-method --code associators/my-method --dry-run   # check + preview your row
bepad submit results/my-method --code associators/my-method    # opens a Hugging Face pull request
```

The full guide, with the template and two worked examples (PyOcto, EQTransformer's simple
associator), is *Contribute your associator* in the documentation (`docs/source/contribute.rst`).

## Rules of the leaderboard

* Tune on `val`, never on `test`; train only on `train` / `val`. Velocity models: published ones,
  or fitted on `train` / `val`; never built from the test earthquakes (nor BEPAD's `label_model.json`,
  which includes them). Per-network settings go in the `networks:` block of `config.yaml`, model
  files in `models/velocity/` and `models/weights/`.
* The test labels are public (BEPAD is built from public UTDQuake earthquakes), so the leaderboard
  relies on reproducibility: submit your code with `--code`. Before merging, a maintainer recomputes
  your scores from your predictions and re-runs your code on part of the test split.
* The BEPAD-10 test is required: run `bepad run associators/<name> --split test --networks core`. It is the main ranking (mean over the 10 core networks).
  Each network is also ranked on its own. Runs on a subset of windows are *partial* and not ranked.
* A new version of your method is a new submission with a higher `version`.

## Code, data and documentation

Bug reports and pull requests to the BEPAD code are welcome on GitHub
(https://github.com/ecastillot/BEPAD). Problems with the underlying earthquakes, picks or stations
belong to UTDQuake (https://github.com/ecastillot/UTDQuake).
