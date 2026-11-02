"""Leaderboard: submit results, verify them, build the tables.

Everything lives in the BEPAD Hugging Face dataset repo::

    associators/<name>/                         contributed code (associator.py, config.yaml, README.md, ...)
    leaderboard/<release>/<name>/submission.json    scores + metadata (written by Result.save)
    leaderboard/<release>/<name>/predictions/       the predictions, so scores can be re-checked
    leaderboard/README.md                            the tables (built by ``bepad leaderboard build``)

Authors run ``bepad submit results/<name> --code associators/<name>``: the
files are checked locally, then a pull request is opened on Hugging Face. It
only ever adds the author's own two folders, never touches anything else.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

REPO_ID = "ecastillot/BEPAD"
SCORE_TOL = 1e-6
TABLE_COLS = ["event_f1", "pick_f1", "noise_rejection", "event_precision", "event_recall", "merge_rate",
              "split_rate", "epi_median_km", "depth_median_km", "t0_median_s"]


# ----------------------------------------------------------------------
# Checking
# ----------------------------------------------------------------------
def verify(result_dir, root=None, code_dir=None):
    """Check a result folder: files, metadata, and scores recomputed from the predictions.

    Returns a list of problems (empty = OK). ``root``: local release folder
    (otherwise the needed labels are downloaded).
    """
    from .metrics import evaluate
    from .associator import METHOD_TYPES, TRAINING

    d = Path(result_dir)
    problems = []
    sub_file = d / "submission.json"
    if not sub_file.exists():
        return [f"{sub_file} not found -- create it with result.save('{d}')"]
    sub = json.loads(sub_file.read_text())
    a, run = sub.get("associator", {}), sub.get("run", {})
    for key in ("name", "version", "authors", "method_type", "training"):
        if not a.get(key):
            problems.append(f"associator.{key} is empty (set it in the class)")
    if a.get("authors") == "Your Name":
        problems.append("associator.authors is still 'Your Name'")
    if a.get("method_type") not in METHOD_TYPES:
        problems.append(f"method_type must be one of {METHOD_TYPES}")
    if a.get("training") not in TRAINING:
        problems.append(f"training must be one of {TRAINING}")
    if run.get("split") != "test":
        problems.append(f"leaderboard results must be on the test split (got {run.get('split')!r})")
    from .data import CORE_NAME, CORE_NETWORKS

    missing = sorted(set(CORE_NETWORKS) - set(run.get("networks") or []))
    if run.get("release") != "dev" and missing:
        problems.append(f"the {CORE_NAME} networks are required, missing: {', '.join(missing)} "
                        "(run with --networks core, plus any other networks)")
    files = sorted((d / "predictions").glob("network=*.parquet"))
    if not files:
        problems.append("no predictions/network=*.parquet files")
        return problems
    if code_dir is not None:
        c = Path(code_dir)
        for f in ("associator.py", "config.yaml", "README.md"):
            if not (c / f).exists():
                problems.append(f"{c / f} missing (bepad new creates it)")
        if c.name != a.get("name"):
            problems.append(f"code folder is named {c.name!r} but the associator is {a.get('name')!r}")

    pred = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    lfiles = sorted((d / "locations").glob("network=*.parquet"))
    locs = pd.concat([pd.read_parquet(f) for f in lfiles], ignore_index=True) if lfiles else None
    try:
        from .data import Release, download

        rel = Release(root) if root else Release(download(run["release"], splits=("test",),
                                                          networks=run["networks"]))
        report = evaluate(pred, rel, split="test", networks=run["networks"],
                          window_ids=set(pred.window_id), locations=locs)
    except Exception as exc:  # noqa: BLE001 -- report instead of crashing
        return problems + [f"could not re-score the predictions: {exc!r}"]
    got = report.overall.iloc[0]
    for k, v in sub["scores"]["overall"].items():
        if k in got and v is not None and abs(float(got[k]) - v) > SCORE_TOL:
            problems.append(f"score {k}: submission says {v}, predictions give {float(got[k]):.6f}")
    if report.meta["n_windows"] != run.get("n_windows"):
        problems.append(f"n_windows: submission says {run.get('n_windows')}, predictions cover "
                        f"{report.meta['n_windows']}")
    return problems


# ----------------------------------------------------------------------
# Submitting
# ----------------------------------------------------------------------
def _operations(result_dir, code_dir, release, name):
    from huggingface_hub import CommitOperationAdd

    ops = []
    base = f"leaderboard/{release}/{name}"
    for f in sorted(Path(result_dir).rglob("*")):
        if f.is_file():
            ops.append(CommitOperationAdd(f"{base}/{f.relative_to(result_dir).as_posix()}", str(f)))
    if code_dir is not None:
        for f in sorted(Path(code_dir).rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                ops.append(CommitOperationAdd(f"associators/{name}/{f.relative_to(code_dir).as_posix()}", str(f)))
    return ops


def _pr_text(sub):
    a, run, s = sub["associator"], sub["run"], sub["scores"]["overall"]
    return (f"**{a['name']} {a['version']}** by {a['authors']} ({a['method_type']}, training: {a['training']})\n\n"
            f"{a.get('description', '')}\n\n"
            f"- release `{run['release']}`, split `{run['split']}`, networks: {', '.join(run['networks'])}\n"
            f"- windows: {run['n_windows']} ({'complete' if run['complete'] else 'partial'})\n"
            f"- event F1 {s['event_f1']}, pick F1 {s['pick_f1']}, noise rejection {s['noise_rejection']}\n"
            f"- paper: {a.get('paper') or '-'} · code: {a.get('code') or '-'}\n\n"
            "Opened with `bepad submit`.")


def preview(result_dir, repo_id=REPO_ID):
    """The leaderboard tables of this submission's networks, with it inserted among the current entries."""
    import shutil
    import tempfile

    sub = json.loads((Path(result_dir) / "submission.json").read_text())
    name, release = sub["associator"]["name"], sub["run"]["release"]
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        try:
            from huggingface_hub import snapshot_download

            cur = Path(snapshot_download(repo_id, repo_type="dataset",
                                         allow_patterns=[f"leaderboard/{release}/*/submission.json"]))
            for f in (cur / "leaderboard").glob("*/*/submission.json"):
                dst = tmp / f.parent.relative_to(cur / "leaderboard")
                dst.mkdir(parents=True, exist_ok=True)
                shutil.copy(f, dst / "submission.json")
            note = "current leaderboard + your submission"
        except Exception:  # noqa: BLE001 -- offline / repo not published yet
            note = "the published leaderboard could not be read, so only your submission is shown"
        (tmp / release / name).mkdir(parents=True, exist_ok=True)
        shutil.copy(Path(result_dir) / "submission.json", tmp / release / name / "submission.json")
        text = build(tmp)
    from .data import CORE_NAME

    keep = [f"## {release} · {n}" for n in [CORE_NAME, "All networks", *sub["run"]["networks"]]]
    blocks = [b for b in text.split("\n## ") if any(("## " + b).startswith(k) for k in keep)]
    return f"Preview ({note}):\n\n" + "\n".join("## " + b for b in blocks)


def submit(result_dir, code_dir=None, repo_id=REPO_ID, root=None, dry_run=False, token=None):
    """Check a result folder, then open a pull request on the BEPAD Hugging Face repo.

    Needs a Hugging Face account and ``hf auth login`` once. With ``dry_run`` (or
    without a login) nothing is sent and the manual steps are printed instead.
    """
    sub = json.loads((Path(result_dir) / "submission.json").read_text())
    name, release = sub["associator"]["name"], sub["run"]["release"]
    problems = verify(result_dir, root=root, code_dir=code_dir)
    if problems:
        print("Please fix these first:\n  - " + "\n  - ".join(problems))
        return None
    ops = _operations(result_dir, code_dir, release, name)
    print(preview(result_dir, repo_id))
    print(f"[submit] checks passed. The pull request adds {len(ops)} files:")
    print(f"           leaderboard/{release}/{name}/...")
    if code_dir is not None:
        print(f"           associators/{name}/...")
    manual = (f"\nTo submit by hand instead: open https://huggingface.co/datasets/{repo_id}/tree/main "
              f"('Files and versions'), choose 'Contribute' -> 'Upload files', and upload the folder "
              f"{result_dir} into leaderboard/{release}/{name}/"
              + (f" and {code_dir} into associators/{name}/" if code_dir else "")
              + ". For people who do not own the repository, the upload is opened as a pull request.")
    if dry_run:
        print("[submit] dry run: nothing sent." + manual)
        return None
    try:
        from huggingface_hub import HfApi

        api = HfApi(token=token)
        user = api.whoami()["name"]
    except Exception:  # noqa: BLE001
        print("[submit] you are not logged in to Hugging Face. Run `hf auth login` (once) and try again."
              + manual)
        return None
    info = api.create_commit(repo_id, repo_type="dataset", operations=ops, create_pr=True,
                             commit_message=f"Leaderboard: {name} {sub['associator']['version']} on {release}",
                             commit_description=_pr_text(sub))
    print(f"[submit] pull request opened by {user}: {info.pr_url}")
    return info.pr_url


# ----------------------------------------------------------------------
# Tables
# ----------------------------------------------------------------------
def collect(leaderboard_dir):
    """All submission.json files of a local leaderboard folder -> one row per (method, network)."""
    rows = []
    for f in sorted(Path(leaderboard_dir).glob("*/*/submission.json")):
        sub = json.loads(f.read_text())
        a, run = sub["associator"], sub["run"]
        common = {"release": run["release"], "method": a["name"], "version": a["version"], "type": a["method_type"],
                  "training": a["training"], "complete": run["complete"], "sec_per_window": run["seconds_per_window"],
                  "paper": a.get("paper", ""), "code": a.get("code", ""), "date": sub["created"][:10]}
        for net, s in sub["scores"]["by_network"].items():
            rows.append({**common, "network": net, "n_windows": s.get("n_windows"),
                         **{k: s.get(k) for k in TABLE_COLS}})
    return pd.DataFrame(rows)


def _mean_over(g, networks):
    """One method's scores averaged over ``networks`` (every network weighs the same)."""
    g = g[g.network.isin(networks)]
    w = g.n_windows.fillna(0).to_numpy(float)
    return {**g.iloc[0][["release", "method", "version", "type", "training", "paper", "code"]].to_dict(),
            "complete": bool(g.complete.all()) and g.network.nunique() == len(networks),
            "n_networks": int(g.network.nunique()), "n_windows": int(w.sum()),
            "sec_per_window": float((g.sec_per_window * w).sum() / w.sum()) if w.sum() else float("nan"),
            **{k: float(pd.to_numeric(g[k], errors="coerce").mean()) for k in TABLE_COLS}}


def views(df, core=None):
    """{release: {view: rows}}, ranked by event F1. Views: ``core`` (mean over the core networks),
    ``all`` (mean over every network of the release), then one per network. A method that did not
    run every window of the view's networks is *partial*: listed, not ranked."""
    from .data import CORE_NETWORKS

    core = list(core or CORE_NETWORKS)
    out = {}
    for release, d in df.groupby("release"):
        nets = sorted(d.network.unique())
        rel = {}
        for view, members in [("core", core), ("all", nets)] + [(n, [n]) for n in nets]:
            rows = [_mean_over(g, members) for _, g in d.groupby(["method", "version"]) if g.network.isin(members).any()]
            rows = sorted(rows, key=lambda r: (not r["complete"], -(r["event_f1"] if r["event_f1"] == r["event_f1"] else -1)))
            rank = 0
            for r in rows:
                rank += r["complete"]
                r["rank"] = rank if r["complete"] else "partial"
                r["n_networks_view"] = len(members)
            rel[view] = rows
        out[release] = rel
    return out


HEADER = ["#", "Method", "Type", "Training", "Event F1", "Pick F1", "Noise rej.", "Merge", "Split",
          "Epicentre err. (km)", "Depth err. (km)", "s/window", "Windows", "Networks"]


def _cells(r):
    fmt = lambda v: "–" if v is None or v != v else f"{v:.3f}"  # noqa: E731
    fmt1 = lambda v: "–" if v is None or v != v else f"{v:.1f}"  # noqa: E731
    return [str(r["rank"]), f"{r['method']} {r['version']}", r["type"], r["training"], fmt(r["event_f1"]),
            fmt(r["pick_f1"]), fmt(r["noise_rejection"]), fmt(r["merge_rate"]), fmt(r["split_rate"]),
            fmt1(r["epi_median_km"]), fmt1(r["depth_median_km"]), f"{r['sec_per_window']:.2f}",
            str(r["n_windows"]), f"{r['n_networks']}/{r['n_networks_view']}"]


def _title(view, core):
    from .data import CORE_NAME, CORE_NETWORKS

    return {"core": f"{CORE_NAME} test ({', '.join(core or CORE_NETWORKS)})", "all": "All networks"}.get(view, view)


def _html(tables, core):
    """A self-contained table with a network filter (default: the core networks), for the docs."""
    data = {rel: {v: {"title": _title(v, core), "rows": [
        {"cells": _cells(r), "link": r["paper"] or r["code"]} for r in rows]} for v, rows in vs.items()}
        for rel, vs in tables.items()}
    return f"""<div class="bepad-lb">
<label>Release <select class="bepad-lb-release"></select></label>
<label>Networks <select class="bepad-lb-view"></select></label>
<table class="docutils"><thead><tr>{"".join(f"<th>{h}</th>" for h in HEADER)}</tr></thead><tbody></tbody></table>
</div>
<script>
(function () {{
  const DATA = {json.dumps(data)};
  const box = document.currentScript.previousElementSibling;
  const rel = box.querySelector(".bepad-lb-release"), view = box.querySelector(".bepad-lb-view");
  const body = box.querySelector("tbody");
  const opt = (v, t) => {{ const o = document.createElement("option"); o.value = v; o.textContent = t; return o; }};
  function fillViews() {{
    view.innerHTML = "";
    for (const [v, d] of Object.entries(DATA[rel.value])) view.appendChild(opt(v, d.title));
  }}
  function draw() {{
    body.innerHTML = "";
    for (const r of DATA[rel.value][view.value].rows) {{
      const tr = document.createElement("tr");
      r.cells.forEach((c, i) => {{
        const td = document.createElement("td");
        if (i === 1 && r.link) {{ const a = document.createElement("a"); a.href = r.link; a.textContent = c; td.appendChild(a); }}
        else td.textContent = c;
        tr.appendChild(td);
      }});
      body.appendChild(tr);
    }}
  }}
  Object.keys(DATA).sort().reverse().forEach(k => rel.appendChild(opt(k, k)));
  rel.onchange = () => {{ fillViews(); draw(); }};
  view.onchange = draw;
  fillViews(); draw();
}})();
</script>
"""


def build(leaderboard_dir, out_md=None, out_csv=None, out_html=None, core=None):
    """The tables: the core networks first, then all networks, then one per network (Markdown, for the
    Hugging Face card), a flat CSV, and a filterable HTML table for the docs."""
    df = collect(leaderboard_dir)
    if df.empty:
        text = "# BEPAD leaderboard\n\nNo submissions yet.\n"
        html = "<p><em>No submissions yet.</em></p>"
    else:
        tables = views(df, core)
        lines = ["# BEPAD leaderboard", "",
                 "Ranked by event F1 on the test split; the core and all-networks tables average the networks "
                 "(each network weighs the same). *Partial* runs (not every window of the networks) are "
                 "listed but not ranked. Location errors are medians over the matched earthquakes, against the "
                 "catalog; – = the method does not locate. Submit with `bepad submit` (see the documentation).",
                 ""]
        for release in sorted(tables, reverse=True):
            for view, rows in tables[release].items():
                lines += [f"## {release} · {_title(view, core)}", "", "| " + " | ".join(HEADER) + " |",
                          "|" + "---|" * len(HEADER)]
                for r in rows:
                    c = _cells(r)
                    link = r["paper"] or r["code"]
                    c[1] = f"[{c[1]}]({link})" if link else c[1]
                    lines.append("| " + " | ".join(c) + " |")
                lines.append("")
        text = "\n".join(lines)
        html = _html(tables, core)
    if out_md:
        Path(out_md).write_text(text)
    if out_csv and not df.empty:
        df.to_csv(out_csv, index=False)
    if out_html:
        Path(out_html).write_text(html)
    return text


# ----------------------------------------------------------------------
# Maintainer
# ----------------------------------------------------------------------
def review(repo_id=REPO_ID, root=None, token=None):
    """List open leaderboard pull requests and re-check each one (maintainer)."""
    from huggingface_hub import HfApi, snapshot_download

    api = HfApi(token=token)
    for d in api.get_repo_discussions(repo_id, repo_type="dataset", discussion_type="pull_request",
                                      discussion_status="open"):
        path = Path(snapshot_download(repo_id, repo_type="dataset", revision=d.git_reference,
                                      allow_patterns=["leaderboard/*", "associators/*"], token=token))
        new = [p for p in (path / "leaderboard").glob("*/*/submission.json")]
        print(f"PR #{d.num} by {d.author}: {d.title}")
        for sub in new:
            probs = verify(sub.parent, root=root)
            print(f"   {sub.parent.relative_to(path)}: " + ("OK" if not probs else "; ".join(probs)))
        print(f"   merge: HfApi().merge_pull_request('{repo_id}', {d.num}, repo_type='dataset')")
