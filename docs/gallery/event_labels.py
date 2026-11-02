import bepad
from bepad.plots import plot_event_labels

test = bepad.load("test", window_ids=["tx.test.ev-low__noise-med.00000"])   # one window, by its window_id
w = test[0]
plot_event_labels(w, test.release.label_model, save_path="event_labels_tx.png")
