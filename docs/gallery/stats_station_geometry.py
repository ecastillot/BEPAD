import bepad
from bepad.plots import plot_station_geometry

test = bepad.load("test")                  # all networks
plot_station_geometry(test, save_path="stats_station_geometry.png")
