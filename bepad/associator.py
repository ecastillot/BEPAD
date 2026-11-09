"""The associator template: fill in one method, get runs, reports and leaderboard submissions.

    import bepad

    class MyAssociator(bepad.Associator):
        name = "my-method"
        version = "1.0"

        def associate(self, picks, stations):
            ...                      # one integer per pick: event number, or -1 for noise
            return labels

    result = MyAssociator(threshold=0.3).run("test", networks=["tx"])
    result.report                    # scores
    result.save("results/my-method")  # predictions + report + submission.json

A contributed associator is a folder (``bepad new <name>`` creates it)::

    associators/<name>/
        associator.py      the class
        config.yaml        its parameters (passed to __init__)
        README.md          what it is, paper, license
        requirements.txt   extra packages it needs
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import sys
import platform
import time
from pathlib import Path

import numpy as np
import pandas as pd

METHOD_TYPES = ("classical", "deep learning", "hybrid")
TRAINING = ("none", "per network", "all networks")


class Associator:
    """Base class. Subclasses set the metadata attributes and implement :meth:`associate`."""

    #: short unique name (letters, digits, dashes), used for folders and the leaderboard
    name: str = "unnamed"
    version: str = "0.1"
    authors: str = ""
    paper: str = ""          # DOI or URL
    code: str = ""           # repository URL
    method_type: str = "classical"   # "classical" | "deep learning" | "hybrid"
    training: str = "none"           # "none" | "per network" | "all networks"
    description: str = ""

    def __init__(self, **config):
        nets = config.get("networks") or {}
        if not isinstance(nets, dict) or not all(isinstance(v, dict) for v in nets.values()):
            raise ValueError("config 'networks' must map a network to its settings, e.g. {tx: {p_velocity: 6.0}}")
        self._base_config = config
        self.network = None          # the network of the current window (set before each associate call)
        self.path = _class_folder(type(self))   # the associator folder, for model files (already in __init__)
        self.config = self.network_config(None)

    def network_config(self, network):
        """``config.yaml`` for one network: the general settings, overridden by its ``networks:`` entry."""
        base = {k: v for k, v in self._base_config.items() if k != "networks"}
        return {**base, **(self._base_config.get("networks") or {}).get(network, {})}

    def use_network(self, network):
        """Called by BEPAD before each window: sets ``self.network`` and ``self.config``."""
        if network != self.network:
            self.network, self.config = network, self.network_config(network)

    # --- to implement --------------------------------------------------------------
    def fit(self, train, val):
        """Optional: learn or tune on the ``train`` / ``val`` splits (never on test)."""

    def associate(self, picks: pd.DataFrame, stations: pd.DataFrame):
        """Associate the picks of ONE window.

        picks:    pick_idx, station, phase ("P"/"S"), t_rel_s (s from window start), time (UTC)
        stations: station, latitude, longitude, elevation -- every station of the window
        returns:  one integer per pick, in the same order: event number (>= 0) or -1 (noise)

        Associators that also locate can return ``labels, events`` instead, where
        ``events`` has one row per event number: event, latitude, longitude,
        depth_km, t0_rel_s (origin time in seconds from the window start); any of
        the location columns may be left out. Location errors are then reported too.
        """
        raise NotImplementedError

    # --- provided ------------------------------------------------------------------
    def run(self, split="test", networks=None, scenarios=None, max_windows=None, window_ids=None, workers=1,
            release=None, root=None, progress=True):
        """Run on every window of a split and score it. Returns a :class:`Result`.

        ``workers``: number of CPU processes (windows are independent).
        ``scenarios`` / ``max_windows`` / ``window_ids`` run a subset (quick tests, as in
        :func:`bepad.load`); such runs are marked partial and are not ranked on the leaderboard.
        """
        from .data import RELEASE, load
        from .metrics import evaluate

        subset = scenarios is not None or max_windows is not None or window_ids is not None
        data = load(split, networks=networks, labels=False, release=release or RELEASE, root=root,
                    scenarios=scenarios, max_windows=max_windows, window_ids=window_ids)
        keep = data.windows
        ids = set(keep.window_id)
        todo = [(win.window_id, win.meta["network"], win.picks, win.stations) for win in data]
        rows, locs, secs, t0, n = [], [], [], time.time(), len(todo)
        _RUNNING[0] = self
        if workers > 1:
            import multiprocessing as mp
            pool = mp.get_context("fork").Pool(workers)
            results = pool.imap(_associate_one, todo, chunksize=2)
        else:
            pool, results = None, map(_associate_one, todo)
        try:
            for k, (df, loc, sec) in enumerate(results):
                rows.append(df)
                secs.append(sec)
                if loc is not None:
                    locs.append(loc)
                if progress and (k + 1) % 50 == 0:
                    print(f"[{self.name}] {k + 1}/{n} windows, {time.time() - t0:.0f} s")
        finally:
            if pool is not None:
                pool.close()
                pool.join()
        runtime = time.time() - t0
        predictions = pd.concat(rows, ignore_index=True)
        locations = pd.concat(locs, ignore_index=True) if locs else None
        report = evaluate(predictions, data, window_ids=ids, locations=locations)
        meta = {
            "split": split, "release": data.release.path.name,
            "networks": sorted(keep.network.unique()),
            "n_windows": n, "complete": not subset,
            "scenarios": "all" if scenarios is None else ([scenarios] if isinstance(scenarios, str) else list(scenarios)),
            "workers": workers, "runtime_s": round(runtime, 2),
            "seconds_per_window": round(float(np.mean(secs)), 4) if secs else None,   # time inside associate()
            "hardware": f"{platform.processor() or platform.machine()} ({platform.system()})",
        }
        return Result(self, predictions, report, meta, locations)

    def metadata(self):
        if self.method_type not in METHOD_TYPES:
            raise ValueError(f"method_type must be one of {METHOD_TYPES}")
        if self.training not in TRAINING:
            raise ValueError(f"training must be one of {TRAINING}")
        return {"name": self.name, "version": self.version, "authors": self.authors, "paper": self.paper,
                "code": self.code, "method_type": self.method_type, "training": self.training,
                "description": self.description, "config": self._base_config}


_RUNNING = [None]          # the associator being run (inherited by forked workers)


def _associate_one(item):
    window_id, network, picks, stations = item
    assoc = _RUNNING[0]
    assoc.use_network(network)
    tic = time.perf_counter()
    out = assoc.associate(picks, stations)
    elapsed = time.perf_counter() - tic
    loc = None
    if isinstance(out, tuple):
        out, loc = out
        loc = pd.DataFrame(loc).rename(columns={"pred_event": "event"})
        if "event" not in loc:
            raise ValueError(f"{assoc.name}: the events table needs an 'event' column (the event numbers)")
        keep = ["event"] + [c for c in ("latitude", "longitude", "depth_km", "t0_rel_s") if c in loc]
        loc = loc[keep].assign(window_id=window_id)
    labels = np.asarray(out)
    if labels.shape != (len(picks),) or not np.issubdtype(labels.dtype, np.integer):
        raise ValueError(f"{assoc.name}.associate must return {len(picks)} integers for {window_id}, "
                         f"got shape {labels.shape} dtype {labels.dtype}")
    return pd.DataFrame({"window_id": window_id, "pick_idx": picks.pick_idx.to_numpy(),
                         "pred_event": labels.astype(np.int64)}), loc, elapsed


class Result:
    """Predictions + report of one run. ``save`` writes everything a submission needs."""

    def __init__(self, associator, predictions, report, meta, locations=None):
        self.associator, self.predictions, self.report, self.meta = associator, predictions, report, meta
        self.locations = locations      # one row per predicted event (only if the associator locates)

    def __repr__(self):
        return f"<bepad.Result {self.associator.name} {self.meta['split']} {self.meta['n_windows']} windows>\n" \
               + repr(self.report).split("\n", 1)[1]

    def submission(self):
        """The leaderboard record (a dict, saved as submission.json)."""
        from . import __version__

        r = self.report
        cols = ["event_precision", "event_recall", "event_f1", "pick_precision", "pick_recall", "pick_f1",
                "noise_rejection", "split_rate", "merge_rate", "ari_mean", "n_windows"]
        cols += [c for c in ("located_frac", "epi_median_km", "epi_p90_km", "depth_median_km", "depth_p90_km",
                             "t0_median_s", "t0_p90_s") if c in r.overall]
        by_net = r.by_network.set_index("network")[cols]
        return {
            "bepad_version": __version__,
            "created": dt.datetime.now().isoformat(timespec="seconds"),
            "associator": self.associator.metadata(),
            "run": self.meta,
            "scores": {"overall": {k: _num(v) for k, v in r.overall.iloc[0][cols].items()},
                       "by_network": {n: {k: _num(v) for k, v in row.items()} for n, row in by_net.iterrows()}},
        }

    def save(self, out_dir):
        """Write ``submission.json``, ``predictions/network=<name>.parquet``, ``locations/`` (if any)
        and the report tables."""
        out = Path(out_dir)
        (out / "predictions").mkdir(parents=True, exist_ok=True)
        net = self.predictions.window_id.str.split(".", n=1).str[0]
        for n, df in self.predictions.groupby(net):
            df.to_parquet(out / "predictions" / f"network={n}.parquet", index=False, compression="zstd")
        if self.locations is not None:
            (out / "locations").mkdir(exist_ok=True)
            lnet = self.locations.window_id.str.split(".", n=1).str[0]
            for n, df in self.locations.groupby(lnet):
                df.to_parquet(out / "locations" / f"network={n}.parquet", index=False)
        self.report.save(out / "report")
        (out / "submission.json").write_text(json.dumps(self.submission(), indent=2))
        return out


def _num(v):
    v = float(v)
    return None if v != v else round(v, 6)


# ----------------------------------------------------------------------
def _class_folder(cls):
    """The folder of the file that defines ``cls`` (None for a class typed in a notebook)."""
    import inspect

    try:
        return Path(inspect.getfile(cls)).resolve().parent
    except (TypeError, OSError):
        return None


def load_associator(path, **overrides):
    """Load an associator folder (or .py file): its Associator subclass + config.yaml."""
    import yaml

    path = Path(path)
    file = path / "associator.py" if path.is_dir() else path
    spec = importlib.util.spec_from_file_location(f"bepad_assoc_{file.parent.name}", file)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod           # so the class knows its file (self.path in __init__)
    spec.loader.exec_module(mod)
    classes = [c for c in vars(mod).values()
               if isinstance(c, type) and issubclass(c, Associator) and c is not Associator]
    if len(classes) != 1:
        raise ValueError(f"{file} must define exactly one bepad.Associator subclass, found {len(classes)}")
    cfg_file = file.parent / "config.yaml"
    config = (yaml.safe_load(cfg_file.read_text()) or {}) if cfg_file.exists() else {}
    obj = classes[0](**{**config, **overrides})
    obj.path = file.parent
    return obj


TEMPLATE = {
    "associator.py": '''"""{name}: a BEPAD associator.

Fill in ``associate`` (required) and ``fit`` (optional), set the metadata, then:
    bepad run associators/{name} --split val        # tune
    bepad run associators/{name} --split test --out results/{name}
    bepad submit results/{name}
"""

import numpy as np

import bepad


class Associator(bepad.Associator):
    name = "{name}"
    version = "0.1"
    authors = "Your Name"
    paper = ""                   # DOI or URL of the paper describing the method
    code = ""                    # URL of the original code, if any
    method_type = "classical"    # "classical" | "deep learning" | "hybrid"
    training = "none"            # "none" | "per network" | "all networks"
    description = "One sentence: what the method does."

    def fit(self, train, val):
        """Optional: learn or tune on train / val. Parameters are in self.config."""

    def associate(self, picks, stations):
        """One window.

        picks:    pick_idx, station, phase ("P"/"S"), t_rel_s (s from window start), time (UTC)
        stations: station, latitude, longitude, elevation
        return:   one integer per pick (same order): event number, or -1 for noise

        self.network is the window's network (e.g. "tx") and self.config its settings
        (config.yaml, with that network's overrides). Files of the folder: self.path / "models/...".
        """
        labels = np.full(len(picks), -1)          # <- replace with your method
        return labels
''',
    "config.yaml": '''# Parameters of {name}; passed to the class as self.config.
# Every value here is saved with the results, so others can reproduce them.
example_threshold: 0.5

# Optional: settings for some networks, overriding the ones above (e.g. a 1D velocity model).
# Model files go in models/velocity/ (velocity models) and models/weights/ (trained models).
# networks:
#   tx:  {{velocity_model: models/velocity/tx_1d.csv}}
#   JMA: {{velocity_model: models/velocity/jma2001.csv}}
''',
    "README.md": '''# {name}

What the method does, in two or three sentences.

- **Paper:** <DOI or URL>
- **Original code:** <URL>
- **License:** <license of this code>
- **Requirements:** see `requirements.txt`

## Parameters

| Parameter | Meaning |
|---|---|
| `example_threshold` | ... |
''',
    "requirements.txt": "# extra packages this associator needs, one per line\n",
}


def new_associator(name, root="associators"):
    """Create ``<root>/<name>/`` from the template."""
    import re

    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]*", name):
        raise ValueError("name: lowercase letters, digits, dashes and underscores (e.g. 'my-method')")
    d = Path(root) / name
    if d.exists():
        raise FileExistsError(f"{d} already exists")
    d.mkdir(parents=True)
    for fname, text in TEMPLATE.items():
        (d / fname).write_text(text.format(name=name))
    return d
