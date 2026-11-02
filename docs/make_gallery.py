"""Run the docs gallery scripts and collect their figures.

    BEPAD_ROOT=data/releases/dev python docs/make_gallery.py [script ...]

Each docs/gallery/<name>.py is exactly the code shown under its figure in the
documentation. Scripts run from the repository root; every PNG they write is
moved to docs/source/_static/figures/.
"""

import os
import runpy
import shutil
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
REPO = HERE.parent
FIGS = HERE / "source" / "_static" / "figures"

names = sys.argv[1:] or sorted(p.stem for p in (HERE / "gallery").glob("*.py"))
os.chdir(REPO)
FIGS.mkdir(parents=True, exist_ok=True)
for name in names:
    t = time.time()
    before = set(REPO.glob("*.png"))
    runpy.run_path(str(HERE / "gallery" / f"{name}.py"), run_name="__main__")
    for png in set(REPO.glob("*.png")) - before:
        shutil.move(str(png), FIGS / png.name)
    print(f"[gallery] {name}: {time.time() - t:.0f} s")
