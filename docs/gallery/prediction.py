import bepad
from bepad.plots import plot_prediction

# run an associator on one window, then compare it with the truth
wid = "tx.test.ev-low__noise-med.00000"
pyocto = bepad.load_associator("associators/pyocto")
result = pyocto.run("test", window_ids=[wid])

test = bepad.load("test", window_ids=[wid])
plot_prediction(test[0], result.predictions, save_path="prediction_pyocto_tx.png")
