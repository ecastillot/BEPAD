import bepad
from bepad.plots import plot_event_labels

test = bepad.load("test", networks=["tx"])
w = test["tx.test.ev-low__noise-med.00000"]
plot_event_labels(w, test.release.label_model, save_path="event_labels_tx.png")
