"""Build a fixed BEPAD release from a benchmark config.

Layout (under <data_root>/releases/<release>/), sharded by split and network
so networks can be built in parallel (Slurm array) and the folders map 1:1 to
Hugging Face dataset configs/splits:

    <split>/windows/network=<name>.parquet          one row per window (metadata)
    <split>/picks/network=<name>.parquet            one row per pick (label: event_idx, -1 noise)
    <split>/events/network=<name>.parquet           one row per event in a window
    <split>/window_stations/network=<name>.parquet  stations available in each window
    (picks, events and window_stations are sorted by window_id and stored in blocks: bepad.blocks)
    _parts/<name>.json                              per-network build record
    --- written by finalize_release ---
    stations.parquet                                station coordinates
    label_model.json                                q(M, r), sigma(r), travel-time curves (bepad.build.labels)
    metadata/windows_<split>.csv                    window metadata as CSV
    metadata/networks.csv                           per network x split summary
    scenarios.json                                  scenario -> window parameters
    manifest.json                                   config, pool, code version, counts

``windows_per_scenario`` is the number of windows per network, split AND
scenario (v1: 1,000 train, 200 val, 100 test). Every window's seed is
sha256(seed_namespace, network, split, scenario, i); ``seed_namespace``
defaults to the release name. A later release that only ADDS networks keeps
the namespace of the first one, so the windows of existing networks stay
identical.
"""

from __future__ import annotations

import datetime as dt
import itertools
import json
import multiprocessing as mp
import shutil
import subprocess
from pathlib import Path

import pandas as pd

from .. import __version__
from ..blocks import BLOCK_ROWS, BLOCKED_TABLES, COMPRESSION, LAYOUT, check_blocked, write_blocked
from .config import REPO_ROOT, WINDOW_DEFAULTS
from .geo import stable_seed
from .labels import LabelModel
from .pool import list_networks, load_network, pool_dir, read_manifest
from .windows import NetworkIndex, generate_window

TABLES = ("windows", "picks", "events", "window_stations")
_INDEX = {}  # network -> NetworkIndex, filled before forking workers


def release_dir(cfg) -> Path:
    return Path(cfg["data_root"]) / "releases" / cfg["release"]


def expand_scenarios(cfg):
    """{scenario_name: full window config}, in a fixed order.

    ``grids``: a list of axis lists, each the full cartesian product of its axes' levels (``grid``:
    one such list). An axis level sets the axis ``param``, plus the axis' ``set`` options (e.g.
    ``sequence: true``). Then ``extra_scenarios``. Each config also gets ``n_events_level`` and
    ``noise_level``: the level of its n_events and noise_ratio (columns of the windows table).
    """
    base = {**WINDOW_DEFAULTS, **cfg.get("window", {})}
    axes = cfg.get("axes", {})
    out = {}
    grids = list(cfg.get("grids") or []) + ([cfg["grid"]] if cfg.get("grid") else [])
    for names in grids:
        level_lists = [list(axes[a]["levels"].items()) for a in names]
        for combo in itertools.product(*level_lists):
            name = "__".join(f"{a}-{lvl}" for a, (lvl, _) in zip(names, combo))
            over = {}
            for a, (_, v) in zip(names, combo):
                over.update(axes[a].get("set") or {})
                over[axes[a]["param"]] = v
            out[name] = {**base, **over}
    for name, over in (cfg.get("extra_scenarios") or {}).items():
        out[name] = {**base, **over}
    if not out:
        out["default"] = base

    def level(param, value):
        for ax in axes.values():
            if ax["param"] == param:
                for lvl, v in ax["levels"].items():
                    if v == value:
                        return lvl
        return None

    for c in out.values():
        c["n_events_level"] = level("n_events", c["n_events"])
        c["noise_level"] = level("noise_ratio", c["noise_ratio"])
    return out


def allocate(total, scenarios):
    """Spread ``total`` windows evenly over scenarios -> {scenario: count}."""
    n = len(scenarios)
    base, extra = divmod(int(total), n)
    return {s: base + (1 if k < extra else 0) for k, s in enumerate(scenarios)}


def resolve_networks(cfg):
    nets = cfg["networks"]
    nets = list_networks(cfg["data_root"]) if nets == "all" else list(nets)
    return [n for n in nets if n not in set(cfg.get("exclude_networks") or [])]


def _git_commit():
    try:
        return subprocess.check_output(["git", "-C", str(REPO_ROOT), "rev-parse", "HEAD"],
                                       stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return None


def _job(args):
    network, split, scenario, wcfg, i, namespace = args
    seed = stable_seed(namespace, network, split, scenario, i)
    wid = f"{network}.{split}.{scenario}.{i:05d}"
    return generate_window(_INDEX[network], split, wcfg, seed, wid, scenario)


def _build_network(network, cfg, scenarios, workers):
    out = release_dir(cfg)
    ev, pk, st = load_network(cfg["data_root"], network)
    model = LabelModel.load(pool_dir(cfg["data_root"]) / "label_model.json")
    _INDEX.clear()
    _INDEX[network] = NetworkIndex(ev, pk, st, network=network, label_model=model)

    min_events = cfg.get("min_events_per_split", 20)
    part = {"network": network, "splits": {}, "skipped_splits": {}}
    for split, per_scenario in cfg["windows_per_scenario"].items():
        n_split_events = int((ev["split"] == split).sum())
        if n_split_events < min_events:
            part["skipped_splits"][split] = f"{n_split_events} events < min_events_per_split={min_events}"
            print(f"[build] {network}/{split}: skipped ({part['skipped_splits'][split]})")
            continue
        counts = {sc: int(per_scenario) for sc in scenarios}
        namespace = cfg.get("seed_namespace") or cfg["release"]
        jobs = [(network, split, s, scenarios[s], i, namespace)
                for s in scenarios for i in range(counts[s])]
        if workers > 1:
            with mp.get_context("fork").Pool(workers) as p:
                results = p.map(_job, jobs, chunksize=16)
        else:
            results = [_job(j) for j in jobs]
        skipped = [f"{j[2]}.{j[4]:05d}" for j, r in zip(jobs, results) if r is None]
        results = [r for r in results if r is not None]
        if not results:
            part["skipped_splits"][split] = "no window could be generated"
            continue

        frames = {
            "windows": pd.DataFrame([r.window for r in results]),
            "picks": pd.concat([r.picks for r in results], ignore_index=True),
            "events": pd.concat([r.events for r in results], ignore_index=True),
            "window_stations": pd.concat([r.stations for r in results], ignore_index=True),
        }
        for t, df in frames.items():
            d = out / split / t
            d.mkdir(parents=True, exist_ok=True)
            if t in BLOCKED_TABLES:                    # one window can be read without the whole file
                write_blocked(df, d / f"network={network}.parquet", BLOCK_ROWS[t])
            else:
                df.to_parquet(d / f"network={network}.parquet", index=False)

        w, e = frames["windows"], frames["events"]
        uses = e["src_event_id"].value_counts()
        part["splits"][split] = {
            "windows": len(w),
            "skipped_windows": skipped,
            "picks": int(w["n_picks"].sum()),
            "real_picks": int(w["n_real_picks"].sum()),
            "generated_picks": int(w["n_generated_picks"].sum()),
            "noise_picks": int(w["n_noise_picks"].sum()),
            "events_in_windows": len(e),
            "scorable_events": int(e["scorable"].sum()),
            "pool_events": n_split_events,
            "unique_events_used": int(len(uses)),
            "event_reuse_median": float(uses.median()),
            "event_reuse_max": int(uses.max()),
        }
        print(f"[build] {network}/{split}: {len(w)} windows, {part['splits'][split]['picks']} picks, "
              f"{len(uses)}/{n_split_events} events used (median reuse {uses.median():.0f})")

    (out / "_parts").mkdir(parents=True, exist_ok=True)
    with open(out / "_parts" / f"{network}.json", "w") as f:
        json.dump(part, f, indent=2)
    return part


def build_release(cfg, networks=None, workers=None, finalize=True):
    """Build shards for ``networks`` (default: all of the config) and optionally finalize."""
    out = release_dir(cfg)
    out.mkdir(parents=True, exist_ok=True)
    networks = networks or resolve_networks(cfg)
    if not networks:
        raise RuntimeError("Pool is empty -- run `python -m bepad pool add <network>` first.")
    scenarios = expand_scenarios(cfg)
    workers = workers or cfg.get("workers", 1)
    print(f"[build] {cfg['release']}: {len(networks)} networks x {len(scenarios)} scenarios, "
          f"per network and scenario {cfg['windows_per_scenario']}")
    for n in networks:
        _build_network(n, cfg, scenarios, workers)
    if finalize:
        finalize_release(cfg)
    return out


def finalize_release(cfg):
    """Assemble stations, metadata CSVs, scenarios and manifest from the built shards."""
    out = release_dir(cfg)
    parts = {}
    for p in sorted((out / "_parts").glob("*.json")):
        with open(p) as f:
            parts[p.stem] = json.load(f)
    networks = sorted(parts)
    if not networks:
        raise RuntimeError(f"nothing to finalize: no built networks in {out / '_parts'}")
    problems = [q for t in BLOCKED_TABLES for f in sorted(out.glob(f"*/{t}/network=*.parquet"))
                for q in check_blocked(f)]
    if problems:
        raise RuntimeError("files not in blocks (rebuild them, or bepad.blocks.reblock):\n  " + "\n  ".join(problems))

    pd.concat([load_network(cfg["data_root"], n)[2] for n in networks], ignore_index=True) \
        .to_parquet(out / "stations.parquet", index=False)

    (out / "metadata").mkdir(exist_ok=True)
    counts = {}
    for split in cfg["windows_per_scenario"]:
        files = sorted((out / split / "windows").glob("network=*.parquet"))
        if not files:
            continue
        w = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
        w.to_csv(out / "metadata" / f"windows_{split}.csv", index=False)
        counts[split] = {"windows": len(w), "picks": int(w["n_picks"].sum()),
                         "networks": int(w["network"].nunique())}

    rows = [{"network": n, "split": s, **{k: v for k, v in d.items() if k != "skipped_windows"},
             "skipped_windows": len(d["skipped_windows"])}
            for n, p in parts.items() for s, d in p["splits"].items()]
    pd.DataFrame(rows).to_csv(out / "metadata" / "networks.csv", index=False)

    with open(out / "scenarios.json", "w") as f:
        json.dump(expand_scenarios(cfg), f, indent=2)
    shutil.copy(pool_dir(cfg["data_root"]) / "label_model.json", out / "label_model.json")
    pool_manifest = read_manifest(cfg["data_root"])
    manifest = {
        "release": cfg["release"],
        "finalized": dt.datetime.now().isoformat(timespec="seconds"),
        "bepad_version": __version__,
        "git_commit": _git_commit(),
        "config": cfg,
        "pool_config": pool_manifest["pool_config"],
        "pool_networks": {n: {k: pool_manifest["networks"][n].get(k)
                              for k in ("utdquake_version", "utdquake_revision", "utdquake_network",
                                        "source_sha256", "n_events", "built")}
                          for n in networks},
        "counts": counts,
        "layout": {"name": LAYOUT, "block_rows": BLOCK_ROWS, "compression": COMPRESSION},
        "skipped_splits": {n: p["skipped_splits"] for n, p in parts.items() if p["skipped_splits"]},
    }
    with open(out / "manifest.json", "w") as f:
        json.dump(manifest, f, indent=2, default=str)
    print(f"[finalize] {out}: {counts}")
    return manifest


def load_release(path, splits=None, networks=None, tables=TABLES):
    """Load (a subset of) a release into DataFrames, concatenated over shards."""
    path = Path(path)
    splits = splits or [d.name for d in sorted(path.iterdir()) if (d / "windows").is_dir()]
    out = {}
    for t in tables:
        files = []
        for s in splits:
            files += sorted((path / s / t).glob("network=*.parquet"))
        if networks is not None:
            keep = {f"network={n}.parquet" for n in networks}
            files = [f for f in files if f.name in keep]
        out[t] = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True) if files else pd.DataFrame()
    if (path / "stations.parquet").exists():
        out["stations"] = pd.read_parquet(path / "stations.parquet")
    return out

