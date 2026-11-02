"""Pool report after the QC array: qc_report.csv, and the networks of the list that are not in the pool.

    python pipeline/01_pool/report.py <networks.txt>

Exits 1 (the label model is then not fitted) if a network of the list failed.
"""
import sys
from pathlib import Path

from bepad.build.config import load_pool_config
from bepad.build.pool import list_networks, write_qc_report

cfg = load_pool_config("configs/pool.yaml")
write_qc_report(cfg["data_root"])
wanted = Path(sys.argv[1]).read_text().split()
missing = sorted(set(wanted) - set(list_networks(cfg["data_root"])))
print(f"pool: {len(wanted) - len(missing)} / {len(wanted)} networks; qc_report.csv written")
if missing:
    print(f"MISSING (see their pool logs): {missing}")
    sys.exit(1)
