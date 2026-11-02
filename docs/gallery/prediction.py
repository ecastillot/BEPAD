import bepad
from bepad.plots import plot_prediction

# run an associator on one window, then compare it with the truth
pyocto = bepad.load_associator("associators/pyocto")
result = pyocto.run("test", networks=["tx"], scenarios=["ev-low__noise-med"], max_windows=1)

test = bepad.load("test", networks=["tx"])
plot_prediction(test["tx.test.ev-low__noise-med.00000"], result.predictions, save_path="prediction_pyocto_tx.png")
