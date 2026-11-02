import bepad
from bepad.plots import plot_prediction

# an associator that also locates: the map joins true (star) and predicted (circle) epicentres
eqt = bepad.load_associator("associators/eqt-utils_simple")
result = eqt.run("test", networks=["CM"], scenarios=["ev-low__noise-med"], max_windows=1)

test = bepad.load("test", networks=["CM"])
plot_prediction(test["CM.test.ev-low__noise-med.00000"], result.predictions, result.locations,
                save_path="prediction_eqt_CM.png")
