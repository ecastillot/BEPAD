import bepad
from bepad.plots import plot_event_proximity

test = bepad.load("test")                  # all networks
plot_event_proximity(test, save_path="stats_event_proximity.png")
