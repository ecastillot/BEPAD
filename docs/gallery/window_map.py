import bepad
from bepad.plots import plot_window_map

test = bepad.load("test", window_ids=["tx.test.ev-med__noise-med.00000"])   # one window, by its window_id
w = test[0]
plot_window_map(w, save_path="window_map_tx.png")
