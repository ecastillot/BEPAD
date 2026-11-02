import bepad
from bepad.plots import plot_window_anatomy

test = bepad.load("test", networks=["CM"])
w = test["CM.test.ev-low__noise-med.00000"]
plot_window_anatomy(w, model=test.release.label_model, save_path="window_anatomy_CM.png")
