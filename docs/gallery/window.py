import bepad
from bepad.plots import plot_window

test = bepad.load("test", window_ids=["tx.test.ev-med__noise-med.00000"])   # one window, by its window_id
w = test[0]
plot_window(w, model=test.release.label_model, save_path="window_tx.png")
