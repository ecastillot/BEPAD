"""YAML configs with defaults.

- configs/pool.yaml       quality control + split (shared by every release)
- configs/<release>.yaml  scenarios, window parameters, window counts
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

POOL_DEFAULTS = {
    "data_root": "data",
    # Same thresholds as hypogt test/09252026 v8 (strict edges, Student-t).
    "qc": {
        "min_p": 4,
        "min_s": 0,
        "min_stations": 3,
        "max_gap_deg": 270.0,
        "max_depth_m": 700_000.0,
        "max_rms_s": 1.8,
        "max_horizontal_uncertainty_m": 200_000.0,
        "max_vertical_uncertainty_m": 30_000.0,
        "zscore_sigma": 3.0,
        "keep_nan_zscore": True,
        "keep_missing": True,      # a missing catalog field does not reject an event
    },
    # Random split per event: hash(salt | network | event_id). Networks are independent.
    "split": {
        "salt": "bepad-v1",
        "fractions": {"train": 0.7, "val": 0.1, "test": 0.2},
        "test_only_below": 200,    # a network with fewer QC'd events is test only
    },
    # Label model (bepad.build.labels)
    "labels": {
        "gamma": 0.5,              # prob = 0.5 + 0.5 * q ** gamma
        "band_k": 2.0,             # band = predicted arrival +/- band_k * sigma(r)
        "max_gap_frac": 0.3,       # generated picks only where neighbouring real picks are <= 30% of r apart
        "sigma_floor_s": 0.05,
        "active_days": 30,         # station "available" for an event if it picked anything within +/- 30 days
        "events_per_network": 1500,  # events sampled per network for the detectability fit
    },
}

WINDOW_DEFAULTS = {
    "n_events": [3, 5],
    # "auto" -> length_factor * longest event duration among the sampled events
    "length_s": "auto",
    "length_factor": 2.0,
    "tail_frac": 0.05,             # origins in [0, (1 - tail_frac) * length]
    # events drawn within +/- this many days of an anchor event (null = anywhere)
    "event_time_neighborhood_days": 365,
    "edge_event_prob": 0.3,        # one extra event starting before t = 0
    # noise picks / real picks; noise never falls inside an event's band
    "noise_ratio": 0.0,
    "noise_any_station_frac": 0.1,  # share of noise on any station (rest: uniform in distance to the events)
    # generated picks / real picks, drawn per window from [lo, hi]
    "generated_ratio": [0.0, 0.2],
    "station_keep_frac": 1.0,
    "gap_range": None,             # event filters on pool columns
    "magnitude_range": None,
    # every event must pass the pool rule INSIDE the window (real picks only)
    "event_min_p": 4,
    "event_min_s": 0,
    "event_min_stations": 3,
}

RELEASE_DEFAULTS = {
    "release": "dev",
    "data_root": "data",
    "networks": "all",
    "exclude_networks": [],
    "min_events_per_split": 20,
    "windows_per_scenario": {"train": 10, "val": 3, "test": 5},   # per network and scenario
    "window": WINDOW_DEFAULTS,
    "axes": {},
    "grid": [],
    "extra_scenarios": {},
    "workers": 1,
}


def _deep_update(base, override):
    out = copy.deepcopy(base)
    for k, v in (override or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_update(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def resolve_path(p):
    p = Path(p)
    return p if p.is_absolute() else REPO_ROOT / p


def load_pool_config(path=None):
    cfg = _deep_update(POOL_DEFAULTS, load_yaml(path) if path else {})
    cfg["data_root"] = str(resolve_path(cfg["data_root"]))
    return cfg


def load_release_config(path):
    cfg = _deep_update(RELEASE_DEFAULTS, load_yaml(path))
    cfg["data_root"] = str(resolve_path(cfg["data_root"]))
    return cfg
