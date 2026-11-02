import bepad
from bepad.plots import plot_window

test = bepad.load("test", networks=["tx"])
w = test["tx.test.ev-med__noise-med.00000"]
plot_window(w, model=test.release.label_model, save_path="window_tx.png")
