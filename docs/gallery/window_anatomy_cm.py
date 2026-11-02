import bepad
from bepad.plots import plot_window_anatomy

test = bepad.load("test", window_ids=["CM.test.ev-low__noise-med.00000"])   # one window, by its window_id
w = test[0]
plot_window_anatomy(w, model=test.release.label_model, save_path="window_anatomy_CM.png")
