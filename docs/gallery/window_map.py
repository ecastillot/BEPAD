import bepad
from bepad.plots import plot_window_map

test = bepad.load("test", networks=["tx"])
w = test["tx.test.ev-med__noise-med.00000"]
plot_window_map(w, save_path="window_map_tx.png")
