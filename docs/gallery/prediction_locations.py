import bepad
from bepad.plots import plot_prediction

# an associator that also locates: the map joins true (star) and predicted (circle) epicentres
wid = "CM.test.ev-low__noise-med.00000"
eqt = bepad.load_associator("associators/eqt-utils_simple")
result = eqt.run("test", window_ids=[wid])

test = bepad.load("test", window_ids=[wid])
plot_prediction(test[0], result.predictions, result.locations, save_path="prediction_eqt_CM.png")
