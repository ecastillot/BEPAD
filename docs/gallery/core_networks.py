import bepad
from bepad.plots import plot_core_networks

test = bepad.load("test", networks=["core"])
plot_core_networks(test, save_path="core_networks.png")
