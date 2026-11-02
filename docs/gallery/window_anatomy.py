import bepad
from bepad.plots import plot_window_anatomy

test = bepad.load("test", networks=["tx"])
w = test["tx.test.ev-low__noise-med.00000"]          # any window_id (or: w = test[0])
plot_window_anatomy(w, model=test.release.label_model, save_path="window_anatomy_tx.png")
