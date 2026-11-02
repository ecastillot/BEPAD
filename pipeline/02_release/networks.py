"""The networks of a release config, one per line (the release build array runs one job per line).

    python pipeline/02_release/networks.py configs/<version>.yaml [<pool networks.txt>]

``networks: all`` is every network of the pool, or of the list the pool step wrote (when the pool
is not built yet, as in a chain), minus ``exclude_networks``.
"""
import sys
from pathlib import Path

from bepad.build.config import load_release_config
from bepad.build.release import resolve_networks

cfg = load_release_config(sys.argv[1])
if cfg["networks"] == "all" and len(sys.argv) > 2:
    nets = [n for n in Path(sys.argv[2]).read_text().split() if n not in set(cfg.get("exclude_networks") or [])]
else:
    nets = resolve_networks(cfg)
print("\n".join(nets))
