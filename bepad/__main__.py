"""Command line interface.

Users
    bepad download --split test [--networks tx CM] [--release v0.1]
    bepad evaluate predictions.parquet --release-dir <dir> [--split test] [--out report/]

Associator authors
    bepad new my-method                                   create associators/my-method/ from the template
    bepad run associators/my-method --split val           run + score (tune on val)
    bepad run associators/my-method --split test --out results/my-method
    bepad submit results/my-method --code associators/my-method   check, then open a Hugging Face pull request

Maintainers (building the dataset)
    python -m bepad pool add tx CM [--force]     QC networks into data/pool
    python -m bepad pool sync [--dry-run]         add every UTDQuake network not in the pool
    python -m bepad pool list
    python -m bepad pool fit-labels [--networks NEW --keep-global]
    python -m bepad build configs/v0.1.yaml [--networks tx] [--workers N] [--no-finalize] [--release NAME]
    python -m bepad finalize configs/v0.1.yaml
    python -m bepad figures configs/v0.1.yaml
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None):
    from .data import RELEASE

    ap = argparse.ArgumentParser(prog="bepad", description="BEPAD phase association benchmark")
    sub = ap.add_subparsers(dest="cmd", required=True)

    dl = sub.add_parser("download", help="download part of a release from Hugging Face")
    dl.add_argument("--split", nargs="*", default=["test"])
    dl.add_argument("--networks", nargs="*")
    dl.add_argument("--release", default=RELEASE)
    dl.add_argument("--local-dir")

    ev = sub.add_parser("evaluate", help="score predictions on a release split")
    ev.add_argument("predictions")
    ev.add_argument("--release-dir", required=True, help="local release folder (see `bepad download`)")
    ev.add_argument("--split", default="test")
    ev.add_argument("--networks", nargs="*")
    ev.add_argument("--min-shared", type=int, default=3)
    ev.add_argument("--out", help="folder for the report (csv + summary.json)")

    nw = sub.add_parser("new", help="create an associator folder from the template")
    nw.add_argument("name")
    nw.add_argument("--root", default="associators")

    rn = sub.add_parser("run", help="run an associator folder on a split and score it")
    rn.add_argument("associator", help="folder with associator.py (e.g. associators/pyocto)")
    rn.add_argument("--split", default="test")
    rn.add_argument("--networks", nargs="*")
    rn.add_argument("--scenarios", nargs="*", help="only these scenarios (partial run)")
    rn.add_argument("--max-windows", type=int, help="at most N windows per network (partial run)")
    rn.add_argument("--workers", type=int, default=1, help="CPU processes (windows run in parallel)")
    rn.add_argument("--release", default=RELEASE)
    rn.add_argument("--release-dir", help="local release folder instead of downloading")
    rn.add_argument("--out", help="save predictions, report and submission.json here")

    sb = sub.add_parser("submit", help="check a result folder and open a leaderboard pull request")
    sb.add_argument("result")
    sb.add_argument("--code", help="the associator folder, published with the results (recommended)")
    sb.add_argument("--release-dir", help="local release folder for the check (otherwise downloaded)")
    sb.add_argument("--dry-run", action="store_true", help="check only; print the manual steps")

    vf = sub.add_parser("verify", help="re-check a result folder (scores recomputed from predictions)")
    vf.add_argument("result")
    vf.add_argument("--code")
    vf.add_argument("--release-dir")

    lb = sub.add_parser("leaderboard", help="[maintainers] build tables / review pull requests")
    lb.add_argument("action", choices=["build", "review"])
    lb.add_argument("--dir", default="leaderboard", help="local leaderboard folder (build)")
    lb.add_argument("--release-dir")

    pool = sub.add_parser("pool", help="[build] QC'd event pool")
    pool.add_argument("action", choices=["add", "sync", "list", "remove", "fit-labels"])
    pool.add_argument("networks", nargs="*")
    pool.add_argument("--config", default="configs/pool.yaml")
    pool.add_argument("--force", action="store_true")
    pool.add_argument("--dry-run", action="store_true")
    pool.add_argument("--keep-global", action="store_true",
                      help="fit-labels: keep q(M,r) and sigma(r), only add curves of the given networks")

    for name, hlp in (("build", "[build] generate release windows"), ("finalize", "[build] manifest + metadata"),
                      ("figures", "[build] release figures")):
        p = sub.add_parser(name, help=hlp)
        p.add_argument("config")
        p.add_argument("--release", help="override the release name of the config")
        if name == "build":
            p.add_argument("--networks", nargs="*")
            p.add_argument("--workers", type=int)
            p.add_argument("--no-finalize", action="store_true")

    a = ap.parse_args(argv)

    if a.cmd == "download":
        from .data import download
        print(download(a.release, splits=a.split, networks=a.networks, local_dir=a.local_dir))
        return

    if a.cmd == "new":
        from .associator import new_associator
        d = new_associator(a.name, a.root)
        print(f"created {d}/ -- fill in associate() in {d}/associator.py, then: bepad run {d} --split val")
        return

    if a.cmd == "run":
        from .associator import load_associator
        assoc = load_associator(a.associator)
        result = assoc.run(a.split, networks=a.networks, scenarios=a.scenarios, max_windows=a.max_windows,
                           workers=a.workers, release=a.release, root=a.release_dir)
        print(result)
        if a.out:
            print(f"[run] saved to {result.save(a.out)}")
        return

    if a.cmd in ("submit", "verify"):
        from . import leaderboard as L
        if a.cmd == "submit":
            L.submit(a.result, code_dir=a.code, root=a.release_dir, dry_run=a.dry_run)
        else:
            probs = L.verify(a.result, root=a.release_dir, code_dir=a.code)
            print("OK" if not probs else "Problems:\n  - " + "\n  - ".join(probs))
        return

    if a.cmd == "leaderboard":
        from . import leaderboard as L
        if a.action == "build":
            from pathlib import Path
            print(L.build(a.dir, out_md=Path(a.dir) / "README.md", out_csv=Path(a.dir) / "leaderboard.csv",
                          out_html=Path(a.dir) / "leaderboard.html"))
        else:
            L.review(root=a.release_dir)
        return

    if a.cmd == "evaluate":
        from .metrics import evaluate
        report = evaluate(a.predictions, a.release_dir, split=a.split, networks=a.networks, min_shared=a.min_shared)
        print(report)
        if a.out:
            print(f"[evaluate] report written to {report.save(a.out)}")
        return

    from .build.config import load_pool_config, load_release_config

    if a.cmd == "pool":
        import json

        from .build import pool as P
        from .build.labels import LabelModel, fit_label_model

        cfg = load_pool_config(a.config)
        if a.action == "add":
            for n in a.networks:
                P.build_network(n, cfg, force=a.force)
        elif a.action == "sync":
            todo = P.missing_networks(cfg)
            print(f"[pool] networks not in pool: {todo}")
            if not a.dry_run:
                failed = []
                for n in todo:
                    try:
                        P.build_network(n, cfg)
                    except Exception as exc:  # keep going; report at the end
                        failed.append(n)
                        print(f"[pool] {n} FAILED: {exc!r}", file=sys.stderr)
                if failed:
                    print(f"[pool] failed networks: {failed}", file=sys.stderr)
        elif a.action == "remove":
            for n in a.networks:
                P.remove_network(n, cfg)
        elif a.action == "fit-labels":
            path = P.pool_dir(cfg["data_root"]) / "label_model.json"
            prev = json.loads(path.read_text()) if path.exists() else None
            nets = a.networks or P.list_networks(cfg["data_root"])
            fit_label_model(cfg["data_root"], nets, cfg["labels"], previous=prev,
                            refit_global=not a.keep_global).save(path)
            print(f"[labels] wrote {path}")
            LabelModel.load(path)
        m = P.read_manifest(cfg["data_root"]) or {"networks": {}}
        for n, e in sorted(m["networks"].items()):
            print(f"  {n:<16} {e['n_events']:>8} events {e['n_picks']:>9} picks  {e['split_counts']}")
        return

    cfg = load_release_config(a.config)
    if a.release:
        cfg["release"] = a.release
    if a.cmd == "build":
        from .build.release import build_release
        build_release(cfg, networks=a.networks, workers=a.workers, finalize=not a.no_finalize)
    elif a.cmd == "finalize":
        from .build.release import finalize_release
        finalize_release(cfg)
    elif a.cmd == "figures":
        from .build.release import release_dir
        from .plots import release_gallery
        print(release_gallery(release_dir(cfg), cfg, networks=cfg.get("gallery_networks")))


if __name__ == "__main__":
    main()
