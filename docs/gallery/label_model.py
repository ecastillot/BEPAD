import bepad
from bepad.plots import plot_label_model

test = bepad.load("test", networks=["tx"])
plot_label_model(test.release.label_model, save_path="label_model.png")
