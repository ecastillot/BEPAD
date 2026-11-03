"""PyTorch datasets for training associators on BEPAD.

- ``ReleaseWindowDataset``: the fixed windows of a release split (train/val).
- ``GeneratedWindowDataset``: fresh windows from the pool on every epoch
  (same generator as the release, different seeds), for unlimited training data.

Each item is a dict of tensors for ONE window (variable number of picks and
stations). ``collate_windows`` concatenates a batch PyG-style, with
``pick_batch``/``station_batch`` vectors and per-window offsets applied to
``pick_station``.

Item keys::

    window_id        str
    station_coords   (S, 3) float32  latitude, longitude [deg], elevation [m]
    pick_station     (N,)   int64    index into station_coords
    pick_phase       (N,)   int64    0 = P, 1 = S
    pick_time        (N,)   float32  seconds from window start
    pick_label       (N,)   int64    event index in the window, -1 = noise
    pick_prob        (N,)   float32  1.0-0.5 real, >= 0.5 generated, 0 noise (soft target)
    pick_real        (N,)   bool     pick comes from UTDQuake (not generated, not noise)
    pick_type        (N,)   int64    0 = real, 1 = generated, 2 = noise
    pick_sigma       (N,)   float32  timing uncertainty [s] at that distance (NaN for noise)
    pick_scorable    (N,)   bool     pick belongs to a scorable event
    event_origin     (E, 4) float32  t0 [s from window start], latitude, longitude, depth [km]
    event_scorable   (E,)   bool

Normalisation is left to the model.
"""

from __future__ import annotations

import numpy as np
import torch
from torch.utils.data import Dataset

from .build.geo import stable_seed

PHASE_CODE = {"P": 0, "S": 1}
TYPE_CODE = {"real": 0, "generated": 1, "noise": 2}


def window_to_tensors(window_id, picks, stations, events=None):
    stations = stations.reset_index(drop=True)
    pos = {s: i for i, s in enumerate(stations["station"])}
    item = {
        "window_id": window_id,
        "station_coords": torch.tensor(stations[["latitude", "longitude", "elevation"]].to_numpy(np.float32)),
        "pick_station": torch.tensor(picks["station"].map(pos).to_numpy(np.int64)),
        "pick_phase": torch.tensor(picks["phase"].map(PHASE_CODE).to_numpy(np.int64)),
        "pick_time": torch.tensor(picks["t_rel_s"].to_numpy(np.float32)),
    }
    if "event_idx" in picks:
        item["pick_label"] = torch.tensor(picks["event_idx"].to_numpy(np.int64))
        item["pick_prob"] = torch.tensor(picks["prob"].to_numpy(np.float32))
        item["pick_real"] = torch.tensor(picks["real"].to_numpy(bool))
        item["pick_type"] = torch.tensor(picks["pick_type"].map(TYPE_CODE).to_numpy(np.int64))
        item["pick_sigma"] = torch.tensor(picks["sigma_s"].to_numpy(np.float32))
        item["pick_scorable"] = torch.tensor(picks["in_scorable_event"].to_numpy(bool))
    if events is not None:
        e = events.sort_values("event_idx")
        item["event_origin"] = torch.tensor(np.stack([
            e["t0_rel_s"], e["latitude"], e["longitude"], e["depth"] / 1e3], axis=1).astype(np.float32))
        item["event_scorable"] = torch.tensor(e["scorable"].to_numpy(bool))
    return item


class ReleaseWindowDataset(Dataset):
    """Fixed windows of one split (use train/val; never tune on test).

    ``release``: a :class:`bepad.data.Release`, a local release folder, or None
    to download ``split`` from Hugging Face.
    Each window is read from disk when the ``DataLoader`` asks for it (``lazy=True``, the default),
    so any split fits in memory. ``lazy=False`` holds all chosen windows in memory (faster per
    window, but 20 GB for R07 train alone). ``networks``, ``scenarios``, ``max_windows`` (per
    network) and ``window_ids`` choose windows, as in :func:`bepad.load`.
    """

    def __init__(self, release=None, split="train", networks=None, scenarios=None, max_windows=None,
                 window_ids=None, lazy=True):
        from .data import Release, load

        sub = dict(scenarios=scenarios, max_windows=max_windows, window_ids=window_ids, lazy=lazy)
        if release is None:
            self.split = load(split, networks=networks, labels=True, **sub)
        else:
            rel = release if isinstance(release, Release) else Release(release)
            self.split = rel.load(split, networks=networks, labels=True, **sub)

    def __len__(self):
        return len(self.split)

    def __getitem__(self, i):
        w = self.split[i]
        return window_to_tensors(w.window_id, w.picks, w.stations, w.events)


class GeneratedWindowDataset(Dataset):
    """On-the-fly windows from the pool.

    Item ``i`` of epoch ``e`` uses seed sha256(base_seed, e, i), so a run is
    reproducible and every epoch sees new windows. Scenario configs (dicts of
    window parameters, e.g. ``Release.scenarios()``, BEPAD's own) are
    drawn uniformly per item, as is the network. Networks without earthquakes in ``split`` (test-only
    networks, e.g. R06 for train) are left out; if a network cannot make the drawn scenario, the item
    draws another network and scenario (still reproducible).
    """

    def __init__(self, data_root, networks, scenarios, split="train", length=10_000, base_seed=0):
        from .build.config import WINDOW_DEFAULTS
        from .build.labels import LabelModel
        from .build.pool import load_network, pool_dir
        from .build.windows import NetworkIndex

        model = LabelModel.load(pool_dir(data_root) / "label_model.json")
        self.index = {}
        for n in networks:
            ev, pk, st = load_network(data_root, n)
            if (ev["split"] == split).any():
                self.index[n] = NetworkIndex(ev, pk, st, network=n, label_model=model)
        skipped = sorted(set(networks) - set(self.index))
        if skipped:
            print(f"[GeneratedWindowDataset] no {split} earthquakes, left out: {', '.join(skipped)}")
        if not self.index:
            raise ValueError(f"no network has {split} earthquakes")
        self.networks = list(self.index)
        self.scenarios = [(k, {**WINDOW_DEFAULTS, **v}) for k, v in
                          (scenarios.items() if isinstance(scenarios, dict) else enumerate(scenarios))]
        self.split = split
        self.length = length
        self.base_seed = base_seed
        self.epoch = 0

    def set_epoch(self, epoch):
        self.epoch = epoch

    def __len__(self):
        return self.length

    def __getitem__(self, i):
        from .build.windows import generate_window

        seed = stable_seed(self.base_seed, self.epoch, i)
        rng = np.random.default_rng(seed)
        for draw in range(20):                          # a network may not be able to make a scenario
            net = self.networks[rng.integers(len(self.networks))]
            name, cfg = self.scenarios[rng.integers(len(self.scenarios))]
            w = generate_window(self.index[net], self.split, cfg, seed + draw, f"gen-{self.epoch}-{i}", str(name))
            if w is not None:
                break
        else:
            raise RuntimeError(f"could not generate window {i}: 20 draws of network and scenario failed")
        st = self.index[net].stations.loc[w.stations["station"]].reset_index()
        return window_to_tensors(w.window["window_id"], w.picks, st, w.events)


def collate_windows(batch):
    """Concatenate variable-size windows; adds pick_batch / station_batch / event_batch."""
    out = {"window_id": [b["window_id"] for b in batch]}
    offset = 0
    parts = {k: [] for k in batch[0] if k != "window_id"}
    parts.update(pick_batch=[], station_batch=[], event_batch=[])
    for k, b in enumerate(batch):
        n_sta = len(b["station_coords"])
        for key in parts:
            if key in b:
                parts[key].append(b[key] + offset if key == "pick_station" else b[key])
        parts["pick_batch"].append(torch.full((len(b["pick_time"]),), k, dtype=torch.long))
        parts["station_batch"].append(torch.full((n_sta,), k, dtype=torch.long))
        if "event_origin" in b:
            parts["event_batch"].append(torch.full((len(b["event_origin"]),), k, dtype=torch.long))
        offset += n_sta
    for key, vals in parts.items():
        if vals:
            out[key] = torch.cat(vals)
    return out
