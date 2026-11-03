"""BEPAD: a benchmark dataset for seismic phase association, built from UTDQuake.

    import bepad
    test = bepad.load("test", labels=False)         # download + read the test split
    report = bepad.evaluate(predictions, test)      # score an associator
    class MyMethod(bepad.Associator): ...           # template for reusable associators
"""

__version__ = "0.1.3"

from .data import CORE_NAME, CORE_NETWORKS, LABEL_COLUMNS, Release, Split, download, load, open, predictions_frame  # noqa: E402,A004
from .metrics import evaluate  # noqa: E402
from .associator import Associator, load_associator  # noqa: E402

__all__ = ["CORE_NAME", "CORE_NETWORKS", "load", "download", "open", "evaluate", "Associator", "load_associator", "predictions_frame",
           "Release", "Split",
           "LABEL_COLUMNS", "__version__"]
